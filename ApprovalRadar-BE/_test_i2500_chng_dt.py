"""
I2500 CHNG_DT 필터 검증 테스트
- I2500/json/{start}/{end}/CHNG_DT=YYYYMMDD 형식으로 호출
- 반환된 LCNS_NO가 우리 DB에 있는지 교차 검증
"""
import asyncio
import sqlite3
import sys
import os
import json
import urllib.request
import time

sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1)

from dotenv import load_dotenv
load_dotenv()

API_KEYS = []
for i in range(1, 10):
    k = os.getenv(f"FOOD_SAFETY_API_KEY_{i}")
    if k:
        API_KEYS.append(k)
if not API_KEYS:
    fallback = os.getenv("FOOD_SAFETY_API_KEY")
    if fallback:
        API_KEYS.append(fallback)

key_idx = 0
def get_key():
    global key_idx
    key = API_KEYS[key_idx % len(API_KEYS)]
    key_idx += 1
    return key

DB_PATH = r"c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\dist_release\food_safety.db"
BASE_URL = "http://openapi.foodsafetykorea.go.kr/api"

def fetch_i2500(chng_dt, start, end):
    """I2500 API 호출 (CHNG_DT 필터)"""
    key = get_key()
    url = f"{BASE_URL}/{key}/I2500/json/{start}/{end}/CHNG_DT={chng_dt}"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=15) as resp:
            text = resp.read().decode("utf-8")
        if "alert(" in text or "<script" in text.lower():
            return {"error": "WAF_BLOCKED"}
        return json.loads(text)
    except json.JSONDecodeError as e:
        return {"error": f"JSON_PARSE: {e}", "raw": text[:200]}
    except Exception as e:
        return {"error": str(e)}

