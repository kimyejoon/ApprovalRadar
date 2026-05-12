import logging
import os
from logging.handlers import TimedRotatingFileHandler

def setup_logger(name: str = "ApprovalRadar") -> logging.Logger:
    logger = logging.getLogger(name)
    
    # 이미 핸들러가 등록되어 있다면 중복 추가 방지
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s - %(message)s")
        
        # Console Handler (터미널 출력용)
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
        
        # File Handler (물리 파일 저장용)
        # ApprovalRadar-BE/logs/ 경로에 생성
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        log_dir = os.path.join(base_dir, "logs")
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, "app.log")
        
        # 매일 자정에 새 파일로 분리하며, 최대 30일(backupCount=30)간 보관
        file_handler = TimedRotatingFileHandler(
            filename=log_file,
            when="midnight",
            interval=1,
            backupCount=30,
            encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        
    return logger

# 앱 전역에서 import 할 수 있는 기본 로거 인스턴스
logger = setup_logger()
