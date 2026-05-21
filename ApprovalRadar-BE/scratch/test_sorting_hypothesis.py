import sys
import os
import asyncio

# UTF-8 출력 설정
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

sys.path.append(r"c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\ApprovalRadar-BE")

from app.core.config import settings
from app.clients.foodsafety_api import ApiClient

async def test_sorting_extended():
    service_id = "I2861"
    sizes = [10, 100, 200, 300, 500, 800, 1000]
    results = {}
    
    async with ApiClient() as client:
        for size in sizes:
            print(f"📡 API 호출 중: /1/{size} ...")
            try:
                res = await client.fetch_data(service_id, 1, size, timeout=30)
                rows = res.get(service_id, {}).get("row", []) if res else []
                results[size] = rows
                print(f"   => 성공: {len(rows)}건 반환됨")
                await asyncio.sleep(1.0) # WAF 방지 간격
            except Exception as e:
                print(f"   => 실패: {e}")
                results[size] = []

    print("\n" + "="*80)
    print("📢 [가설 검증] 각 요청 크기별 첫 5개 레코드 비교표")
    print("="*80)
    
    # 첫 5개 레코드가 각 사이즈별로 어떻게 나오는지 표 형식으로 출력
    # (상호명, 라이선스 번호)
    for idx in range(5):
        print(f"\n[레코드 인덱스 #{idx+1}]")
        for size in sizes:
            rows = results[size]
            if idx < len(rows):
                r = rows[idx]
                print(f"  - 크기 1/{size:4d} : {r.get('BSSH_NM')} ({r.get('LCNS_NO')}) | 변경일자: {r.get('CHNG_DT')}")
            else:
                print(f"  - 크기 1/{size:4d} : (데이터 없음)")

    print("\n" + "="*80)
    print("📢 [정밀 대조] 1/10 결과와 각 사이즈별 첫 10개 일치율")
    print("="*80)
    
    rows_10 = results.get(10, [])
    if not rows_10:
        print("1/10 결과가 없어 대조할 수 없습니다.")
        return
        
    for size in sizes[1:]:
        rows_other = results.get(size, [])
        matches = 0
        limit = min(10, len(rows_10), len(rows_other))
        
        print(f"\n▶ 1/10 vs 1/{size} 비교:")
        for idx in range(limit):
            lcns_10 = rows_10[idx].get("LCNS_NO")
            lcns_other = rows_other[idx].get("LCNS_NO")
            if lcns_10 == lcns_other:
                matches += 1
            else:
                print(f"  * Idx {idx} 불일치: [1/10]={rows_10[idx].get('BSSH_NM')} vs [1/{size}]={rows_other[idx].get('BSSH_NM')}")
        
        print(f"  => 총 10개 중 일치 개수: {matches}개 ({matches/limit*100:.1f}%)")

if __name__ == "__main__":
    asyncio.run(test_sorting_extended())
