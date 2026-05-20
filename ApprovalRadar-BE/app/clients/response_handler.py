from app.core.logger import logger

class ResponseHandler:
    @classmethod
    def handle_api_response_code(cls, res: dict, service_id: str, api_key: str, key_manager, current_key_idx: int) -> dict | None:
        """
        API 응답 코드를 분석합니다.
        - 정상: 응답 dict 반환
        - 키 회전/재시도 필요: {"__rotate_key__": True} 또는 None 반환
        - 복구 불가 오류: dict 반환
        """
        code = res[service_id]['RESULT']['CODE']
        msg = res[service_id]['RESULT']['MSG']

        if code in ("INFO-000", "INFO-200"):
            key_manager._increment_usage(api_key, service_id)
            # 성공한 키 인덱스를 클래스에 공유
            with key_manager._class_lock:
                key_manager._last_working_key_idx = current_key_idx
            return res

        if code in ("INFO-300", "INFO-333") or "유효 호출건수" in msg:
            return {"__rotate_key__": True}

        if code in ("ERROR-500", "ERROR-601"):
            logger.warning(f"[API 서버 오류] {code}: {msg}.")
            return None

        logger.error(f"[API 파라미터/기타 오류] {code}: {msg}")
        return res

    @classmethod
    def handle_value_error(cls, e: Exception, api_key: str, service_id: str, kwargs: dict, response, key_manager) -> None:
        """JSON 파싱 실패(WAF 차단 의심)를 처리합니다."""
        ctx = f"서비스:{service_id}, 추가:{kwargs}" if kwargs else f"서비스:{service_id}"
        raw_text = response.text[:200].replace('\n', ' ') if response is not None else "N/A"
        logger.warning(
            f"[API 파싱 오류] {ctx} | WAF 차단 의심. 미리보기: {raw_text} | 사유: {str(e)}"
        )
        if "현재 접속 중인 인증키입니다" in raw_text:
            logger.warning("WAF 임시 차단 감지! 키를 즉시 전환합니다.")
