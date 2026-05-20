"""
experiments/exp_view_ab_deep.py — View A vs View B 심층 비교

[실험 1] tc 추이 비교: plain vs aa=2, 여러 구간×여러 범위
[실험 2] 업종(INDUTY_CD_NM) 분포 비교 — tc 차이 원인 추적
[실험 3] tc(B, size=작은값) — View B에서도 동일한 size→tc 함수인가?
[실험 4] View A에서 실제로 무엇이 제거되는가 — 오늘 이외 다른 필터도 있는가?
[실험 5] 같은 LCNS_NO가 두 View에서 동일한 데이터를 가지는가?
"""
import sys, os, time, json, datetime, argparse, collections
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import httpx

BASE_URL = "http://openapi.foodsafetykorea.go.kr/api"
SVC = "I2861"
REPORT_PATH = os.path.join(os.path.dirname(__file__), "report_view_ab_deep.md")
GAP = 0.45


def fetch(client, key, start, end, sixth="", timeout=60, retries=3):
    url = f"{BASE_URL}/{key}/{SVC}/json/{start}/{end}"
    if sixth:
        url += f"/{sixth}"
    for attempt in range(retries):
        try:
            resp = client.get(url, timeout=timeout)
            data = resp.json()
            block = data.get(SVC, {})
            code = block.get("RESULT", {}).get("CODE", "?")
            tc_raw = block.get("total_count")
            tc = int(tc_raw) if tc_raw not in (None, "", "null") else None
            rows = block.get("row", [])
            return {"code": code, "tc": tc, "ret": len(rows), "rows": rows, "ok": True}
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(1.5 * (attempt + 1))
            else:
                return {"code": "ERR", "tc": None, "ret": 0, "rows": [], "ok": False}


