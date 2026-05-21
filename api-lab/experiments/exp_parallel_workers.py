import asyncio
import httpx
import time
import os
import sys
import json
from dotenv import load_dotenv

# 상위 디렉토리(ApprovalRadar-BE)를 path에 추가하여 app 모듈 임포트가 가능하게 함
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../ApprovalRadar-BE')))

from app.core.events import broadcaster
from app.services.scraper.service import run_scraper_for_service_with_rows
from app.core.logger import logger

load_dotenv(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../dist_release/.env')))

keys_env = []
for i in range(1, 51):
    key = os.getenv(f"FOOD_SAFETY_API_KEY_{i}")
    if key:
        keys_env.append(key.strip())
API_KEYS = keys_env

BASE_URL = "http://openapi.foodsafetykorea.go.kr/api"
SERVICE_ID = "I2861"
DATA_TYPE = "json"
PAGE_SIZE = 1000
MAX_PAGES = 500

async def fetch_with_key(api_key: str, page: int, session: httpx.AsyncClient):
    start_idx = (page - 1) * PAGE_SIZE + 1
    end_idx = page * PAGE_SIZE
    url = f"{BASE_URL}/{api_key}/{SERVICE_ID}/{DATA_TYPE}/{start_idx}/{end_idx}"
    
    try:
        response = await session.get(url, timeout=30.0)
        if "현재 접속 중인 인증키입니다" in response.text:
            return False, [], "WAF 차단 (동시접속 등)"
            
        response.raise_for_status()
        data = response.json()
        
        if SERVICE_ID in data and data[SERVICE_ID]["RESULT"]["CODE"] == "INFO-000":
            return True, data[SERVICE_ID].get("row", []), "성공"
        else:
            code = data.get(SERVICE_ID, {}).get("RESULT", {}).get("CODE", "UNKNOWN")
            msg = data.get(SERVICE_ID, {}).get("RESULT", {}).get("MSG", "알 수 없는 오류")
            return False, [], f"API 오류 ({code}: {msg})"
            
    except Exception as e:
        return False, [], f"네트워크/통신 실패 ({str(e)})"

async def worker(worker_id: int, queue: asyncio.Queue, primary_key: str, spare_key: str, session: httpx.AsyncClient):
    current_key = primary_key
    
    while not queue.empty():
        try:
            page = queue.get_nowait()
        except asyncio.QueueEmpty:
            break
            
        start_time = time.time()
        print(f"[Worker-{worker_id}] 📥 P{page} 스캔 시작 (Key: {current_key[:5]}***)")
        
        success, rows, error_msg = await fetch_with_key(current_key, page, session)
        
        # Primary 실패 시 Spare로 전환 로직
        if not success:
            if current_key == primary_key:
                print(f"⚠️ [Worker-{worker_id}] Primary Key({current_key[:5]}***) 실패! 사유: {error_msg}")
                print(f"🔄 [Worker-{worker_id}] Spare Key({spare_key[:5]}***)로 전환하여 P{page} 재시도합니다.")
                current_key = spare_key
                # 지연시간 조금 주고 재시도
                await asyncio.sleep(1)
                success, rows, error_msg = await fetch_with_key(current_key, page, session)
                if not success:
                    print(f"❌ [Worker-{worker_id}] Spare Key마저 실패! 사유: {error_msg}. P{page} 포기.")
            else:
                print(f"❌ [Worker-{worker_id}] Spare Key 사용 중 실패! 사유: {error_msg}. P{page} 포기.")
        
        elapsed = time.time() - start_time
        
        if success and rows:
            print(f"✅ [Worker-{worker_id}] P{page} 데이터 로드 성공 ({len(rows)}건) | 소요: {elapsed:.1f}초")
            
            # DB 파이프라인에 삽입 (실제 BE scraper 로직 재사용)
            try:
                result = await run_scraper_for_service_with_rows(SERVICE_ID, rows, collected_by="parallel_test")
                page_stats = {
                    "total_fetched": len(rows),
                    "new_indexed": result.get("new_indexed", 0),
                    "skipped_dup": result.get("skipped_dup", 0),
                    "today": result.get("today", 0),
                    "yesterday": result.get("yesterday", 0),
                }
                
                # 프론트엔드 실시간 연동을 위한 SSE 브로드캐스트
                broadcaster.broadcast_sync(json.dumps({
                    "type": "PLAYGROUND_UPDATE",
                    "page": page,
                    "page_label": f"[W-{worker_id} 병렬테스트]",
                    "stats": page_stats,
                    "cycle": {
                        "elapsed_sec": elapsed,
                        "pages_done": page,
                        "pages_total": MAX_PAGES,
                    }
                }, ensure_ascii=False))
                
                print(f"💾 [Worker-{worker_id}] P{page} DB 저장 완료 (신규 {page_stats['new_indexed']}건)")
                
            except Exception as e:
                print(f"❌ [Worker-{worker_id}] P{page} DB 저장 중 오류 발생: {e}")
                
        queue.task_done()
        # WAF 방지를 위한 워커별 최소한의 딜레이
        await asyncio.sleep(0.5)

async def main():
    print("=== 🚀 4-Worker 병렬 스캔 테스트 (Limit 500 pages) ===")
    
    if len(API_KEYS) < 8:
        print(f"⚠️ API 키가 {len(API_KEYS)}개뿐입니다. 8개가 필요하므로 일부 키를 중복 할당합니다.")
        # 부족한 키 채우기
        extended_keys = API_KEYS * (8 // len(API_KEYS) + 1)
        test_keys = extended_keys[:8]
    else:
        test_keys = API_KEYS[:8]
        
    # Queue 생성 (1~500 페이지)
    queue = asyncio.Queue()
    for p in range(1, MAX_PAGES + 1):
        queue.put_nowait(p)
        
    async with httpx.AsyncClient(headers={'Connection': 'keep-alive'}) as session:
        workers = []
        for i in range(4):
            primary = test_keys[i * 2]
            spare = test_keys[i * 2 + 1]
            print(f"- Worker-{i+1} 셋업 완료 | Primary: {primary[:5]}*** | Spare: {spare[:5]}***")
            task = asyncio.create_task(worker(i + 1, queue, primary, spare, session))
            workers.append(task)
            
        print("\n--- 🏁 병렬 스캔 시작 ---")
        overall_start = time.time()
        
        await asyncio.gather(*workers)
        
        print(f"\n=== 🏁 500페이지 스캔 완전 종료 ===")
        print(f"- 총 소요 시간: {time.time() - overall_start:.2f}초")

if __name__ == "__main__":
    asyncio.run(main())
