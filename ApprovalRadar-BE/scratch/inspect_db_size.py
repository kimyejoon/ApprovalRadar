import sqlite3
import os
import sys

# database.py 경로 가져오기
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import DB_FILE

print(f"DB File Path: {DB_FILE}")
print(f"DB Size: {os.path.getsize(DB_FILE) / 1024 / 1024:.2f} MB")

conn = sqlite3.connect(DB_FILE)
cursor = conn.cursor()

# 테이블 목록 가져오기
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = [row[0] for row in cursor.fetchall()]

print("\n--- Table Record Counts ---")
for table in sorted(tables):
    try:
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        count = cursor.fetchone()[0]
        print(f"Table: {table:<30} | Records: {count:,}")
    except Exception as e:
        print(f"Table: {table:<30} | Error: {e}")

# 각 테이블의 대략적인 크기 추정 (SQLite dbstat 가상 테이블 이용, 가능할 경우)
# dbstat 가상 테이블은 SQLite가 SQLITE_ENABLE_DBSTAT_VTAB 옵션과 함께 빌드되었을 때만 제공됨
try:
    print("\n--- SQLite dbstat (Table size estimate) ---")
    cursor.execute("""
        SELECT name, sum(pgsize)/1024.0/1024.0 as size_mb 
        FROM dbstat 
        GROUP BY name 
        ORDER BY size_mb DESC;
    """)
    for name, size_mb in cursor.fetchall():
        print(f"Table: {name:<30} | Size: {size_mb:.2f} MB")
except Exception as e:
    print(f"Could not read dbstat virtual table: {e}")

conn.close()