def run(api_key):
    now = datetime.datetime.now()
    today = now.strftime("%Y%m%d")
    lines = []

    def p(s=""):
        print(s)
        lines.append(s)

    p("=" * 72)
    p("  View A vs View B 심층 비교")
    p(f"  시각: {now.strftime('%Y-%m-%d %H:%M:%S')} | 오늘: {today}")
    p("=" * 72)

    with httpx.Client(follow_redirects=True, headers={"Accept": "application/json"}) as client:

        # ════════════════════════════════════════════════════════════════
        # 실험 1: tc 추이 비교 (plain vs aa=2, 여러 구간×범위)
        # ════════════════════════════════════════════════════════════════
        p(f"\n{'═'*72}")
        p("  [실험 1] tc 추이 비교 — plain vs aa=2, 여러 구간·범위")
        p("  핵심: tc 차이가 모든 구간에서 일정한가? 비율은 얼마인가?")
        p(f"{'═'*72}")

        anchors = [1, 50001, 150001, 300001, 500001, 700001, 900001]
        sizes   = [100, 500, 1000]

        p(f"\n  {'앵커':>8}  {'size':>5}  {'tc_A(plain)':>12}  {'tc_B(aa=2)':>12}  {'비율B/A':>8}  {'차이':>8}")
        p(f"  {'─'*62}")

        ratios_all = []
        for anchor in anchors:
            for size in sizes:
                end = anchor + size - 1
                ra = fetch(client, api_key, anchor, end)
                time.sleep(GAP)
                rb = fetch(client, api_key, anchor, end, sixth="aa=2")
                time.sleep(GAP)

                tc_a = ra["tc"]
                tc_b = rb["tc"]
                if tc_a and tc_b and tc_a > 0:
                    ratio = tc_b / tc_a
                    diff  = tc_b - tc_a
                    ratios_all.append(ratio)
                    p(f"  {anchor:>8}  {size:>5}  {tc_a:>12}  {tc_b:>12}  {ratio:>8.3f}  {diff:>8}")
                else:
                    p(f"  {anchor:>8}  {size:>5}  {str(tc_a):>12}  {str(tc_b):>12}  {'—':>8}  {'—':>8}")

        if ratios_all:
            avg_r = sum(ratios_all) / len(ratios_all)
            min_r = min(ratios_all)
            max_r = max(ratios_all)
            p(f"\n  ★ 비율 요약: 평균={avg_r:.3f}  최소={min_r:.3f}  최대={max_r:.3f}")
            p(f"     → 비율이 {'일정' if max_r - min_r < 0.5 else '불규칙'}함 (편차={max_r-min_r:.3f})")

        # ════════════════════════════════════════════════════════════════
        # 실험 2: 업종(INDUTY_CD_NM) 분포 비교
        # ════════════════════════════════════════════════════════════════
        p(f"\n{'═'*72}")
        p("  [실험 2] 업종(INDUTY_CD_NM) 분포 비교")
        p("  핵심: tc 3.7배 차이가 업종 필터 때문인가?")
        p(f"{'═'*72}")

        pages = [(1,1000),(1001,2000),(2001,3000),(3001,4000),(4001,5000)]
        rows_a, rows_b = [], []

        p(f"\n  View A 수집 중...")
        for s, e in pages:
            r = fetch(client, api_key, s, e)
            rows_a.extend(r["rows"])
            time.sleep(GAP)

        p(f"  View B 수집 중...")
        for s, e in pages:
            r = fetch(client, api_key, s, e, sixth="aa=2")
            rows_b.extend(r["rows"])
            time.sleep(GAP)

        cnt_a = collections.Counter(row.get("INDUTY_CD_NM", "?") for row in rows_a)
        cnt_b = collections.Counter(row.get("INDUTY_CD_NM", "?") for row in rows_b)
        all_types = sorted(set(cnt_a) | set(cnt_b), key=lambda x: -cnt_a.get(x, 0))

        p(f"\n  {'업종':^20}  {'View A':>8}  {'View B':>8}  {'차이':>8}")
        p(f"  {'─'*50}")
        for t in all_types:
            a = cnt_a.get(t, 0)
            b = cnt_b.get(t, 0)
            p(f"  {t[:20]:^20}  {a:>8}  {b:>8}  {b-a:>+8}")

        p(f"\n  ★ 업종 분포 결론:")
        if set(cnt_a.keys()) == set(cnt_b.keys()):
            p(f"     동일 업종 → 업종 필터는 아님")
        else:
            new_types = set(cnt_b.keys()) - set(cnt_a.keys())
            p(f"     View B에만 있는 업종: {new_types}")
            p(f"     → 업종 필터 가능성 {'있음' if new_types else '없음'}")

        # ════════════════════════════════════════════════════════════════
        # 실험 3: View B에서도 tc = f(size) 동일 함수인가?
        # ════════════════════════════════════════════════════════════════
        p(f"\n{'═'*72}")
        p("  [실험 3] View B에서의 size→tc 관계")
        p("  핵심: View B도 size에만 의존하는 고정 함수인가?")
        p(f"{'═'*72}")

        test_sizes = [1, 2, 5, 10, 20, 50, 100, 200, 500, 1000]
        p(f"\n  {'size':>5}  {'tc_A(1번앵커)':>14}  {'tc_B(1번앵커)':>14}  {'tc_B(500001앵커)':>18}  {'B 일치?':>8}")
        p(f"  {'─'*64}")

        for sz in test_sizes:
            ra = fetch(client, api_key, 1, sz)
            time.sleep(GAP)
            rb1 = fetch(client, api_key, 1, sz, sixth="aa=2")
            time.sleep(GAP)
            rb2 = fetch(client, api_key, 500001, 500000+sz, sixth="aa=2")
            time.sleep(GAP)
            same_b = "✅" if rb1["tc"] is not None and rb1["tc"] == rb2["tc"] else "🔴"
            p(f"  {sz:>5}  {str(ra['tc']):>14}  {str(rb1['tc']):>14}  {str(rb2['tc']):>18}  {same_b:>8}")

        # ════════════════════════════════════════════════════════════════
        # 실험 4: View A가 제거하는 것의 정체 — CHNG_DT 분포 정밀 비교
        # ════════════════════════════════════════════════════════════════
        p(f"\n{'═'*72}")
        p("  [실험 4] View A가 실제로 제거하는 것의 정체")
        p("  핵심: 오늘 날짜 5건만 제거인가? 아니면 다른 기준이 있는가?")
        p(f"{'═'*72}")

        # CHNG_DT 전체 분포 비교
        chng_a = collections.Counter(row.get("CHNG_DT", "")[:8] for row in rows_a if row.get("CHNG_DT"))
        chng_b = collections.Counter(row.get("CHNG_DT", "")[:8] for row in rows_b if row.get("CHNG_DT"))
        all_dates = sorted(set(chng_a) | set(chng_b), reverse=True)[:20]  # 최근 20일

        p(f"\n  {'CHNG_DT':>10}  {'View A':>8}  {'View B':>8}  {'차이':>8}")
        p(f"  {'─'*42}")
        for d in all_dates:
            a = chng_a.get(d, 0)
            b = chng_b.get(d, 0)
            marker = " ← 오늘!" if d == today else ""
            p(f"  {d:>10}  {a:>8}  {b:>8}  {b-a:>+8}{marker}")

        # LCNS_NO 집합 비교
        lcns_a = set(row.get("LCNS_NO","") for row in rows_a)
        lcns_b = set(row.get("LCNS_NO","") for row in rows_b)
        inter = lcns_a & lcns_b
        a_only = lcns_a - lcns_b
        b_only = lcns_b - lcns_a

        p(f"\n  LCNS_NO 집합 비교 (5000건 기준):")
        p(f"    View A 고유: {len(lcns_a)}개")
        p(f"    View B 고유: {len(lcns_b)}개")
        p(f"    교집합: {len(inter)}개 ({len(inter)/len(lcns_a)*100:.1f}%)")
        p(f"    A만: {len(a_only)}개  |  B만: {len(b_only)}개")

        # A에만 있는 LCNS의 CHNG_DT 분포
        if a_only:
            rows_a_only = [r for r in rows_a if r.get("LCNS_NO") in a_only]
            a_only_chng = collections.Counter(r.get("CHNG_DT","")[:8] for r in rows_a_only)
            p(f"\n  A에만 있는 {len(a_only)}개 LCNS의 CHNG_DT 분포:")
            for dt, cnt in sorted(a_only_chng.items(), reverse=True)[:5]:
                p(f"    {dt}: {cnt}건")

        # B에만 있는 LCNS의 CHNG_DT 분포
        if b_only:
            rows_b_only = [r for r in rows_b if r.get("LCNS_NO") in b_only]
            b_only_chng = collections.Counter(r.get("CHNG_DT","")[:8] for r in rows_b_only)
            p(f"\n  B에만 있는 {len(b_only)}개 LCNS의 CHNG_DT 분포:")
            for dt, cnt in sorted(b_only_chng.items(), reverse=True)[:5]:
                p(f"    {dt}: {cnt}건")

        # ════════════════════════════════════════════════════════════════
        # 실험 5: 동일 LCNS_NO의 데이터가 두 View에서 같은가?
        # ════════════════════════════════════════════════════════════════
        p(f"\n{'═'*72}")
        p("  [실험 5] 동일 LCNS_NO — 두 View에서 데이터 일치 확인")
        p("  핵심: View B가 View A의 완전한 상위집합인가?")
        p(f"{'═'*72}")

        # 교집합에서 10개 샘플링 확인
        sample_lcns = list(inter)[:10]
        rows_a_map = {r.get("LCNS_NO",""): r for r in rows_a}
        rows_b_map = {r.get("LCNS_NO",""): r for r in rows_b}

        mismatch_count = 0
        p(f"\n  {'LCNS_NO':<14} {'View A CHNG_DT':>16} {'View B CHNG_DT':>16} {'일치?':>6}")
        p(f"  {'─'*60}")
        for lcns in sample_lcns:
            ra_row = rows_a_map.get(lcns, {})
            rb_row = rows_b_map.get(lcns, {})
            a_dt = ra_row.get("CHNG_DT","?")
            b_dt = rb_row.get("CHNG_DT","?")
            match = "✅" if a_dt == b_dt else "🔴"
            if a_dt != b_dt:
                mismatch_count += 1
            p(f"  {lcns:<14} {a_dt:>16} {b_dt:>16} {match:>6}")

        p(f"\n  ★ 동일 LCNS의 데이터 일치율: {len(sample_lcns)-mismatch_count}/{len(sample_lcns)}")

        # ════════════════════════════════════════════════════════════════
        # 최종 가설 정리
        # ════════════════════════════════════════════════════════════════
        p(f"\n{'═'*72}")
        p("  [최종 분석] 가설 검증 결과")
        p(f"{'═'*72}")

        today_in_b = sum(1 for r in rows_b if r.get("CHNG_DT","") == today)
        today_in_a = sum(1 for r in rows_a if r.get("CHNG_DT","") == today)
        tc_diff = 4870 - 1307

        p(f"""
  수집된 증거:
  - View A tc=1307 vs View B tc=4870 → 차이 {tc_diff}
  - 오늘 날짜 레코드: View A={today_in_a}건, View B={today_in_b}건
  - 두 View의 5000건 CHNG_DT 분포: {"거의 동일" if sum(abs(chng_b.get(d,0)-chng_a.get(d,0)) for d in all_dates) < 50 else "다름"}
  - 업종 분포: {"동일" if set(cnt_a.keys()) == set(cnt_b.keys()) else "다름"}
  - LCNS_NO 교집합: {len(inter)}/{len(lcns_a)} ({len(inter)/len(lcns_a)*100:.1f}%)

  tc 차이 {tc_diff} 설명 시도:
  - 오늘 날짜로만 설명: {today_in_b}건 (전혀 설명 안 됨)
  - 업종 필터로 설명: {"가능" if set(cnt_a.keys()) != set(cnt_b.keys()) else "불가 (업종 동일)"}
  - tc 자체가 실제 레코드 수가 아님 → View별로 다른 계산식 사용 가능

  가장 합리적 가설:
  ─ View A와 View B는 동일한 기반 데이터에서
    서로 다른 tc 계산식을 사용하거나
    DB의 서로 다른 물리 파티션을 봄
  ─ "오늘 날짜만 제거"가 아닐 가능성 높음
  ─ tc 차이는 레코드 수 차이가 아닌 View별 산출 방식 차이
""")

    # 보고서 저장
    md = f"""# View A vs View B 심층 비교 보고서

> 실행 시각: {now.strftime('%Y-%m-%d %H:%M:%S')} | 오늘: {today}

## 핵심 질문

`tc(ViewA)=1307` vs `tc(ViewB)=4870` — 3.7배 차이의 원인은?  
"View A = View B에서 오늘 날짜만 제거"는 성립하는가?

## 실험 로그

```
{chr(10).join(lines)}
```
"""
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write(md)
    p(f"\n  📄 보고서: {REPORT_PATH}")
    p("=" * 72)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--key", required=True)
    args = parser.parse_args()
    run(args.key)
