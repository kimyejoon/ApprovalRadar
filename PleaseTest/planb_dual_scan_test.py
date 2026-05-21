"""
Plan B: I2861 이중 구간 탐색 실험
======================================================
목적: 단일 1000단위 풀스캔이 놓치는 레코드를 오버랩 방식으로 탐지 가능한지 검증.

이중 사이클 전략:
  사이클 A (현재): 1~1000, 1001~2000, ... (고정 1000단위)
  사이클 B (실험): 500~1500, 1501~2500, ... (500 오프셋 이동)

미탐 의심 업체 예상 위치 (DB 사전순 기준):
  빽보이피자 둔촌점      → 121,265 / 294,443
  미친양꼬치 홍대직영점  →  97,187 / 294,443
  호미스피자 명지대점    → 286,693 / 294,443
  너도나도식당 상암DMC점 →  43,753 / 294,443

주의: API 인덱스 ≠ DB 사전순 위치 (API 총 레코드 ≈ 954,000건)
      API 위치 추정 = DB위치 / 294,443 × 954,000
"""
import httpx
import sqlite3
import asyncio
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

db_path = r"c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\ApprovalRadar-BE\food_safety.db"

conn = sqlite3.connect(db_path)
api_keys = [r[0] for r in conn.execute("SELECT key_value FROM api_keys WHERE is_active = 1").fetchall()]
conn.close()

# 미탐 의심 업체 (이름, DB 사전순 위치, API 추정 위치)
# API 추정 위치 = DB위치 / 294,443 * 954,000 (비율 스케일)
TARGETS = [
    ("빽보이피자 둔촌점",        121265, int(121265 / 294443 * 954000)),
    ("미친양꼬치 홍대직영점",     97187, int(97187  / 294443 * 954000)),
    ("호미스피자 명지대점",       286693, int(286693 / 294443 * 954000)),
    ("너도나도식당 상암DMC점",     43753, int(43753  / 294443 * 954000)),
]

WINDOW = 300   # 각 타깃 위치 전후 탐색 범위 (±300)
API_TOTAL = 954000  # I2861 추정 총 레코드 수

async def find_valid_key(client: httpx.AsyncClient) -> str | None:
    for key in api_keys:
        url = f"http://openapi.foodsafetykorea.go.kr/api/{key}/I2861/json/1/1/SYS_SYNC=LIVE"
        try:
            res = await client.get(url, timeout=5.0)
            js = res.json()
            code = js.get("I2861", {}).get("RESULT", {}).get("CODE", "")
            if code not in ["INFO-300", "INFO-333"]:
                print(f"유효 키 발견: {key[:10]}...")
                return key
        except Exception:
            pass
    return None

async def probe_range(client: httpx.AsyncClient, key: str, start: int, end: int, target_name: str) -> list:
    """지정 범위를 조회하여 target_name을 포함하는 레코드 반환"""
    url = f"http://openapi.foodsafetykorea.go.kr/api/{key}/I2861/json/{start}/{end}/SYS_SYNC=LIVE"
    try:
        res = await client.get(url, timeout=10.0)
        js = res.json().get("I2861", {})
        code = js.get("RESULT", {}).get("CODE", "")
        rows = js.get("row", [])
        matched = [r for r in rows if target_name in r.get("BSSH_NM", "")]
        return code, len(rows), matched
    except Exception as e:
        return "ERROR", 0, []

async def main():
    async with httpx.AsyncClient() as client:
        key = await find_valid_key(client)
        if not key:
            print("❌ 유효한 API 키 없음 — 자정(00:00) 이후 재실행하세요.")
            return

        print(f"\n{'='*70}")
        print("Plan B: I2861 이중 구간 탐색 — 미탐 업체 위치 직접 탐색")
        print(f"{'='*70}")

        for name, db_pos, api_est in TARGETS:
            print(f"\n🎯 대상: '{name}'")
            print(f"   DB 사전순 위치: {db_pos:,} / 294,443")
            print(f"   API 추정 위치:  {api_est:,} / {API_TOTAL:,}")

            # ── 사이클 A 방식 (고정 1000단위 경계 기준 구간)
            # 해당 위치가 속하는 A사이클 구간
            a_start = (api_est // 1000) * 1000 + 1
            a_end   = a_start + 999

            # ── 사이클 B 방식 (500 오프셋 경계 기준 구간)
            b_start = ((api_est - 500) // 1000) * 1000 + 501
            b_end   = b_start + 999

            print(f"\n   [사이클 A] {a_start:,}~{a_end:,} 조회 중...")
            code_a, cnt_a, found_a = await probe_range(client, key, a_start, a_end, name)
            print(f"   → Code: {code_a} | 반환 레코드: {cnt_a}건 | 타깃 발견: {'✅ ' + str(len(found_a)) + '건' if found_a else '❌ 없음'}")
            if found_a:
                for r in found_a:
                    print(f"     └ LCNS:{r.get('LCNS_NO')} CHNG_DT:{r.get('CHNG_DT')} 사유:{r.get('CHNG_PRVNS')}")

            await asyncio.sleep(0.5)

            print(f"\n   [사이클 B] {b_start:,}~{b_end:,} 조회 중...")
            code_b, cnt_b, found_b = await probe_range(client, key, b_start, b_end, name)
            print(f"   → Code: {code_b} | 반환 레코드: {cnt_b}건 | 타깃 발견: {'✅ ' + str(len(found_b)) + '건' if found_b else '❌ 없음'}")
            if found_b:
                for r in found_b:
                    print(f"     └ LCNS:{r.get('LCNS_NO')} CHNG_DT:{r.get('CHNG_DT')} 사유:{r.get('CHNG_PRVNS')}")

            # ── Wide probe: ±WINDOW 범위 전수 탐색 (단건이라도 찾으면 위치 확정)
            wide_start = max(1, api_est - WINDOW)
            wide_end   = api_est + WINDOW
            print(f"\n   [Wide Probe] {wide_start:,}~{wide_end:,} ({WINDOW*2}건) 조회 중...")
            code_w, cnt_w, found_w = await probe_range(client, key, wide_start, wide_end, name)
            print(f"   → Code: {code_w} | 반환 레코드: {cnt_w}건 | 타깃 발견: {'✅ ' + str(len(found_w)) + '건' if found_w else '❌ 없음'}")
            if found_w:
                for r in found_w:
                    print(f"     └ LCNS:{r.get('LCNS_NO')} CHNG_DT:{r.get('CHNG_DT')} 사유:{r.get('CHNG_PRVNS')}")
            else:
                print(f"   ⚠️ Wide Probe에서도 미발견 → API 위치 추정 오차 가능성")

            await asyncio.sleep(0.5)
            print()

        print(f"{'='*70}")
        print("Plan B 실험 완료")

if __name__ == "__main__":
    asyncio.run(main())
