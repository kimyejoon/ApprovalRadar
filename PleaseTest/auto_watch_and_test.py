"""
Plan A + Plan B 통합 테스트 (느린 서버 대응 버전)
타임아웃: 키 탐색 30초, API 쿼리 300초
"""
import httpx
import sqlite3
import asyncio
import sys
import os
import json
from datetime import datetime

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

db_path   = r"c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\ApprovalRadar-BE\food_safety.db"
flag_path = r"c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\PleaseTest\test_completed.flag"
BASE      = "http://openapi.foodsafetykorea.go.kr/api"
TODAY     = datetime.now().strftime("%Y%m%d")
YESTERDAY = "20260521"

PROBE_TIMEOUT = 30      # 키 탐색용 (초)
QUERY_TIMEOUT = 300     # 실제 쿼리용 (초)

conn = sqlite3.connect(db_path)
ALL_KEYS = [r[0] for r in conn.execute("SELECT key_value FROM api_keys WHERE is_active = 1").fetchall()]
conn.close()
print(f"[{datetime.now().strftime('%H:%M:%S')}] 총 키 {len(ALL_KEYS)}개 로드, 타임아웃={QUERY_TIMEOUT}초")

# ── 유효 키 탐색 (순차, 30초 타임아웃) ─────────────
async def find_valid_key(client):
    for i, key in enumerate(ALL_KEYS):
        try:
            url  = f"{BASE}/{key}/I2861/json/1/1"
            print(f"  키 [{i+1}/{len(ALL_KEYS)}] 확인 중... ", end="", flush=True)
            res  = await client.get(url, timeout=PROBE_TIMEOUT)
            code = res.json().get("I2861", {}).get("RESULT", {}).get("CODE", "")
            print(f"{code}")
            if code not in ["INFO-300", "INFO-333", "ERROR-500"]:
                return key
        except asyncio.TimeoutError:
            print("타임아웃(30s) — 다음 키")
        except Exception as e:
            print(f"오류: {str(e)[:40]}")
    return None

# ── 단일 쿼리 (300초 타임아웃) ────────────────────
async def q(client, key, svc, date, extra="", n=5):
    url = (f"{BASE}/{key}/{svc}/json/1/{n}/CHNG_DT={date}&{extra}"
           if extra else
           f"{BASE}/{key}/{svc}/json/1/{n}/CHNG_DT={date}")
    t0 = datetime.now()
    try:
        res  = await client.get(url, timeout=QUERY_TIMEOUT)
        js   = res.json().get(svc, {})
        elapsed = (datetime.now() - t0).seconds
        code = js.get("RESULT", {}).get("CODE")
        tot  = js.get("total_count")
        rows = js.get("row", [])
        return code, tot, rows, elapsed
    except asyncio.TimeoutError:
        return "TIMEOUT", None, [], QUERY_TIMEOUT
    except Exception as e:
        return f"ERR:{str(e)[:30]}", None, [], (datetime.now()-t0).seconds

# ── BSSH_NM 탐색 ─────────────────────────────────
async def bssh(client, key, name):
    url = f"{BASE}/{key}/I2861/json/1/100/BSSH_NM={name}"
    t0  = datetime.now()
    try:
        res  = await client.get(url, timeout=QUERY_TIMEOUT)
        js   = res.json().get("I2861", {})
        elapsed = (datetime.now() - t0).seconds
        return js.get("RESULT",{}).get("CODE"), js.get("total_count"), js.get("row",[]), elapsed
    except asyncio.TimeoutError:
        return "TIMEOUT", None, [], QUERY_TIMEOUT
    except Exception as e:
        return f"ERR:{str(e)[:30]}", None, [], 0

def prt(label, code, total, rows, elapsed=None):
    icon = "✅" if code == "INFO-000" else ("⏳" if code == "TIMEOUT" else "❌")
    samp = ""
    if rows:
        r0 = rows[0]
        nm = r0.get("BSSH_NM") or r0.get("PRSDNT_NM","?")
        dt = r0.get("CHNG_DT") or r0.get("PRMS_DT","?")
        samp = f" | {nm[:20]} / {dt}"
    t = f" ({elapsed}s)" if elapsed is not None else ""
    print(f"  {icon} {label:32s} {code} total={total}{t}{samp}")

