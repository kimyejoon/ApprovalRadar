"""
experiments/exp1b_total_count_across_range.py — 전 구간 total_count 표본 실험

★ 핵심 질문:
  같은 크기의 구간(예: 1000건짜리)을 DB 전체에 걸쳐 다른 위치에서 조회할 때
  total_count가 동일한가, 다른가?

  - 동일 → total_count = 전체 테이블 COUNT(*) (조건/위치 무관)
  - 다름 → total_count = WHERE row_id BETWEEN start AND end COUNT (가설 B)

구간 설계 (전체 ~900,000):
  - 동일 크기(1000건) 구간을 균등 간격으로 샘플링
  - 추가: 크기를 바꿔서도 실험 (10, 100, 1000, 10000)

실행:
    python experiments/exp1b_total_count_across_range.py --key YOUR_KEY
"""
import sys, os, time, json, argparse, datetime
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import httpx
from db.schema import get_conn, LAB_DB

BASE_URL = "http://openapi.foodsafetykorea.go.kr/api"
SERVICE_ID = "I2861"


def fetch(client, key, start, end, timeout=45) -> dict:
    url = f"{BASE_URL}/{key}/{SERVICE_ID}/json/{start}/{end}"
    t0 = time.time()
    try:
        resp = client.get(url, timeout=timeout)
        ms = int((time.time() - t0) * 1000)
        data = resp.json()
        block = data.get(SERVICE_ID, {})
        code = block.get("RESULT", {}).get("CODE", "?")
        tc_raw = block.get("total_count", None)
        try:
            tc = int(tc_raw) if tc_raw is not None else None
        except (ValueError, TypeError):
            tc = None
        rows = block.get("row", [])
        first_chng = rows[0].get("CHNG_DT", "") if rows else ""
        first_nm = rows[0].get("BSSH_NM", "") if rows else ""
        last_chng = rows[-1].get("CHNG_DT", "") if rows else ""
        return {
            "code": code, "total_count": tc, "returned": len(rows),
            "ms": ms, "first_chng_dt": first_chng, "last_chng_dt": last_chng,
            "first_nm": first_nm,
        }
    except Exception as e:
        ms = int((time.time() - t0) * 1000)
        return {"code": "ERR", "total_count": None, "returned": 0, "ms": ms,
                "first_chng_dt": "", "last_chng_dt": "", "first_nm": "", "error": str(e)}


