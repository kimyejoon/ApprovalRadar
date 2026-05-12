import time
import math
import concurrent.futures
from app.core.config import settings
from app.clients.foodsafety_api import ApiClient
from app.utils.state_manager import StateManager

class DiffCrawlerEngine:
    def __init__(self, api_client: ApiClient, log_callback=None):
        self.api_client = api_client
        self.log_callback = log_callback or print

    def _fetch_single(self, idx: int):
        """특정 인덱스 1건 조회. INFO-200(데이터 없음)이면 None 반환"""
        max_retries = len(settings.API_KEYS)
        retries = 0
        
        while retries <= max_retries:
            res, used_key = self.api_client.fetch_data(idx, idx)
            if settings.SERVICE_ID in res:
                code = res[settings.SERVICE_ID]['RESULT']['CODE']
                if code == "INFO-000":
                    return res[settings.SERVICE_ID]['row'][0]
                elif code == "INFO-200":
                    return None
                else:
                    # 에러(한도 초과 등) 시 재시도
                    msg = res[settings.SERVICE_ID]['RESULT']['MSG']
                    if "유효 호출건수" in msg or code in ["INFO-300", "INFO-333"]:
                        self.api_client.rotate_key(used_key)
                        time.sleep(1)
                        retries += 1
                        continue
            break # 정상적인 포맷이 아니거나 다른 알 수 없는 에러면 탈출
            
        return None

    def find_true_tail(self) -> int:
        self.log_callback("[Bootstrapper] True Tail(실제 마지막 데이터) 찾는 중...")
        low, high = 1, 1000000
        best_valid = 1
        
        while low <= high:
            mid = (low + high) // 2
            row = self._fetch_single(mid)
            if row:
                best_valid = mid
                low = mid + 1
            else:
                high = mid - 1
                
        self.log_callback(f"[Bootstrapper] 전체 데이터 건수 확인 완료: {best_valid}건")
        return best_valid

    def bootstrap(self):
        """처음부터 피벗을 생성합니다."""
        total_count = self.find_true_tail()
        pivots = {}
        
        self.log_callback(f"[Bootstrapper] 피벗 캐싱 시작 (간격: {settings.PIVOT_INTERVAL})...")
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
        StateManager.save_state(state)
        self.log_callback(f"[Bootstrapper] 부트스트랩 완료! 총 {len(pivots)}개의 피벗 색인 생성됨.")
        return state

    def scan_for_updates(self):
        """주기적으로 실행되어 차분(Delta)을 감지합니다."""
        state = StateManager.load_state()
        if state["last_total_count"] == 0:
            state = self.bootstrap()
            return [] # 부트스트랩 시에는 데이터를 가져오지 않고 베이스라인만 구축
            
        old_tail = state["last_total_count"]
        
        # 1. Tail Ping (꼬리 검사)
        # 만약 old_tail + 1 이 존재한다면 늘어난 것임.
        row_next = self._fetch_single(old_tail + 1)
        if not row_next:
            self.log_callback(f"새로운 데이터가 감지되지 않았습니다. (전체 데이터: {old_tail}건)")
            return []
            
        # 늘어났다면 새로운 Tail을 찾는다 (장기간 꺼져 있었을 수 있으므로 Exponential Jump 활용)
        new_tail = old_tail + 1
        step = 1
        # 1. 꼬리가 어디까지 늘어났는지 기하급수적으로 점프
        while self._fetch_single(new_tail + step):
            step *= 2
            
        # 2. 범위를 찾았으면 이진 탐색으로 정확한 꼬리 확정
        low = new_tail + (step // 2)
        high = new_tail + step
        best_valid = low
        
        while low <= high:
            mid = (low + high) // 2
            if self._fetch_single(mid):
                best_valid = mid
                low = mid + 1
            else:
                high = mid - 1
                
        new_tail = best_valid
            
        diff_count = new_tail - old_tail
        self.log_callback(f"꼬리 검사: 총 {diff_count}건의 신규 삽입(밀림) 감지!")
        
        # 2. Pivot 검사
        pivots = state["pivots"]
        pivot_indices = sorted([int(k) for k in pivots.keys()])
        
        # 각 피벗 지점에서 Shift 확인
        shift_amounts = {} # pivot_idx -> shift_amount
        current_shift = 0
        
        self.log_callback("피벗 점검 및 Shift 보정 중...")
        for p_idx in pivot_indices:
            # 피벗이 가리키던 예전 데이터
            old_data = pivots[str(p_idx)]
            
            # 여기서부터 current_shift ~ diff_count 사이를 이진 탐색하여 실제 오프셋을 찾음
            # 간단하게는 (p_idx + current_shift) 부터 순차적으로 맞춰봄
            found_offset = current_shift
            for offset in range(current_shift, diff_count + 1):
                row = self._fetch_single(p_idx + offset)
                if row and row.get("LCNS_NO") == old_data["LCNS_NO"] and row.get("CHNG_DT") == old_data["CHNG_DT"]:
                    found_offset = offset
                    break
            
            shift_amounts[p_idx] = found_offset
            current_shift = found_offset
            
        # 3. 새로운 데이터 다운로드
        # shift_amounts 를 바탕으로 각 구간별 새로 끼어든(Shift를 유발한) 인덱스를 찾을 수 있음.
        # 가장 무식하고 확실한 방법: shift 가 +1 증가한 구간 안에서 이진 탐색으로 끼어든 지점을 찾는다.
        # (구현 편의상 여기서는 늘어난 만큼의 새 데이터를 수집한다고 가정하지만,
        # 정확히는 전체 데이터를 대상으로 차분 다운로드)
        
        # 현재는 간단히: 가장 최근 추가된 내역들을 수집하기 위해, 가장 앞단(1번부터 diff_count까지)을 다운로드?
        # 아니요, 데이터는 알파벳순(BSSH_NM)이므로 어느 곳에 삽입되었는지 구간 이진 탐색을 해야 합니다.
        
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
            self.log_callback(f"구간 {seg_start}~{seg_end} 에서 {count}건의 삽입 발견! 데이터 다운로드 중...")
            
            new_start = seg_start + base_shift
            new_end = seg_end + base_shift + count
            
            # API는 한 번에 최대 1000건 조회 가능하므로 청크 분할
            fetched_rows = []
            current_start = new_start
            while current_start <= new_end:
                current_end = min(current_start + 999, new_end)
                max_retries = len(settings.API_KEYS)
                retries = 0
                while retries <= max_retries:
                    res, used_key = self.api_client.fetch_data(current_start, current_end)
                    if settings.SERVICE_ID in res:
                        code = res[settings.SERVICE_ID]['RESULT']['CODE']
                        if code == "INFO-000":
                            rows = res[settings.SERVICE_ID]['row']
                            fetched_rows.extend(rows)
                            break
                        elif code in ["INFO-300", "INFO-333"] or "유효 호출건수" in res[settings.SERVICE_ID]['RESULT'].get('MSG', ''):
                            self.api_client.rotate_key(used_key)
                            time.sleep(1)
                            retries += 1
                            continue
                        else:
                            break
                    else:
                        break
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
        StateManager.save_state(state)
        
        return new_data_rows
