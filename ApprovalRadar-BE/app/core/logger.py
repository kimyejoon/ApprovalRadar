import logging
import os
import sqlite3
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler

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
            # 로거 초기화 중 에러는 print로 대체 (무한루프 방지)
            print(f"Failed to create system_logs table: {e}")

    def emit(self, record):
        try:
            # 포맷팅된 메시지 가져오기 (시간 등 제외, 순수 메시지)
            msg = self.format(record)
            level = record.levelname
            module = record.name
            
            # DB 연결 및 저장
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

def custom_namer(default_name):
    """
    TimedRotatingFileHandler의 기본 백업 파일명(app.log.2026-05-12)을
    app_20260512.log 형태로 변경하는 커스텀 네이머
    """
    # default_name: .../logs/app.log.2026-05-12
    base_dir = os.path.dirname(default_name)
    filename = os.path.basename(default_name)
    # filename ex: app.log.2026-05-12
    parts = filename.split('.')
    if len(parts) >= 3 and parts[-1].count('-') == 2:
        date_str = parts[-1].replace('-', '')
        return os.path.join(base_dir, f"app_{date_str}.log")
    return default_name

def setup_logger(name: str = "ApprovalRadar") -> logging.Logger:
    logger = logging.getLogger(name)
    
    # 이미 핸들러가 등록되어 있다면 중복 추가 방지
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s - %(message)s")
        db_formatter = logging.Formatter("%(message)s") # DB에는 순수 메시지만 저장 (시간은 DB 컬럼에 기록됨)
        
        # 1. Console Handler
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
        
        # 2. File Handler (물리 파일 저장용)
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        log_dir = os.path.join(base_dir, "logs")
        os.makedirs(log_dir, exist_ok=True)
        
        # 현재 활성 파일은 app_{YYYYMMDD}.log
        current_date = datetime.now().strftime("%Y%m%d")
        log_file = os.path.join(log_dir, f"app_{current_date}.log")
        
        # 자정마다 새로운 날짜의 파일로 회전
        file_handler = TimedRotatingFileHandler(
            filename=log_file,
            when="midnight",
            interval=1,
            backupCount=30,
            encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        
        # 3. DB Handler (SQLite)
        db_path = os.path.join(base_dir, "food_safety.db")
        # 백그라운드 환경에서 SQLite DB가 준비되기 전일 수도 있으므로, 예외 처리가 필요할 수 있지만,
        # emit 내부에서 매번 connect 하므로 안전합니다.
        db_handler = SQLiteHandler(db_path)
        db_handler.setFormatter(db_formatter)
        logger.addHandler(db_handler)
        
    return logger

# 앱 전역에서 import 할 수 있는 기본 로거 인스턴스
logger = setup_logger()
