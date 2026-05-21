import sqlite3
import httpx
import asyncio
import datetime
import os
import sys

# UTF-8 출력 설정
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

db_path = r"c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\ApprovalRadar-BE\food_safety.db"

if not os.path.exists(db_path):
    print("Error: Database not found")
    sys.exit(1)

# Fetch one working key
conn = sqlite3.connect(db_path)
cursor = conn.cursor()
rows = cursor.execute("SELECT key_value FROM api_keys WHERE is_active = 1").fetchall()
api_keys = [r[0] for r in rows]
conn.close()

async def find_valid_key():
    async with httpx.AsyncClient() as client:
        for key in api_keys:
            url = f"http://openapi.foodsafetykorea.go.kr/api/{key}/I2861/json/1/1/CHNG_DT=20260519"
            try:
                res = await client.get(url, timeout=5.0)
                if res.status_code == 200:
                    js = res.json()
                    i2861 = js.get("I2861", {})
                    result = i2861.get("RESULT", {})
                    code = result.get("CODE")
                    if code != "INFO-300":
                        return key
            except Exception:
                pass
    return None

async def verify():
    key = await find_valid_key()
    if not key:
        print("❌ 사용 가능한 API 키가 없습니다.")
        return
        
    # 실행 시점의 당일 날짜 구하기 (내일 실행하든 언제 실행하든 그 날의 오늘 날짜 기준)
    today_str = datetime.date.today().strftime("%Y%m%d")
    print(f"📅 테스트 기준 날짜 (오늘): {today_str}")
    print(f"🔑 사용 API 키: {key[:6]}...")
    
    url_plain = f"http://openapi.foodsafetykorea.go.kr/api/{key}/I2500/json/1/5/CHNG_DT={today_str}"
    url_bypass = f"http://openapi.foodsafetykorea.go.kr/api/{key}/I2500/json/1/5/CHNG_DT={today_str}&SYS_SYNC=LIVE"
    
    async with httpx.AsyncClient() as client:
        # 1. 일반 요청
        print("\n--- 1. 일반 요청 (Plain Query) ---")
        try:
            res_a = await client.get(url_plain, timeout=10.0)
            js_a = res_a.json()
            result_a = js_a.get("I2500", {}).get("RESULT", {})
            code_a = result_a.get("CODE")
            msg_a = result_a.get("MSG")
            print(f"결과 코드: {code_a}")
            print(f"메시지: {msg_a}")
            if code_a == "INFO-700":
                print("🔒 [결과] 19시 이전 제한으로 인해 정상적으로 차단되었습니다. (정상 동작)")
            elif code_a == "INFO-000":
                print("🔓 [결과] 19시 이후이거나 차단이 풀려 데이터가 정상 조회되었습니다.")
        except Exception as e:
            print(f"요청 실패: {e}")
            
        # 2. 우회 요청
        print("\n--- 2. 우회 요청 (Bypassed Query) ---")
        try:
            res_b = await client.get(url_bypass, timeout=10.0)
            js_b = res_b.json()
            result_b = js_b.get("I2500", {}).get("RESULT", {})
            code_b = result_b.get("CODE")
            msg_b = result_b.get("MSG")
            total_b = js_b.get("I2500", {}).get("total_count", "0")
            print(f"결과 코드: {code_b}")
            print(f"메시지: {msg_b}")
            print(f"데이터 건수: {total_b}건")
            if code_b in ("INFO-000", "INFO-200"):
                print("✨ [결과] SYS_SYNC=LIVE 우회가 성공적으로 작동했습니다! (INFO-700이 발생하지 않음)")
            else:
                print("❌ [결과] 우회에 실패했거나 다른 에러가 발생했습니다.")
        except Exception as e:
            print(f"요청 실패: {e}")

if __name__ == "__main__":
    asyncio.run(verify())
