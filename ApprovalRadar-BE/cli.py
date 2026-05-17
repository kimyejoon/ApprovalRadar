import asyncio
import argparse
import sys
import os
import shutil
import datetime
import sqlite3

# app 모듈 경로 인식
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app.clients.foodsafety_api import ApiClient
from app.services.diff_crawler import DiffCrawlerEngine

def check_keys():
    print("API 키 상태를 점검합니다...")
    async def _run():
        async with ApiClient() as client:
            await client.check_keys_status()
    asyncio.run(_run())

def test_tail():
    import time
    print("현재 데이터의 꼬리(Tail) 지점을 조회합니다 (서비스별 최적 전략)...")
    print("(I2500은 Backfill 전용 단건 조회 API이므로 tail 스캔 대상 아님)")
    async def _run():
        async with ApiClient() as client:
            services = ["I2859", "I2861"]
            for i, service_id in enumerate(services):
                if i > 0:
                    print(f"  (다음 서비스 전 3초 대기 - WAF 방지)")
                    await asyncio.sleep(3)
                crawler = DiffCrawlerEngine(api_client=client, service_id=service_id)
                tail = await crawler.find_true_tail()
                print(f"  [{service_id}] 현재 전체 데이터 건수: {tail:,}건")
    asyncio.run(_run())
    print("\n✅ 조회 완료")

def run_sync():
    print("수동으로 차분 동기화(Delta Sync)를 1회 실행합니다...")
    from scraper import run_all_scrapers
    asyncio.run(run_all_scrapers())


def run_backfill():
    print("DB에 누락된 세부업종 데이터를 단건 조회를 통해 채워넣습니다(Backfill)...")
    from app.services.industry_filler import fill_missing_industry_types
    fill_missing_industry_types()

def test_stream_update():
    print("가상의 SSE 업데이트 이벤트를 트리거합니다...")
    try:
        import requests
        response = requests.post("http://localhost:8000/api/v1/stream/test-trigger")
        if response.status_code == 200:
            print("✅ SSE 이벤트 브로드캐스트 트리거 성공!")
        else:
            print(f"❌ 트리거 실패 (Status: {response.status_code})")
    except Exception as e:
        print(f"❌ 요청 중 오류 발생: {e}\n(서버가 http://localhost:8000 에서 켜져있는지 확인해주세요)")


# ─── Full-Scan Init ────────────────────────────────────────────────────────────

def reset_state(services: list | None = None):
    """crawler_state 테이블만 리셋합니다. businesses 데이터는 보존합니다."""
    from database import DB_FILE, init_db
    init_db()
    services = services or ["I2859", "I2861"]

    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    try:
        for svc in services:
            conn.execute(
                "INSERT OR REPLACE INTO crawler_state (service_id, last_total_count, pivots, updated_at) VALUES (?, 0, '{}', ?)",
                (svc, datetime.datetime.now().isoformat())
            )
        conn.commit()
        print(f"✅ crawler_state 리셋 완료: {', '.join(services)}")
        print("   다음 크롤링 주기에 자동으로 bootstrap이 실행됩니다.")
    finally:
        conn.close()


