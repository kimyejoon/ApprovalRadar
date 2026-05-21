"""
Plan B 패턴 분석: 미탐 업체의 실제 API 위치 탐색
이진 탐색으로 (BSSH_NM, CHNG_DT) 정렬 기준 실제 위치 추정
"""
import httpx
import sqlite3
import asyncio
import sys
from datetime import datetime

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

db_path = r"c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\ApprovalRadar-BE\food_safety.db"
BASE    = "http://openapi.foodsafetykorea.go.kr/api"
TIMEOUT = 200

conn = sqlite3.connect(db_path)
KEY = conn.execute("SELECT key_value FROM api_keys WHERE is_active = 1 LIMIT 1").fetchone()[0]
conn.close()
print(f"키: {KEY[:12]}...\n")

TARGETS = [
    ("빽보이피자 둔촌점",     "20230154976", "20260521"),
    ("미친양꼬치 홍대직영점",  "20230092283", "20260521"),
    ("호미스피자 명지대점",    "20230088005", "20260521"),
    ("너도나도식당 상암DMC점", "20250098526", "20260521"),
]

async def get_range(client, start, end):
    """지정 범위 조회 → (code, total_count, first_bssh_nm, last_bssh_nm, rows)"""
    url = f"{BASE}/{KEY}/I2861/json/{start}/{end}/SYS_SYNC=LIVE"
    try:
        res  = await client.get(url, timeout=TIMEOUT)
        js   = res.json().get("I2861", {})
        code = js.get("RESULT", {}).get("CODE")
        tot  = js.get("total_count")
        rows = js.get("row", [])
        first_nm = rows[0].get("BSSH_NM","") if rows else ""
        last_nm  = rows[-1].get("BSSH_NM","") if rows else ""
        return code, tot, first_nm, last_nm, rows
    except asyncio.TimeoutError:
        return "TIMEOUT", None, "", "", []
    except Exception as e:
        return f"ERR:{e}"[:40], None, "", "", []

async def find_actual_position(client, target_name, target_lcns, probe_size=2000):
    """
    브래킷 탐색: 넓은 범위 probe_size로 스캔하여 target_name이 등장하는 구간 찾기
    """
    print(f"\n  '{target_name}' 실제 위치 탐색 중...")

    # 먼저 총 레코드 수 파악
    code, total, _, _, _ = await get_range(client, 1, 1)
    if not total:
        print(f"  → 총 레코드 수 파악 실패 ({code})")
        return None
    total = int(total)
    print(f"  → API 총 레코드: {total:,}")

    # probe_size 단위로 스캔하여 target이 나타나는 구간 찾기
    found_range = None
    step = probe_size
    for start in range(1, total, step):
        end = min(start + step - 1, total)
        code, tot, first_nm, last_nm, rows = await get_range(client, start, end)
        
        matched = [r for r in rows if r.get("LCNS_NO") == target_lcns]
        if matched:
            print(f"  ✅ 발견! 구간 [{start:,}~{end:,}] | 업체위치 내 확인")
            print(f"     구간 시작 상호명: '{first_nm[:20]}'")
            print(f"     구간 끝  상호명:  '{last_nm[:20]}'")
            # 정확 위치 찾기 (해당 구간 내 index)
            for i, r in enumerate(rows):
                if r.get("LCNS_NO") == target_lcns:
                    actual_pos = start + i
                    print(f"     정확 위치: {actual_pos:,} / {total:,}")
                    found_range = (start, end, actual_pos, total, first_nm, last_nm)
                    break
            break
        
        # 진행 상황 (10만 단위로만 출력)
        if start % 100000 < step:
            pct = start / total * 100
            print(f"  ... [{start:,}~{end:,}] {pct:.1f}% 탐색 중 | {first_nm[:15]!r} ~ {last_nm[:15]!r}")
        
        await asyncio.sleep(0.1)

    if not found_range:
        print(f"  ❌ {total:,}건 전체 탐색에서 미발견")
    return found_range

async def analyze_boundary_effect(client, actual_pos, total, target_name, window=50):
    """
    실제 위치 주변 ±window건을 조회하여
    1000단위 경계와의 관계 분석
    """
    if not actual_pos:
        return
    
    start = max(1, actual_pos - window)
    end   = min(total, actual_pos + window)
    code, tot, first_nm, last_nm, rows = await get_range(client, start, end)
    
    # 어느 1000단위 사이클에 속하는지
    cycle_a_block = ((actual_pos - 1) // 1000) * 1000 + 1
    cycle_b_block_1 = max(1, ((actual_pos - 500) // 1000) * 1000 + 1)
    cycle_b_block_2 = cycle_b_block_1 + 500
    
    # 경계면까지 거리
    dist_to_a_boundary = actual_pos % 1000
    if dist_to_a_boundary == 0:
        dist_to_a_boundary = 1000
    dist_from_a_boundary = 1000 - dist_to_a_boundary

    print(f"\n  경계 분석 (실제위치={actual_pos:,}):")
    print(f"    사이클A 해당 블록: [{cycle_a_block:,} ~ {cycle_a_block+999:,}]")
    print(f"    사이클B 해당 블록: [{cycle_b_block_1:,} ~ {cycle_b_block_1+999:,}]")
    print(f"    블록 내 위치: {dist_to_a_boundary}/1000 (경계까지 {dist_from_a_boundary}건 남음)")
    print(f"    경계에서 {min(dist_to_a_boundary, dist_from_a_boundary)}건 이내 여부: {'⚠️ 경계 근접' if min(dist_to_a_boundary, dist_from_a_boundary) < 50 else '✅ 경계와 충분한 거리'}")

async def main():
    print("=" * 65)
    print("Plan B 패턴 분석 — 미탐 업체 실제 API 위치 탐색")
    print("(probe_size=50,000 단위 스캔 → 위치 확인 후 정밀 탐색)")
    print("=" * 65)

    async with httpx.AsyncClient() as client:
        # 총 레코드 수 확인
        code, total, _, _, _ = await get_range(client, 1, 1)
        total = int(total) if total else 0
        print(f"\nAPI 총 레코드 수: {total:,}")

        results = {}

        for name, lcns, chng_dt in TARGETS:
            print(f"\n{'─'*60}")
            print(f"🎯 대상: '{name}' (LCNS={lcns}, CHNG_DT={chng_dt})")
            
            # 큰 구간으로 탐색 (50,000단위)
            found = await find_actual_position(client, name, lcns, probe_size=50000)
            
            if found:
                start, end, actual_pos, total_cnt, first_nm, last_nm = found
                results[name] = actual_pos
                await analyze_boundary_effect(client, actual_pos, total_cnt, name)
            else:
                results[name] = None

        # 요약
        print(f"\n{'='*65}")
        print("실제 위치 vs 추정 위치 비교 요약")
        print(f"{'='*65}")
        db_positions = {
            "빽보이피자 둔촌점":       121265,
            "미친양꼬치 홍대직영점":    97187,
            "호미스피자 명지대점":      286693,
            "너도나도식당 상암DMC점":    43753,
        }
        api_total_est = 954000
        for name, db_pos in db_positions.items():
            est = int(db_pos / 294443 * api_total_est)
            act = results.get(name)
            print(f"  '{name}'")
            print(f"    DB 사전순 위치:  {db_pos:>7,} / 294,443")
            print(f"    추정 API 위치:  {est:>7,} / {api_total_est:,}")
            if act:
                print(f"    실제 API 위치:  {act:>7,} / {total:,}  (오차: {abs(est-act):,})")
            else:
                print(f"    실제 API 위치:  탐색 실패")
            print()

asyncio.run(main())
