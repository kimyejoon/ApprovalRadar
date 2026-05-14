import argparse
import sys
import os

# app 모듈 경로 인식
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app.clients.foodsafety_api import ApiClient
from app.services.diff_crawler import DiffCrawlerEngine

def check_keys():
    print("API 키 상태를 점검합니다...")
    client = ApiClient()
    client.check_keys_status()

def test_tail():
    import time
    print("현재 데이터의 꼬리(Tail) 지점을 조회합니다 (서비스별 최적 전략)...")
    print("(I2500은 Backfill 전용 단건 조회 API이므로 tail 스캔 대상 아님)")
    client = ApiClient()
    # 스캐닝 대상 서비스만 조회 (I2500 제외 - Backfill 전용)
    services = ["I2859", "I2861"]
    for i, service_id in enumerate(services):
        if i > 0:
            print(f"  (다음 서비스 전 3초 대기 - WAF 방지)")
            time.sleep(3)
        crawler = DiffCrawlerEngine(api_client=client, service_id=service_id)
        tail = crawler.find_true_tail()
        print(f"  [{service_id}] 현재 전체 데이터 건수: {tail:,}건")
    print("\n✅ 조회 완료")

def run_sync():
    print("수동으로 차분 동기화(Delta Sync)를 1회 실행합니다...")
    from scraper import run_all_scrapers
    run_all_scrapers()

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

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ApprovalRadar Backend CLI Tools")
    parser.add_argument("--check-keys", action="store_true", help="등록된 API 키들의 유효성 및 한도 초과 여부를 점검합니다.")
    parser.add_argument("--test-tail", action="store_true", help="현재 외부 API 데이터의 총 건수(Tail) 위치를 이진 탐색으로 확인합니다.")
    parser.add_argument("--run-sync", action="store_true", help="수동으로 1회 크롤링(차분 동기화)을 실행하여 DB에 반영합니다.")
    parser.add_argument("--backfill", action="store_true", help="누락된 세부업종(industry_type) 데이터를 공공API 단건 조회를 통해 채웁니다.")
    parser.add_argument("--test-stream-update", action="store_true", help="로컬 서버에 가상의 업데이트 신호를 발생시켜 SSE 이벤트를 테스트합니다.")
    
    args = parser.parse_args()
    
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
    else:
        parser.print_help()
