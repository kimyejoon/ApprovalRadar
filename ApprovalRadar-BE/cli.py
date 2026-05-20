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

    # 액션과 해당 도움말, 핸들러 매핑 (람다 인터페이스 통일: lambda args, services)
    actions = {
        "--check-keys": ("등록된 API 키들의 유효성 및 한도 초과 여부를 점검합니다.", lambda a, s: check_keys()),
        "--test-tail": ("현재 외부 API 데이터의 총 건수(Tail) 위치를 확인합니다.", lambda a, s: test_tail()),
        "--run-sync": ("수동으로 1회 크롤링(차분 동기화)을 실행하여 DB에 반영합니다.", lambda a, s: run_sync()),
        "--backfill": ("누락된 세부업종(industry_type) 데이터를 공공API 단건 조회를 통해 채웁니다.", lambda a, s: run_backfill()),
        "--test-stream-update": ("로컬 서버에 가상의 업데이트 신호를 발생시켜 SSE 이벤트를 테스트합니다.", lambda a, s: test_stream_update()),
        "--full-scan-init": ("⚠️ DB를 완전 초기화하고 전체 스캔을 재준비합니다. (확인 프롬프트 포함)", lambda a, s: full_scan_init(no_backup=a.no_backup, services=s)),
        "--reset-state": ("businesses 데이터는 보존하고 crawler_state(피벗/Tail)만 리셋합니다.", lambda a, s: reset_state(services=s)),
        "--mirror": ("전체 API 데이터를 businesses 테이블에 미러링합니다. (일회성, API 호출)", lambda a, s: full_mirror(services=s, from_index=a.from_index, force=a.force)),
    }

    for flag, (help_text, _) in actions.items():
        parser.add_argument(flag, action="store_true", help=help_text)

    # 추가 옵션 파라미터 등록
    parser.add_argument("--no-backup", action="store_true", help="--full-scan-init 시 DB 백업을 건너뜝니다.")
    parser.add_argument("--service", type=str, default=None, help="특정 서비스 ID만 대상으로 합니다. (예: --service I2861)")
    parser.add_argument("--force", action="store_true", help="--mirror 시 기존 레코드를 API 최신값으로 덮어씁니다. (OR REPLACE)")
    parser.add_argument("--from-index", type=int, default=1, help="--mirror 시 시작할 API 인덱스를 지정합니다. (default=1)")

    args = parser.parse_args()
    target_services = [args.service] if args.service else None

    # 매핑 테이블을 기반으로 활성화된 액션 탐색 및 실행
    for flag, (_, handler) in actions.items():
        attr_name = flag.lstrip("-").replace("-", "_")
        if getattr(args, attr_name, False):
            handler(args, target_services)
            sys.exit(0)

    parser.print_help()
