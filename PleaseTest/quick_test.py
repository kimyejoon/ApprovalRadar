import sqlite3, httpx, asyncio, sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

db_path = r"c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\ApprovalRadar-BE\food_safety.db"
conn = sqlite3.connect(db_path)
keys = [r[0] for r in conn.execute("SELECT key_value FROM api_keys WHERE is_active = 1").fetchall()]
conn.close()

BASE = "http://openapi.foodsafetykorea.go.kr/api"

async def main():
    async with httpx.AsyncClient() as client:
        print(f"총 {len(keys)}개 키 순차 확인 중...\n")
        for i, key in enumerate(keys):
            url = f"{BASE}/{key}/I2861/json/1/1"
            try:
                res = await client.get(url, timeout=5.0)
                js = res.json()
                i2861 = js.get("I2861", {})
                code = i2861.get("RESULT", {}).get("CODE", "?")
                msg  = i2861.get("RESULT", {}).get("MSG", "?")
                print(f"  [{i+1:2d}] {key[:12]}... → {code} | {msg[:40]}")
                if code not in ["INFO-300", "INFO-333"]:
                    print(f"\n  ✅ 유효 키 발견: {key}")
                    # 빠른 테스트 실행
                    for label, svc, date, extra in [
                        ("I2500 어제 Plain",    "I2500", "20260521", ""),
                        ("I2500 어제 Live",     "I2500", "20260521", "SYS_SYNC=LIVE"),
                        ("I2500 오늘 Plain",    "I2500", "20260522", ""),
                        ("I2500 오늘 Live ★",  "I2500", "20260522", "SYS_SYNC=LIVE"),
                        ("I2861 오늘 Plain",    "I2861", "20260522", ""),
                        ("I2861 오늘 Live",     "I2861", "20260522", "SYS_SYNC=LIVE"),
                    ]:
                        if extra:
                            turl = f"{BASE}/{key}/{svc}/json/1/5/CHNG_DT={date}&{extra}"
                        else:
                            turl = f"{BASE}/{key}/{svc}/json/1/5/CHNG_DT={date}"
                        try:
                            tres = await client.get(turl, timeout=10.0)
                            tjs = tres.json().get(svc, {})
                            tcode = tjs.get("RESULT", {}).get("CODE")
                            ttotal = tjs.get("total_count")
                            trows = tjs.get("row", [])
                            icon = "✅" if tcode == "INFO-000" else "❌"
                            samp = ""
                            if trows:
                                r0 = trows[0]
                                samp = f" | {r0.get('BSSH_NM') or r0.get('PRSDNT_NM','?')} / {r0.get('CHNG_DT') or r0.get('PRMS_DT','?')}"
                            print(f"    {icon} {label:20s} code={tcode} total={ttotal}{samp}")
                        except Exception as e:
                            print(f"    ❌ {label}: {e}")
                        await asyncio.sleep(0.2)
                    break
            except Exception as e:
                print(f"  [{i+1:2d}] {key[:12]}... → ERROR: {e}")
            await asyncio.sleep(0.15)
        else:
            print("\n❌ 모든 키 소진 — 공공데이터포털 일일 리셋 대기 필요")

asyncio.run(main())
