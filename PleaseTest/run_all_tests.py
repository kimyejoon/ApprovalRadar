"""
Plan A + Plan B 통합 빠른 테스트 (자정/오전 공용)
키 목록에서 첫 번째 유효한 키를 빠르게 찾아 바로 테스트.
"""
import httpx
import sqlite3
import asyncio
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

db_path = r"c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\ApprovalRadar-BE\food_safety.db"

# ── 키 로드 ────────────────────────────────────────
conn = sqlite3.connect(db_path)
ALL_KEYS = [r[0] for r in conn.execute("SELECT key_value FROM api_keys WHERE is_active = 1").fetchall()]
conn.close()
print(f"총 키 {len(ALL_KEYS)}개 로드됨")

TODAY     = "20260522"
YESTERDAY = "20260521"
BASE      = "http://openapi.foodsafetykorea.go.kr/api"

# ── 빠른 키 찾기 (병렬) ────────────────────────────
async def find_key_fast(client: httpx.AsyncClient) -> str | None:
    """모든 키를 병렬로 시도해서 가장 빠르게 유효한 키 반환"""
    async def probe(key):
        url = f"{BASE}/{key}/I2861/json/1/1"
        try:
            res = await client.get(url, timeout=5.0)
            js = res.json()
            code = js.get("I2861", {}).get("RESULT", {}).get("CODE", "")
            return key if code not in ["INFO-300", "INFO-333", "ERROR-500"] else None
        except Exception:
            return None

    tasks = [probe(k) for k in ALL_KEYS]
    results = await asyncio.gather(*tasks)
    valid = [r for r in results if r is not None]
    return valid[0] if valid else None

# ── 단일 쿼리 ──────────────────────────────────────
async def q(client, key, svc, date, extra="", n=10):
    if extra:
        url = f"{BASE}/{key}/{svc}/json/1/{n}/CHNG_DT={date}&{extra}"
    else:
        url = f"{BASE}/{key}/{svc}/json/1/{n}/CHNG_DT={date}"
    try:
        res = await client.get(url, timeout=10.0)
        js  = res.json().get(svc, {})
        return js.get("RESULT", {}).get("CODE"), js.get("total_count"), js.get("row", [])
    except Exception as e:
        return "ERROR", None, []

# ── Plan B: BSSH_NM 직접 탐색 ─────────────────────
async def bssh_nm_search(client, key, name):
    url = f"{BASE}/{key}/I2861/json/1/100/BSSH_NM={name}"
    try:
        res = await client.get(url, timeout=10.0)
        js  = res.json().get("I2861", {})
        return js.get("RESULT", {}).get("CODE"), js.get("total_count"), js.get("row", [])
    except Exception as e:
        return "ERROR", None, []

