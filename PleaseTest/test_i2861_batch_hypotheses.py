"""
I2861 집합 조회 가능성 테스트 v5 - BSSH_NM 심화 + 복합 필터
발견: BSSH_NM 부분 매칭 가능! 이를 더 깊이 파고든다.

테스트 목표:
1. BSSH_NM + LCNS_NO 복합 필터 → 교차 검증 가능한가?
2. BSSH_NM 결과가 CHNG_DT 포함인지? (날짜 필터링에 활용 가능한지)
3. BSSH_NM 1글자 vs 2글자 → 그룹 크기 비교
4. SITE_ADDR (주소) 필터 가능성
5. CHNG_PRVNS 필터 가능성
6. 이름 앞 2글자 기준 배치 전략 실현 가능성 추정
"""
import requests
from collections import defaultdict

API_KEY = "c4d13100b0ba4cbb8813"
BASE = f"http://openapi.foodsafetykorea.go.kr/api/{API_KEY}/I2861/json"

def fetch_all_pages(url_template, max_pages=5):
    """전체 페이지 수집 (max_pages 제한)"""
    results = []
    total = None
    for p in range(1, max_pages + 1):
        start = (p-1)*1000 + 1
        end   = p * 1000
        url = url_template.format(start=start, end=end)
        try:
            r = requests.get(url, timeout=20)
            d = r.json()
            svc = d.get("I2861", {})
            if total is None:
                total = svc.get("total_count", "?")
            rows = svc.get("row", [])
            code = svc.get("RESULT", {}).get("CODE", "?")
            results.extend(rows)
            if code == "INFO-300" or not rows:
                break
        except Exception as e:
            print(f"  오류: {e}")
            break
    return results, total

def fetch_one(param_str, start=1, end=20):
    url = f"{BASE}/{start}/{end}/{param_str}"
    print(f"  URL: .../{param_str}")
    try:
        r = requests.get(url, timeout=20)
        d = r.json()
        svc = d.get("I2861", {})
        total = svc.get("total_count","")
        rows  = svc.get("row",[])
        code  = svc.get("RESULT",{}).get("CODE","?")
        return {"total": total, "rows_count": len(rows), "code": code, "rows": rows}
    except Exception as e:
        return {"error": str(e)}

def show(res, show_rows=3):
    if not res: return
    if res.get("error"): print(f"  오류: {res['error']}"); return
    print(f"  code={res['code']} | total={res['total']} | rows_returned={res['rows_count']}")
    for r in res["rows"][:show_rows]:
        print(f"  -> {r.get('LCNS_NO')} | {r.get('BSSH_NM')} | CHNG_DT={r.get('CHNG_DT')} | CHNG_PRVNS={r.get('CHNG_PRVNS')}")

S = "=" * 65

# ─── TEST 1: BSSH_NM + LCNS_NO 복합 필터 ────────────────────────────────
print(S)
print("[T1] BSSH_NM + LCNS_NO 복합 필터 (찐따포차 + 20200094867)")
res = fetch_one("BSSH_NM=찐따포차&LCNS_NO=20200094867", end=10)
show(res)

# ─── TEST 2: BSSH_NM 단독으로 찐따포차 ────────────────────────────────
# --- TEST 2: BSSH_NM 단독으로 찐따포차 --------------------------------
print(S)
print("[T2] BSSH_NM=찐따포차 단독 (동명이업 확인)")
res = fetch_one("BSSH_NM=찐따포차", end=20)
show(res, show_rows=5)
if res and res.get("rows"):
    lcns_set = {r["LCNS_NO"] for r in res["rows"]}
    print(f"  => LCNS_NO: {len(lcns_set)}개 -> {lcns_set}")

# --- TEST 3: BSSH_NM 결과의 CHNG_DT 분포 분석 (스타벅스) -----------------------------
print(S)
print("[T3] BSSH_NM=스타벅스 전체 (CHNG_DT 분포 분석)")
res = fetch_one("BSSH_NM=스타벅스", start=1, end=50)
show(res, show_rows=0)
if res and res.get("rows"):
    date_dist = defaultdict(int)
    for r in res["rows"]:
        dt = r.get("CHNG_DT", "unknown")[:6]  # YYYYMM
        date_dist[dt] += 1
    print(f"  CHNG_DT 분포 (YYYYMM): {dict(sorted(date_dist.items(), reverse=True)[:10])}")
    lcns_set = {r["LCNS_NO"] for r in res["rows"]}
    print(f"  고유 LCNS_NO: {len(lcns_set)}개")

# ─── TEST 4: 글자 수별 그룹 크기 비교 ────────────────────────────────────
print(S)
print("[T4] BSSH_NM 글자 수별 효율 비교 (그룹 크기 = total_count)")
test_names = [
    ("1글자", "스"),
    ("2글자", "스타"),
    ("3글자", "스타벅"),
    ("정확(4글자)", "스타벅스"),
    ("1글자", "찐"),
    ("2글자", "찐따"),
    ("정확", "찐따포차"),
]
for label, nm in test_names:
    res = fetch_one(f"BSSH_NM={nm}", end=5)
    total = res.get("total","?") if res else "ERR"
    code  = res.get("code","?") if res else "ERR"
    print(f"  [{label}] BSSH_NM={nm!r:<10} → total={total}, code={code}")

# ─── TEST 5: SITE_ADDR 필터 ────────────────────────────────────────────
print(S)
print("[T5] SITE_ADDR (주소) 필터 가능성")
res = fetch_one("SITE_ADDR=관악구", end=10)
show(res)

# ─── TEST 6: CHNG_PRVNS (변경사유) 필터 ──────────────────────────────────
print(S)
print("[T6] CHNG_PRVNS=대표자변경 필터")
res = fetch_one("CHNG_PRVNS=대표자변경", end=10)
show(res)

# ─── TEST 7: 핵심 - I2500 후보를 2글자 이름 그룹으로 배치 가능성 ─────────
print(S)
print("[T7] 배치 전략 현실성 추정")
print("  시나리오: I2500 18,000건의 상호명을 앞 2글자 그룹으로 묶기")
print("  → BSSH_NM=XX 로 I2861 조회, total이 작으면 교차 검증 효율적")
sample_prefixes = ["찐따", "스타", "맥도", "이마", "롯데", "편의", "치킨"]
for prefix in sample_prefixes:
    res = fetch_one(f"BSSH_NM={prefix}", end=3)
    total = res.get("total","?") if res else "ERR"
    print(f"  BSSH_NM={prefix!r} → total={total} (I2861 이력 전체)")

print(S)
print("완료")
