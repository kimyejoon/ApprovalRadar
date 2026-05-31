import sqlite3
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import DB_FILE

conn = sqlite3.connect(DB_FILE)
cursor = conn.cursor()

print("--- Size Estimation of major tables (character length sum) ---")
try:
    cursor.execute("SELECT sum(length(raw_json)) FROM api_raw_data")
    raw_json_len = cursor.fetchone()[0] or 0
    print(f"api_raw_data (raw_json length sum): {raw_json_len / 1024 / 1024:.2f} MB")
except Exception as e:
    print(f"Error checking api_raw_data size: {e}")

try:
    cursor.execute("SELECT sum(length(message)) FROM system_logs")
    logs_len = cursor.fetchone()[0] or 0
    print(f"system_logs (message length sum): {logs_len / 1024 / 1024:.2f} MB")
except Exception as e:
    print(f"Error checking system_logs size: {e}")

try:
    cursor.execute("SELECT fetched_at FROM api_raw_data LIMIT 1")
    print(f"api_raw_data fetched_at sample: {cursor.fetchone()[0]}")
except Exception as e:
    print(f"Error checking api_raw_data: {e}")

try:
    cursor.execute("SELECT created_at FROM system_logs LIMIT 1")
    print(f"system_logs created_at sample: {cursor.fetchone()[0]}")
except Exception as e:
    print(f"Error checking system_logs: {e}")

try:
    cursor.execute("SELECT sum(length(representative_history) + length(licensing_history) + length(address) + length(business_name)) FROM businesses")
    biz_len = cursor.fetchone()[0] or 0
    print(f"businesses (key columns length sum): {biz_len / 1024 / 1024:.2f} MB")
except Exception as e:
    print(f"Error checking businesses size: {e}")

conn.close()