async def main():
    async with httpx.AsyncClient() as client:
        print("유효한 API 키 탐색 중 (병렬)...")
        key = await find_key_fast(client)
        if not key:
            print("❌ 유효한 키 없음 (모두 소진)")
            return
        print(f"✅ 유효 키 확인: {key[:10]}...\n")

        # ════════════════════════════════════════
        # PLAN A: I2500 자정 테스트
        # ════════════════════════════════════════
        print("=" * 60)
        print("PLAN A — I2500 자정 검증")
        print("=" * 60)

        tests = [
            ("A-1 I2500 어제 Plain    (H7: 자정 이후 오픈?)",     "I2500", YESTERDAY, ""),
            ("A-2 I2500 어제 Live     (H8: Plain vs Live diff?)", "I2500", YESTERDAY, "SYS_SYNC=LIVE"),
            ("A-3 I2500 오늘 Plain    (H4: 차단 여부)",            "I2500", TODAY,     ""),
            ("A-4 I2500 오늘 Live ★  (실험1: 19시 에러 없음?)",   "I2500", TODAY,     "SYS_SYNC=LIVE"),
            ("I2861 오늘 Plain        (비교)",                      "I2861", TODAY,     ""),
            ("I2861 오늘 Live         (비교)",                      "I2861", TODAY,     "SYS_SYNC=LIVE"),
        ]

        results = {}
        for label, svc, date, extra in tests:
            code, total, rows = await q(client, key, svc, date, extra)
            icon = "✅" if code == "INFO-000" else "❌"
            sample = ""
            if rows:
                r0 = rows[0]
                nm = r0.get("BSSH_NM") or r0.get("PRSDNT_NM", "?")
                dt = r0.get("CHNG_DT") or r0.get("PRMS_DT", "?")
                sample = f" | 샘플: {nm} / {dt}"
            print(f"  {icon} {label}")
            print(f"     Code={code} Total={total}{sample}")
            results[label] = (code, total, rows)
            await asyncio.sleep(0.3)

        # H7 판정
        r_a1_code, r_a1_total, _ = results["A-1 I2500 어제 Plain    (H7: 자정 이후 오픈?)"]
        print(f"\n  [H7 판정] 어제 Plain → {'✅ INFO-000 = 자정 동기화 확인' if r_a1_code == 'INFO-000' else '❌ ' + str(r_a1_code) + ' = 아직 차단'}")

        # H8 판정 (Plain vs Live count 비교)
        _, r_a2_total, _ = results["A-2 I2500 어제 Live     (H8: Plain vs Live diff?)"]
        if r_a1_total and r_a2_total:
            diff = int(r_a2_total) - int(r_a1_total)
            print(f"  [H8 판정] 어제 Plain({r_a1_total}) vs Live({r_a2_total}) → 차이: {diff:+d}")

        # 실험1 판정
        r_a4_code, r_a4_total, _ = results["A-4 I2500 오늘 Live ★  (실험1: 19시 에러 없음?)"]
        if r_a4_code == "INFO-000":
            print(f"  [실험1 ★] 🎉 INFO-000! 19시 타임에러 없이 Live 진입 성공! total={r_a4_total}")
        else:
            print(f"  [실험1 ★] {r_a4_code} — Live 진입 실패 또는 데이터 없음")

        # ════════════════════════════════════════
        # PLAN B: I2861 이중 구간 + BSSH_NM 직접 탐색
        # ════════════════════════════════════════
        print()
        print("=" * 60)
        print("PLAN B — I2861 미탐 업체 탐색")
        print("=" * 60)

        targets = [
            ("빽보이피자 둔촌점",        121265),
            ("미친양꼬치 홍대직영점",     97187),
            ("호미스피자 명지대점",       286693),
            ("너도나도식당 상암DMC점",     43753),
        ]
        API_TOTAL = 954000

        for name, db_pos in targets:
            api_est = int(db_pos / 294443 * API_TOTAL)
            print(f"\n  🎯 '{name}' (DB위치:{db_pos:,} → API추정:{api_est:,})")

            # BSSH_NM 직접 탐색
            bcode, btotal, brows = await bssh_nm_search(client, key, name)
            if brows:
                r0 = brows[0]
                print(f"     BSSH_NM 직접: ✅ {bcode} total={btotal} | LCNS={r0.get('LCNS_NO')} CHNG_DT={r0.get('CHNG_DT')}")
                print(f"       사유: {r0.get('CHNG_PRVNS')} | 주소: {r0.get('SITE_ADDR','?')[:30]}")
            else:
                print(f"     BSSH_NM 직접: ❌ {bcode} total={btotal} (미발견)")
            await asyncio.sleep(0.3)

            # 사이클 A 구간
            a_s = (api_est // 1000) * 1000 + 1
            a_e = a_s + 999
            url_a = f"{BASE}/{key}/I2861/json/{a_s}/{a_e}/SYS_SYNC=LIVE"
            try:
                res_a = await client.get(url_a, timeout=10.0)
                js_a = res_a.json().get("I2861", {})
                code_a = js_a.get("RESULT", {}).get("CODE")
                rows_a = js_a.get("row", [])
                hit_a = [r for r in rows_a if name in r.get("BSSH_NM", "")]
                print(f"     사이클A [{a_s:,}~{a_e:,}]: {code_a} {len(rows_a)}건 | 타깃: {'✅ 발견' if hit_a else '❌ 없음'}")
            except Exception as e:
                print(f"     사이클A: ERROR {e}")
            await asyncio.sleep(0.3)

            # 사이클 B 구간 (500 오프셋)
            b_s = max(1, api_est - 500)
            b_e = b_s + 999
            url_b = f"{BASE}/{key}/I2861/json/{b_s}/{b_e}/SYS_SYNC=LIVE"
            try:
                res_b = await client.get(url_b, timeout=10.0)
                js_b = res_b.json().get("I2861", {})
                code_b = js_b.get("RESULT", {}).get("CODE")
                rows_b = js_b.get("row", [])
                hit_b = [r for r in rows_b if name in r.get("BSSH_NM", "")]
                print(f"     사이클B [{b_s:,}~{b_e:,}]: {code_b} {len(rows_b)}건 | 타깃: {'✅ 발견' if hit_b else '❌ 없음'}")
            except Exception as e:
                print(f"     사이클B: ERROR {e}")
            await asyncio.sleep(0.3)

        print()
        print("=" * 60)
        print("테스트 완료")

if __name__ == "__main__":
    asyncio.run(main())
