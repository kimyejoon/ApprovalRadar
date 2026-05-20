"""
experiments/exp_chng_dt_compare.py — 실험2: CHNG_DT 필터 비교 분석

핵심 질문:
  1/5000 (plain) 과 1/5000/CHNG_DT=오늘 은 동일한 데이터인가?
  → CHNG_DT 파라미터가 단순 필터인가, 아니면 다른 데이터 뷰를 사용하는가?

방법:
  - plain:    1/1000, 1001/2000, ... 4001/5000  (5페이지)
  - filtered: 1/1000, 1001/2000, ... 4001/5000  (CHNG_DT=오늘, 5페이지)
  - 두 데이터셋의 LCNS_NO 교집합/차집합 분석

결과 → experiments/report_exp2_chng_dt.md
"""
import sys, os, time, json, datetime, argparse, collections
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import httpx

BASE_URL = "http://openapi.foodsafetykorea.go.kr/api"
SVC = "I2861"
GAP = 0.4
REPORT_PATH = os.path.join(os.path.dirname(__file__), "report_exp2_chng_dt.md")


def fetch(client, key, start, end, extra="", timeout=45):
    url = f"{BASE_URL}/{key}/{SVC}/json/{start}/{end}"
    if extra:
        url += f"/{extra}"
    t0 = time.time()
    try:
        resp = client.get(url, timeout=timeout)
        ms = int((time.time() - t0) * 1000)
        data = resp.json()
        block = data.get(SVC, {})
        code = block.get("RESULT", {}).get("CODE", "?")
        tc_raw = block.get("total_count", None)
        tc = int(tc_raw) if tc_raw not in (None, "", "null") else None
        rows = block.get("row", [])
        return {"code": code, "tc": tc, "ret": len(rows), "ms": ms, "rows": rows}
    except Exception as e:
        ms = int((time.time() - t0) * 1000)
        return {"code": "ERR", "tc": None, "ret": 0, "ms": ms, "rows": [], "err": str(e)[:80]}


