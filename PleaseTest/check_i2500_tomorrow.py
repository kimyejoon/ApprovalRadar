import httpx
import sqlite3
import asyncio
import os
import sys

# UTF-8 출력 설정
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

db_path = r"c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\ApprovalRadar-BE\food_safety.db"

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

async def main():
    key = await find_valid_key()
    if not key:
        print("No valid key")
        return
        
    async with httpx.AsyncClient() as client:
        # Plain for 20260522 (tomorrow)
        url_plain = f"http://openapi.foodsafetykorea.go.kr/api/{key}/I2500/json/1/10/CHNG_DT=20260522"
        res_plain = await client.get(url_plain, timeout=10.0)
        js_plain = res_plain.json().get("I2500", {})
        code_p = js_plain.get("RESULT", {}).get("CODE")
        msg_p = js_plain.get("RESULT", {}).get("MSG")
        
        # Live for 20260522 (tomorrow)
        url_live = f"http://openapi.foodsafetykorea.go.kr/api/{key}/I2500/json/1/10/CHNG_DT=20260522&SYS_SYNC=LIVE"
        res_live = await client.get(url_live, timeout=10.0)
        js_live = res_live.json().get("I2500", {})
        code_l = js_live.get("RESULT", {}).get("CODE")
        msg_l = js_live.get("RESULT", {}).get("MSG")
        
        print("=== I2500 CHNG_DT=20260522 (Tomorrow) Test ===")
        print(f"Plain | Code: {code_p} | Msg: {msg_p}")
        print(f"Live  | Code: {code_l} | Msg: {msg_l}")

if __name__ == "__main__":
    asyncio.run(main())
