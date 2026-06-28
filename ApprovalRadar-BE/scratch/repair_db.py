import sqlite3
import os
import sys

# UTF-8 output
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

db_path = r"c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\ApprovalRadar-BE\food_safety.db"
repaired_path = r"c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\ApprovalRadar-BE\food_safety_repaired.db"

def repair():
    if not os.path.exists(db_path):
        print("Original database not found.")
        return

    if os.path.exists(repaired_path):
        os.remove(repaired_path)

    print(f"Connecting to corrupted database: {db_path}")
    conn_orig = sqlite3.connect(db_path)
    cursor_orig = conn_orig.cursor()

    print(f"Creating repaired database: {repaired_path}")
    conn_rep = sqlite3.connect(repaired_path)
    cursor_rep = conn_rep.cursor()

    # WAL mode for performance
    cursor_rep.execute("PRAGMA journal_mode=WAL;")
    cursor_rep.execute("PRAGMA synchronous=OFF;")

    # Get all tables
    tables = [r[0] for r in cursor_orig.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()]
    print(f"Found {len(tables)} tables to copy: {tables}")

    for table in tables:
        print(f"\nProcessing table: {table}")
        # Get CREATE TABLE statement
        create_sql = cursor_orig.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()[0]
        cursor_rep.execute(create_sql)

        # Get column names
        cursor_orig.execute(f"SELECT * FROM {table} LIMIT 1")
        columns = [desc[0] for desc in cursor_orig.description]
        placeholders = ",".join(["?"] * len(columns))

        # Try bulk copy
        try:
            print("  Attempting bulk copy...")
            rows = cursor_orig.execute(f"SELECT {','.join(columns)} FROM {table}").fetchall()
            print(f"  Successfully fetched {len(rows)} rows. Inserting...")
            cursor_rep.executemany(f"INSERT INTO {table} ({','.join(columns)}) VALUES ({placeholders})", rows)
            conn_rep.commit()
            print(f"  Bulk copy for {table} completed successfully.")
        except Exception as e:
            print(f"  ❌ Bulk copy failed: {e}. Switching to row-by-row recovery via rowid...")
            # Recover row-by-row
            try:
                min_max = cursor_orig.execute(f"SELECT min(rowid), max(rowid) FROM {table}").fetchone()
                min_id, max_id = min_max[0], min_max[1]
                if min_id is None or max_id is None:
                    print("  No rows or rowid not accessible.")
                    continue

                print(f"  Rowid range: {min_id} to {max_id}")
                success_count = 0
                error_count = 0
                
                # Fetch row by row
                for rowid in range(min_id, max_id + 1):
                    try:
                        row = cursor_orig.execute(f"SELECT {','.join(columns)} FROM {table} WHERE rowid = ?", (rowid,)).fetchone()
                        if row:
                            cursor_rep.execute(f"INSERT INTO {table} ({','.join(columns)}) VALUES ({placeholders})", row)
                            success_count += 1
                            if success_count % 10000 == 0:
                                conn_rep.commit()
                                print(f"    - Recovered {success_count} rows...")
                    except Exception as row_err:
                        error_count += 1
                        # Log error once every few rows to avoid bloating
                        if error_count <= 5 or error_count % 100 == 0:
                            print(f"    ❌ Error at rowid {rowid}: {row_err}")

                conn_rep.commit()
                print(f"  Row-by-row recovery for {table} finished: {success_count} succeeded, {error_count} failed.")
            except Exception as outer_err:
                print(f"  ❌ Rowid recovery initialization failed for {table}: {outer_err}")

    # Build indexes
    print("\n[Index Building] Rebuilding indexes in the repaired database...")
    indexes = cursor_orig.execute("SELECT sql FROM sqlite_master WHERE type='index' AND sql IS NOT NULL").fetchall()
    for idx_sql_row in indexes:
        idx_sql = idx_sql_row[0]
        try:
            cursor_rep.execute(idx_sql)
            print(f"  Built index: {idx_sql[:60]}...")
        except Exception as idx_err:
            print(f"  ❌ Error building index: {idx_err} (SQL: {idx_sql})")

    conn_rep.commit()
    conn_orig.close()
    conn_rep.close()

    print("\n[Integrity Check] Running integrity check on repaired database...")
    conn_check = sqlite3.connect(repaired_path)
    check_res = conn_check.execute("PRAGMA integrity_check;").fetchall()
    conn_check.close()
    print(f"Repaired DB Integrity check result: {check_res}")

    if check_res == [('ok',)]:
        print("\n🎉 Repair succeeded! Swapping databases...")
        corrupted_backup_path = db_path + ".corrupted"
        if os.path.exists(corrupted_backup_path):
            os.remove(corrupted_backup_path)
        os.rename(db_path, corrupted_backup_path)
        os.rename(repaired_path, db_path)
        print(f"  - Corrupted DB renamed to: {corrupted_backup_path}")
        print(f"  - Repaired DB set as: {db_path}")
    else:
        print("\n❌ Repaired database still has integrity issues. Swapping aborted.")

if __name__ == "__main__":
    repair()
