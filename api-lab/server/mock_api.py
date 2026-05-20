"""
server/mock_api.py — 식품안전나라 API 모방 Mock 서버

실제 API와 완전히 동일한 URL 패턴 + 응답 형식으로 서빙.
★ 핵심: total_count 계산 방식 / 정렬 기준을 실험적으로 변경 가능.

실행:
    uvicorn server.mock_api:app --reload --port 8001

또는:
    python server/mock_api.py

API 호출 예시:
    GET http://localhost:8001/api/test/I2861/json/1/1000
    GET http://localhost:8001/api/test/I2861/json/1/1000/CHNG_DT=20260520
    GET http://localhost:8001/api/test/I2861/json/1/1/LCNS_NO=1234567890

설정 변경 (GET /config):
    GET http://localhost:8001/config
    POST http://localhost:8001/config  (JSON body)
"""
import json
import os
import sys
import datetime
import sqlite3

# 상위 경로 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.schema import get_conn, LAB_DB

try:
    from fastapi import FastAPI, Path, Query
    from fastapi.responses import JSONResponse
    import uvicorn
except ImportError:
    print("[error] fastapi/uvicorn 미설치 — pip install fastapi uvicorn")
    sys.exit(1)

app = FastAPI(
    title="식품안전나라 API Mock 서버",
    description="실제 openapi.foodsafetykorea.go.kr를 로컬에서 모방하는 실험용 서버",
    version="1.0.0",
)

# ─────────────────────────────────────────────────────────────────────────────
# ★ 핵심 실험 설정 — 이 값을 바꾸면서 패턴 재현 실험 수행
# ─────────────────────────────────────────────────────────────────────────────
CONFIG = {
    # total_count 계산 방식
    # "full"    → 전체 테이블 COUNT(*) (조건 무관)
    # "range"   → WHERE row_id BETWEEN startIdx AND endIdx COUNT — 가설 B
    # "filter"  → 조건 필터 후 COUNT(*) — 가설 C
    "total_count_mode": "filter",

    # 정렬 기준
    # "none"       → ORDER BY 없음 (SQLite 내부 B-Tree 순서 = row_id 오름차순)
    # "row_id_asc" → ORDER BY row_id ASC (삽입 순서)
    # "row_id_desc"→ ORDER BY row_id DESC (역삽입 순서 — 최신이 먼저)
    # "chng_dt_desc"→ ORDER BY CHNG_DT DESC (최신 변경일 먼저 — ★ 유력 가설)
    # "chng_dt_asc" → ORDER BY CHNG_DT ASC
    # "lcns_no_asc" → ORDER BY LCNS_NO ASC
    "sort_mode": "row_id_asc",

    # CHNG_DT 시간 필터 (실제 API는 19:00 이전 오늘 데이터 제거)
    "chng_dt_time_filter": True,      # True = 19:00 이전 오늘 날짜 숨김
    "chng_dt_hide_hour": 19,          # 이 시간 이전이면 오늘 데이터 숨김

    # CHNG_DT 파라미터 해석
    # "exact" → 정확히 해당 날짜만 (WHERE chng_dt = ?)
    # "after" → 해당 날짜 이후 전체 (WHERE chng_dt >= ?) — API 스펙 설명
    "chng_dt_filter_mode": "after",

    # 페이지 Gap 재현 (삭제된 row_id 시뮬레이션)
    # True이면 row_id BETWEEN 으로 처리 (실제 건수 < 페이지 크기 발생 가능)
    "simulate_gaps": False,

    # 사용 DB 경로
    "db_path": LAB_DB,
}


def _get_conn() -> sqlite3.Connection:
    return get_conn(CONFIG["db_path"])


def _build_order_by() -> str:
    mode = CONFIG["sort_mode"]
    return {
        "none": "",
        "row_id_asc": "ORDER BY row_id ASC",
        "row_id_desc": "ORDER BY row_id DESC",
        "chng_dt_desc": "ORDER BY CHNG_DT DESC",
        "chng_dt_asc": "ORDER BY CHNG_DT ASC",
        "lcns_no_asc": "ORDER BY LCNS_NO ASC",
        "api_original": "ORDER BY api_start_idx ASC, api_row_pos ASC",  # 원본 API 순서
    }.get(mode, "")


def _should_hide_today() -> bool:
    """현재 시각이 설정된 hide_hour 미만이면 오늘 데이터 숨김."""
    if not CONFIG["chng_dt_time_filter"]:
        return False
    return datetime.datetime.now().hour < CONFIG["chng_dt_hide_hour"]


