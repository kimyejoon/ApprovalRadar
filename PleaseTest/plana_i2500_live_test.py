"""
Plan A: I2500 Live View 검증 스크립트
======================================================
자정(00:00)과 오전(09:00~) 두 단계에서 실행.

검증 목표:
  1. CHNG_DT=20260522&SYS_SYNC=LIVE — 19시 타임에러 없이 접근 가능한지
  2. 시간 흐름에 따라 count가 실시간으로 늘어나는지
  3. I2861 Live에서 나온 업체가 I2500 Live에서도 동일하게 나오는지
  4. I2500 Plain은 오전에 여전히 차단되는지

실행 방법:
  자정 직후 (00:00~00:05):  python plana_i2500_midnight_test.py --mode midnight
  오전 영업시간 (09:00~):   python plana_i2500_midnight_test.py --mode morning
"""
import httpx
import sqlite3
import asyncio
import sys
import argparse
from datetime import datetime

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

db_path = r"c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\ApprovalRadar-BE\food_safety.db"

conn = sqlite3.connect(db_path)
api_keys = [r[0] for r in conn.execute("SELECT key_value FROM api_keys WHERE is_active = 1").fetchall()]
conn.close()

TODAY = datetime.now().strftime("%Y%m%d")  # 실행 시점 기준 오늘 날짜
YESTERDAY = "20260521"
BASE = "http://openapi.foodsafetykorea.go.kr/api"

async def find_valid_key(client: httpx.AsyncClient) -> str | None:
    for key in api_keys:
        for svc in ["I2500", "I2861"]:
            url = f"{BASE}/{key}/{svc}/json/1/1/SYS_SYNC=LIVE"
            try:
                res = await client.get(url, timeout=5.0)
                js = res.json()
                code = js.get(svc, {}).get("RESULT", {}).get("CODE", "")
                if code not in ["INFO-300", "INFO-333"]:
                    print(f"유효 키 발견: {key[:10]}... (서비스: {svc})")
                    return key
            except Exception:
                pass
    return None

async def query(client, key, svc, date, extra_param="", n=10):
    """단일 API 쿼리 실행"""
    if extra_param:
        url = f"{BASE}/{key}/{svc}/json/1/{n}/CHNG_DT={date}&{extra_param}"
    else:
        url = f"{BASE}/{key}/{svc}/json/1/{n}/CHNG_DT={date}"
    try:
        res = await client.get(url, timeout=10.0)
        js = res.json().get(svc, {})
        return {
            "url": url,
            "code": js.get("RESULT", {}).get("CODE"),
            "msg": js.get("RESULT", {}).get("MSG"),
            "total": js.get("total_count"),
            "rows": js.get("row", []),
        }
    except Exception as e:
        return {"url": url, "code": "ERROR", "msg": str(e), "total": None, "rows": []}

def print_result(label, r):
    icon = "✅" if r["code"] == "INFO-000" else "❌"
    print(f"  {icon} [{label}]")
    print(f"     URL:   {r['url']}")
    print(f"     Code:  {r['code']} | Total: {r['total']}")
    if r["rows"]:
        first = r["rows"][0]
        name = first.get("BSSH_NM") or first.get("PRSDNT_NM", "-")
        lcns = first.get("LCNS_NO", "-")
        chng = first.get("CHNG_DT") or first.get("PRMS_DT", "-")
        print(f"     샘플:  {name} | LCNS: {lcns} | Date: {chng}")

