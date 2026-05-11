import sqlite3
import os
from contextlib import contextmanager

DB_FILE = "food_safety.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    # Create businesses table with JSON columns for history
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS businesses (
            license_no TEXT PRIMARY KEY,
            business_name TEXT,
            address TEXT,
            representative_name TEXT,
            business_status TEXT,
            license_date TEXT,
            phone_number TEXT,
            representative_history TEXT DEFAULT '[]', -- JSON array
            licensing_history TEXT DEFAULT '[]', -- JSON array
            last_event_date TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_new INTEGER DEFAULT 1 -- 1 for True, 0 for False
        )
    ''')
    conn.commit()
    conn.close()

@contextmanager
def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row # To access columns by name
    try:
        yield conn
    finally:
        conn.close()

if __name__ == "__main__":
    init_db()
    print("Database initialized successfully.")
