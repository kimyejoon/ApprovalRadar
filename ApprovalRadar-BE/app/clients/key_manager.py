import datetime
import time
import threading
import httpx
from app.core.config import settings
from app.core.logger import logger
from app.clients import key_usage_repository as key_usage_repo

class ApiKeysExhaustedError(Exception):
    """모든 API 키가 소진되었을 때 발생하는 예외"""
    pass

class KeyManager:
    # ─── 클래스 레벨 공유 상태 (모든 인스턴스 공유) ──────────────────────────
    _exhausted_until: datetime.datetime | None = None
    _class_lock = threading.Lock()
    _usage: dict[str, dict] = {}
    _recovery_client: httpx.AsyncClient | None = None
    _last_working_key_idx: int = 0
    _REFRESH_INTERVAL: float = 60.0
    _exhausted_keys: set[str] = set()
    _db_loaded: bool = False

    def __init__(self):
        settings._load_api_keys()
        self.api_keys = settings.API_KEYS.copy()
        with self._class_lock:
            if self._last_working_key_idx < len(self.api_keys):
                self.current_key_idx = self._last_working_key_idx
            else:
                self.current_key_idx = 0
            
            # 모든 워커 인스턴스 간 소진 키 목록 실시간 연동을 위해 클래스 레벨 세트 연결
            self.exhausted_keys = self._exhausted_keys

            # 서버 재기동 시 데이터베이스로부터 오늘치 사용량과 소진 키 상태를 메모리로 동기화
            if not self.__class__._db_loaded:
                try:
                    from database import get_db
                    today = datetime.date.today().isoformat()
                    with get_db() as conn:
                        # 1. 소진 키 상태 로드
                        rows_ex = conn.execute(
                            "SELECT key_masked FROM api_key_usage WHERE usage_date = ? AND exhausted = 1",
                            (today,)
                        ).fetchall()
                        db_exhausted_masked = {r["key_masked"] for r in rows_ex}
                        for key in self.api_keys:
                            if self._mask_key(key) in db_exhausted_masked:
                                self._exhausted_keys.add(key)
                        
                        # 2. API 사용량 로드
                        rows_usage = conn.execute(
                            "SELECT key_masked, call_count FROM api_key_usage WHERE usage_date = ?",
                            (today,)
                        ).fetchall()
                        for r in rows_usage:
                            self._usage[r["key_masked"]] = {"date": today, "count": r["call_count"]}
                    
                    self.__class__._db_loaded = True
                except Exception:
                    pass

        self.key_lock = threading.Lock()
        self._last_refresh_time: float = time.time()

    @classmethod
    def _mask_key(cls, key: str) -> str:
        return f"{key[:5]}***{key[-3:]}" if len(key) > 8 else "***"

    @classmethod
    def is_exhausted(cls) -> bool:
        with cls._class_lock:
            if cls._exhausted_until is None:
                return False
            if datetime.datetime.now() >= cls._exhausted_until:
                cls._exhausted_until = None
                logger.info("🔄 자정이 지나 API 키 소진 상태가 초기화되었습니다. 크롤링을 재개합니다.")
                return False
            return True

    @classmethod
    def mark_exhausted(cls):
        with cls._class_lock:
            now = datetime.datetime.now()
            cls._exhausted_until = now + datetime.timedelta(minutes=10)

    @classmethod
    def _increment_usage(cls, key: str, service_id: str = ""):
        today = datetime.date.today().isoformat()
        masked = cls._mask_key(key)
        with cls._class_lock:
            entry = cls._usage.setdefault(masked, {"date": today, "count": 0})
            if entry["date"] != today:
                entry["date"] = today
                entry["count"] = 0
            entry["count"] += 1
            today_count = entry["count"]
        key_usage_repo.increment(masked, today, service_id)

        svc_name = key_usage_repo.SERVICE_NAME_MAP.get(service_id, service_id) if service_id else "알 수 없음"
        logger.debug(
            f"[API 호출] {svc_name}({service_id}) | 키: {masked} | 오늘 누적: {today_count}회"
        )

        if today_count in (900, 950, 990):
            try:
                from app.core.events import broadcaster
                import json
                warn_msg = json.dumps({
                    "type": "WARN",
                    "message": f"API 키 잔여량 경고: {masked} 키가 {today_count}/1000건 사용됨 — 잔여 {1000 - today_count}건"
                }, ensure_ascii=False)
                broadcaster.broadcast_sync(warn_msg)
            except Exception:
                pass

    @classmethod
    def _mark_key_exhausted_in_db(cls, key: str):
        today = datetime.date.today().isoformat()
        key_usage_repo.mark_exhausted(cls._mask_key(key), today)

    @classmethod
    def recover_exhaustion(cls, active_masked_keys: set[str]) -> None:
        today = datetime.date.today().isoformat()
        with cls._class_lock:
            cls._exhausted_until = None
        for masked in active_masked_keys:
            key_usage_repo.reset(masked, today)

    @classmethod
    async def check_key_recovery(cls, api_keys: list, base_url: str, data_type: str, service_id: str = "I2859") -> bool:
        if not cls.is_exhausted():
            return False

        with cls._class_lock:
            if cls._recovery_client is None or cls._recovery_client.is_closed:
                cls._recovery_client = httpx.AsyncClient(
                    headers={'Connection': 'keep-alive', 'Accept': 'application/json'},
                    follow_redirects=True,
                )

        logger.info("[키 회복 체크] 소진된 키 활성화 여부 확인 중...")
        active_masked: set[str] = set()
        for key in api_keys:
            url = f"{base_url}/{key}/{service_id}/{data_type}/1/1"
            try:
                res = (await cls._recovery_client.get(url, timeout=7)).json()
                if service_id in res:
                    code = res[service_id]['RESULT']['CODE']
                    if code == "INFO-000":
                        active_masked.add(cls._mask_key(key))
            except Exception:
                pass

        if active_masked:
            cls.recover_exhaustion(active_masked)
            logger.info(f"키 회복: {len(active_masked)}개 키가 정상화됨. 다음 크롤링 주기에 자동 재개됩니다.")
            return True

        logger.info("[키 회복 체크] 아직 소진 상태 유지 중.")
        return False

    def refresh_keys(self):
        settings._load_api_keys()
        new_keys = settings.API_KEYS.copy()
        with self.key_lock:
            old_keys = set(self.api_keys)
            new_set = set(new_keys)
            added = new_set - old_keys
            removed = old_keys - new_set

            if added or removed:
                self.api_keys = new_keys
                self.exhausted_keys -= removed
                if self.current_key_idx >= len(self.api_keys):
                    self.current_key_idx = 0
                if added:
                    logger.info(
                        f"🔑 [키 리프레시] {len(added)}개 키 추가 감지 → "
                        f"총 {len(self.api_keys)}개 활성 (소진: {len(self.exhausted_keys)}개)"
                    )
                if removed:
                    logger.info(f"🔑 [키 리프레시] {len(removed)}개 키 제거 감지")

    def get_current_key(self) -> str:
        with self.key_lock:
            # 현재 인덱스의 키가 다른 워커에 의해 이미 소진된 키 목록에 존재할 경우,
            # 불필요한 실패 요청 방지를 위해 소진되지 않은 다음 키로 즉시 건너뜁니다.
            for _ in range(len(self.api_keys)):
                key = self.api_keys[self.current_key_idx]
                if key not in self.exhausted_keys:
                    return key
                self.current_key_idx = (self.current_key_idx + 1) % len(self.api_keys)
            return self.api_keys[self.current_key_idx]

    async def rotate_key(self, failed_key: str, renew_session_callback):
        with self.key_lock:
            self.exhausted_keys.add(failed_key)
            self._mark_key_exhausted_in_db(failed_key)

            if len(self.exhausted_keys) >= len(self.api_keys):
                self.mark_exhausted()
                logger.error("🚨 [긴급] 오늘자 식품나라 API 키가 모두 소진되었습니다. 크롤링이 중단됩니다.")
                raise ApiKeysExhaustedError("All API keys are exhausted for today.")

            if self.api_keys[self.current_key_idx] != failed_key:
                return

            for _ in range(len(self.api_keys)):
                self.current_key_idx = (self.current_key_idx + 1) % len(self.api_keys)
                candidate = self.api_keys[self.current_key_idx]
                if candidate not in self.exhausted_keys:
                    logger.info(
                        f"[키 회전] API 한도 초과 감지! "
                        f"(소진 키: {self._mask_key(failed_key)}) ➔ "
                        f"활성 키로 교체: {self._mask_key(candidate)}"
                    )
                    break
            else:
                raise ApiKeysExhaustedError("All API keys are exhausted for today.")
        await renew_session_callback()

    async def switch_key(self, current_key: str, renew_session_callback):
        with self.key_lock:
            if self.api_keys[self.current_key_idx] != current_key:
                return
            self.current_key_idx = (self.current_key_idx + 1) % len(self.api_keys)
            new_key = self.api_keys[self.current_key_idx]
            logger.info(
                f"[키 전환] 일시적 오류(WAF/Timeout)로 임시 키 전환: "
                f"{self._mask_key(current_key)} ➔ {self._mask_key(new_key)}"
            )
        await renew_session_callback()

    async def check_keys_status(self, service_id: str = "I2861"):
        logger.info(f"\n--- API 키 상태 점검 시작 (총 {len(self.api_keys)}개) ---")
        async with httpx.AsyncClient(follow_redirects=True) as client:
            for idx, key in enumerate(self.api_keys):
                masked_key = self._mask_key(key)
                url = f"{settings.BASE_URL}/{key}/{service_id}/{settings.DATA_TYPE}/1/1"

                try:
                    res = (await client.get(url, timeout=5)).json()
                    if service_id in res:
                        code = res[service_id]['RESULT']['CODE']
                        msg = res[service_id]['RESULT']['MSG']
                        if code == "INFO-000":
                            status = "[정상 동작 (Active)]"
                        elif code in ["INFO-300", "INFO-333"] or "유효 호출건수" in msg:
                            status = "[일일 한도 초과 (Exhausted)]"
                        else:
                            status = f"[오류 ({code}: {msg})]"
                    else:
                        status = "[알 수 없는 응답 형식]"
                except Exception as e:
                    status = f"[통신 오류 또는 WAF 차단 ({str(e)})]"

                logger.info(f"Key {idx+1} ({masked_key}): {status}")
                await asyncio.sleep(0.5)
        logger.info("--- 점검 완료 ---\n")

    @classmethod
    async def startup_key_health_check(cls, service_id: str = "I2859") -> dict:
        """
        서버 시작 시 모든 키의 실제 만료 여부를 병렬로 검증합니다.

        - DB 기록/오늘자 사용량과 무관하게 실제 API 호출로 확인
        - 소진 키 → exhausted_keys 등록 + DB 기록
        - 어제 소진됐다가 오늘 복구된 키 → 자동 해제
        - 전체 병렬 처리 (timeout 7s), 오류 시 정상으로 간주 (오탐 방지)

        Returns:
            {"alive": int, "exhausted": int, "unknown": int, "total": int}
        """
        import asyncio as _asyncio
        today = datetime.date.today().isoformat()
        keys = settings.API_KEYS[:]
        if not keys:
            logger.warning("[🔑 키 헬스체크] 등록된 키 없음 — 스킵")
            return {"alive": 0, "exhausted": 0, "unknown": 0, "total": 0}

        logger.info(f"[🔑 키 헬스체크] 시작: {len(keys)}개 키 실시간 병렬 검증 중...")

        alive_keys: list[str] = []
        exhausted_keys: list[str] = []
        unknown_keys: list[str] = []

        async def _check_one(client: httpx.AsyncClient, key: str) -> tuple[str, str]:
            """단일 키 헬스체크. 반환: (key, "alive" | "exhausted" | "unknown")"""
            url = f"{settings.BASE_URL}/{key}/{service_id}/{settings.DATA_TYPE}/1/1"
            try:
                resp = await client.get(url, timeout=7)
                data = resp.json()
                if service_id in data:
                    code = data[service_id]["RESULT"]["CODE"]
                    msg  = data[service_id]["RESULT"].get("MSG", "")
                    if code in ("INFO-300", "INFO-333") or "유효 호출건수" in msg:
                        return key, "exhausted"
                    else:
                        return key, "alive"
                return key, "unknown"
            except Exception:
                # 통신 오류는 정상으로 간주 (오탐 방지)
                return key, "alive"

        async with httpx.AsyncClient(follow_redirects=True) as client:
            tasks = [_check_one(client, k) for k in keys]
            outcomes = await _asyncio.gather(*tasks)

        # 결과 반영
        with cls._class_lock:
            for key, status in outcomes:
                masked = cls._mask_key(key)
                if status == "exhausted":
                    cls._exhausted_keys.add(key)
                    key_usage_repo.mark_exhausted(masked, today)
                    exhausted_keys.append(masked)
                elif status == "alive":
                    # 어제 소진 기록이 있던 키라면 복구 (자정 경과)
                    if key in cls._exhausted_keys:
                        cls._exhausted_keys.discard(key)
                        key_usage_repo.reset(masked, today)
                    alive_keys.append(masked)
                else:
                    unknown_keys.append(masked)

        logger.info(
            f"[🔑 키 헬스체크] 완료: "
            f"정상 {len(alive_keys)}개 ✅ | "
            f"소진 {len(exhausted_keys)}개 ❌ | "
            f"확인불가 {len(unknown_keys)}개 ❓ "
            f"(총 {len(keys)}개)"
        )
        if exhausted_keys:
            logger.warning(f"[🔑 키 헬스체크] 소진된 키: {', '.join(exhausted_keys)}")
        if len(alive_keys) == 0:
            logger.error("[🔑 키 헬스체크] ⚠️ 모든 키 소진 — 크롤링 불가 상태!")

        return {
            "alive":     len(alive_keys),
            "exhausted": len(exhausted_keys),
            "unknown":   len(unknown_keys),
            "total":     len(keys),
        }