def test_chng_dt(chng_dt, label=""):
    """특정 CHNG_DT로 I2500 호출하여 결과 분석"""
    print(f"\n{'='*60}")
    print(f"📡 I2500 CHNG_DT={chng_dt} 테스트 {label}")
    print(f"{'='*60}")
    
    all_items = []
    
    # 1~1000 먼저 조회
    res = fetch_i2500(chng_dt, 1, 1000)
    
    if "error" in res:
        print(f"  ❌ 오류: {res['error']}")
        if "raw" in res:
            print(f"  원시 응답: {res['raw'][:200]}")
        return []
    
    if "I2500" not in res:
        print(f"  ❌ I2500 키 없음. 응답 키: {list(res.keys())}")
        for k, v in res.items():
            if isinstance(v, dict):
                print(f"  {k}: {json.dumps(v, ensure_ascii=False)[:200]}")
        return []
    
    block = res["I2500"]
    result_code = block.get("RESULT", {}).get("CODE", "")
    result_msg = block.get("RESULT", {}).get("MSG", "")
    
    if result_code != "INFO-000":
        print(f"  ⚠️ 응답 코드: {result_code} — {result_msg}")
        return []
    
    total = int(block.get("total_count", "0"))
    items = block.get("row", [])
    all_items.extend(items)
    
    print(f"  ✅ 전체 {total}건, 첫 페이지 {len(items)}건")
    
    if items:
        sample = items[0]
        print(f"  📋 필드: {list(sample.keys())}")
        lcns = sample.get("LCNS_NO", "?")
        name = sample.get("BSSH_NM", "?")
        chng = sample.get("CHNG_DT", "?")
        print(f"  샘플: LCNS={lcns} | BSSH_NM={name} | CHNG_DT={chng}")
    
    # 추가 페이지 (최대 5000건)
    if total > 1000:
        pages = min((total - 1) // 1000, 4)
        for p in range(1, pages + 1):
            s = p * 1000 + 1
            e = (p + 1) * 1000
            time.sleep(0.5)
            res2 = fetch_i2500(chng_dt, s, e)
            if "error" not in res2 and "I2500" in res2:
                items2 = res2["I2500"].get("row", [])
                all_items.extend(items2)
                print(f"  페이지 {s}~{e}: {len(items2)}건")
            else:
                print(f"  페이지 {s}~{e}: 오류 ({res2.get('error','?')})")
        print(f"  총 수집: {len(all_items)}건 / 전체 {total}건")
    
    return all_items

def cross_check(items, chng_dt):
    """I2500 결과와 DB 교차 검증"""
    if not items:
        print("  교차검증 스킵: 데이터 없음")
        return
    
    lcns_field = "LCNS_NO" if "LCNS_NO" in items[0] else None
    if not lcns_field:
        print(f"  ⚠️ LCNS_NO 필드 없음")
        return
    
    api_lcns_set = {item[lcns_field] for item in items if item.get(lcns_field)}
    print(f"\n  📊 교차검증: API {len(api_lcns_set)}개 고유 LCNS")
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    
    # DB에 존재 확인
    found_lcns = 0
    matched_date = 0
    sample_matches = []
    
    lcns_list = list(api_lcns_set)
    for i in range(0, len(lcns_list), 500):
        batch = lcns_list[i:i+500]
        ph = ",".join(["?"] * len(batch))
        rows = conn.execute(
            f"SELECT DISTINCT license_no, last_event_date FROM businesses WHERE license_no IN ({ph})",
            batch
        ).fetchall()
        for row in rows:
            found_lcns += 1
            if row["last_event_date"] == chng_dt:
                matched_date += 1
                if len(sample_matches) < 5:
                    sample_matches.append(row["license_no"])
    
    db_total_date = conn.execute(
        "SELECT COUNT(*) FROM businesses WHERE last_event_date = ?", (chng_dt,)
    ).fetchone()[0]
    
    conn.close()
    
    pct = found_lcns * 100 // max(len(api_lcns_set), 1)
    print(f"  DB에 LCNS 존재: {found_lcns}/{len(api_lcns_set)} ({pct}%)")
    print(f"  DB에서 같은 CHNG_DT({chng_dt})로 저장된 건: {matched_date}")
    print(f"  DB 전체 event_date={chng_dt}: {db_total_date}건")
    if sample_matches:
        print(f"  일치 LCNS 샘플: {sample_matches[:5]}")
    
    # API에만 있고 DB에 없는 LCNS 샘플
    not_in_db = [item for item in items[:20] if item[lcns_field] not in {r for r in lcns_list[:found_lcns]}]
    if not_in_db:
        print(f"  DB에 없는 샘플:")
        for item in not_in_db[:3]:
            print(f"    LCNS={item.get('LCNS_NO')} | {item.get('BSSH_NM')} | CHNG_DT={item.get('CHNG_DT')}")

def main():
    print("="*60)
    print("I2500 CHNG_DT 필터 신빙성 검증")
    print(f"API 키: {len(API_KEYS)}개 로드")
    print("="*60)
    
    # 테스트 1: 오늘 (20260519)
    today = test_chng_dt("20260519", "(오늘)")
    cross_check(today, "20260519")
    
    time.sleep(1)
    
    # 테스트 2: 어제 (20260518) — DB에 236건 있음
    yesterday = test_chng_dt("20260518", "(어제, DB에 236건)")
    cross_check(yesterday, "20260518")
    
    time.sleep(1)
    
    # 테스트 3: DB에서 레코드가 많은 과거 날짜
    conn = sqlite3.connect(DB_PATH)
    top = conn.execute(
        "SELECT last_event_date, COUNT(*) as cnt FROM businesses "
        "WHERE last_event_date >= '20260101' AND last_event_date < '20260518' "
        "GROUP BY last_event_date ORDER BY cnt DESC LIMIT 1"
    ).fetchone()
    conn.close()
    
    if top:
        past_date, past_cnt = top[0], top[1]
        print(f"\n  DB에서 최다 레코드 날짜: {past_date} ({past_cnt}건)")
        past = test_chng_dt(past_date, f"(검증: DB {past_cnt}건)")
        cross_check(past, past_date)
    
    print(f"\n{'='*60}")
    print("검증 완료!")
    print("="*60)

main()