def run(api_key):
    now = datetime.datetime.now()
    today = now.strftime("%Y%m%d")
    yesterday = (datetime.date.today() - datetime.timedelta(days=1)).strftime("%Y%m%d")
    lines = []

    def p(s=""):
        print(s)
        lines.append(s)

    p("=" * 72)
    p(f"  실험2: CHNG_DT 필터 비교 — plain vs filtered 데이터 동일성")
    p(f"  실행 시각: {now.strftime('%Y-%m-%d %H:%M:%S')}  |  오늘: {today}")
    p("=" * 72)

    pages = [(1,1000),(1001,2000),(2001,3000),(3001,4000),(4001,5000)]

    plain_rows    = []
    filtered_rows = []

    with httpx.Client(follow_redirects=True, headers={"Accept": "application/json"}) as client:

        # ── A. Plain 조회 (CHNG_DT 없음) ─────────────────────────────────
        p(f"\n[A] Plain 조회 — CHNG_DT 파라미터 없음")
        p(f"{'─'*72}")
        p(f"{'페이지':>6}  {'범위':<14} {'tc':>7} {'반환':>6}  {'첫BSSH_NM':<25} {'첫CHNG_DT'}")
        p(f"{'─'*72}")

        for pn, (s, e) in enumerate(pages, 1):
            r = fetch(client, api_key, s, e)
            plain_rows.extend(r["rows"])
            fn = (r["rows"][0].get("BSSH_NM","") if r["rows"] else "")[:23]
            fc = (r["rows"][0].get("CHNG_DT","") if r["rows"] else "")
            p(f"  {pn:>4}  {s:>6}~{e:<6}  {str(r['tc']):>7} {r['ret']:>6}  {fn:<25} {fc}")
            time.sleep(GAP)

        # ── B. Filtered 조회 (CHNG_DT=오늘) ──────────────────────────────
        p(f"\n[B] Filtered 조회 — CHNG_DT={today}")
        p(f"{'─'*72}")
        p(f"{'페이지':>6}  {'범위':<14} {'tc':>7} {'반환':>6}  {'첫BSSH_NM':<25} {'첫CHNG_DT'}")
        p(f"{'─'*72}")

        for pn, (s, e) in enumerate(pages, 1):
            r = fetch(client, api_key, s, e, extra=f"CHNG_DT={today}")
            filtered_rows.extend(r["rows"])
            fn = (r["rows"][0].get("BSSH_NM","") if r["rows"] else "")[:23]
            fc = (r["rows"][0].get("CHNG_DT","") if r["rows"] else "")
            p(f"  {pn:>4}  {s:>6}~{e:<6}  {str(r['tc']):>7} {r['ret']:>6}  {fn:<25} {fc}")
            time.sleep(GAP)

        # ── C. 어제 날짜 Filtered 조회 (비교용) ──────────────────────────
        p(f"\n[C] Filtered 조회 — CHNG_DT={yesterday} (비교용)")
        p(f"{'─'*72}")
        yest_rows = []
        for pn, (s, e) in enumerate(pages[:2], 1):  # 2페이지만
            r = fetch(client, api_key, s, e, extra=f"CHNG_DT={yesterday}")
            yest_rows.extend(r["rows"])
            fn = (r["rows"][0].get("BSSH_NM","") if r["rows"] else "")[:23]
            fc = (r["rows"][0].get("CHNG_DT","") if r["rows"] else "")
            p(f"  페이지{pn}  {s}~{e}: tc={r['tc']}, 반환={r['ret']}  첫레코드: {fn} ({fc})")
            time.sleep(GAP)

    # ── D. 비교 분석 ──────────────────────────────────────────────────────
    p(f"\n{'─'*72}")
    p(f"[D] 비교 분석: Plain vs CHNG_DT={today}")
    p(f"{'─'*72}")

    plain_lcns    = set(r.get("LCNS_NO","") for r in plain_rows)
    filtered_lcns = set(r.get("LCNS_NO","") for r in filtered_rows)
    yest_lcns     = set(r.get("LCNS_NO","") for r in yest_rows)

    inter    = plain_lcns & filtered_lcns
    plain_only    = plain_lcns - filtered_lcns
    filtered_only = filtered_lcns - plain_lcns

    p(f"\n  Plain    : {len(plain_rows)}건 ({len(plain_lcns)}개 고유 LCNS_NO)")
    p(f"  Filtered : {len(filtered_rows)}건 ({len(filtered_lcns)}개 고유 LCNS_NO)")
    p(f"\n  교집합   : {len(inter)}개 LCNS_NO")
    p(f"  Plain만  : {len(plain_only)}개 LCNS_NO  ← filtered에 없는 것")
    p(f"  Filter만 : {len(filtered_only)}개 LCNS_NO ← plain에 없는 것")
    p(f"\n  데이터 완전 일치 여부: {'✅ 완전 동일' if not plain_only and not filtered_only else '🔴 다름!'}")

    if plain_only:
        p(f"\n  ★ Plain에만 있는 LCNS_NO (CHNG_DT 필터로 제외된 것):")
        for lcns in list(plain_only)[:10]:
            rec = next((r for r in plain_rows if r.get("LCNS_NO")==lcns), {})
            p(f"    {lcns}  {rec.get('BSSH_NM',''):<20} CHNG_DT={rec.get('CHNG_DT','')}")

    if filtered_only:
        p(f"\n  ★ Filter에만 있는 LCNS_NO (plain에 없는 것):")
        for lcns in list(filtered_only)[:10]:
            rec = next((r for r in filtered_rows if r.get("LCNS_NO")==lcns), {})
            p(f"    {lcns}  {rec.get('BSSH_NM',''):<20} CHNG_DT={rec.get('CHNG_DT','')}")

    # 순서 비교: 첫 20개 LCNS_NO 순서 일치하는가?
    plain_order    = [r.get("LCNS_NO","") for r in plain_rows[:20]]
    filtered_order = [r.get("LCNS_NO","") for r in filtered_rows[:20]]
    order_match = sum(1 for a, b in zip(plain_order, filtered_order) if a == b)
    p(f"\n  첫 20개 LCNS_NO 순서 일치: {order_match}/20")
    p(f"  {'─'*50}")
    p(f"  {'순위':>4}  {'Plain LCNS_NO':<16} {'Filtered LCNS_NO':<16} {'일치?'}")
    for i, (a, b) in enumerate(zip(plain_order, filtered_order), 1):
        ok = "✅" if a == b else "❌"
        p(f"  {i:>4}  {a:<16} {b:<16} {ok}")

    # CHNG_DT 분포 비교
    p(f"\n  [CHNG_DT 분포 비교]")
    for label, rows in [("Plain", plain_rows), (f"CHNG_DT={today}", filtered_rows)]:
        chng_cnts = collections.Counter(r.get("CHNG_DT","")[:7] for r in rows if r.get("CHNG_DT"))
        top = sorted(chng_cnts.items(), key=lambda x: -x[1])[:8]
        p(f"  {label}: " + ", ".join(f"{k}:{v}" for k,v in top))

    # ── 결론 ──────────────────────────────────────────────────────────────
    p(f"\n{'='*72}")
    p(f"  [결론]")
    p(f"{'='*72}")
    if len(inter) == len(plain_lcns) == len(filtered_lcns):
        p(f"""
  ✅ Plain과 Filtered 데이터는 완전히 동일한 LCNS_NO 집합.
  → CHNG_DT 파라미터는 데이터 풀(pool)을 바꾸지 않음.
  → 단순히 해당 날짜 이후 CHNG_DT 필드를 가진 레코드 필터링.
  → 정렬 기준도 동일 (BSSH_NM ASC 기반).
""")
    else:
        p(f"""
  🔴 Plain과 Filtered 데이터가 다름.
  → CHNG_DT 파라미터는 단순 필터 이상의 역할을 함.
  → 가능성 1: CHNG_DT가 인덱스/View 선택 기준으로 사용됨
  → 가능성 2: 서로 다른 테이블/뷰를 조회함
  → 가능성 3: CHNG_DT ≥ 파라미터 조건으로 레코드 필터링 후
              별도 OFFSET/LIMIT 적용 → 순서 및 내용 달라짐
""")

    # ── 보고서 저장 ────────────────────────────────────────────────────────
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("# 실험2 보고서 — CHNG_DT 필터 비교 분석\n\n")
        f.write(f"> 실행 시각: {now.strftime('%Y-%m-%d %H:%M:%S')} | 오늘: {today}\n\n")
        f.write("## 실험 목적\n\n")
        f.write("CHNG_DT 파라미터가 단순 필터인지 아니면 데이터 풀 자체를 바꾸는지 규명.\n")
        f.write("`1/5000 plain` 과 `1/5000/CHNG_DT=오늘` 결과 비교.\n\n")
        f.write("## 실험 결과\n\n```\n")
        f.write("\n".join(lines))
        f.write("\n```\n\n")
        f.write("## 다음 실험 제안\n\n")
        f.write("- CHNG_DT 파라미터를 어제/그제로 설정하여 포함 범위 확인\n")
        f.write("- filtered 결과에서 CHNG_DT < today인 레코드가 있는지 확인\n")
        f.write("- (있다면) CHNG_DT 파라미터는 시작 날짜 기준 이후 전체 필터\n")

    p(f"\n  📄 보고서 저장 완료: {REPORT_PATH}")
    p("=" * 72)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--key", required=True)
    args = parser.parse_args()
    run(args.key)
