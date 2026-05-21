import sqlite3
import sys
import re
from collections import Counter

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

db_path = r"c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\ApprovalRadar-BE\food_safety.db"

def main():
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    rows = cursor.execute(
        "SELECT business_name FROM businesses WHERE business_name IS NOT NULL"
    ).fetchall()
    all_names = [r[0] for r in rows]
    total = len(all_names)
    print(f"전체 상호명: {total:,}건\n")

    # ───────────────────────────────────────
    # 1글자 한글 음절 빈도 분석
    # ───────────────────────────────────────
    onegram_counter = Counter()
    for name in all_names:
        seen = set()
        for ch in name:
            if '가' <= ch <= '힣' and ch not in seen:
                onegram_counter[ch] += 1
                seen.add(ch)

    # 커버리지: 상위 N개 1글자를 사용했을 때 탐지 가능한 업체 비율
    print("=== 1글자 음절 빈도 TOP 50 ===")
    for ch, cnt in onegram_counter.most_common(50):
        pct = cnt / total * 100
        print(f"  '{ch}': {cnt:,}건 ({pct:.1f}%)")

    # 상위 N개의 누적 커버리지 (중복 제거 기준)
    print("\n=== 1글자 상위 N개 누적 커버리지 ===")
    covered = set()
    idx_set = {i: name for i, name in enumerate(all_names)}
    for n, (ch, _) in enumerate(onegram_counter.most_common(30), 1):
        for i, name in idx_set.items():
            if ch in name:
                covered.add(i)
        print(f"  TOP {n:2d}글자 사용 시 커버: {len(covered):,}/{total:,} ({len(covered)/total*100:.2f}%)")
    
    # ───────────────────────────────────────
    # 2글자 한글 바이그램 빈도 분석
    # ───────────────────────────────────────
    bigram_counter = Counter()
    for name in all_names:
        seen = set()
        for i in range(len(name) - 1):
            bg = name[i:i+2]
            if re.match(r'^[가-힣]{2}$', bg) and bg not in seen:
                bigram_counter[bg] += 1
                seen.add(bg)

    print("\n=== 2글자 바이그램 빈도 TOP 50 ===")
    for bg, cnt in bigram_counter.most_common(50):
        pct = cnt / total * 100
        print(f"  '{bg}': {cnt:,}건 ({pct:.1f}%)")

    # 2글자 누적 커버리지
    print("\n=== 2글자 상위 N개 누적 커버리지 ===")
    covered2 = set()
    for n, (bg, _) in enumerate(bigram_counter.most_common(50), 1):
        for i, name in idx_set.items():
            if bg in name:
                covered2.add(i)
        if n in [10, 20, 30, 40, 50]:
            print(f"  TOP {n:2d}글자쌍 사용 시 커버: {len(covered2):,}/{total:,} ({len(covered2)/total*100:.2f}%)")

    # ───────────────────────────────────────
    # 1글자 + 2글자 조합 커버리지
    # ───────────────────────────────────────
    print("\n=== 1글자 TOP20 + 2글자 TOP30 조합 커버리지 ===")
    combined = set()
    for ch, _ in onegram_counter.most_common(20):
        for i, name in idx_set.items():
            if ch in name:
                combined.add(i)
    for bg, _ in bigram_counter.most_common(30):
        for i, name in idx_set.items():
            if bg in name:
                combined.add(i)
    print(f"  커버: {len(combined):,}/{total:,} ({len(combined)/total*100:.2f}%)")

    # ───────────────────────────────────────
    # 미탐 업체 타깃 검색어 분석
    # ───────────────────────────────────────
    targets = [
        "너도나도식당 상암DMC점",
        "처갓집양념치킨 대림점",
        "빽보이피자 둔촌점",
        "미친양꼬치 홍대직영점",
        "호미스피자 명지대점",
    ]
    print("\n=== 미탐 업체 — 1글자/2글자 매핑 가능 여부 ===")
    for t in targets:
        matched_1 = [ch for ch, _ in onegram_counter.most_common(20) if ch in t]
        matched_2 = [bg for bg, _ in bigram_counter.most_common(30) if bg in t]
        print(f"  '{t}'")
        print(f"    1글자 매핑: {matched_1}")
        print(f"    2글자 매핑: {matched_2}")

    conn.close()

if __name__ == "__main__":
    main()
