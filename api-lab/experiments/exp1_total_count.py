"""
experiments/exp1_total_count.py — total_count 정체 규명

다양한 start/end 조합으로 API를 직접 호출하여
total_count 계산 방식을 역추적한다.

실행:
    python experiments/exp1_total_count.py --key YOUR_KEY
"""
import sys, os, time, json, argparse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import httpx
from db.schema import get_conn, LAB_DB

BASE_URL = "http://openapi.foodsafetykorea.go.kr/api"

def fetch(client, key, start, end, extra=None, timeout=30):
    url = f"{BASE_URL}/{key}/I2861/json/{start}/{end}"
    if extra:
        url += "/" + "&".join(f"{k}={v}" for k, v in extra.items())
    t0 = time.time()
    try:
        resp = client.get(url, timeout=timeout)
        ms = int((time.time()-t0)*1000)
        data = resp.json()
        block = data.get("I2861", {})
        code = block.get("RESULT", {}).get("CODE", "?")
        tc = block.get("total_count", "?")
        rows = block.get("row", [])
        return {"code": code, "total_count": tc, "returned": len(rows), "ms": ms, "rows": rows}
    except Exception as e:
        ms = int((time.time()-t0)*1000)
        return {"code": "ERR", "total_count": "?", "returned": 0, "ms": ms, "rows": [], "error": str(e)}


def run(api_key):
    print("=" * 65)
    print("  Exp-1: total_count 정체 규명")
    print("=" * 65)

    with httpx.Client(follow_redirects=True) as client:

        # ── Phase 1: start/end 범위 변화 ──────────────────────────────
        print(f"\n  [Phase 1] start=1 고정, end만 변화")
        print(f"  {'start':>8} {'end':>10} {'total_count':>12} {'반환':>6} {'응답':>6}ms")
        print(f"  {'─'*55}")

        tests_1 = [
            (1, 1), (1, 5), (1, 10), (1, 100), (1, 500),
            (1, 1000), (1, 2000), (1, 5000), (1, 10000), (1, 999999),
        ]
        prev_tc = None
        for s, e in tests_1:
            r = fetch(client, api_key, s, e)
            tc_changed = "★변화!" if prev_tc and r["total_count"] != prev_tc else ""
            print(f"  {s:>8} {e:>10} {str(r['total_count']):>12} {r['returned']:>6} {r['ms']:>6} {tc_changed}")
            prev_tc = r["total_count"]
            time.sleep(0.4)

        # ── Phase 2: end=1 고정, start만 변화 ─────────────────────────
        print(f"\n  [Phase 2] end=1 고정, start만 변화 (GAP 검출)")
        print(f"  {'start':>8} {'end':>10} {'total_count':>12} {'반환':>6} {'응답':>6}ms")
        print(f"  {'─'*55}")

        tests_2 = [(1,1),(100,100),(500,500),(1000,1000),(1307,1307),(1308,1308),(2000,2000),(5000,5000)]
        for s, e in tests_2:
            r = fetch(client, api_key, s, e)
            print(f"  {s:>8} {e:>10} {str(r['total_count']):>12} {r['returned']:>6} {r['ms']:>6}")
            time.sleep(0.4)

        # ── Phase 3: 첫 레코드 고정 비교 ─────────────────────────────
        print(f"\n  [Phase 3] 1/1 vs 1/10 vs 1/1000 — 첫 번째 레코드 동일한가?")
        first_records = {}
        for s, e in [(1,1),(1,10),(1,100),(1,1000)]:
            r = fetch(client, api_key, s, e)
            rows = r["rows"]
            first = rows[0] if rows else {}
            first_records[f"{s}/{e}"] = first
            print(f"\n  {s}/{e} → 첫번째: {first.get('BSSH_NM','?')} | CHNG_DT={first.get('CHNG_DT','?')} | LCNS={first.get('LCNS_NO','?')}")
            time.sleep(0.4)

        # 첫 번째 레코드 일치 여부
        all_same = len(set(v.get("LCNS_NO","") for v in first_records.values())) == 1
        print(f"\n  → 첫 번째 레코드 LCNS_NO 전부 동일? {'✅ 예' if all_same else '❌ 아니오 (정렬이 페이지크기에 따라 달라짐!)'}")

        # ── Phase 4: CHNG_DT 파라미터 추가 시 total_count ─────────────
        print(f"\n  [Phase 4] CHNG_DT 파라미터 추가 시 total_count 변화")
        print(f"  {'CHNG_DT':>12} {'total_count':>12} {'반환':>6}")
        print(f"  {'─'*40}")

        import datetime
        today = datetime.date.today()
        chng_tests = [
            ("20200101", "2020이후 전체"),
            ("20240101", "2024이후"),
            ("20250101", "2025이후"),
            ("20260101", "2026이후"),
            ("20260501", "2026-05이후"),
            (today.strftime("%Y%m%d"), "오늘"),
            ((today - datetime.timedelta(days=1)).strftime("%Y%m%d"), "어제"),
        ]
        for dt, label in chng_tests:
            r = fetch(client, api_key, 1, 1000, extra={"CHNG_DT": dt})
            print(f"  {dt:>12} ({label:12s}) → total={str(r['total_count']):>8} 반환={r['returned']:>5}")
            time.sleep(0.4)

        # ── Phase 5: 역순 접근 — 끝 페이지 ───────────────────────────
        print(f"\n  [Phase 5] 큰 번호 접근 — DB 실제 크기 탐색")
        for s, e in [(50000,51000),(100000,101000),(500000,501000),(950000,951000),(953001,954000)]:
            r = fetch(client, api_key, s, e)
            print(f"  {s:>8}~{e:<8} → total={str(r['total_count']):>8} 반환={r['returned']:>5} code={r['code']}")
            time.sleep(0.5)

    print(f"\n{'='*65}")
    print("  실험 완료 — 결과로 total_count 정체를 판별하세요")
    print("=" * 65)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--key", required=True)
    args = parser.parse_args()
    run(args.key)
