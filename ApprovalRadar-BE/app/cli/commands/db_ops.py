import asyncio
import datetime
import sqlite3
import shutil
import os
from app.clients.foodsafety_api import ApiClient

def reset_state(services: list | None = None):
    """crawler_state 테이블만 리셋합니다. businesses 데이터는 보존합니다."""
    from database import DB_FILE, init_db
    init_db()
    services = services or ["I2861"]

    conn = sqlite3.connect(DB_FILE)
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
    DB를 완전 초기화하고 전체 스캔을 재준비합니다.
    - businesses, api_raw_data, crawler_state 초기화
    - I2861 최적화 초기화 세팅
    """
    from database import DB_FILE, init_db
    init_db()

    services = services or ["I2861"]
    svc_names = {"I2861": "음식점업소 인허가변경"}

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
        conn.execute("DELETE FROM businesses")
        conn.execute("DELETE FROM api_raw_data")
        print("   ✓ businesses, api_raw_data 초기화")
        for svc in services:
            conn.execute("DELETE FROM crawler_state WHERE service_id = ?", (svc,))
        conn.commit()
        print("   ✓ crawler_state 초기화 완료")
    finally:
        conn.close()

    # VACUUM
    vacuum_conn = sqlite3.connect(DB_FILE, isolation_level=None)
    try:
        vacuum_conn.execute("VACUUM")
        print("   ✓ VACUUM 완료 (디스크 공간 회수)")
    finally:
        vacuum_conn.close()

    # ④ 서비스별 초기화 실행
    total_start = datetime.datetime.now()
    summary = []

    async def _run_init():
        for i, svc in enumerate(services):
            if i > 0:
                await asyncio.sleep(2)

            sep = "─" * 50
            print(f"\n{sep}")
            print(f"🚀 [{svc}] {svc_names.get(svc, svc)} 초기 꼬리 상태 세팅 시작...")
            print(sep)

            state = {
                "last_total_count": 4800,
                "extra_state": {
                    "page_timestamps": {},
                    "page_labels": {}
                }
            }
            from app.repositories.state_repository import StateRepository
            StateRepository().save_state(svc, state)

            summary.append((svc, 4800, 0))
            print(f"✅ [{svc}] 완료: tail=4,800건으로 베이스라인 수립")

    asyncio.run(_run_init())

    elapsed = (datetime.datetime.now() - total_start).total_seconds()
    print(f"\n{'=' * 60}")
    print("✅ Full-Scan Init 완료!")
    print(f"{'=' * 60}")
    for svc, tail, calls in summary:
        print(f"  [{svc}] tail={tail:,}건 / API {calls}회")
    print(f"  소요 시간: {elapsed:.1f}초")
    print()
    print("이제 정상적인 차분 동기화를 시작하세요:")
    print("  python cli.py --run-sync    # 수동 1회 실행")
    print("  uvicorn main:app ...        # 자동 주기 크롤링 시작")


def full_mirror(services: list | None = None, from_index: int = 1, force: bool = False):
    """
    전체 API 데이터를 businesses 테이블에 미러링합니다. (일회성 운영 작업)
    """
    from database import init_db, get_db
    from app.repositories.state_repository import StateRepository
    from scraper import _map_row_fields, _parse_datetime_fields

    init_db()
    services = services or ["I2861"]
    svc_names = {"I2861": "음식점업소 인허가변경"}
    PAGE_SIZE = 1000

    print("\n" + "=" * 60)
    print("📸  전체 미러링(Full Mirror)을 시작합니다.")
    print("=" * 60)
    svc_label = ", ".join(f"{s}({svc_names.get(s, s)})" for s in services)
    print(f"  대상: {svc_label}")
    print(f"  시작 인덱스: {from_index:,}")
    if force:
        print("\n  🔄  --force 모드: 기존 레코드를 API 최신값으로 덮어씁니다. (OR REPLACE)")
    else:
        print("\n  ⚠️  기존 businesses 데이터는 덮어쓰지 않고 OR IGNORE로 작동합니다.")
    print()

    yn = input("계속하시겠습니까? (yes/no): ").strip().lower()
    if yn != "yes":
        print("❌ 취소되었습니다.")
        return

    total_start = datetime.datetime.now()
    grand_total_calls = 0
    grand_total_saved = 0

    async def _run_mirror():
        nonlocal grand_total_calls, grand_total_saved

        async with ApiClient() as client:
            state_repo = StateRepository()

            for svc in services:
                state = state_repo.load_state(svc)
                tail = state.get("last_total_count", 0)

                if tail == 0:
                    print(f"[{svc}] ⚠️  crawler_state에 tail 정보가 없습니다. --full-scan-init을 먼저 실행하세요.")
                    continue

                print(f"\n{'─' * 50}")
                print(f"📸 [{svc}] {svc_names.get(svc, svc)} 미러링 시작... (tail={tail:,}건)")
                print(f"{'─' * 50}")

                call_before = client.get_total_call_count()
                svc_saved = 0
                svc_skipped = 0
                current = max(from_index, 1)

                import random
                from app.core.config import settings

                while current <= tail:
                    end = min(current + PAGE_SIZE - 1, tail)
                    try:
                        res = await client.fetch_data(svc, current, end)
                        rows = res.get(svc, {}).get("row", [])
                    except Exception as e:
                        print(f"\n  ⚠️  [{svc}] idx={current:,} fetch 실패: {e}")
                        rows = []

                    with get_db() as conn:
                        for row in rows:
                            fields = _map_row_fields(svc, row)
                            if not fields or not fields.get("lcns_no"):
                                continue
                            lcns_no = fields["lcns_no"]
                            event_date, event_time, license_date, license_time = _parse_datetime_fields(
                                fields.get("event_date_raw", ""), fields.get("license_date", "")
                            )
                            try:
                                insert_mode = "OR REPLACE" if force else "OR IGNORE"
                                conn.execute(
                                    f"""INSERT {insert_mode} INTO businesses
                                    (license_no, business_name, address, representative_name,
                                     business_status, license_date, phone_number, industry_type,
                                     last_event_date, last_event_time, license_time,
                                     is_new, update_type, infer_update_type)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 'mirror', 'mirror')""",
                                    (
                                        lcns_no, fields["business_name"], fields.get("address", ""),
                                        fields.get("representative_name", ""),
                                        fields.get("business_status"), license_date,
                                        fields.get("phone_number", ""), fields.get("industry_type", ""),
                                        event_date, event_time, license_time,
                                    )
                                )
                                if conn.execute("SELECT changes()").fetchone()[0] > 0:
                                    svc_saved += 1
                                else:
                                    svc_skipped += 1
                            except Exception:
                                pass
                        conn.commit()

                    pct = current / tail * 100
                    calls_so_far = client.get_total_call_count() - call_before
                    print(
                        f"  ✔  {current:>9,} ~ {end:>9,} / {tail:,} ({pct:5.1f}%)"
                        f" │ 저장 {svc_saved:,}건 │ API {calls_so_far}회",
                        end="\r"
                    )

                    current += PAGE_SIZE
                    await asyncio.sleep(random.uniform(settings.GAP_MIN, settings.GAP_MAX))

                calls_used = client.get_total_call_count() - call_before
                grand_total_calls += calls_used
                grand_total_saved += svc_saved
                print()
                print(f"  ✅ [{svc}] 완료: 신규 {svc_saved:,}건 저장 / {svc_skipped:,}건 중복 스킵 / API {calls_used}회")

    asyncio.run(_run_mirror())

    elapsed = (datetime.datetime.now() - total_start).total_seconds()
    print(f"\n{'=' * 60}")
    print("✅ Full Mirror 완료!")
    print(f"{'=' * 60}")
    print(f"  신규 저장: {grand_total_saved:,}건")
    print(f"  사용 API 호출: {grand_total_calls}회")
    print(f"  소요 시간: {elapsed:.1f}초")


def run_prune(days: int = 7):
    """
    7일 이전의 api_raw_data 및 system_logs 데이터를 삭제하고,
    incremental_vacuum을 통해 디스크 공간을 회수합니다. (수동 강제 실행)
    """
    from database import prune_db
    print(f"🚀 DB 오래된 데이터 수동 정리 (Pruning) 시작... (보존 기간: {days}일)")
    prune_db(days=days, force=True)
    print("✅ DB Pruning 작업 완료!")

