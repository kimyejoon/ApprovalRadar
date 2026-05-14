import time
import math
import concurrent.futures
from app.core.config import settings
from app.clients.foodsafety_api import ApiClient
from app.repositories.state_repository import StateRepository
from app.core.logger import logger
from app.core.events import shutdown_event

class DiffCrawlerEngine:
    def __init__(self, api_client: ApiClient, service_id: str):
        self.api_client = api_client
        self.service_id = service_id
        self.state_repo = StateRepository()

    def _fetch_single(self, idx: int):
        """특정 인덱스 1건 조회. INFO-200(데이터 없음)이면 None 반환"""
        res = self.api_client.fetch_data(self.service_id, idx, idx)
        if not res or self.service_id not in res:
            return None
            
        code = res[self.service_id]['RESULT']['CODE']
        if code == "INFO-000":
            return res[self.service_id]['row'][0]
        elif code == "INFO-200":
            return None
        return None

    def _get_total_count(self) -> int:
        """
        API의 TOTAL_COUNT 필드를 직접 읽어 전체 데이터 건수를 1회 호출로 파악합니다.
        이진탐색 방식은 WAF 차단 시 항상 최댓값을 반환하는 결함이 있었습니다.
        """
        res = self.api_client.fetch_data(self.service_id, 1, 1)
        if not res or self.service_id not in res:
            raise RuntimeError("전체 건수 확인 실패: API 응답 없음")
        
        result_block = res[self.service_id]
        # API가 반환하는 공식 전체 레코드 수 (TOTAL_COUNT 필드)
        total_count = int(result_block.get("TOTAL_COUNT", 0))
        
        if total_count == 0:
            code = result_block['RESULT']['CODE']
            raise RuntimeError(f"전체 건수 확인 실패: 코드={code}, TOTAL_COUNT=0")
        
        return total_count

    def find_true_tail(self) -> int:
        """
        API TOTAL_COUNT를 기반으로 전체 데이터 건수를 반환합니다.
        (구: 이진탐색 방식 → API 공식 필드 직접 읽기로 교체)
        """
        logger.info("[Bootstrapper] 전체 데이터 건수 확인 중... (API TOTAL_COUNT 직접 조회)")
        total_count = self._get_total_count()
        logger.info(f"[Bootstrapper] 전체 데이터 건수 확인 완료: {total_count:,}건")
        return total_count

    def bootstrap(self):
        """처음부터 피벗을 생성합니다."""
        total_count = self.find_true_tail()
        pivots = {}
        
        logger.info(f"[Bootstrapper] 피벗 캐싱 시작 (간격: {settings.PIVOT_INTERVAL})...")
        pivot_indices = list(range(settings.PIVOT_INTERVAL, total_count, settings.PIVOT_INTERVAL))
        
        # 피벗 병렬 조회
        with concurrent.futures.ThreadPoolExecutor(max_workers=settings.MAX_WORKERS) as executor:
            future_to_idx = {executor.submit(self._fetch_single, idx): idx for idx in pivot_indices}
            for future in concurrent.futures.as_completed(future_to_idx):
                idx = future_to_idx[future]
                row = future.result()
                if row:
                    pivots[str(idx)] = {
                        "LCNS_NO": row.get("LCNS_NO", ""),
                        "CHNG_DT": row.get("CHNG_DT", ""),
                        "BSSH_NM": row.get("BSSH_NM", "")
                    }
                    
        state = {
            "last_total_count": total_count,
            "pivots": pivots
        }
        self.state_repo.save_state(self.service_id, state)
        logger.info(f"[Bootstrapper] 부트스트랩 완료! 총 {len(pivots)}개의 피벗 색인 생성됨.")
        return state

    def scan_for_updates(self):
        """주기적으로 실행되어 차분(Delta)을 감지합니다."""
        start_time = time.time()
        state = self.state_repo.load_state(self.service_id)
        if state["last_total_count"] == 0:
            logger.info("최초 실행: 베이스라인 부트스트랩을 시작합니다...")
            state = self.bootstrap()
            return []  # 부트스트랩 시에는 데이터를 가져오지 않고 베이스라인만 구축
            
        old_tail = state["last_total_count"]
        
        # 1. TOTAL_COUNT 비교로 신규 삽입 감지 (단 1회 API 호출)
        try:
            new_tail = self._get_total_count()
        except RuntimeError as e:
            logger.warning(f"[Delta Sync] 전체 건수 조회 실패: {e}. 이번 주기 스킵.")
            return []
        
        if new_tail <= old_tail:
            elapsed = time.time() - start_time
            logger.info(f"✨ [소요시간: {elapsed:.2f}초] 새로운 데이터가 감지되지 않았습니다. (현재 전체 데이터: {old_tail:,}건)")
            return []

            
        diff_count = new_tail - old_tail
        logger.info(f"🔍 [Tail 탐색] 인덱스가 {old_tail}에서 {new_tail}로 증가했습니다. (총 {diff_count}건의 신규 삽입 감지)")
        
        # 2. Pivot 검사
        pivots = state["pivots"]
        pivot_indices = sorted([int(k) for k in pivots.keys()])
        
        # 각 피벗 지점에서 Shift 확인
        shift_amounts = {} # pivot_idx -> shift_amount
        current_shift = 0
        
        logger.info(f"⚙️ 총 {len(pivot_indices)}개의 피벗 지점에서 Shift 오프셋 보정을 시작합니다...")
        for p_idx in pivot_indices:
            # 피벗이 가리키던 예전 데이터
            old_data = pivots[str(p_idx)]
            
            # 여기서부터 current_shift ~ diff_count 사이를 이진 탐색하여 실제 오프셋을 찾음
            found_offset = current_shift
            for offset in range(current_shift, diff_count + 1):
                row = self._fetch_single(p_idx + offset)
                if row and row.get("LCNS_NO") == old_data["LCNS_NO"] and row.get("CHNG_DT") == old_data["CHNG_DT"]:
                    found_offset = offset
                    break
            
            shift_amounts[p_idx] = found_offset
            current_shift = found_offset
            
        # 3. 새로운 데이터 다운로드
        new_data_rows = []
        prev_idx = 0
        prev_shift = 0
        
        segments = []
        for p_idx in pivot_indices:
            shift = shift_amounts[p_idx]
            if shift > prev_shift:
                # 구간 [prev_idx+1, p_idx] 사이에 (shift - prev_shift) 개의 데이터가 삽입됨
                segments.append((prev_idx + 1, p_idx, shift - prev_shift, prev_shift))
            prev_idx = p_idx
            prev_shift = shift
            
        if prev_shift < diff_count:
            # 마지막 피벗 이후 구간
            segments.append((prev_idx + 1, new_tail, diff_count - prev_shift, prev_shift))
            
        for seg_start, seg_end, count, base_shift in segments:
            # seg_start ~ seg_end 사이에서 count 개의 신규 데이터를 찾아야 함.
            new_start = seg_start + base_shift
            new_end = seg_end + base_shift + count
            logger.info(f"📥 [구간 {seg_start}~{seg_end}] 내에 {count}건의 중간 삽입 감지. (실제 요청: {new_start}~{new_end}) 다운로드 진행...")
            
            # API는 한 번에 최대 1000건 조회 가능하므로 청크 분할
            fetched_rows = []
            current_start = new_start
            while current_start <= new_end:
                current_end = min(current_start + 999, new_end)
                res = self.api_client.fetch_data(self.service_id, current_start, current_end)
                
                if res and self.service_id in res:
                    code = res[self.service_id]['RESULT']['CODE']
                    if code == "INFO-000":
                        rows = res[self.service_id]['row']
                        fetched_rows.extend(rows)
                
                current_start += 1000
                
            if fetched_rows:
                # CHNG_DT 기준 내림차순 정렬하여 가장 최근 변경된 count 개 추출 (가장 확실한 신규/변경 항목)
                fetched_rows.sort(key=lambda x: x.get("CHNG_DT", ""), reverse=True)
                top_new = fetched_rows[:count]
                for r in top_new:
                    r["DB_INDEX_RANGE"] = f"{new_start}~{new_end}"
                new_data_rows.extend(top_new)
            
        # 4. 피벗 및 Tail 갱신
        new_pivots = {}
        for p_idx in pivot_indices:
            shift = shift_amounts[p_idx]
            new_p_idx = p_idx + shift
            new_pivots[str(new_p_idx)] = pivots[str(p_idx)]
            
        # 새 꼬리까지의 새 피벗들 추가 필요
        max_pivot = max(pivot_indices) if pivot_indices else 0
        next_pivot = ((max_pivot + shift_amounts.get(max_pivot, diff_count)) // settings.PIVOT_INTERVAL + 1) * settings.PIVOT_INTERVAL
        while next_pivot < new_tail:
            row = self._fetch_single(next_pivot)
            if row:
                new_pivots[str(next_pivot)] = {
                    "LCNS_NO": row.get("LCNS_NO", ""),
                    "CHNG_DT": row.get("CHNG_DT", ""),
                    "BSSH_NM": row.get("BSSH_NM", "")
                }
            next_pivot += settings.PIVOT_INTERVAL
            
        state["last_total_count"] = new_tail
        state["pivots"] = new_pivots
        self.state_repo.save_state(self.service_id, state)
        
        return new_data_rows
