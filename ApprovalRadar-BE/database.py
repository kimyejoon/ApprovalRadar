import sqlite3
import os
import sys
import threading
from contextlib import contextmanager

# PyInstaller 번들 실행 시: exe 옆에 DB 파일 위치
# 개발 환경: 소스 파일과 같은 디렉토리에 위치
if getattr(sys, 'frozen', False):
    _exe_dir = os.path.dirname(sys.executable)
    # macOS .app 번들 내부 구조: .app/Contents/MacOS/ApprovalRadar
    # DB/설정 파일은 .app 파일과 같은 폴더(배포 폴더)에 위치
    if (os.path.basename(_exe_dir) == 'MacOS'
            and os.path.basename(os.path.dirname(_exe_dir)) == 'Contents'):
        _BASE_DIR = os.path.abspath(os.path.join(_exe_dir, '..', '..', '..'))
    else:
        _BASE_DIR = _exe_dir  # Windows/Linux 단일 바이너리
else:
    _BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DB_FILE = os.path.join(_BASE_DIR, "food_safety.db")

# 스레드별 독립 커넥션 캐싱 (Connection Pool)
# - 동일 스레드 내에서는 커넥션을 재사용하여 open/close 오버헤드 제거
# - 크롤러 스레드 / FastAPI 요청 스레드가 각자 독립 커넥션을 보유하여 lock 충돌 방지
_thread_local = threading.local()


def _get_thread_conn() -> sqlite3.Connection:
    """현재 스레드의 커넥션을 반환합니다. 없으면 새로 생성합니다."""
    conn = getattr(_thread_local, "conn", None)
    if conn is None:
        conn = sqlite3.connect(DB_FILE, check_same_thread=False, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        _thread_local.conn = conn
    return conn


def close_thread_conn() -> None:
    """현재 스레드의 커넥션을 닫고 캐시에서 제거합니다. (테스트용)"""
    conn = getattr(_thread_local, "conn", None)
    if conn is not None:
        conn.close()
        _thread_local.conn = None


@contextmanager
def get_db():
    """스레드 로컬 커넥션을 반환하는 컨텍스트 매니저.
    커넥션은 스레드별로 캐싱되어 재사용됩니다.
    """
    conn = _get_thread_conn()
    try:
        yield conn
    except Exception:
        conn.rollback()
        raise


# 외부 모듈 호환성을 위해 DDL 스키마 및 유지보수 기능을 이관한 모듈로부터 노출
from app.database.schema import init_db
from app.database.maintenance import backup_db, vacuum_db, prune_db, prune_log_files

if __name__ == "__main__":
    init_db()
    print("Database initialized successfully.")
