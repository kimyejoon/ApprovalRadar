import sqlite3, sys
sys.path.insert(0, '.')
from database import DB_FILE
conn = sqlite3.connect(DB_FILE)
conn.row_factory = sqlite3.Row
r = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%poll%'").fetchall()
print('poll 관련 테이블:', [x[0] for x in r])
r2 = conn.execute('SELECT COUNT(*) FROM chng_dt_poll_history').fetchone()[0]
print('chng_dt_poll_history rows:', r2)