async def run_tests(key):
    print(f"\n{'='*65}")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 유효키={key[:12]}... 테스트 시작")
    print(f"{'='*65}")

    async with httpx.AsyncClient() as c:

        # ══════════════════════════════════
        # PLAN A: I2500 검증
        # ══════════════════════════════════
        print("\n▶ PLAN A — I2500 Live View 검증")
        print("-" * 50)

        a1c,a1t,a1r,a1e = await q(c, key, "I2500", YESTERDAY)
        prt(f"A-1 I2500 {YESTERDAY} Plain  (H7)", a1c, a1t, a1r, a1e)

        a2c,a2t,a2r,a2e = await q(c, key, "I2500", YESTERDAY, "SYS_SYNC=LIVE")
        prt(f"A-2 I2500 {YESTERDAY} Live   (H8)", a2c, a2t, a2r, a2e)
        if a1t and a2t and a1c=="INFO-000" and a2c=="INFO-000":
            print(f"     H8 diff: Plain({a1t}) vs Live({a2t}) = {int(a2t)-int(a1t):+d}")

        a3c,a3t,a3r,a3e = await q(c, key, "I2500", TODAY)
        prt(f"A-3 I2500 {TODAY} Plain  (H4)", a3c, a3t, a3r, a3e)

        a4c,a4t,a4r,a4e = await q(c, key, "I2500", TODAY, "SYS_SYNC=LIVE")
        prt(f"A-4 I2500 {TODAY} Live ★ (실험1)", a4c, a4t, a4r, a4e)

        ib_p_c,ib_p_t,_,ib_p_e = await q(c, key, "I2861", TODAY)
        prt(f"    I2861 {TODAY} Plain  (비교)", ib_p_c, ib_p_t, [], ib_p_e)

        ib_l_c,ib_l_t,ib_l_r,ib_l_e = await q(c, key, "I2861", TODAY, "SYS_SYNC=LIVE")
        prt(f"    I2861 {TODAY} Live   (비교)", ib_l_c, ib_l_t, ib_l_r, ib_l_e)

        print("\n  ── PLAN A 판정 ──")
        print(f"  H7 자정 동기화: {'✅' if a1c=='INFO-000' else '❌'} ({a1c})")
        print(f"  H4 오늘 차단:   {'✅' if a3c!='INFO-000' else '❌'} ({a3c})")
        if a4c == "INFO-000":
            print(f"  실험1 ★:       🎉 I2500 Live 진입 성공! total={a4t}")
            if ib_p_c != "INFO-000":
                print(f"  H6 미탐커버:    🎉 I2861 Plain 차단({ib_p_c}) + I2500 Live 성공 → 구조적 미탐 커버 가능!")
        else:
            print(f"  실험1 ★:       ❌ I2500 Live 실패 ({a4c})")

        # ══════════════════════════════════
        # PLAN B: 미탐 업체 탐색
        # ══════════════════════════════════
        print("\n▶ PLAN B — I2861 미탐 업체 BSSH_NM 탐색 + 이중 구간")
        print("-" * 50)

        targets = [
            ("빽보이피자 둔촌점",        121265),
            ("미친양꼬치 홍대직영점",     97187),
            ("호미스피자 명지대점",       286693),
            ("너도나도식당 상암DMC점",     43753),
        ]
        API_TOTAL = 954000

        for name, db_pos in targets:
            api_est = int(db_pos / 294443 * API_TOTAL)
            print(f"\n  🎯 '{name}'  (API추정:{api_est:,})")

            # BSSH_NM 직접
            bc,bt,br,be = await bssh(c, key, name)
            if br:
                r0 = br[0]
                print(f"    BSSH_NM: ✅ {bc} total={bt} ({be}s) LCNS={r0.get('LCNS_NO')} CHNG_DT={r0.get('CHNG_DT')}")
                print(f"      사유: {r0.get('CHNG_PRVNS')} | {r0.get('SITE_ADDR','?')[:40]}")
            else:
                print(f"    BSSH_NM: {'⏳ TIMEOUT' if bc=='TIMEOUT' else '❌ ' + bc} total={bt} ({be}s)")

            # 사이클 A
            as_ = (api_est // 1000) * 1000 + 1
            ae  = as_ + 999
            url_a = f"{BASE}/{key}/I2861/json/{as_}/{ae}/SYS_SYNC=LIVE"
            t0 = datetime.now()
            try:
                res_a = await c.get(url_a, timeout=QUERY_TIMEOUT)
                js_a  = res_a.json().get("I2861", {})
                ac    = js_a.get("RESULT",{}).get("CODE")
                arows = js_a.get("row",[])
                hit_a = [r for r in arows if name in r.get("BSSH_NM","")]
                print(f"    사이클A [{as_:,}~{ae:,}]: {ac} {len(arows)}건 ({(datetime.now()-t0).seconds}s) | {'✅ 타깃발견' if hit_a else '❌ 미발견'}")
            except asyncio.TimeoutError:
                print(f"    사이클A: ⏳ TIMEOUT")
            except Exception as e:
                print(f"    사이클A: ❌ {e}")

            # 사이클 B (500 오프셋)
            bs_ = max(1, api_est - 500)
            be_ = bs_ + 999
            url_b = f"{BASE}/{key}/I2861/json/{bs_}/{be_}/SYS_SYNC=LIVE"
            t0 = datetime.now()
            try:
                res_b = await c.get(url_b, timeout=QUERY_TIMEOUT)
                js_b  = res_b.json().get("I2861", {})
                bc2   = js_b.get("RESULT",{}).get("CODE")
                brows2= js_b.get("row",[])
                hit_b = [r for r in brows2 if name in r.get("BSSH_NM","")]
                print(f"    사이클B [{bs_:,}~{be_:,}]: {bc2} {len(brows2)}건 ({(datetime.now()-t0).seconds}s) | {'✅ 타깃발견' if hit_b else '❌ 미발견'}")
            except asyncio.TimeoutError:
                print(f"    사이클B: ⏳ TIMEOUT")
            except Exception as e:
                print(f"    사이클B: ❌ {e}")

    print(f"\n{'='*65}")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 전체 테스트 완료")
    with open(flag_path, "w", encoding="utf-8") as f:
        json.dump({"completed_at": datetime.now().isoformat()}, f)

async def main():
    if os.path.exists(flag_path):
        with open(flag_path, encoding="utf-8") as f:
            info = json.load(f)
        print(f"이미 완료됨 ({info.get('completed_at')}). 플래그 삭제 후 재실행하세요.")
        return

    print(f"[{datetime.now().strftime('%H:%M:%S')}] 유효 키 탐색 시작 (타임아웃={PROBE_TIMEOUT}s/키)...")
    async with httpx.AsyncClient() as client:
        key = await find_valid_key(client)

    if not key:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ 유효 키 없음 — 서버 점검 중 또는 전체 소진")
        return

    await run_tests(key)

asyncio.run(main())
