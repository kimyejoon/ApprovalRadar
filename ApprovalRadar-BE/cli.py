import argparse
import sys
import os

# app 모듈 경로 인식
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app.cli.commands.keys import check_keys
from app.cli.commands.tail import test_tail
from app.cli.commands.sync import run_sync
from app.cli.commands.backfill import run_backfill
from app.cli.commands.stream import test_stream_update
from app.cli.commands.db_ops import reset_state, full_scan_init, full_mirror

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ApprovalRadar Backend CLI Tools")
    parser.add_argument("--check-keys", action="store_true", help="등록된 API 키들의 유효성 및 한도 초과 여부를 점검합니다.")
    parser.add_argument("--test-tail", action="store_true", help="현재 외부 API 데이터의 총 건수(Tail) 위치를 확인합니다.")
    parser.add_argument("--run-sync", action="store_true", help="수동으로 1회 크롤링(차분 동기화)을 실행하여 DB에 반영합니다.")
    parser.add_argument("--backfill", action="store_true", help="누락된 세부업종(industry_type) 데이터를 공공API 단건 조회를 통해 채웁니다.")
    parser.add_argument("--test-stream-update", action="store_true", help="로컬 서버에 가상의 업데이트 신호를 발생시켜 SSE 이벤트를 테스트합니다.")
    parser.add_argument(
        "--full-scan-init",
        action="store_true",
        help="⚠️ DB를 완전 초기화하고 전체 스캔을 재준비합니다. (확인 프롬프트 포함)"
    )
    parser.add_argument(
        "--reset-state",
        action="store_true",
        help="businesses 데이터는 보존하고 crawler_state(피벗/Tail)만 리셋합니다."
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="--full-scan-init 시 DB 백업을 건너뜝니다."
    )
    parser.add_argument(
        "--service",
        type=str,
        default=None,
        help="특정 서비스 ID만 대상으로 합니다. (예: --service I2861)"
    )
    parser.add_argument(
        "--mirror",
        action="store_true",
        help="전체 API 데이터를 businesses 테이블에 미러링합니다. (일회성, API 호출)"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="--mirror 시 기존 레코드를 API 최신값으로 덮어씁니다. (OR REPLACE)"
    )
    parser.add_argument(
        "--from-index",
        type=int,
        default=1,
        help="--mirror 시 시작할 API 인덱스를 지정합니다. (default=1)"
    )

    args = parser.parse_args()
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
    elif args.mirror:
        full_mirror(services=target_services, from_index=args.from_index, force=args.force)
    else:
        parser.print_help()