def run(api_key: str):
    today = datetime.date.today().strftime("%Y%m%d")
    print("=" * 75)
    print(f"  Exp-1B: 전 구간(~900,000) total_count 표본 실험")
    print(f"  시각: {datetime.datetime.now().strftime('%H:%M:%S')}  |  오늘: {today}")
    print("=" * 75)

    TOTAL_DB_MAX = 953000  # 이전 실험에서 확인된 대략적 DB 크기
    PAGE_SIZE = 1000       # 구간 크기 고정

    results = []

    with httpx.Client(follow_redirects=True, headers={"Accept": "application/json"}) as client:

        # ── Phase A: 동일 크기(1000) 구간을 전체에 걸쳐 균등 샘플링 ──────────────
        # 약 20개 표본 → 구간별 total_count 비교
        print(f"\n{'─'*75}")
        print(f"  [Phase A] 동일 크기(1000건) 구간 균등 샘플링 — 위치별 total_count 비교")
        print(f"  (핵심: total_count가 위치마다 다르면 가설 B 확증)")
        print(f"{'─'*75}")
        print(f"  {'start':>8} {'end':>8} {'size':>6} {'total_count':>12} {'반환':>6} {'코드':>8} {'ms':>6}  {'첫레코드_CHNG_DT'}")
        print(f"  {'─'*72}")

        # 0~TOTAL_DB_MAX 균등 간격 20개 표본
        sample_starts = [
            1,        # 맨 앞
            50001,
            100001,
            150001,
            200001,
            250001,
            300001,
            350001,
            400001,
            450001,
            500001,
            550001,
            600001,
            650001,
            700001,
            750001,
            800001,
            850001,
            900001,
            952001,   # 맨 끝 근처
        ]

        for s in sample_starts:
            e = s + PAGE_SIZE - 1
            r = fetch(client, api_key, s, e)
            results.append({"start": s, "end": e, "phase": "A", **r})
            marker = ""
            if r["code"] == "INFO-200":
                marker = "← 데이터 없음"
            elif r["code"] == "ERR":
                marker = f"← 오류: {r.get('error','')[:20]}"
            print(f"  {s:>8} {e:>8} {PAGE_SIZE:>6} {str(r['total_count']):>12} {r['returned']:>6} {r['code']:>8} {r['ms']:>6}  {r['first_chng_dt']} {marker}")
            time.sleep(0.5)

        # ── Phase B: 다양한 크기 구간, 동일 시작점들 ─────────────────────────────
        print(f"\n{'─'*75}")
        print(f"  [Phase B] 동일 시작점 3곳 × 다양한 구간 크기 — 크기별 total_count 비교")
        print(f"{'─'*75}")
        print(f"  {'start':>8} {'end':>8} {'size':>6} {'total_count':>12} {'반환':>6} {'코드':>8} {'ms':>6}")
        print(f"  {'─'*60}")

        # 앞/중간/뒤 3곳
        anchor_points = [1, 300001, 700001]
        sizes = [1, 10, 100, 1000, 5000, 10000]

        for anchor in anchor_points:
            print(f"\n  ── anchor={anchor:,} ──")
            for size in sizes:
                s, e = anchor, anchor + size - 1
                r = fetch(client, api_key, s, e)
                results.append({"start": s, "end": e, "phase": "B", "size": size, **r})
                print(f"  {s:>8} {e:>8} {size:>6} {str(r['total_count']):>12} {r['returned']:>6} {r['code']:>8} {r['ms']:>6}")
                time.sleep(0.5)

        # ── Phase C: 역방향 — 큰 번호에서 작은 번호 ─────────────────────────────
        print(f"\n{'─'*75}")
        print(f"  [Phase C] end=start+1000으로 고정, start를 뒤에서 앞으로")
        print(f"  (데이터가 없어지는 지점 = 실제 DB 레코드 끝 지점 탐색)")
        print(f"{'─'*75}")
        print(f"  {'start':>8} {'end':>8} {'total_count':>12} {'반환':>6} {'코드':>8} {'ms':>6}  {'마지막레코드_CHNG_DT'}")
        print(f"  {'─'*72}")

        boundary_tests = [940001, 945001, 948001, 950001, 951001, 952001, 953001, 954001, 955001, 960001]
        for s in boundary_tests:
            e = s + PAGE_SIZE - 1
            r = fetch(client, api_key, s, e)
            results.append({"start": s, "end": e, "phase": "C", **r})
            print(f"  {s:>8} {e:>8} {str(r['total_count']):>12} {r['returned']:>6} {r['code']:>8} {r['ms']:>6}  {r['last_chng_dt']}")
            time.sleep(0.5)

    # ── 전체 분석 ─────────────────────────────────────────────────────────────
    print(f"\n{'─'*75}")
    print(f"  ★ 핵심 분석: total_count 값 분포")
    print(f"{'─'*75}")

    phase_a = [r for r in results if r["phase"] == "A" and r["total_count"] is not None]
    if phase_a:
        tc_values = [r["total_count"] for r in phase_a]
        unique_tcs = sorted(set(tc_values))
        print(f"\n  [Phase A] 위치별 total_count:")
        print(f"    unique 값 수: {len(unique_tcs)}")
        print(f"    값 목록: {unique_tcs}")
        if len(unique_tcs) == 1:
            print(f"    → ✅ 모든 구간 동일 ({unique_tcs[0]:,}) — 전체 COUNT(*) 확정")
        else:
            print(f"    → 🔴 구간마다 다름! min={min(tc_values):,} max={max(tc_values):,}")
            print(f"       가설 B (rowid BETWEEN COUNT) 또는 다른 위치 의존 메커니즘")
            # 패턴 분석
            print(f"\n  위치-total_count 상관:")
            for r in phase_a:
                bar = "█" * min(r["total_count"] // 50000, 30)
                print(f"    start={r['start']:>8}: tc={r['total_count']:>8}  {bar}")

    # Phase B — 크기별 변화
    print(f"\n  [Phase B] 크기별 total_count (같은 anchor, 다른 size):")
    for anchor in [1, 300001, 700001]:
        phase_b_anchor = [r for r in results if r["phase"] == "B" and r["start"] == anchor and r["total_count"] is not None]
        if phase_b_anchor:
            tc_vals = [r["total_count"] for r in phase_b_anchor]
            sizes = [r["size"] for r in phase_b_anchor]
            print(f"    anchor={anchor:,}: tc={tc_vals} (size={sizes})")
            if len(set(tc_vals)) == 1:
                print(f"      → 크기 무관 동일")
            else:
                print(f"      → 🔴 크기에 따라 다름!")

    # 결론
    print(f"\n{'='*75}")
    print(f"  결론")
    print(f"{'='*75}")
    all_tc = [r["total_count"] for r in results if r["total_count"] is not None]
    if all_tc:
        if len(set(all_tc)) == 1:
            print(f"  total_count = 고정값 {all_tc[0]:,} → 전체 테이블 COUNT(*)")
            print(f"  (단, 이 값이 실제 전체 레코드 수인지는 별도 확인 필요)")
        else:
            print(f"  total_count가 구간/크기에 따라 다름:")
            for uv in sorted(set(all_tc)):
                cnt = all_tc.count(uv)
                print(f"    {uv:>10,} → {cnt}회 등장")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--key", required=True, help="API 키")
    args = parser.parse_args()
    run(args.key)
