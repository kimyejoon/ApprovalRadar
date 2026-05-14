import socket


def find_available_port(start: int = 8000, end: int = 8010) -> tuple[int, bool]:
    """
    사용 가능한 포트를 start부터 end까지 순차적으로 탐색합니다.

    Returns:
        (port, was_fallback) — was_fallback이 True이면 start 포트가 이미 사용 중이었음을 의미합니다.

    Raises:
        RuntimeError: start ~ end 범위 내 사용 가능한 포트가 없는 경우
    """
    for port in range(start, end + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            result = s.connect_ex(('localhost', port))
            if result != 0:
                # 연결 실패 = 해당 포트가 사용 가능함
                was_fallback = (port != start)
                return port, was_fallback

    raise RuntimeError(
        f"포트 {start}~{end} 범위 내 사용 가능한 포트가 없습니다.\n"
        "다른 프로그램을 종료한 후 다시 시도해주세요."
    )