async def midnight_mode(client, key):
    """자정 직후 테스트: H7(I2500 자정 동기화), H8(CHNG_DT≤필터), 실험1(19시에러 없음)"""
    print(f"\n{'='*65}")
    print(f"[자정 테스트] {datetime.now().strftime('%H:%M:%S')} — 어제({YESTERDAY}) vs 오늘({TODAY})")
    print(f"{'='*65}")

    # A-1: I2500 어제 날짜 Plain → H7: 자정 이후 차단 해제되어야 함
    r = await query(client, key, "I2500", YESTERDAY)
    print_result(f"A-1  I2500 {YESTERDAY} Plain (H7 검증)", r)

    # A-2: I2500 어제 날짜 Live → H8: Plain과 count 차이 있는지
    r2 = await query(client, key, "I2500", YESTERDAY, "SYS_SYNC=LIVE")
    print_result(f"A-2  I2500 {YESTERDAY} Live  (H8 검증)", r2)
    if r["total"] and r2["total"]:
        diff = int(r2["total"]) - int(r["total"])
        print(f"     → Plain vs Live count 차이: {diff:+d} (양수면 Live에 추가 레코드 있음)")

    # A-3: I2500 오늘 날짜 Plain → 차단 여부
    r3 = await query(client, key, "I2500", TODAY)
    print_result(f"A-3  I2500 {TODAY} Plain   (차단 여부)", r3)

    # A-4 = 실험1 핵심: I2500 오늘 날짜 Live → 19시 에러 없이 접근 가능한지
    r4 = await query(client, key, "I2500", TODAY, "SYS_SYNC=LIVE")
    print_result(f"A-4★ I2500 {TODAY} Live    (실험1 핵심)", r4)
    if r4["code"] == "INFO-000":
        print(f"     🎉 Live View 진입 성공 — 19시 타임에러 없이 접근 가능!")
    elif r4["code"] == "INFO-700":
        print(f"     ⚠️ 여전히 차단 — 자정에도 오늘 데이터는 Live에서 제한")

    # I2861 비교: 오늘 Live
    r5 = await query(client, key, "I2861", TODAY, "SYS_SYNC=LIVE")
    print_result(f"I2861 {TODAY} Live (비교용)", r5)

async def morning_mode(client, key):
    """오전 영업시간 테스트: H3/H4/H6 핵심 검증 + 실시간 증가 관찰"""
    print(f"\n{'='*65}")
    print(f"[오전 테스트] {datetime.now().strftime('%H:%M:%S')} — 오늘({TODAY})")
    print(f"{'='*65}")

    # B-1: I2861 오늘 Plain → 차단 재확인
    r1 = await query(client, key, "I2861", TODAY)
    print_result(f"B-1  I2861 {TODAY} Plain (차단 재확인)", r1)

    # B-2: I2861 오늘 Live → 당일 실시간 데이터
    r2 = await query(client, key, "I2861", TODAY, "SYS_SYNC=LIVE", n=10)
    print_result(f"B-2  I2861 {TODAY} Live  (당일 변경분)", r2)

    # B-3: I2500 오늘 Plain → H4 검증
    r3 = await query(client, key, "I2500", TODAY)
    print_result(f"B-3  I2500 {TODAY} Plain (H4 검증)", r3)

    # B-4 = 실험2 핵심: I2500 오늘 Live → H3/H6 판정
    r4 = await query(client, key, "I2500", TODAY, "SYS_SYNC=LIVE", n=10)
    print_result(f"B-4★ I2500 {TODAY} Live  (실험2 핵심)", r4)

    if r4["code"] == "INFO-000" and r1["code"] != "INFO-000":
        print(f"\n  🎉 H6 입증: I2861 Plain이 차단({r1['code']})된 동안")
        print(f"      I2500 Live는 정상({r4['total']}건) → 미탐 커버 가능!")

    # B-5: I2861 Live vs I2500 Live LCNS_NO 교집합
    if r2["rows"] and r4["rows"]:
        lcns_i2861 = {r.get("LCNS_NO") for r in r2["rows"]}
        lcns_i2500 = {r.get("LCNS_NO") for r in r4["rows"]}
        common = lcns_i2861 & lcns_i2500
        print(f"\n  B-5 교차 검증: I2861 Live {len(lcns_i2861)}건 ∩ I2500 Live {len(lcns_i2500)}건 = 공통 {len(common)}건")
        if common:
            print(f"      공통 LCNS: {list(common)[:5]}")

    # 실시간 증가 관찰 (3회, 30초 간격)
    print(f"\n  [실시간 증가 관찰] 30초 간격 3회 체크 중...")
    for i in range(3):
        await asyncio.sleep(30)
        r_chk = await query(client, key, "I2500", TODAY, "SYS_SYNC=LIVE", n=1)
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"  [{ts}] I2500 Live total_count = {r_chk['total']}")

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["midnight", "morning"], default="midnight",
                        help="midnight: 자정 직후 | morning: 오전 영업시간")
    args = parser.parse_args()

    async with httpx.AsyncClient() as client:
        key = await find_valid_key(client)
        if not key:
            print("❌ 유효한 API 키 없음 — 자정(00:00) 이후 재실행하세요.")
            return

        if args.mode == "midnight":
            await midnight_mode(client, key)
        else:
            await morning_mode(client, key)

if __name__ == "__main__":
    asyncio.run(main())
