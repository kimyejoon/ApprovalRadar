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

    print("=== [Plan C] business_name 공통 단어/글자 빈도 분석 ===\n")

    # 전체 상호명 수집
    rows = cursor.execute("SELECT business_name FROM businesses WHERE business_name IS NOT NULL").fetchall()
    all_names = [r[0] for r in rows]
    print(f"분석 대상 상호명 총 {len(all_names):,}개\n")

    # --- 방법 1: 공백 기준 단어 토큰 빈도 ---
    word_counter = Counter()
    for name in all_names:
        tokens = name.split()
        for tok in tokens:
            # 순수 한글/영문/숫자 단어만 (특수문자 제외), 2글자 이상
            clean = re.sub(r'[^\w가-힣]', '', tok)
            if len(clean) >= 2:
                word_counter[clean] += 1

    print("=== 단어(공백 분리) 빈도 TOP 80 ===")
    for word, cnt in word_counter.most_common(80):
        print(f"  '{word}': {cnt:,}")

    print()

    # --- 방법 2: 연속 2글자 바이그램 빈도 (더 세밀한 딕셔너리용) ---
    bigram_counter = Counter()
    for name in all_names:
        for i in range(len(name) - 1):
            bg = name[i:i+2]
            # 한글 또는 영문 바이그램만
            if re.match(r'^[가-힣a-zA-Z]{2}$', bg):
                bigram_counter[bg] += 1

    print("=== 2글자 바이그램 빈도 TOP 50 ===")
    for bg, cnt in bigram_counter.most_common(50):
        print(f"  '{bg}': {cnt:,}")

    # --- Plan C 실행 시 예상 BSSH_NM 검색어 후보 추출 ---
    # 최소 1,000회 이상 등장하는 단어만 추려서 API 검색어 후보로 제안
    print("\n=== Plan C API 검색어 후보 (단어 빈도 >= 1,000) ===")
    candidates = [(w, c) for w, c in word_counter.most_common() if c >= 1000]
    print(f"  총 후보 단어 수: {len(candidates)}")
    for w, c in candidates:
        print(f"  '{w}': {c:,}")

    conn.close()

if __name__ == "__main__":
    main()
