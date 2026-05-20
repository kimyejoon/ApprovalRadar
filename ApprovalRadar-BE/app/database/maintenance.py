import sqlite3
import os
import datetime
import time

def backup_db():
    from app.core.logger import logger
    from database import DB_FILE

    logger.info("Starting SQLite DB Local Backup...")
    try:
        # DB_FILE 기준으로 backups/ 폴더 생성
        # (개발: ApprovalRadar-BE/backups/,
        #  macOS .app: .app 옆 폴더/backups/,
        #  Windows .exe: exe 옆 폴더/backups/)
        backup_dir = os.path.join(os.path.dirname(DB_FILE), "backups")
        os.makedirs(backup_dir, exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = os.path.join(backup_dir, f"food_safety_backup_{timestamp}.db")

        # SQLite 온라인 핫 백업 (쓰기 잠금 없이 일관성 보장)
        conn = sqlite3.connect(DB_FILE)
        bck = sqlite3.connect(backup_file)
        with bck:
            conn.backup(bck)
        bck.close()
        conn.close()

        # 백업 파일 크기 검증 로그
        src_size = os.path.getsize(DB_FILE)
        bck_size = os.path.getsize(backup_file)
        size_mb = bck_size / 1024 / 1024
        ratio = (bck_size / src_size * 100) if src_size > 0 else 0
        logger.info(
            f"SQLite DB Backup completed: {backup_file} "
            f"({size_mb:.1f} MB, 원본 대비 {ratio:.0f}%)"
        )

        # 최근 7일치 백업만 유지 (오래된 백업 자동 삭제)
        now = time.time()
        for filename in os.listdir(backup_dir):
            file_path = os.path.join(backup_dir, filename)
            if os.path.isfile(file_path) and filename.startswith("food_safety_backup_"):
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
