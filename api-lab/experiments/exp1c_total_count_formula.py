"""
experiments/exp1c_total_count_formula.py — total_count 공식 완전 규명

[실험 1+2] total_count 함수 도출
  - size를 촘촘하게 (1~1000, 비균등 간격) 모든 구간에서 다중 앵커 테스트
  - 3~6개 앵커 위치 × 20+개 size → 수식 피팅 (선형/로그/지수/멱함수)

[실험 3] CHNG_DT=20260520 필터로 1~5000 5분할 조회
  - 각 페이지 상위 레코드 확인

실행:
    python experiments/exp1c_total_count_formula.py --key YOUR_KEY
"""
import sys, os, time, json, argparse, datetime, math
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import httpx

BASE_URL = "http://openapi.foodsafetykorea.go.kr/api"
SVC = "I2861"
GAP = 0.35  # 페이지 간 대기 (WAF 방지)


def fetch(client, key, start, end, extra_params="", timeout=45):
    url = f"{BASE_URL}/{key}/{SVC}/json/{start}/{end}"
    if extra_params:
        url += f"/{extra_params}"
    t0 = time.time()
    try:
        resp = client.get(url, timeout=timeout)
        ms = int((time.time() - t0) * 1000)
        data = resp.json()
        block = data.get(SVC, {})
        code  = block.get("RESULT", {}).get("CODE", "?")
        tc_raw = block.get("total_count", None)
        tc = int(tc_raw) if tc_raw not in (None, "", "null") else None
        rows = block.get("row", [])
        return {"code": code, "tc": tc, "ret": len(rows), "ms": ms, "rows": rows}
    except Exception as e:
        ms = int((time.time() - t0) * 1000)
        return {"code": "ERR", "tc": None, "ret": 0, "ms": ms, "rows": [], "err": str(e)[:60]}