def _build_query(
    start_idx: int,
    end_idx: int,
    lcns_no: str | None = None,
    chng_dt: str | None = None,
    bssh_nm: str | None = None,
) -> tuple[str, list, str, list]:
    """
    SELECT 및 COUNT 쿼리 생성.

    Returns:
        (data_sql, data_params, count_sql, count_params)
    """
    today_str = datetime.date.today().strftime("%Y%m%d")
    hide_today = _should_hide_today()

    # ── 공통 WHERE 조건 ──────────────────────────────────────────────
    conditions = []
    params = []

    # LCNS_NO 필터
    if lcns_no:
        conditions.append("LCNS_NO = ?")
        params.append(lcns_no)

    # BSSH_NM 필터
    if bssh_nm:
        conditions.append("BSSH_NM LIKE ?")
        params.append(f"%{bssh_nm}%")

    # CHNG_DT 파라미터 필터
    if chng_dt:
        if CONFIG["chng_dt_filter_mode"] == "exact":
            conditions.append("CHNG_DT = ?")
            params.append(chng_dt)
        else:  # "after" — 해당일 이후 전체
            conditions.append("CHNG_DT >= ?")
            params.append(chng_dt)

    # 오늘 데이터 숨김 (19:00 이전 시간 제한)
    if hide_today and not chng_dt:
        # CHNG_DT 파라미터 없을 때만 적용 (CHNG_DT 파라미터 있으면 별도 처리)
        conditions.append("CHNG_DT < ?")
        params.append(today_str)
    elif hide_today and chng_dt and chng_dt == today_str:
        # CHNG_DT=오늘 이면 전체 차단
        conditions.append("1 = 0")  # 항상 False

    where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    # ── total_count 계산 ─────────────────────────────────────────────
    tc_mode = CONFIG["total_count_mode"]

    if tc_mode == "full":
        # 전체 테이블 COUNT (조건 무관)
        count_sql = f"SELECT COUNT(*) FROM cloned_businesses {where_clause}"
        count_params = list(params)

    elif tc_mode == "range":
        # row_id BETWEEN start~end COUNT — 가설 B
        range_conds = list(conditions) + ["row_id BETWEEN ? AND ?"]
        range_params = list(params) + [start_idx, end_idx]
        range_where = "WHERE " + " AND ".join(range_conds) if range_conds else ""
        count_sql = f"SELECT COUNT(*) FROM cloned_businesses {range_where}"
        count_params = range_params

    else:  # "filter"
        # 조건 필터 후 전체 COUNT (CHNG_DT 필터 포함)
        count_sql = f"SELECT COUNT(*) FROM cloned_businesses {where_clause}"
        count_params = list(params)

    # ── 데이터 SELECT (페이지네이션) ──────────────────────────────────
    order_by = _build_order_by()

    if CONFIG["simulate_gaps"]:
        # Gap 재현: row_id BETWEEN으로 실제 start~end 처리
        gap_conds = list(conditions) + ["row_id BETWEEN ? AND ?"]
        gap_params = list(params) + [start_idx, end_idx]
        gap_where = "WHERE " + " AND ".join(gap_conds) if gap_conds else ""
        data_sql = f"""
            SELECT * FROM cloned_businesses
            {gap_where}
            {order_by}
        """
        data_params = gap_params
    else:
        # 정상 페이지네이션: LIMIT/OFFSET
        offset = start_idx - 1
        limit = end_idx - start_idx + 1
        data_sql = f"""
            SELECT * FROM cloned_businesses
            {where_clause}
            {order_by}
            LIMIT ? OFFSET ?
        """
        data_params = list(params) + [limit, offset]

    return data_sql, data_params, count_sql, count_params


def _row_to_api_dict(row: sqlite3.Row) -> dict:
    """cloned_businesses 행을 실제 API 응답 형식으로 변환."""
    return {
        "LCNS_NO": row["LCNS_NO"] or "",
        "BSSH_NM": row["BSSH_NM"] or "",
        "SITE_ADDR": row["SITE_ADDR"] or "",
        "SITE_ADDR_RDN": row["SITE_ADDR_RDN"] or "",
        "PRSDNT_NM": row["PRSDNT_NM"] or "",
        "TELNO": row["TELNO"] or "",
        "INDUTY_CD_NM": row["INDUTY_CD_NM"] or "",
        "PRMS_DT": row["PRMS_DT"] or "",
        "BSN_STATE_NM": row["BSN_STATE_NM"] or "",
        "CHNG_DT": row["CHNG_DT"] or "",
        # 역공학용 추가 필드 (실제 API에는 없음 — 분석용)
        "_row_id": row["row_id"],
        "_api_start_idx": row["api_start_idx"],
        "_api_row_pos": row["api_row_pos"],
    }


