"""
Plan A + Plan B 직접 테스트 (키 탐색 없이 첫 번째 키 사용, 타임아웃 200초)
"""
import httpx
import sqlite3
import asyncio
import sys
from datetime import datetime

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

db_path   = r"c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\ApprovalRadar-BE\food_safety.db"
BASE      = "http://openapi.foodsafetykorea.go.kr/api"
TODAY     = "20260522"
YESTERDAY = "20260521"
TIMEOUT   = 200  # 초

conn = sqlite3.connect(db_path)
KEY = conn.execute("SELECT key_value FROM api_keys WHERE is_active = 1 LIMIT 1").fetchone()[0]
conn.close()
print(f"사용 키: {KEY[:12]}...")

async def q(client, key, svc, date, extra="", n=5):
    url = (f"{BASE}/{key}/{svc}/json/1/{n}/CHNG_DT={date}&{extra}"
           if extra else
           f"{BASE}/{key}/{svc}/json/1/{n}/CHNG_DT={date}")
    t0 = datetime.now()
    print(f"  → {url}", flush=True)
    try:
        res  = await client.get(url, timeout=TIMEOUT)
        js   = res.json().get(svc, {})
        elapsed = int((datetime.now()-t0).total_seconds())
        return js.get("RESULT",{}).get("CODE"), js.get("total_count"), js.get("row",[]), elapsed
    except asyncio.TimeoutError:
        return "TIMEOUT", None, [], TIMEOUT
    except Exception as e:
        return f"ERR:{e}"[:50], None, [], int((datetime.now()-t0).total_seconds())

async def bssh(client, key, name):
    url = f"{BASE}/{key}/I2861/json/1/100/BSSH_NM={name}"
    t0  = datetime.now()
    print(f"  → {url}", flush=True)
    try:
        res  = await client.get(url, timeout=TIMEOUT)
        js   = res.json().get("I2861", {})
        return js.get("RESULT",{}).get("CODE"), js.get("total_count"), js.get("row",[]), int((datetime.now()-t0).total_seconds())
    except asyncio.TimeoutError:
        return "TIMEOUT", None, [], TIMEOUT
    except Exception as e:
        return f"ERR:{e}"[:50], None, [], 0

def prt(label, code, total, rows, elapsed):
    icon = "✅" if code=="INFO-000" else ("⏳" if "TIMEOUT" in str(code) else "❌")
    samp = ""
    if rows:
        r0 = rows[0]
        nm = r0.get("BSSH_NM") or r0.get("PRSDNT_NM","?")
        dt = r0.get("CHNG_DT") or r0.get("PRMS_DT","?")
        samp = f"  [{nm[:18]}/{dt}]"
    print(f"  {icon} {label:35s} {code} total={total} ({elapsed}s){samp}")

async def range_probe(client, key, name, start, end, label):
    url = f"{BASE}/{key}/I2861/json/{start}/{end}/SYS_SYNC=LIVE"
    t0  = datetime.now()
    print(f"  → {url}", flush=True)
    try:
        res   = await client.get(url, timeout=TIMEOUT)
        js    = res.json().get("I2861", {})
        code  = js.get("RESULT",{}).get("CODE")
        rows  = js.get("row",[])
        elapsed = int((datetime.now()-t0).total_seconds())
        hit   = [r for r in rows if name in r.get("BSSH_NM","")]
        print(f"  {'✅' if hit else '❌'} {label:20s} [{start:,}~{end:,}] {code} {len(rows)}건 ({elapsed}s) | {'타깃발견: ' + str(len(hit)) + '건' if hit else '미발견'}")
        if hit:
            for r in hit:
                print(f"    LCNS={r.get('LCNS_NO')} CHNG_DT={r.get('CHNG_DT')} 사유={r.get('CHNG_PRVNS')}")
    except asyncio.TimeoutError:
        print(f"  ⏳ {label} TIMEOUT ({TIMEOUT}s)")
    except Exception as e:
        print(f"  ❌ {label} ERR: {e}")

