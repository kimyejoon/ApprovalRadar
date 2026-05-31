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


def prune_db(days: int = 7, force: bool = False):
    import logging
    from app.core.logger import logger, SQLiteHandler
    from database import DB_FILE

    # 1. 중복 방지 및 락 방지를 위해 SQLiteHandler 임시 분리
    # Pruning 진행 도중 로그가 DB에 다시 적재되며 발생하는 Self-Locking 방지
    root_logger = logging.getLogger("ApprovalRadar")
    removed_handlers = []
    for h in list(root_logger.handlers):
        if isinstance(h, SQLiteHandler):
            root_logger.removeHandler(h)
            removed_handlers.append(h)

    logger.info(f"Starting SQLite DB Pruning (keeping last {days} days, force={force})...")
    try:
        # 2. 24시간 중복 방지 체크 (force=False 일 때만)
        if not force:
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            try:
                cursor.execute("SELECT updated_at FROM crawler_state WHERE service_id = 'db_maintenance'")
                row = cursor.fetchone()
                if row:
                    last_pruned = datetime.datetime.fromisoformat(row[0])
                    if datetime.datetime.now() - last_pruned < datetime.timedelta(hours=24):
                        logger.info(f"DB Pruning skipped: last pruned at {row[0]} (less than 24 hours ago).")
                        conn.close()
                        return
            except Exception as ex:
                logger.warning(f"Failed to parse last pruned time: {ex}, proceeding with pruning.")
            finally:
                if conn:
                    conn.close()

        # 3. 작업 전 파일 크기
        size_before = os.path.getsize(DB_FILE)
        size_before_mb = size_before / 1024 / 1024

        # timeout 60초 설정 및 BEGIN IMMEDIATE 트랜잭션으로 락 충돌 방지
        conn = sqlite3.connect(DB_FILE, timeout=60.0)
        conn.execute("BEGIN IMMEDIATE;")
        cursor = conn.cursor()

        # 4. auto_vacuum = INCREMENTAL 설정 및 최초 1회 마이그레이션
        cursor.execute("PRAGMA auto_vacuum;")
        auto_vacuum_mode = cursor.fetchone()[0]
        if auto_vacuum_mode != 2:  # 2: INCREMENTAL
            logger.info("Migrating SQLite auto_vacuum mode to INCREMENTAL...")
            cursor.execute("PRAGMA auto_vacuum = INCREMENTAL;")
            cursor.execute("VACUUM;")
            logger.info("Successfully migrated auto_vacuum mode to INCREMENTAL.")

        # 5. 데이터 삭제
        raw_deleted = 0
        logs_deleted = 0
        
        # api_raw_data 삭제 재시도 루프
        for retry in range(5):
            try:
                cursor.execute(
                    "DELETE FROM api_raw_data WHERE datetime(fetched_at) < datetime('now', ?)",
                    (f"-{days} days",)
                )
                raw_deleted = cursor.rowcount
                break
            except sqlite3.OperationalError as oe:
                if "locked" in str(oe).lower() and retry < 4:
                    time.sleep(0.5)
                else:
                    raise

        # system_logs 삭제 재시도 루프
        for retry in range(5):
            try:
                cursor.execute(
                    "DELETE FROM system_logs WHERE datetime(created_at) < datetime('now', ?)",
                    (f"-{days} days",)
                )
                logs_deleted = cursor.rowcount
                break
            except sqlite3.OperationalError as oe:
                if "locked" in str(oe).lower() and retry < 4:
                    time.sleep(0.5)
                else:
                    raise

        # 'db_maintenance' 상태 갱신
        now_str = datetime.datetime.now().isoformat()
        cursor.execute(
            "INSERT OR REPLACE INTO crawler_state (service_id, last_total_count, pivots, updated_at) VALUES (?, 0, '{}', ?)",
            ('db_maintenance', now_str)
        )

        conn.commit()
        conn.close()  # 커넥션을 명시적으로 닫아 락 해제
        logger.info(f"DB Pruning data deletion completed. Deleted {raw_deleted:,} rows from api_raw_data, {logs_deleted:,} rows from system_logs.")

        # 6. incremental_vacuum 실행 (5000 페이지씩 락 부담 없이 점진적 회수)
        logger.info("Starting incremental_vacuum space reclamation...")
        vacuumed_total_pages = 0
        
        # autocommit 모드 (isolation_level=None) 및 타임아웃 60초 설정
        vac_conn = sqlite3.connect(DB_FILE, isolation_level=None, timeout=60.0)
        vac_cursor = vac_conn.cursor()
        try:
            while True:
                # freelist 조회 시 락 방어 재시도 루프
                freelist_count = 0
                for retry in range(5):
                    try:
                        vac_cursor.execute("PRAGMA freelist_count;")
                        freelist_count = vac_cursor.fetchone()[0]
                        break
                    except sqlite3.OperationalError as oe:
                        if "locked" in str(oe).lower() and retry < 4:
                            time.sleep(0.5)
                        else:
                            raise

                if freelist_count == 0:
                    break

                # 한 번에 5000 페이지씩 비우기
                pages_to_vacuum = min(5000, freelist_count)
                
                # vacuum 실행 시 락 방어 재시도 루프
                for retry in range(5):
                    try:
                        vac_cursor.execute(f"PRAGMA incremental_vacuum({pages_to_vacuum});")
                        break
                    except sqlite3.OperationalError as oe:
                        if "locked" in str(oe).lower() and retry < 4:
                            time.sleep(0.5)
                        else:
                            raise

                vacuumed_total_pages += pages_to_vacuum
                time.sleep(0.05)  # 다른 스레드가 쓰기 작업을 할 수 있도록 양보
        finally:
            vac_conn.close()

        # 7. 작업 후 파일 크기 및 절약된 공간
        size_after = os.path.getsize(DB_FILE)
        size_after_mb = size_after / 1024 / 1024
        saved_mb = size_before_mb - size_after_mb

        logger.info(
            f"SQLite DB Pruning completed successfully.\n"
            f"  - Size Before: {size_before_mb:.2f} MB\n"
            f"  - Size After: {size_after_mb:.2f} MB\n"
            f"  - Saved Space: {saved_mb:.2f} MB\n"
            f"  - Vacuumed Pages: {vacuumed_total_pages:,} pages"
        )

    except Exception as e:
        logger.error(f"Failed to prune DB: {e}", exc_info=True)
    finally:
        # 8. 임시 제거한 SQLiteHandler 복구
        for h in removed_handlers:
            root_logger.addHandler(h)