def run(api_key):
    now_str = datetime.datetime.now().strftime("%H:%M:%S")
    today   = datetime.date.today().strftime("%Y%m%d")
    print("=" * 72)
    print(f"  Exp-1C: total_count 공식 규명 + CHNG_DT 조회 실험")
    print(f"  시각: {now_str}  |  오늘: {today}")
    print("=" * 72)

    # ─── 앵커 위치 ───────────────────────────────────────────────────────────
    ANCHORS = [1, 100001, 300001, 500001, 700001, 900001]

    # ─── 테스트할 size 목록 (1~1000, 촘촘하게) ───────────────────────────────
    SIZES = [
        1, 2, 3, 4, 5, 6, 7, 8, 9, 10,
        12, 15, 18, 20, 25, 30, 35, 40, 50,
        60, 70, 80, 90, 100,
        120, 150, 200, 250, 300, 400, 500,
        600, 700, 800, 900, 1000,
    ]

    # ── Phase 1: size별 × 앵커별 total_count 수집 ───────────────────────────
    print(f"\n{'─'*72}")
    print(f"  [Phase 1] {len(SIZES)}개 size × {len(ANCHORS)}개 앵커 = {len(SIZES)*len(ANCHORS)}회 호출")
    print(f"  목표: total_count = f(size) 수식 도출")
    print(f"{'─'*72}")
    header = f"  {'size':>5}  " + "  ".join(f"a={a//1000 if a>1 else 0}k{'>7'}" for a in ANCHORS)
    print(f"  {'size':>5}", end="")
    for a in ANCHORS:
        label = f"a={a//1000}k" if a > 1 else "a=1"
        print(f"  {label:>7}", end="")
    print(f"  {'일치?':>6}")
    print(f"  {'─'*70}")

    # (size → [tc per anchor]) 수집
    size_tc_map = {}   # size → list of tc values
    all_data = []      # 전체 원시 데이터

    with httpx.Client(follow_redirects=True, headers={"Accept": "application/json"}) as client:

        for size in SIZES:
            tcs = []
            row_str = f"  {size:>5}"
            for anchor in ANCHORS:
                s = anchor
                e = anchor + size - 1
                r = fetch(client, api_key, s, e)
                tc = r["tc"]
                tcs.append(tc)
                tc_str = str(tc) if tc is not None else "ERR"
                row_str += f"  {tc_str:>7}"
                all_data.append({"size": size, "anchor": anchor, "tc": tc, "ret": r["ret"], "code": r["code"]})
                time.sleep(GAP)

            # 앵커 간 일치 여부
            valid_tcs = [t for t in tcs if t is not None]
            all_same = len(set(valid_tcs)) <= 1 if valid_tcs else False
            marker = "✅" if all_same else "🔴 앵커마다 다름!"
            print(row_str + f"  {marker}")
            size_tc_map[size] = valid_tcs

        # ── Phase 2: 수식 피팅 ─────────────────────────────────────────────
        print(f"\n{'─'*72}")
        print(f"  [Phase 2] total_count = f(size) 수식 피팅")
        print(f"{'─'*72}")

        # 대표값 수집 (앵커별 중앙값 사용)
        xy = []  # (size, tc) pairs
        for size, tcs in size_tc_map.items():
            valid = [t for t in tcs if t is not None and t > 0]
            if valid:
                avg_tc = sum(valid) / len(valid)
                xy.append((size, avg_tc))

        if xy:
            xs = [p[0] for p in xy]
            ys = [p[1] for p in xy]

            print(f"\n  수집된 (size, total_count) 쌍: {len(xy)}개")
            print(f"\n  {'size':>6}  {'avg_tc':>10}  {'tc/size':>10}  {'log(size)':>10}  {'tc/log':>10}")
            print(f"  {'─'*58}")
            for x, y in xy[:20]:
                ratio = y / x if x > 0 else 0
                log_x = math.log(x) if x > 0 else 0
                log_ratio = y / log_x if log_x > 0 else 0
                print(f"  {x:>6}  {y:>10.2f}  {ratio:>10.3f}  {log_x:>10.4f}  {log_ratio:>10.2f}")

            # 선형 피팅 시도: tc = a * size + b
            n = len(xs)
            sum_x  = sum(xs)
            sum_y  = sum(ys)
            sum_xy = sum(x*y for x,y in zip(xs,ys))
            sum_xx = sum(x*x for x in xs)
            denom  = n * sum_xx - sum_x**2
            if denom != 0:
                a_lin = (n * sum_xy - sum_x * sum_y) / denom
                b_lin = (sum_y - a_lin * sum_x) / n
                # R² 계산
                y_mean = sum_y / n
                ss_tot = sum((y - y_mean)**2 for y in ys)
                ss_res = sum((y - (a_lin * x + b_lin))**2 for x, y in zip(xs, ys))
                r2_lin = 1 - ss_res / ss_tot if ss_tot > 0 else 0
                print(f"\n  [선형 피팅]  tc ≈ {a_lin:.4f} × size + {b_lin:.2f}  (R²={r2_lin:.4f})")

            # 로그 피팅: tc = a * ln(size) + b
            log_xs = [math.log(x) for x in xs if x > 0]
            log_ys = [y for x, y in zip(xs, ys) if x > 0]
            n2 = len(log_xs)
            if n2 > 1:
                sum_lx  = sum(log_xs)
                sum_ly  = sum(log_ys)
                sum_lxly= sum(lx*ly for lx,ly in zip(log_xs,log_ys))
                sum_lxlx= sum(lx*lx for lx in log_xs)
                denom2  = n2 * sum_lxlx - sum_lx**2
                if denom2 != 0:
                    a_log = (n2 * sum_lxly - sum_lx * sum_ly) / denom2
                    b_log = (sum_ly - a_log * sum_lx) / n2
                    ss_res2 = sum((y - (a_log * lx + b_log))**2 for y, lx in zip(log_ys, log_xs))
                    y2_mean = sum_ly / n2
                    ss_tot2 = sum((y - y2_mean)**2 for y in log_ys)
                    r2_log = 1 - ss_res2 / ss_tot2 if ss_tot2 > 0 else 0
                    print(f"  [로그 피팅]  tc ≈ {a_log:.4f} × ln(size) + {b_log:.2f}  (R²={r2_log:.4f})")

            # 멱함수 피팅: tc = a * size^b → ln(tc) = ln(a) + b*ln(size)
            pow_xy = [(math.log(x), math.log(y)) for x, y in zip(xs, ys) if x > 0 and y > 0]
            if len(pow_xy) > 1:
                lxs = [p[0] for p in pow_xy]
                lys = [p[1] for p in pow_xy]
                np = len(lxs)
                sum_plx  = sum(lxs)
                sum_ply  = sum(lys)
                sum_plxly= sum(lx*ly for lx,ly in zip(lxs,lys))
                sum_plxlx= sum(lx*lx for lx in lxs)
                dp = np * sum_plxlx - sum_plx**2
                if dp != 0:
                    b_pow = (np * sum_plxly - sum_plx * sum_ply) / dp
                    a_pow = math.exp((sum_ply - b_pow * sum_plx) / np)
                    ss_pr = sum((ly - (math.log(a_pow) + b_pow * lx))**2 for ly, lx in zip(lys, lxs))
                    ly_mean = sum_ply / np
                    ss_pt = sum((ly - ly_mean)**2 for ly in lys)
                    r2_pow = 1 - ss_pr / ss_pt if ss_pt > 0 else 0
                    print(f"  [멱함수 피팅] tc ≈ {a_pow:.4f} × size^{b_pow:.4f}  (R²={r2_pow:.4f})")
                    print(f"             → size=1000: 예측={a_pow * 1000**b_pow:.1f}  실제=1307")
                    print(f"             → size=100:  예측={a_pow * 100**b_pow:.1f}   실제=298")
                    print(f"             → size=10:   예측={a_pow * 10**b_pow:.1f}    실제=38")
                    print(f"             → size=1:    예측={a_pow * 1**b_pow:.1f}     실제=8")

                    # 오차 분석
                    known = [(1, 8), (10, 38), (100, 298), (1000, 1307)]
                    print(f"\n  검증 (알려진 값 vs 멱함수 예측):")
                    print(f"  {'size':>6}  {'실제':>8}  {'예측':>8}  {'오차%':>8}")
                    for ks, kt in known:
                        pred = a_pow * ks**b_pow
                        err  = abs(pred - kt) / kt * 100
                        print(f"  {ks:>6}  {kt:>8}  {pred:>8.1f}  {err:>8.1f}%")

        # ── Phase 3: CHNG_DT=오늘 필터로 1~5000 5분할 ───────────────────────
        today_filter = datetime.date.today().strftime("%Y%m%d")
        print(f"\n{'─'*72}")
        print(f"  [Phase 3] CHNG_DT={today_filter} 필터, 1~5000 5분할 조회")
        print(f"  (각 페이지 상위 레코드 분석 — 정렬 기준 재확인)")
        print(f"{'─'*72}")

        pages = [(1,1000), (1001,2000), (2001,3000), (3001,4000), (4001,5000)]

        for s, e in pages:
            r = fetch(client, api_key, s, e, extra_params=f"CHNG_DT={today_filter}")
            rows = r["rows"]
            print(f"\n  ── 페이지 {s}~{e} | total_count={r['tc']} | 반환={r['ret']}건 | code={r['code']} ──")

            if not rows:
                print(f"  (데이터 없음)")
                time.sleep(GAP)
                continue

            print(f"  {'순위':>4}  {'LCNS_NO':<14} {'CHNG_DT':<10} {'BSSH_NM':<22} {'INDUTY_CD_NM'}")
            print(f"  {'─'*72}")
            for i, row in enumerate(rows[:10], 1):
                nm    = (row.get("BSSH_NM") or "")[:20]
                chng  = row.get("CHNG_DT", "")
                lcns  = row.get("LCNS_NO", "")
                ind   = (row.get("INDUTY_CD_NM") or "")[:15]
                print(f"  {i:>4}  {lcns:<14} {chng:<10} {nm:<22} {ind}")

            # 마지막 레코드도 출력 (페이지 끝 패턴 확인)
            if len(rows) > 10:
                print(f"  ...")
                last = rows[-1]
                nm    = (last.get("BSSH_NM") or "")[:20]
                chng  = last.get("CHNG_DT", "")
                lcns  = last.get("LCNS_NO", "")
                print(f"  {len(rows):>4}  {lcns:<14} {chng:<10} {nm:<22} (마지막)")

            # CHNG_DT 분포 요약
            chng_dts = [row.get("CHNG_DT","") for row in rows if row.get("CHNG_DT")]
            if chng_dts:
                unique_dts = sorted(set(chng_dts), reverse=True)
                print(f"\n  CHNG_DT 고유값: {unique_dts[:8]}")
                most_recent = unique_dts[0]
                oldest = unique_dts[-1]
                print(f"  범위: {oldest} ~ {most_recent}")

            time.sleep(GAP)

    print(f"\n{'='*72}")
    print(f"  실험 완료")
    print("=" * 72)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--key", required=True)
    args = parser.parse_args()
    run(args.key)
