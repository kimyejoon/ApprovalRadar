import asyncio
import httpx
import time
import os
from dotenv import load_dotenv

# .env 파일 로드 (실제 프로젝트 경로에 맞게 조정 필요할 수 있음)
load_dotenv("../../dist_release/.env")

# 콤마로 구분된 API_KEYS 환경변수 로드
keys_env = os.getenv("API_KEYS", "")
API_KEYS = [k.strip() for k in keys_env.split(",") if k.strip()]

BASE_URL = "http://openapi.foodsafetykorea.go.kr/api"
SERVICE_ID = "I2861"
DATA_TYPE = "json"
PAGE_SIZE = 1000

async def fetch_page(api_key: str, page: int, session: httpx.AsyncClient):
    start_idx = (page - 1) * PAGE_SIZE + 1
    end_idx = page * PAGE_SIZE
    url = f"{BASE_URL}/{api_key}/{SERVICE_ID}/{DATA_TYPE}/{start_idx}/{end_idx}"
    
    print(f"[요청 시작] 키: {api_key[:5]}*** | 페이지: {page} ({start_idx}~{end_idx})")
    start_time = time.time()
    
    try:
        response = await session.get(url, timeout=30.0)
        elapsed = time.time() - start_time
        
        # 텍스트 내부에 WAF 에러 메시지가 있는지 확인
        if "현재 접속 중인 인증키입니다" in response.text:
            print(f"❌ [WAF 차단] 키: {api_key[:5]}*** | 페이지: {page} | 소요시간: {elapsed:.2f}초 | 사유: WAF 차단 (동시접속 등)")
            return False
            
        response.raise_for_status()
        data = response.json()
        
        if SERVICE_ID in data and data[SERVICE_ID]["RESULT"]["CODE"] == "INFO-000":
            row_count = len(data[SERVICE_ID].get("row", []))
            print(f"✅ [요청 성공] 키: {api_key[:5]}*** | 페이지: {page} | 소요시간: {elapsed:.2f}초 | 데이터: {row_count}건 수집")
            return True
        else:
            code = data.get(SERVICE_ID, {}).get("RESULT", {}).get("CODE", "UNKNOWN")
            msg = data.get(SERVICE_ID, {}).get("RESULT", {}).get("MSG", "알 수 없는 오류")
            print(f"⚠️ [API 응답 오류] 키: {api_key[:5]}*** | 페이지: {page} | 소요시간: {elapsed:.2f}초 | 코드: {code} ({msg})")
            return False
            
    except Exception as e:
        elapsed = time.time() - start_time
        print(f"❌ [통신 실패] 키: {api_key[:5]}*** | 페이지: {page} | 소요시간: {elapsed:.2f}초 | 에러: {str(e)}")
        return False

async def main():
    print("=== 🚀 병렬 스캔(Parallel Scan) 테스트 시작 ===")
    
    if len(API_KEYS) < 5:
        print(f"⚠️ 경고: 등록된 API 키가 {len(API_KEYS)}개뿐입니다. 최소 5개가 권장되지만, 중복 키를 사용하여 테스트를 강행합니다.")
        # 키가 부족하면 반복해서 사용
        keys_to_use = [API_KEYS[i % len(API_KEYS)] for i in range(5)]
    else:
        keys_to_use = API_KEYS[:5]
        
    pages_to_scan = [1, 2, 3, 4, 5]  # 테스트할 페이지 번호
    
    print(f"- 사용할 키: {[k[:5] + '***' for k in keys_to_use]}")
    print(f"- 대상 페이지: {pages_to_scan}")
    
    # httpx Session (커넥션 풀) 생성
    async with httpx.AsyncClient(headers={'Connection': 'keep-alive'}) as session:
        tasks = []
        for i in range(5):
            api_key = keys_to_use[i]
            page = pages_to_scan[i]
            tasks.append(fetch_page(api_key, page, session))
            
        print("\n--- 5개 동시 요청 발송 ---")
        overall_start = time.time()
        
        # 병렬로 5개 요청 동시 실행
        results = await asyncio.gather(*tasks)
        
        overall_elapsed = time.time() - overall_start
        print(f"\n=== 🏁 테스트 완료 ===")
        print(f"- 총 소요 시간: {overall_elapsed:.2f}초")
        print(f"- 성공: {sum(1 for r in results if r)}/5")
        print(f"- 실패: {sum(1 for r in results if not r)}/5")

if __name__ == "__main__":
    asyncio.run(main())