async def main():
    async with httpx.AsyncClient() as c:

        # ════════════════════════════════
        # PLAN A: I2500 검증
        # ════════════════════════════════
        print(f"\n{'='*60}")
        print("PLAN A — I2500 Live View 검증")
        print(f"{'='*60}")

        a1c,a1t,a1r,a1e = await q(c, KEY, "I2500", YESTERDAY)
        prt(f"A-1 I2500 {YESTERDAY} Plain (H7)", a1c,a1t,a1r,a1e)

        a2c,a2t,a2r,a2e = await q(c, KEY, "I2500", YESTERDAY, "SYS_SYNC=LIVE")
        prt(f"A-2 I2500 {YESTERDAY} Live  (H8)", a2c,a2t,a2r,a2e)
        if a1t and a2t and "INFO" in str(a1c) and "INFO" in str(a2c):
            print(f"     H8: Plain({a1t}) vs Live({a2t}) 차이={int(a2t)-int(a1t):+d}")

        a3c,a3t,a3r,a3e = await q(c, KEY, "I2500", TODAY)
        prt(f"A-3 I2500 {TODAY} Plain  (H4)", a3c,a3t,a3r,a3e)

        a4c,a4t,a4r,a4e = await q(c, KEY, "I2500", TODAY, "SYS_SYNC=LIVE")
        prt(f"A-4 I2500 {TODAY} Live ★ (실험1)", a4c,a4t,a4r,a4e)

        ic,it,ir,ie = await q(c, KEY, "I2861", TODAY)
        prt(f"    I2861 {TODAY} Plain  (비교)", ic,it,ir,ie)

        ilc,ilt,ilr,ile = await q(c, KEY, "I2861", TODAY, "SYS_SYNC=LIVE")
        prt(f"    I2861 {TODAY} Live   (비교)", ilc,ilt,ilr,ile)

        print("\n  ── 판정 ──")
        print(f"  H7 자정동기화: {'✅' if a1c=='INFO-000' else '❌'} ({a1c})")
        print(f"  H4 오늘차단:   {'✅' if a3c!='INFO-000' else '❌'} ({a3c})")
        if a4c == "INFO-000":
            print(f"  실험1 ★:       🎉 I2500 Live 진입 성공! total={a4t}")
            if ic != "INFO-000":
                print(f"  H6 미탐커버:    🎉 I2861 Plain 차단 + I2500 Live 성공!")
        else:
            print(f"  실험1 ★:       ❌ ({a4c})")

        # ════════════════════════════════
        # PLAN B: 미탐 업체 탐색
        # ════════════════════════════════
        print(f"\n{'='*60}")
        print("PLAN B — I2861 미탐 업체 탐색")
        print(f"{'='*60}")

        targets = [
            ("빽보이피자 둔촌점",       121265),
            ("미친양꼬치 홍대직영점",    97187),
            ("호미스피자 명지대점",      286693),
            ("너도나도식당 상암DMC점",    43753),
        ]

        for name, db_pos in targets:
            api_est = int(db_pos / 294443 * 954000)
            print(f"\n  🎯 '{name}'  (API추정:{api_est:,})")

            bc,bt,br,be = await bssh(c, KEY, name)
            if br:
                r0 = br[0]
                print(f"  ✅ BSSH_NM: {bc} total={bt} ({be}s) LCNS={r0.get('LCNS_NO')} CHNG_DT={r0.get('CHNG_DT')}")
                print(f"     사유: {r0.get('CHNG_PRVNS')} | {r0.get('SITE_ADDR','?')[:40]}")
            else:
                print(f"  ❌ BSSH_NM: {bc} total={bt} ({be}s)")

            as_ = (api_est // 1000) * 1000 + 1
            ae  = as_ + 999
            await range_probe(c, KEY, name, as_, ae, "사이클A")

            bs_ = max(1, api_est - 500)
            be_ = bs_ + 999
            await range_probe(c, KEY, name, bs_, be_, "사이클B")

    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 완료")

asyncio.run(main())
