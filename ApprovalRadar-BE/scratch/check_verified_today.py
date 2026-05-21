import sys

# UTF-8 출력 설정
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

sys.path.append(r"c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\ApprovalRadar-BE")

from database import get_db

def main():
    target_date = "20260521"
    date_hyphen = f"{target_date[:4]}-{target_date[4:6]}-{target_date[6:8]}"
    print(f"🔎 오늘({date_hyphen}) 처리된 업소 목록 조회 시도...")
    
    with get_db() as conn:
        rows = conn.execute(
            "SELECT license_no, business_name, last_event_date, updated_at, created_at FROM businesses WHERE updated_at LIKE ? OR created_at LIKE ? LIMIT 10",
            (f"{date_hyphen}%", f"{date_hyphen}%")
        ).fetchall()
        
        print(f"📊 발견된 레코드 수 (최대 10개 표시): {len(rows)}")
        for r in rows:
            print(f"   - BSSH_NM: {r['business_name']} | LCNS: {r['license_no']} | Event: {r['last_event_date']} | Updated: {r['updated_at']} | Created: {r['created_at']}")

if __name__ == "__main__":
    main()
