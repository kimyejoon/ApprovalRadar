import logging
import os
import sys
import json
import sqlite3
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler


def _get_app_base_dir() -> str:
    """실행 환경에 따른 앱 기준 디렉토리 반환.
    - PyInstaller 번들: exe 옆 폴더 (sys.executable 기준)
    - 개발 환경: 소스 루트 폴더 (__file__ 기준)
    """
    if getattr(sys, 'frozen', False):
        # PyInstaller: exe 위치 기준 (임시 압축해제 폴더 아님)
        return os.path.dirname(sys.executable)
    # 개발: logger.py → app/core/ → app/ → BE루트
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

class SQLiteHandler(logging.Handler):
    """
    DB의 system_logs 테이블에 로그를 저장하는 커스텀 핸들러
    """
    def __init__(self, db_file: str):
        super().__init__()
        self.db_file = db_file
        self._create_table_if_not_exists()
        
    def _create_table_if_not_exists(self):
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS system_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    level TEXT,
                    module TEXT,
                    message TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Failed to create system_logs table: {e}")

    def emit(self, record):
        try:
            msg = self.format(record)
            level = record.levelname
            module = record.name
            
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO system_logs (level, module, message) VALUES (?, ?, ?)",
                (level, module, msg)
            )
            conn.commit()
            conn.close()
        except Exception:
            self.handleError(record)


class WebSocketLogHandler(logging.Handler):
    """
    연결된 WebSocket 클라이언트들에게 실시간으로 로그를 전달하는 핸들러.
    순환참조를 방지하기 위해 log_broadcaster를 지연 임포트(lazy import)로 참조합니다.
    """
    def emit(self, record):
        try:
            from app.core.events import log_broadcaster
            from datetime import datetime
            timestamp = datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S")
            payload = json.dumps({
                "timestamp": timestamp,
                "level": record.levelname,
                "message": record.getMessage(),
            }, ensure_ascii=False)
            log_broadcaster.broadcast_log(payload)
        except Exception:
            pass  # 로거 핸들러 내부 오류는 무시 (무한루프 방지)


def custom_namer(default_name):
    """
    TimedRotatingFileHandler의 기본 백업 파일명(app.log.2026-05-12)을
    app_20260512.log 형태로 변경하는 커스텀 네이머
    """
    base_dir = os.path.dirname(default_name)
    filename = os.path.basename(default_name)
    parts = filename.split('.')
    if len(parts) >= 3 and parts[-1].count('-') == 2:
        date_str = parts[-1].replace('-', '')
        return os.path.join(base_dir, f"app_{date_str}.log")
    return default_name

def setup_logger(name: str = "ApprovalRadar") -> logging.Logger:
    logger = logging.getLogger(name)
    
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s - %(message)s")
        db_formatter = logging.Formatter("%(message)s")
        
        # 1. Console Handler
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
        
        # 2. File Handler (물리 파일 저장용)
        base_dir = _get_app_base_dir()
        log_dir = os.path.join(base_dir, "logs")
        os.makedirs(log_dir, exist_ok=True)
        
        current_date = datetime.now().strftime("%Y%m%d")
        log_file = os.path.join(log_dir, f"app_{current_date}.log")
        
        file_handler = TimedRotatingFileHandler(
            filename=log_file,
            when="midnight",
            interval=1,
            backupCount=30,
            encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        
        # 3. DB Handler (SQLite) — database.py와 동일한 경로 로직
        db_path = os.path.join(base_dir, "food_safety.db")
        db_handler = SQLiteHandler(db_path)
        db_handler.setFormatter(db_formatter)
        logger.addHandler(db_handler)

        # 4. WebSocket Handler (실시간 프론트엔드 모니터링용)
        ws_handler = WebSocketLogHandler()
        ws_handler.setFormatter(formatter)
        logger.addHandler(ws_handler)
        
    return logger

# 앱 전역에서 import 할 수 있는 기본 로거 인스턴스
logger = setup_logger()
