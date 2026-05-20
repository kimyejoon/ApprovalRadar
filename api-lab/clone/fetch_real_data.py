"""
clone/fetch_real_data.py — 실제 식품안전나라 I2861 API 클론 수집기

1~5000 범위를 1000건씩 5페이지로 호출하여 lab.db에 저장한다.
★ 각 페이지의 total_count를 api_page_log에 기록 (역공학 핵심 데이터)

사용법:
    python clone/fetch_real_data.py
    python clone/fetch_real_data.py --key YOUR_API_KEY
    python clone/fetch_real_data.py --key YOUR_API_KEY --max-idx 5000 --page-size 1000
    python clone/fetch_real_data.py --extra CHNG_DT=20260520   # CHNG_DT 필터 포함 클론
"""
import argparse
import httpx
import json
import os
import sys
import time
import datetime

# 상위 디렉토리 경로 추가 (db/schema.py import용)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.schema import get_conn, init_db, LAB_DB, print_stats

BASE_URL = "http://openapi.foodsafetykorea.go.kr/api"
SERVICE_ID = "I2861"
DATA_TYPE = "json"

# ── 기본 API 키 (환경변수 또는 .env에서 로드) ──────────────────────────────
def _load_default_key() -> str:
    # 1순위: 환경변수
    key = os.environ.get("FOOD_SAFETY_API_KEY_1") or os.environ.get("FOOD_SAFETY_API_KEY")
    if key:
        return key
    # 2순위: 상위 .env 파일
    env_paths = [
        os.path.join(os.path.dirname(__file__), "..", "..", "ApprovalRadar-BE", ".env"),
        os.path.join(os.path.dirname(__file__), "..", ".env"),
    ]
    for env_path in env_paths:
        if os.path.exists(env_path):
            with open(env_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("FOOD_SAFETY_API_KEY_1=") or line.startswith("FOOD_SAFETY_API_KEY="):
                        return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def fetch_page(
    client: httpx.Client,
    api_key: str,
    start: int,
    end: int,
    extra_params: dict | None = None,
    timeout: int = 60,
) -> tuple[dict | None, int]:
    """
    단일 페이지 API 호출.
    Returns: (block_dict, elapsed_ms)
      block_dict: None이면 실패
    """
    url = f"{BASE_URL}/{api_key}/{SERVICE_ID}/{DATA_TYPE}/{start}/{end}"
    if extra_params:
        url += "/" + "&".join(f"{k}={v}" for k, v in extra_params.items())

    t0 = time.time()
    try:
        resp = client.get(url, timeout=timeout)
        elapsed_ms = int((time.time() - t0) * 1000)
        resp.raise_for_status()

        # WAF 차단 감지
        if "alert(" in resp.text or "<script" in resp.text.lower():
            print(f"  ⚠ WAF 차단 의심 — {url[:80]}")
            return None, elapsed_ms

        data = resp.json()
        if SERVICE_ID not in data:
            print(f"  ⚠ 알 수 없는 응답 형식: {list(data.keys())}")
            return None, elapsed_ms

        return data[SERVICE_ID], elapsed_ms

    except httpx.TimeoutException:
        elapsed_ms = int((time.time() - t0) * 1000)
        print(f"  ⚠ 타임아웃 ({timeout}s 초과): start={start}")
        return None, elapsed_ms
    except Exception as e:
        elapsed_ms = int((time.time() - t0) * 1000)
        print(f"  ⚠ 오류: {e}")
        return None, elapsed_ms


def run_clone(
    api_key: str,
    max_idx: int = 5000,
    page_size: int = 1000,
    extra_params: dict | None = None,
    gap_sec: float = 0.3,
    timeout: int = 60,
    db_path: str = LAB_DB,
):
    """
    실제 API에서 1~max_idx 범위를 page_size씩 호출하여 db_path에 저장.
    """
    init_db(db_path)
    conn = get_conn(db_path)

    pages = []
    start = 1
    while start <= max_idx:
        end = min(start + page_size - 1, max_idx)
        pages.append((start, end))
        start += page_size

    total_inserted = 0
    total_pages = len(pages)
    extra_label = json.dumps(extra_params, ensure_ascii=False) if extra_params else "없음"

    print(f"\n{'='*60}")
    print(f"  식품안전나라 I2861 클론 수집 시작")
    print(f"{'='*60}")
    print(f"  범위: 1 ~ {max_idx} ({total_pages}페이지, {page_size}건/페이지)")
    print(f"  API 키: {api_key[:5]}***{api_key[-3:]}")
    print(f"  추가 파라미터: {extra_label}")
    print(f"  저장 DB: {db_path}")
    print(f"{'='*60}\n")

    with httpx.Client(follow_redirects=True, headers={"Accept": "application/json"}) as client:
        for page_num, (start, end) in enumerate(pages, 1):
            print(f"  [{page_num}/{total_pages}] 페이지 {start}~{end} 호출 중...", end=" ", flush=True)

            block, elapsed_ms = fetch_page(client, api_key, start, end, extra_params, timeout)

            if block is None:
                print(f"실패 ({elapsed_ms}ms)")
                # page_log에 실패 기록
                conn.execute("""
                    INSERT INTO api_page_log
                    (service_id, start_idx, end_idx, total_count, returned_count, result_code, elapsed_ms, chng_dt_filter)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (SERVICE_ID, start, end, None, 0, "FAILED", elapsed_ms,
                      extra_params.get("CHNG_DT") if extra_params else None))
                conn.commit()
                time.sleep(gap_sec * 3)
                continue

            result_code = block.get("RESULT", {}).get("CODE", "")
            total_count_raw = block.get("total_count")
            try:
                total_count = int(total_count_raw) if total_count_raw is not None else None
            except (ValueError, TypeError):
                total_count = None

            rows = block.get("row", [])
            returned_count = len(rows)

            # ── api_page_log 기록 (★ total_count 추적 핵심) ──
            conn.execute("""
                INSERT INTO api_page_log
                (service_id, start_idx, end_idx, total_count, returned_count, result_code, elapsed_ms, chng_dt_filter)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (SERVICE_ID, start, end, total_count, returned_count, result_code, elapsed_ms,
                  extra_params.get("CHNG_DT") if extra_params else None))
            conn.commit()

            if result_code == "INFO-200":
                print(f"데이터 없음 (INFO-200, total={total_count}, {elapsed_ms}ms)")
                continue

            if result_code != "INFO-000":
                print(f"오류 코드: {result_code} ({elapsed_ms}ms)")
                continue

            print(f"✅ {returned_count:,}건 | total_count={total_count:,} | {elapsed_ms}ms", end="")

            # ── cloned_businesses에 삽입 ──
            insert_count = 0
            for pos, row in enumerate(rows):
                raw_json = json.dumps(row, ensure_ascii=False)
                try:
                    conn.execute("""
                        INSERT INTO cloned_businesses
                        (api_start_idx, api_row_pos, api_total_count,
                         LCNS_NO, BSSH_NM, SITE_ADDR, SITE_ADDR_RDN, PRSDNT_NM,
                         TELNO, INDUTY_CD_NM, PRMS_DT, BSN_STATE_NM, CHNG_DT, raw_json)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        start, pos, total_count,
                        row.get("LCNS_NO"),
                        row.get("BSSH_NM"),
                        row.get("SITE_ADDR"),
                        row.get("SITE_ADDR_RDN"),
                        row.get("PRSDNT_NM"),
                        row.get("TELNO"),
                        row.get("INDUTY_CD_NM"),
                        row.get("PRMS_DT"),
                        row.get("BSN_STATE_NM"),
                        row.get("CHNG_DT"),
                        raw_json,
                    ))
                    insert_count += 1
                except Exception as e:
                    print(f"\n  ⚠ 삽입 오류: {e} (row={row.get('LCNS_NO')})")

            conn.commit()
            total_inserted += insert_count
            print(f" → 저장 {insert_count:,}건")

            # 페이지 간 갭 (WAF 방지)
            time.sleep(gap_sec)

    conn.close()

    print(f"\n{'='*60}")
    print(f"  수집 완료")
    print(f"{'='*60}")
    print(f"  총 저장: {total_inserted:,}건 / {total_pages}페이지")
    print(f"  DB: {db_path}")
    print(f"{'='*60}")

    print_stats(db_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="식품안전나라 I2861 API 클론 수집기")
    parser.add_argument("--key", type=str, default="", help="API 키 (기본: .env에서 로드)")
    parser.add_argument("--max-idx", type=int, default=5000, help="최대 endIdx (기본: 5000)")
    parser.add_argument("--page-size", type=int, default=1000, help="페이지 크기 (기본: 1000)")
    parser.add_argument("--gap", type=float, default=0.3, help="페이지 간 대기 시간 초 (기본: 0.3)")
    parser.add_argument("--timeout", type=int, default=60, help="API 타임아웃 초 (기본: 60)")
    parser.add_argument("--extra", type=str, default="", help="추가 파라미터 (예: CHNG_DT=20260520)")
    parser.add_argument("--db", type=str, default=LAB_DB, help="저장 DB 경로")
    args = parser.parse_args()

    api_key = args.key or _load_default_key()
    if not api_key:
        print("[error] API 키가 없습니다. --key 옵션이나 .env 파일에 FOOD_SAFETY_API_KEY_1을 설정하세요.")
        sys.exit(1)

    extra = {}
    if args.extra:
        for param in args.extra.split("&"):
            if "=" in param:
                k, v = param.split("=", 1)
                extra[k.strip()] = v.strip()

    run_clone(
        api_key=api_key,
        max_idx=args.max_idx,
        page_size=args.page_size,
        extra_params=extra or None,
        gap_sec=args.gap,
        timeout=args.timeout,
        db_path=args.db,
    )
