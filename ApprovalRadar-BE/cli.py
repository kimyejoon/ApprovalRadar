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
    print("현재 데이터의 꼬리(Tail) 지점을 탐색합니다 (이진 탐색)...")
    client = ApiClient()
    crawler = DiffCrawlerEngine(api_client=client)
    tail = crawler.find_true_tail()
    print(f"\n✅ 탐색 완료: 현재 실제 마지막 데이터(Tail)는 {tail}건 입니다.")

def run_sync():
    print("수동으로 차분 동기화(Delta Sync)를 1회 실행합니다...")
    from scraper import run_all_scrapers
    run_all_scrapers()

def run_backfill():
    print("DB에 누락된 세부업종 데이터를 단건 조회를 통해 채워넣습니다(Backfill)...")
    from app.services.industry_filler import fill_missing_industry_types
    fill_missing_industry_types()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ApprovalRadar Backend CLI Tools")
    parser.add_argument("--check-keys", action="store_true", help="등록된 API 키들의 유효성 및 한도 초과 여부를 점검합니다.")
    parser.add_argument("--test-tail", action="store_true", help="현재 외부 API 데이터의 총 건수(Tail) 위치를 이진 탐색으로 확인합니다.")
    parser.add_argument("--run-sync", action="store_true", help="수동으로 1회 크롤링(차분 동기화)을 실행하여 DB에 반영합니다.")
    parser.add_argument("--backfill", action="store_true", help="누락된 세부업종(industry_type) 데이터를 공공API 단건 조회를 통해 채웁니다.")
    
    args = parser.parse_args()
    
    if args.check_keys:
        check_keys()
    elif args.test_tail:
        test_tail()
    elif args.run_sync:
        run_sync()
    elif args.backfill:
        run_backfill()
    else:
        parser.print_help()
