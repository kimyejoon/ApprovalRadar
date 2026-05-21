import sqlite3
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

db_path = r"c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\ApprovalRadar-BE\food_safety.db"

def main():
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # --- 1. 삭제 대상 사전 확인 ---
    biz_count = cursor.execute(
        "SELECT count(*) FROM businesses WHERE collected_by = 'chng_dt_poller'"
    ).fetchone()[0]
    hist_count = cursor.execute(
        "SELECT count(*) FROM chng_dt_poll_history"
    ).fetchone()[0]

    print(f"[DRY-RUN] 삭제 대상:")
    print(f"  businesses (collected_by='chng_dt_poller'): {biz_count:,} 건")
    print(f"  chng_dt_poll_history:                       {hist_count:,} 건")
    print()

    # --- 2. 실제 삭제 ---
    cursor.execute("DELETE FROM businesses WHERE collected_by = 'chng_dt_poller'")
    deleted_biz = cursor.rowcount
    print(f"✅ businesses 삭제 완료: {deleted_biz:,} 건")

    cursor.execute("DELETE FROM chng_dt_poll_history")
    deleted_hist = cursor.rowcount
    print(f"✅ chng_dt_poll_history 삭제 완료: {deleted_hist:,} 건")

    conn.commit()

    # --- 3. 결과 검증 ---
    remaining_biz = cursor.execute(
        "SELECT count(*) FROM businesses WHERE collected_by = 'chng_dt_poller'"
    ).fetchone()[0]
    remaining_hist = cursor.execute(
        "SELECT count(*) FROM chng_dt_poll_history"
    ).fetchone()[0]
    total_biz = cursor.execute("SELECT count(*) FROM businesses").fetchone()[0]

    print()
    print("=== 삭제 후 검증 ===")
    print(f"  chng_dt_poller 잔존 건수: {remaining_biz}")
    print(f"  chng_dt_poll_history 잔존 건수: {remaining_hist}")
    print(f"  businesses 총 레코드 수: {total_biz:,}")

    conn.close()
    print("\n완료.")

if __name__ == "__main__":
    main()
