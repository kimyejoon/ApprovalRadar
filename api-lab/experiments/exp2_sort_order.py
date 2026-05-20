"""
experiments/exp2_sort_order.py — 정렬 기준 역추적

유저가 제공한 실제 API 응답 첫 9개 레코드를 기반으로
우리 클론 DB에서 동일한 정렬을 재현하는 가설을 검증.

관찰된 데이터:
  Row1: 1.5도씨        CHNG_DT=20260518  LCNS=20210094297
  Row2: 100%순메밀...  CHNG_DT=20260515  LCNS=20250155588
  Row3: 119불닭발      CHNG_DT=20260515  LCNS=20140548421  ← Row4와 동일 LCNS
  Row4: 119불닭발      CHNG_DT=20250424  LCNS=20140548421  ← 동일 LCNS의 이전 이력
  Row5: (주)한정선     CHNG_DT=20260513  LCNS=20240054702
  Row6: 061김밥        CHNG_DT=20260508  LCNS=20250808269
  Row7: 10티하우스     CHNG_DT=20260430  LCNS=19970332324  ← Row8과 동일 LCNS
  Row8: 10티하우스     CHNG_DT=20170712  LCNS=19970332324  ← 동일 LCNS의 과거 이력
  Row9: 061            CHNG_DT=20260423  LCNS=20240800053
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db.schema import get_conn, LAB_DB

OBSERVED_ROWS = [
    {"BSSH_NM": "1.5도씨",              "CHNG_DT": "20260518", "LCNS_NO": "20210094297"},
    {"BSSH_NM": "100%순메밀 본동막국수","CHNG_DT": "20260515", "LCNS_NO": "20250155588"},
    {"BSSH_NM": "119불닭발",            "CHNG_DT": "20260515", "LCNS_NO": "20140548421"},
    {"BSSH_NM": "119불닭발",            "CHNG_DT": "20250424", "LCNS_NO": "20140548421"},
    {"BSSH_NM": "(주)한정선",           "CHNG_DT": "20260513", "LCNS_NO": "20240054702"},
    {"BSSH_NM": "061김밥",              "CHNG_DT": "20260508", "LCNS_NO": "20250808269"},
    {"BSSH_NM": "10티하우스",           "CHNG_DT": "20260430", "LCNS_NO": "19970332324"},
    {"BSSH_NM": "10티하우스",           "CHNG_DT": "20170712", "LCNS_NO": "19970332324"},
    {"BSSH_NM": "061",                  "CHNG_DT": "20260423", "LCNS_NO": "20240800053"},
]

def print_sep(title=""):
    print(f"\n{'─'*65}")
    if title:
        print(f"  {title}")
        print(f"{'─'*65}")


def analyze_observed():
    """유저 제공 데이터에서 패턴을 먼저 분석."""
    print_sep("★ 관찰 데이터 패턴 분석")

    # LCNS_NO별 그룹핑
    groups = {}
    for r in OBSERVED_ROWS:
        lcns = r["LCNS_NO"]
        groups.setdefault(lcns, []).append(r)

    print(f"\n  LCNS_NO 그룹 수: {len(groups)}개")
    for lcns, rows in groups.items():
        max_dt = max(r["CHNG_DT"] for r in rows)
        print(f"  [{lcns}] {rows[0]['BSSH_NM']} | 이력 {len(rows)}건 | MAX_CHNG_DT={max_dt}")

    # 그룹의 MAX_CHNG_DT 순서 확인
    print(f"\n  그룹별 MAX_CHNG_DT 순서:")
    group_max = [(lcns, max(r["CHNG_DT"] for r in rows), rows[0]["BSSH_NM"])
                 for lcns, rows in groups.items()]
    group_max_sorted = sorted(group_max, key=lambda x: (x[1], x[2]), reverse=False)
    group_max_sorted = sorted(group_max, key=lambda x: x[1], reverse=True)  # MAX_DT DESC

    print(f"  {'순위':<4} {'MAX_CHNG_DT':<12} {'BSSH_NM':<25} {'LCNS_NO'}")
    for i, (lcns, max_dt, nm) in enumerate(group_max_sorted, 1):
        marker = "✅" if group_max_sorted[i-1] == (lcns, max_dt, nm) else ""
        print(f"  {i:<4} {max_dt:<12} {nm:<25} {lcns}")

    print(f"\n  🔎 가설: ORDER BY MAX(CHNG_DT) OVER (PARTITION BY LCNS_NO) DESC,")
    print(f"              BSSH_NM ASC,")
    print(f"              CHNG_DT DESC")
    print(f"\n  (= 업소 그룹을 '가장 최근 변경일 기준'으로 정렬,")
    print(f"     동일 업소 내 여러 이력은 최신순)")


def check_clone_db_distribution():
    """클론 DB 5,000건의 CHNG_DT 분포 분석."""
    print_sep("클론 DB CHNG_DT 분포 (5,000건)")
    conn = get_conn()

    # 연도별 분포
    rows = conn.execute("""
        SELECT substr(CHNG_DT,1,4) AS yr,
               substr(CHNG_DT,5,2) AS mo,
               COUNT(*) AS cnt
        FROM cloned_businesses
        WHERE CHNG_DT IS NOT NULL AND CHNG_DT != ''
        GROUP BY yr, mo
        ORDER BY yr DESC, mo DESC
        LIMIT 30
    """).fetchall()

    print(f"\n  {'연월':<10} {'건수':>6}  {'바'}")
    for r in rows:
        bar = "█" * min(r["cnt"] // 5, 50)
        print(f"  {r['yr']}-{r['mo']:<6} {r['cnt']:>6}  {bar}")

    # 오늘/어제
    import datetime
    today = datetime.date.today().strftime("%Y%m%d")
    yesterday = (datetime.date.today() - datetime.timedelta(days=1)).strftime("%Y%m%d")
    today_cnt = conn.execute("SELECT COUNT(*) FROM cloned_businesses WHERE CHNG_DT = ?", (today,)).fetchone()[0]
    yest_cnt  = conn.execute("SELECT COUNT(*) FROM cloned_businesses WHERE CHNG_DT = ?", (yesterday,)).fetchone()[0]
    print(f"\n  📅 오늘({today}): {today_cnt}건")
    print(f"  📅 어제({yesterday}): {yest_cnt}건")

    # 고유 LCNS_NO 수
    uniq_lcns = conn.execute("SELECT COUNT(DISTINCT LCNS_NO) FROM cloned_businesses").fetchone()[0]
    total = conn.execute("SELECT COUNT(*) FROM cloned_businesses").fetchone()[0]
    print(f"\n  고유 LCNS_NO: {uniq_lcns:,}개 / 전체: {total:,}건")
    print(f"  → 평균 이력: {total/uniq_lcns:.2f}건/업소")
    print(f"\n  ★ 주목: total_count=1307 vs 고유LCNS_NO={uniq_lcns}")
    if uniq_lcns == 1307:
        print(f"     → total_count = 고유 LCNS_NO 수! (업소 수 기준)")
    elif total == 1307:
        print(f"     → total_count = 전체 레코드 수")
    else:
        print(f"     → 불일치. 추가 분석 필요.")

    conn.close()


def check_sort_hypotheses():
    """
    3가지 정렬 가설을 클론 DB에서 시뮬레이션하여
    실제 API 응답 첫 9개 레코드와 비교.
    """
    print_sep("정렬 가설 검증 — 클론 DB vs 실제 API 응답 비교")
    conn = get_conn()

    hypotheses = {
        "H1: CHNG_DT DESC, BSSH_NM ASC": """
            SELECT LCNS_NO, BSSH_NM, CHNG_DT
            FROM cloned_businesses
            ORDER BY CHNG_DT DESC, BSSH_NM ASC
            LIMIT 15
        """,
        "H2: BSSH_NM ASC, CHNG_DT DESC": """
            SELECT LCNS_NO, BSSH_NM, CHNG_DT
            FROM cloned_businesses
            ORDER BY BSSH_NM ASC, CHNG_DT DESC
            LIMIT 15
        """,
        "H3: MAX_CHNG_DT DESC(그룹), BSSH_NM ASC, CHNG_DT DESC [★유력]": """
            SELECT c.LCNS_NO, c.BSSH_NM, c.CHNG_DT, mx.max_dt
            FROM cloned_businesses c
            JOIN (
                SELECT LCNS_NO, MAX(CHNG_DT) AS max_dt
                FROM cloned_businesses
                GROUP BY LCNS_NO
            ) mx ON c.LCNS_NO = mx.LCNS_NO
            ORDER BY mx.max_dt DESC, c.BSSH_NM ASC, c.CHNG_DT DESC
            LIMIT 15
        """,
        "H4: row_id ASC (삽입순 = API 원본순)": """
            SELECT LCNS_NO, BSSH_NM, CHNG_DT
            FROM cloned_businesses
            ORDER BY api_start_idx ASC, api_row_pos ASC
            LIMIT 15
        """,
    }

    expected = [(r["LCNS_NO"], r["BSSH_NM"], r["CHNG_DT"]) for r in OBSERVED_ROWS]

    for h_name, sql in hypotheses.items():
        rows = conn.execute(sql).fetchall()
        predicted = [(r["LCNS_NO"], r["BSSH_NM"], r["CHNG_DT"]) for r in rows[:9]]

        match_count = sum(1 for i, (p, e) in enumerate(zip(predicted, expected)) if p == e)
        match_pct = match_count / len(expected) * 100

        print(f"\n  [{h_name}]")
        print(f"  일치: {match_count}/{len(expected)} ({match_pct:.0f}%)")
        print(f"  {'순위':<4} {'BSSH_NM':<25} {'CHNG_DT':<10}  {'일치?'}")
        for i, row in enumerate(rows[:9]):
            exp = expected[i] if i < len(expected) else None
            ok = "✅" if exp and row["LCNS_NO"] == exp[0] and row["CHNG_DT"] == exp[2] else "❌"
            print(f"  {i+1:<4} {(row['BSSH_NM'] or ''):<25} {(row['CHNG_DT'] or ''):<10}  {ok}")

    conn.close()


def check_total_count_mystery():
    """
    total_count=1307인데 5000건 반환 — 불일치 분석.
    """
    print_sep("★ 핵심 미스터리: total_count=1307 vs 반환=5000")
    conn = get_conn()

    total = conn.execute("SELECT COUNT(*) FROM cloned_businesses").fetchone()[0]
    uniq_lcns = conn.execute("SELECT COUNT(DISTINCT LCNS_NO) FROM cloned_businesses").fetchone()[0]

    # LCNS_NO당 이력 건수 분포
    dist = conn.execute("""
        SELECT cnt_per_lcns, COUNT(*) AS group_cnt
        FROM (SELECT LCNS_NO, COUNT(*) AS cnt_per_lcns FROM cloned_businesses GROUP BY LCNS_NO)
        GROUP BY cnt_per_lcns ORDER BY cnt_per_lcns
    """).fetchall()

    print(f"\n  전체 레코드: {total:,}건")
    print(f"  고유 LCNS_NO: {uniq_lcns:,}개")
    print(f"  API total_count: 1,307")
    print(f"\n  LCNS_NO당 이력 건수 분포:")
    for r in dist:
        bar = "█" * min(r["group_cnt"] // 5, 40)
        print(f"    이력 {r['cnt_per_lcns']:>2}건인 업소: {r['group_cnt']:>5}개  {bar}")

    # 가설 검증
    print(f"\n  가설 검증:")
    print(f"    total_count == 고유 LCNS_NO 수?    {uniq_lcns} == 1307 → {'✅ 일치!' if uniq_lcns == 1307 else f'❌ 불일치 (차이: {abs(uniq_lcns-1307)})'}")
    print(f"    total_count == 전체 레코드 수?      {total} == 1307 → {'✅' if total == 1307 else '❌'}")

    # 특정 범위의 레코드 수
    for date_filter in ["2026%", "2025%", "2024%"]:
        cnt = conn.execute(f"SELECT COUNT(*) FROM cloned_businesses WHERE CHNG_DT LIKE '{date_filter}'").fetchone()[0]
        print(f"    CHNG_DT LIKE '{date_filter}' 건수: {cnt}")

    conn.close()


if __name__ == "__main__":
    print("=" * 65)
    print("  Exp-2: 정렬 기준 역추적 + total_count 미스터리")
    print("=" * 65)

    analyze_observed()
    check_clone_db_distribution()
    check_total_count_mystery()
    check_sort_hypotheses()

    print(f"\n{'='*65}")
    print("  실험 완료")
    print("=" * 65)
