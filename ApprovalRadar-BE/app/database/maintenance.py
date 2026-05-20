import sqlite3
import os
import shutil
import datetime
import time

def backup_db():
    from app.core.logger import logger
    from database import DB_FILE
    
    logger.info("Starting SQLite DB Local Backup...")
    try:
        backup_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "backups")
        os.makedirs(backup_dir, exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = os.path.join(backup_dir, f"food_safety_backup_{timestamp}.db")
        
        # 안전한 백업을 위해 DB에 Shared Lock을 걸고 복사
        conn = sqlite3.connect(DB_FILE)
        bck = sqlite3.connect(backup_file)
        with bck:
            conn.backup(bck)
        bck.close()
        conn.close()
        
        logger.info(f"SQLite DB Backup completed successfully: {backup_file}")
        
        # 최근 7일치 백업만 유지 (오래된 백업 삭제 로직)
        now = time.time()
        for filename in os.listdir(backup_dir):
            file_path = os.path.join(backup_dir, filename)
            if os.path.isfile(file_path):
                if os.stat(file_path).st_mtime < now - 7 * 86400:
                    os.remove(file_path)
                    logger.info(f"Deleted old backup: {filename}")
                    
    except Exception as e:
        logger.error(f"Failed to backup DB: {e}")


def vacuum_db():
    from app.core.logger import logger
    from database import DB_FILE
    logger.info("Starting SQLite DB VACUUM (Optimization)...")
    try:
        conn = sqlite3.connect(DB_FILE)
        conn.execute("VACUUM;")
        conn.close()
        logger.info("SQLite DB VACUUM completed successfully.")
    except Exception as e:
        logger.error(f"Failed to VACUUM DB: {e}")