# ─────────────────────────────────────────────────────────────────────────────
# API 엔드포인트
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/{key}/{svc}/json/{start}/{end}")
@app.get("/api/{key}/{svc}/json/{start}/{end}/{extra_params:path}")
async def mock_api(
    key: str,
    svc: str,
    start: int,
    end: int,
    extra_params: str = "",
):
    """
    실제 식품안전나라 API와 동일한 응답 형식.
    URL: /api/{key}/{svc}/json/{startIdx}/{endIdx}[/PARAM=VALUE&...]
    """
    # extra_params 파싱 (예: "CHNG_DT=20260520&LCNS_NO=1234")
    params: dict = {}
    if extra_params:
        for part in extra_params.split("&"):
            if "=" in part:
                k, v = part.split("=", 1)
                params[k.strip()] = v.strip()

    lcns_no = params.get("LCNS_NO")
    chng_dt = params.get("CHNG_DT")
    bssh_nm = params.get("BSSH_NM")

    conn = _get_conn()
    try:
        data_sql, data_params, count_sql, count_params = _build_query(
            start, end, lcns_no, chng_dt, bssh_nm
        )

        total_count = conn.execute(count_sql, count_params).fetchone()[0]
        rows = conn.execute(data_sql, data_params).fetchall()

    except Exception as e:
        conn.close()
        return JSONResponse({
            svc: {
                "RESULT": {"CODE": "ERROR-500", "MSG": f"서버 오류: {e}"},
                "total_count": "0",
                "row": [],
            }
        })
    finally:
        conn.close()

    if not rows:
        return JSONResponse({
            svc: {
                "RESULT": {"CODE": "INFO-200", "MSG": "해당하는 데이터가 없습니다."},
                "total_count": str(total_count),
                "row": [],
            }
        })

    return JSONResponse({
        svc: {
            "RESULT": {"CODE": "INFO-000", "MSG": "정상 처리되었습니다."},
            "total_count": str(total_count),
            "row": [_row_to_api_dict(r) for r in rows],
        }
    })


@app.get("/config")
async def get_config():
    """현재 Mock 서버 설정 조회."""
    today = datetime.date.today().strftime("%Y%m%d")
    now_hour = datetime.datetime.now().hour
    return {
        "config": CONFIG,
        "runtime_info": {
            "today": today,
            "current_hour": now_hour,
            "hiding_today_data": _should_hide_today(),
        },
        "available_options": {
            "total_count_mode": ["full", "range", "filter"],
            "sort_mode": ["none", "row_id_asc", "row_id_desc", "chng_dt_desc", "chng_dt_asc", "lcns_no_asc", "api_original"],
            "chng_dt_filter_mode": ["exact", "after"],
        }
    }


@app.post("/config")
async def update_config(body: dict):
    """Mock 서버 설정 변경 (실험 중 동적 변경 가능)."""
    for k, v in body.items():
        if k in CONFIG:
            CONFIG[k] = v
    return {"message": "설정 변경 완료", "config": CONFIG}


@app.get("/stats")
async def get_stats():
    """lab.db 현황 조회."""
    conn = _get_conn()
    try:
        total = conn.execute("SELECT COUNT(*) FROM cloned_businesses").fetchone()[0]
        pages = conn.execute("SELECT COUNT(DISTINCT api_start_idx) FROM cloned_businesses").fetchone()[0]
        chng_dist = conn.execute("""
            SELECT substr(CHNG_DT,1,4) AS yr, COUNT(*) AS cnt
            FROM cloned_businesses
            WHERE CHNG_DT IS NOT NULL
            GROUP BY yr ORDER BY yr DESC LIMIT 10
        """).fetchall()
        page_logs = conn.execute("""
            SELECT start_idx, end_idx, total_count, returned_count, result_code, elapsed_ms
            FROM api_page_log ORDER BY start_idx
        """).fetchall()
        today_str = datetime.date.today().strftime("%Y%m%d")
        today_count = conn.execute(
            "SELECT COUNT(*) FROM cloned_businesses WHERE CHNG_DT = ?", (today_str,)
        ).fetchone()[0]
    finally:
        conn.close()

    return {
        "total_records": total,
        "pages_collected": pages,
        "today_records": today_count,
        "chng_dt_year_distribution": [{"year": r["yr"], "count": r["cnt"]} for r in chng_dist],
        "page_logs": [
            {
                "start_idx": r["start_idx"],
                "end_idx": r["end_idx"],
                "total_count": r["total_count"],
                "returned_count": r["returned_count"],
                "result_code": r["result_code"],
                "elapsed_ms": r["elapsed_ms"],
            }
            for r in page_logs
        ],
        "total_count_analysis": {
            "note": "total_count가 페이지마다 다르면 가설 B (rowid BETWEEN range COUNT) 유력",
            "values": [r["total_count"] for r in page_logs],
            "all_same": len(set(r["total_count"] for r in page_logs if r["total_count"])) <= 1,
        }
    }


@app.get("/")
async def root():
    return {
        "name": "식품안전나라 API Mock 서버",
        "version": "1.0.0",
        "endpoints": {
            "API": "GET /api/{key}/I2861/json/{start}/{end}[/{extra_params}]",
            "설정 조회": "GET /config",
            "설정 변경": "POST /config",
            "DB 통계": "GET /stats",
        },
        "quick_test": "http://localhost:8001/api/test/I2861/json/1/1000",
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--host", type=str, default="127.0.0.1")
    parser.add_argument("--db", type=str, default=LAB_DB)
    args = parser.parse_args()

    CONFIG["db_path"] = args.db

    if not os.path.exists(args.db):
        print(f"[error] DB 없음: {args.db}")
        print("  먼저 실행: python clone/fetch_real_data.py")
        sys.exit(1)

    print(f"\n🚀 Mock API 서버 시작")
    print(f"   URL: http://{args.host}:{args.port}")
    print(f"   DB:  {args.db}")
    print(f"   설정: http://{args.host}:{args.port}/config")
    print(f"   통계: http://{args.host}:{args.port}/stats\n")

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
