import sqlite3
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

db_path = r"c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\ApprovalRadar-BE\food_safety.db"

def main():
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    print("=== oldest_first_scan: last_event_date year distribution ===")
    rows = cursor.execute("""
        SELECT substr(last_event_date, 1, 4) as yr, count(*) as cnt
        FROM businesses
        WHERE collected_by = 'oldest_first_scan'
        GROUP BY yr
        ORDER BY yr ASC
    """).fetchall()
    for r in rows:
        print(f"  Year: {r['yr']} | Count: {r['cnt']:,}")

    print("\n=== Duplicate check (same license_no AND last_event_date, different rows) ===")
    dups = cursor.execute("""
        SELECT b1.id, b1.license_no, b1.last_event_date, b1.created_at, b1.collected_by
        FROM businesses b1
        INNER JOIN businesses b2
          ON b1.license_no = b2.license_no
         AND b1.last_event_date = b2.last_event_date
         AND b1.id != b2.id
        LIMIT 20
    """).fetchall()
    if dups:
        for d in dups:
            print(f"  ID:{d['id']} LCNS:{d['license_no']} DATE:{d['last_event_date']} COLLECTED:{d['collected_by']} AT:{d['created_at']}")
    else:
        print("  No true duplicates (UNIQUE constraint intact)")

    print("\n=== chng_dt_poller: last_event_date distribution ===")
    not_today = cursor.execute("""
        SELECT last_event_date, count(*) as cnt
        FROM businesses
        WHERE collected_by = 'chng_dt_poller'
        GROUP BY last_event_date
        ORDER BY last_event_date DESC
    """).fetchall()
    for r in not_today:
        print(f"  EventDate: {r['last_event_date']} | Count: {r['cnt']:,}")

    print("\n=== oldest_first_scan: last_event_date distribution ===")
    ofscan = cursor.execute("""
        SELECT last_event_date, count(*) as cnt
        FROM businesses
        WHERE collected_by = 'oldest_first_scan'
        GROUP BY last_event_date
        ORDER BY last_event_date DESC
        LIMIT 20
    """).fetchall()
    for r in ofscan:
        print(f"  EventDate: {r['last_event_date']} | Count: {r['cnt']:,}")

    print("\n=== api_raw_data count vs businesses count ===")
    raw_count = cursor.execute("SELECT count(*) FROM api_raw_data").fetchone()[0]
    biz_count = cursor.execute("SELECT count(*) FROM businesses").fetchone()[0]
    print(f"  api_raw_data: {raw_count:,}")
    print(f"  businesses:   {biz_count:,}")
    print(f"  Difference:   {raw_count - biz_count:,}")

    print("\n=== api_raw_data fetched_at distribution ===")
    raw_dates = cursor.execute("""
        SELECT date(fetched_at) as dt, count(*) as cnt
        FROM api_raw_data
        GROUP BY dt
        ORDER BY dt DESC
        LIMIT 10
    """).fetchall()
    for r in raw_dates:
        print(f"  Date: {r['dt']} | Count: {r['cnt']:,}")

    conn.close()

if __name__ == "__main__":
    main()