def full_scan_init(no_backup: bool = False, services: list | None = None):
    """
    DB를 완전 초기화하고 전체 bootstrap을 재실행합니다.
    - businesses, api_raw_data, crawler_state 초기화
    - 서비스별 find_true_tail + bootstrap 순차 실행
    - API 호출 횟수 실측 보고
    """
    from database import DB_FILE, init_db
    init_db()

    services = services or ["I2859", "I2861"]
    svc_names = {"I2859": "식품업소 인허가변경", "I2861": "음식점업소 인허가변경"}

    # ① 확인 프롬프트
    print("\n" + "=" * 60)
    print("⚠️  경고: Full-Scan Init을 시작하려 합니다.")
    print("=" * 60)
    print("아래 테이블의 모든 데이터가 삭제됩니다:")
    print("  - businesses       (모든 인허가 변동 기록)")
    print("  - api_raw_data     (원본 API JSON 캐시)")
    print("  - crawler_state    (피벗/Tail 상태)")
    print(f"  대상 서비스: {', '.join(f'{s}({svc_names.get(s, s)})' for s in services)}")
    print()
    confirm = input("계속하시겠습니까? (yes/no): ").strip().lower()
    if confirm != "yes":
        print("✋ 작업을 취소했습니다.")
        return

    # ② DB 백업
    if not no_backup:
        try:
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = DB_FILE.replace(".db", f"_backup_{ts}.db")
            shutil.copy2(DB_FILE, backup_path)
            print(f"\n💾 DB 백업 완료: {backup_path}")
        except Exception as e:
            print(f"⚠️  DB 백업 실패 (계속 진행): {e}")
    else:
        print("\n(백업 스킵)")

    # ③ DB 초기화
    print("\n🗑  DB 초기화 중...")
    conn = sqlite3.connect(DB_FILE)
    try:
        # 특정 서비스만 리셋하는 경우는 businesses 전체 삭제 없이 state만
        if set(services) == {"I2859", "I2861"}:
            conn.execute("DELETE FROM businesses")
            conn.execute("DELETE FROM api_raw_data")
            print("   ✓ businesses, api_raw_data 초기화")
        for svc in services:
            conn.execute("DELETE FROM crawler_state WHERE service_id = ?", (svc,))
        conn.execute("VACUUM")
        conn.commit()
        print("   ✓ crawler_state 초기화 + VACUUM 완료")
    finally:
        conn.close()

    # ④ 서비스별 bootstrap 실행
    total_start = datetime.datetime.now()
    summary = []

    async def _run_bootstrap():
        async with ApiClient() as client:
            for i, svc in enumerate(services):
                if i > 0:
                    print(f"\n   (다음 서비스 전 5초 대기 - WAF 방지)")
                    await asyncio.sleep(5)

                print(f"\n{'─' * 50}")
                print(f"🚀 [{svc}] {svc_names.get(svc, svc)} Bootstrap 시작...")
                print(f"{'─' * 50}")

                call_count_before = client.get_total_call_count() if hasattr(client, 'get_total_call_count') else 0

                crawler = DiffCrawlerEngine(api_client=client, service_id=svc)
                state = await crawler.bootstrap()

                call_count_after = client.get_total_call_count() if hasattr(client, 'get_total_call_count') else 0
                calls_used = call_count_after - call_count_before

                pivot_count = len(state.get("pivots", {}))
                tail = state.get("last_total_count", 0)
                summary.append((svc, tail, pivot_count, calls_used))

                print(f"✅ [{svc}] 완료: tail={tail:,}건 / 피벗 {pivot_count}개 / API {calls_used}회 호출")

    asyncio.run(_run_bootstrap())

    # ⑤ 완료 보고
    elapsed = (datetime.datetime.now() - total_start).total_seconds()
    total_calls = sum(s[3] for s in summary)

    print(f"\n{'=' * 60}")
    print("✅ Full-Scan Init 완료!")
    print(f"{'=' * 60}")
    for svc, tail, pivots, calls in summary:
        print(f"  [{svc}] tail={tail:,}건 / 피벗 {pivots}개 / API {calls}회")
    print(f"\n  총 API 호출: {total_calls}회 / 5,000회 한도 ({total_calls / 50:.1f}% 사용)")
    print(f"  소요 시간: {elapsed:.1f}초")
    print()
    print("이제 정상적인 차분 동기화를 시작하세요:")
    print("  python cli.py --run-sync    # 수동 1회 실행")
    print("  uvicorn main:app ...        # 자동 30분 주기 크롤링 시작")


# ─── CLI Entry Point ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ApprovalRadar Backend CLI Tools")
    parser.add_argument("--check-keys", action="store_true", help="등록된 API 키들의 유효성 및 한도 초과 여부를 점검합니다.")
    parser.add_argument("--test-tail", action="store_true", help="현재 외부 API 데이터의 총 건수(Tail) 위치를 이진 탐색으로 확인합니다.")
    parser.add_argument("--run-sync", action="store_true", help="수동으로 1회 크롤링(차분 동기화)을 실행하여 DB에 반영합니다.")
    parser.add_argument("--backfill", action="store_true", help="누락된 세부업종(industry_type) 데이터를 공공API 단건 조회를 통해 채웁니다.")
    parser.add_argument("--test-stream-update", action="store_true", help="로컬 서버에 가상의 업데이트 신호를 발생시켜 SSE 이벤트를 테스트합니다.")
    parser.add_argument(
        "--full-scan-init",
        action="store_true",
        help="⚠️ DB를 완전 초기화하고 전체 bootstrap을 재실행합니다. (확인 프롬프트 포함)"
    )
    parser.add_argument(
        "--reset-state",
        action="store_true",
        help="businesses 데이터는 보존하고 crawler_state(피벗/Tail)만 리셋합니다."
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="--full-scan-init 시 DB 백업을 건너뜁니다."
    )
    parser.add_argument(
        "--service",
        type=str,
        default=None,
        help="특정 서비스 ID만 대상으로 합니다. (예: --service I2859)"
    )

    args = parser.parse_args()

    # --service 파싱
    target_services = [args.service] if args.service else None

    if args.check_keys:
        check_keys()
    elif args.test_tail:
        test_tail()
    elif args.run_sync:
        run_sync()
    elif args.backfill:
        run_backfill()
    elif args.test_stream_update:
        test_stream_update()
    elif args.full_scan_init:
        full_scan_init(no_backup=args.no_backup, services=target_services)
    elif args.reset_state:
        reset_state(services=target_services)
    else:
        parser.print_help()
