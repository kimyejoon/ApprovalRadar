"""
I2500 CHNG_DT 최종 신빙성 검증 v3

검증 항목:
  1. 1000건 페이지로 full pagination (CHNG_DT=오늘)
  2. 공휴일/주말 데이터 확인 (어린이날 등)
  3. "이후" 의미 검증: 이전 날짜 → 더 큰 데이터셋? (포함적이면)
  4. 전체 수집 데이터 vs DB 교차 분포
"""
import json
import sys
import os
import time
import urllib.request
import sqlite3

sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1)

from dotenv import load_dotenv
load_dotenv()

API_KEYS = []
for i in range(1, 21):
    k = os.getenv(f"FOOD_SAFETY_API_KEY_{i}")
    if k:
        API_KEYS.append(k)

exhausted_keys = set()
key_idx = 0
call_count = 0

BASE = "http://openapi.foodsafetykorea.go.kr/api"
DB = r"c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\dist_release\food_safety.db"

def alive_keys():
    return len(API_KEYS) - len(exhausted_keys)

def fetch(start, end, chng_dt=None):
    global key_idx, call_count
    
    for _ in range(len(API_KEYS)):
        key = API_KEYS[key_idx % len(API_KEYS)]
        key_idx += 1
        
        if key in exhausted_keys:
            continue
        
        url = f"{BASE}/{key}/I2500/json/{start}/{end}"
        if chng_dt:
            url += f"/CHNG_DT={chng_dt}"
        
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=20) as resp:
                text = resp.read().decode("utf-8")
            
            if "alert(" in text or "<script" in text.lower():
                exhausted_keys.add(key)
                continue
            
            data = json.loads(text)
            call_count += 1
            
            if "I2500" not in data:
                return None
            
            block = data["I2500"]
            code = block.get("RESULT", {}).get("CODE", "")
            
            if code == "INFO-300":
                exhausted_keys.add(key)
                continue
            
            return block
        except Exception as e:
            print(f"    ❌ {e}")
            time.sleep(0.5)
    
    print(f"    💀 살아있는 키 없음!")
    return None

def get_total_and_rows(chng_dt=None):
    """1~1000 범위로 호출하여 total_count + rows 반환"""
    block = fetch(1, 1000, chng_dt=chng_dt)
    if not block:
        return 0, []
    code = block.get("RESULT", {}).get("CODE", "")
    if code == "INFO-200":
        return 0, []
    if code != "INFO-000":
        return -1, []
    total = int(block.get("total_count", "0"))
    rows = block.get("row", [])
    return total, rows


print("=" * 70)
print("I2500 CHNG_DT 최종 검증 v3")
print(f"API 키: {len(API_KEYS)}개, 살아있는 키: {alive_keys()}개")
print("=" * 70)


# ══════════════════════════════════════════════════════════════════════
# PHASE 1: "이후" 의미 검증 — 날짜별 total_count 비교
# 만약 "이후" = inclusive라면: 과거날짜 total > 최신날짜 total
# ══════════════════════════════════════════════════════════════════════
print("\n" + "─" * 70)
print("PHASE 1: '이후' 의미 검증 — 날짜별 total_count (1~1000 페이지)")
print("         과거 → 최신 순으로 조회. '이후'면 과거가 더 커야 함")
print("─" * 70)

test_dates = [
    ("20250101", "작년초"),
    ("20260101", "올해초"),
    ("20260505", "어린이날"),
    ("20260517", "그저께 토"),
    ("20260518", "어제 일"),
    ("20260519", "오늘 월"),
]

date_results = {}
for dt, label in test_dates:
    if alive_keys() < 1:
        print(f"  ⛔ 키 소진 — 테스트 중단")
        break
    
    total, rows = get_total_and_rows(chng_dt=dt)
    date_results[dt] = {"total": total, "rows": rows, "count": len(rows)}
    
    if total >= 0:
        first_lcns = rows[0].get("LCNS_NO", "?") if rows else "N/A"
        last_lcns = rows[-1].get("LCNS_NO", "?") if rows else "N/A"
        print(f"  CHNG_DT={dt} ({label}): total={total:,}, 반환={len(rows)}건")
        print(f"    첫건: {first_lcns} | 끝건: {last_lcns}")
    else:
        print(f"  CHNG_DT={dt} ({label}): 실패")
    
    time.sleep(0.3)

