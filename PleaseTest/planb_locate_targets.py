import sqlite3
import sys
import re
from collections import Counter

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

db_path = r"c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\ApprovalRadar-BE\food_safety.db"

# 미탐 의심 업체 목록 (Plan B 검증 대상)
TARGET_NAMES = [
    "너도나도식당 상암DMC점",
    "처갓집양념치킨 대림점",
    "빽보이피자 둔촌점",
    "미친양꼬치 홍대직영점",
    "호미스피자 명지대점",
]

def main():
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    total = cursor.execute("SELECT count(*) FROM businesses").fetchone()[0]
    print(f"=== businesses 총 레코드 수: {total:,} ===\n")

    # --- Plan B: 미탐 의심 업체 DB 내 존재 여부 및 위치 탐색 ---
    print("=== [Plan B] 미탐 의심 업체 DB 내 존재 여부 ===")
    for name in TARGET_NAMES:
        rows = cursor.execute(
            "SELECT id, license_no, business_name, last_event_date, created_at, collected_by "
            "FROM businesses WHERE business_name = ?",
            (name,)
        ).fetchall()
        if rows:
            for r in rows:
                print(f"  ✅ 존재 | '{name}' | LCNS:{r['license_no']} | EventDate:{r['last_event_date']} | Source:{r['collected_by']}")
        else:
            # 유사 이름도 검색
            like_rows = cursor.execute(
                "SELECT id, license_no, business_name, last_event_date, collected_by FROM businesses "
                "WHERE business_name LIKE ?",
                (f"%{name[:6]}%",)
            ).fetchall()
            if like_rows:
                print(f"  ⚠️ 부분일치 | '{name}' 검색결과:")
                for lr in like_rows[:3]:
                    print(f"     - '{lr['business_name']}' | LCNS:{lr['license_no']}")
            else:
                print(f"  ❌ 미존재 | '{name}'")
    print()

    # I2861 ORDER BY 상호명 기준으로 위치 추정 (DB 내 사전순 정렬 위치)
    print("=== [Plan B] 미탐 의심 업체의 DB 내 사전순 위치 (I2861 정렬 기준 추정) ===")
    all_names = cursor.execute(
        "SELECT DISTINCT business_name FROM businesses ORDER BY business_name ASC"
    ).fetchall()
    name_list = [r[0] for r in all_names]
    total_unique = len(name_list)
    print(f"  총 유니크 상호명: {total_unique:,}")

    for name in TARGET_NAMES:
        # 해당 이름 주변 50개 위치 탐색
        import bisect
        pos = bisect.bisect_left(name_list, name)
        print(f"\n  '{name}' → 예상 위치: {pos:,}/{total_unique:,}")
        # 위아래 3개씩 확인
        start = max(0, pos - 3)
        end = min(total_unique, pos + 4)
        for i in range(start, end):
            marker = " ← 삽입위치" if i == pos else ""
            print(f"    [{i:6,}] {name_list[i]}{marker}")

    conn.close()

if __name__ == "__main__":
    main()