# 필터 없이도 조회
if alive_keys() >= 1:
    total_nf, rows_nf = get_total_and_rows()
    date_results["none"] = {"total": total_nf, "rows": rows_nf, "count": len(rows_nf)}
    print(f"\n  필터없음: total={total_nf:,}, 반환={len(rows_nf)}건")
    if rows_nf:
        print(f"    첫건: {rows_nf[0].get('LCNS_NO')} | 끝건: {rows_nf[-1].get('LCNS_NO')}")

# 분석
print(f"\n  📊 total_count 비교 (endIdx=1000으로 고정):")
valid_dates = [(dt, d) for dt, d in sorted(date_results.items()) if d["total"] > 0 and dt != "none"]
for dt, d in valid_dates:
    label = next((l for _d, l in test_dates if _d == dt), dt)
    bar = "█" * min(d["count"] // 20, 50)
    print(f"    {dt} ({label:6s}): {d['count']:>5,}건 {bar}")

if len(valid_dates) >= 2:
    first_dt, first_d = valid_dates[0]
    last_dt, last_d = valid_dates[-1]
    if first_d["count"] > last_d["count"]:
        print(f"\n  ✅ 과거({first_dt}) {first_d['count']:,}건 > 최신({last_dt}) {last_d['count']:,}건")
        print(f"     → '이후' = 해당일 포함 이후 전체. 확인!")
    elif first_d["count"] == last_d["count"]:
        print(f"\n  ⚠️ 과거와 최신 동일 건수 → 전체 레코드가 1000건 이하이거나 total_count가 요청범위에 제한됨")
    else:
        print(f"\n  ❓ 과거 < 최신 → 예상과 다름, 추가 분석 필요")


# ══════════════════════════════════════════════════════════════════════
# PHASE 2: CHNG_DT=오늘 full pagination (1000건씩)
# ══════════════════════════════════════════════════════════════════════
print("\n" + "─" * 70)
print("PHASE 2: CHNG_DT=오늘(20260519) full pagination (1000건/페이지)")
print("─" * 70)

today = "20260519"
today_data = date_results.get(today, {})
first_page_count = today_data.get("count", 0)
all_today_rows = list(today_data.get("rows", []))

print(f"  1페이지(1~1000): {first_page_count}건 (이미 수집)")

if first_page_count >= 1000:
    # 추가 페이지 필요
    page = 2
    while alive_keys() >= 1:
        start = (page - 1) * 1000 + 1
        end = page * 1000
        block = fetch(start, end, chng_dt=today)
        time.sleep(0.3)
        
        if not block:
            print(f"  {page}페이지({start}~{end}): 실패")
            break
        
        code = block.get("RESULT", {}).get("CODE", "")
        if code == "INFO-200":
            print(f"  {page}페이지({start}~{end}): 데이터 없음 → 끝")
            break
        
        rows = block.get("row", [])
        all_today_rows.extend(rows)
        print(f"  {page}페이지({start}~{end}): {len(rows)}건")
        
        if len(rows) < 1000:
            print(f"  → 마지막 페이지 (반환 {len(rows)} < 1000)")
            break
        
        page += 1
        
        if page > 20:  # 안전장치
            print(f"  ⚠️ 20페이지 초과 → 중단")
            break
else:
    print(f"  → 1000건 미만이므로 추가 페이지 없음")

print(f"\n  📦 CHNG_DT=오늘 전체 수집: {len(all_today_rows)}건")

# 고유 LCNS 확인
today_lcns = list(set(r.get("LCNS_NO") for r in all_today_rows if r.get("LCNS_NO")))
print(f"  고유 LCNS: {len(today_lcns)}개")

# 정렬 확인
if len(all_today_rows) > 1:
    lcns_list = [r.get("LCNS_NO", "") for r in all_today_rows]
    is_sorted_asc = all(lcns_list[i] <= lcns_list[i+1] for i in range(len(lcns_list)-1))
    is_sorted_desc = all(lcns_list[i] >= lcns_list[i+1] for i in range(len(lcns_list)-1))
    print(f"  정렬: {'오름차순' if is_sorted_asc else '내림차순' if is_sorted_desc else '무작위'}")


# ══════════════════════════════════════════════════════════════════════
# PHASE 3: 공휴일/주말 검증
# ══════════════════════════════════════════════════════════════════════
print("\n" + "─" * 70)
print("PHASE 3: 공휴일/주말 데이터 존재 여부")
print("─" * 70)

for dt, label in test_dates:
    d = date_results.get(dt, {})
    if d.get("count", 0) > 0:
        # 공휴일 표시
        is_holiday = dt in ["20260505"]
        is_weekend = dt in ["20260517", "20260518"]  # 토, 일
        tag = " 🎌공휴일" if is_holiday else " 📅주말" if is_weekend else " 📅평일"
        print(f"  {dt} ({label}){tag}: {d['count']:,}건 데이터 있음 ✅")
    else:
        print(f"  {dt} ({label}): 데이터 없음")


# ══════════════════════════════════════════════════════════════════════
# PHASE 4: CHNG_DT=오늘 전체 데이터 vs DB 교차 분포
# ══════════════════════════════════════════════════════════════════════
print("\n" + "─" * 70)
print("PHASE 4: I2500 CHNG_DT=오늘 전체 vs DB 교차 분포")
print("─" * 70)

if today_lcns:
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    
    # DB에서 일치하는 LCNS 조회
    db_map = {}  # lcns → [event_dates]
    for i in range(0, len(today_lcns), 500):
        batch = today_lcns[i:i+500]
        ph = ",".join(["?"] * len(batch))
        rows_db = conn.execute(
            f"SELECT license_no, last_event_date, business_name FROM businesses "
            f"WHERE license_no IN ({ph}) ORDER BY license_no, last_event_date DESC",
            batch
        ).fetchall()
        for r in rows_db:
            lcns = r["license_no"]
            if lcns not in db_map:
                db_map[lcns] = []
            db_map[lcns].append({
                "event_date": r["last_event_date"],
                "name": r["business_name"],
            })
    
    found_in_db = len(db_map)
    not_in_db = len(today_lcns) - found_in_db
    
    # 이벤트 날짜별 분포
    event_date_dist = {}
    for lcns, entries in db_map.items():
        for e in entries:
            ed = e["event_date"]
            event_date_dist[ed] = event_date_dist.get(ed, 0) + 1
    
    print(f"  I2500 오늘 변동: {len(today_lcns)}개 고유 LCNS")
    print(f"  DB에 존재:      {found_in_db}개 ({found_in_db*100//max(len(today_lcns),1)}%)")
    print(f"  DB에 없음:      {not_in_db}개 ({not_in_db*100//max(len(today_lcns),1)}%)")
    
    # 이력 건수 분포
    history_counts = {}
    for lcns, entries in db_map.items():
        cnt = len(entries)
        history_counts[cnt] = history_counts.get(cnt, 0) + 1
    
    print(f"\n  📊 DB 이력 건수 분포 (DB에 있는 {found_in_db}건):")
    for cnt in sorted(history_counts.keys()):
        print(f"    {cnt}건 이력: {history_counts[cnt]}개 업소")
    
    # event_date 분포 (최근 10개)
    print(f"\n  📊 DB event_date 분포 (상위 10):")
    sorted_dates = sorted(event_date_dist.items(), key=lambda x: x[1], reverse=True)[:10]
    for ed, cnt in sorted_dates:
        print(f"    {ed}: {cnt}건")
    
    # 20260519 이미 있는 건
    today_in_db = event_date_dist.get("20260519", 0)
    print(f"\n  🔑 event_date=20260519 이미 DB에 저장: {today_in_db}건")
    
    # 샘플 5건 (DB에 있는 것)
    print(f"\n  📋 샘플 (DB에 있는 건, 상세):")
    shown = 0
    for lcns, entries in list(db_map.items()):
        if shown >= 5:
            break
        api_row = next((r for r in all_today_rows if r.get("LCNS_NO") == lcns), None)
        api_name = api_row.get("BSSH_NM", "?") if api_row else "?"
        db_dates = [e["event_date"] for e in entries]
        print(f"    {lcns} | I2500:{api_name}")
        print(f"      DB이력: {db_dates}")
        shown += 1
    
    # 샘플 3건 (DB에 없는 것)
    print(f"\n  📋 샘플 (DB에 없는 건):")
    shown = 0
    for lcns in today_lcns:
        if lcns not in db_map and shown < 3:
            api_row = next((r for r in all_today_rows if r.get("LCNS_NO") == lcns), None)
            if api_row:
                print(f"    {lcns} | {api_row.get('BSSH_NM','?')} | PRMS_DT={api_row.get('PRMS_DT','?')}")
            shown += 1
    
    conn.close()
else:
    print("  ⚠️ 오늘 데이터 없음 → 교차검증 스킵")


# ══════════════════════════════════════════════════════════════════════
# PHASE 5: "이후" 최종 확인 — 큰 범위(1~100000)로 total_count 비교
# ══════════════════════════════════════════════════════════════════════
print("\n" + "─" * 70)
print("PHASE 5: 큰 범위(1~100000)로 진짜 total_count 확인")
print("─" * 70)

if alive_keys() >= 2:
    # 오늘 (큰 범위)
    block_big_today = fetch(1, 100000, chng_dt="20260519")
    time.sleep(0.3)
    
    if block_big_today and block_big_today.get("RESULT", {}).get("CODE") == "INFO-000":
        big_total_today = int(block_big_today.get("total_count", "0"))
        big_rows_today = len(block_big_today.get("row", []))
        print(f"  CHNG_DT=20260519, 1~100000: total_count={big_total_today:,}, 반환={big_rows_today:,}건")
    else:
        print(f"  CHNG_DT=20260519 큰 범위 실패")
        big_total_today = 0
    
    # 작년초 (큰 범위) — "이후"면 훨씬 클 것
    block_big_past = fetch(1, 100000, chng_dt="20250101")
    time.sleep(0.3)
    
    if block_big_past and block_big_past.get("RESULT", {}).get("CODE") == "INFO-000":
        big_total_past = int(block_big_past.get("total_count", "0"))
        big_rows_past = len(block_big_past.get("row", []))
        print(f"  CHNG_DT=20250101, 1~100000: total_count={big_total_past:,}, 반환={big_rows_past:,}건")
    else:
        print(f"  CHNG_DT=20250101 큰 범위 실패")
        big_total_past = 0
    
    if big_total_today > 0 and big_total_past > 0:
        if big_total_past > big_total_today:
            print(f"\n  ✅ 작년초({big_total_past:,}) > 오늘({big_total_today:,})")
            print(f"     → '이후' = 해당일 포함, 누적 합산 확인!")
            print(f"     → 작년초 - 오늘 = {big_total_past - big_total_today:,}건 (작년 변동분)")
        elif big_total_past == big_total_today:
            print(f"\n  🤔 동일 건수 → 둘 다 같은 데이터셋 반환?")
        else:
            print(f"\n  ❓ 오늘 > 작년초 → 예상 밖")
else:
    print(f"  ⚠️ 키 부족 ({alive_keys()}개) → 스킵")


# ── 최종 요약 ──
print("\n" + "=" * 70)
print(f"최종 요약")
print("=" * 70)
print(f"  API 호출: {call_count}회")
print(f"  키 상태: {alive_keys()}/{len(API_KEYS)}개 생존")
print(f"  CHNG_DT=오늘 수집: {len(all_today_rows)}건")
if today_lcns:
    found_in_db = len([l for l in today_lcns if l in db_map]) if 'db_map' in dir() else 0
    print(f"  DB 교차: {found_in_db}/{len(today_lcns)} ({found_in_db*100//max(len(today_lcns),1)}%)")
print("=" * 70)
