import sys
import os

# 백엔드 모듈 경로 추가
sys.path.insert(0, r"c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\ApprovalRadar-BE")

import sqlite3
import pandas as pd
import asyncio
from app.clients.foodsafety_api import ApiClient

xlsx_path = r"c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\PleaseTest\업소인허가 데이터 조회(2026-06-05).xlsx"
db_path = r"c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\ApprovalRadar-BE\food_safety.db"

# 엑셀 로드
df = pd.read_excel(xlsx_path)
df['인허가번호_str'] = df['인허가번호'].dropna().astype(float).astype(int).astype(str)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()
db_all_licenses = set(r[0].strip() for r in cursor.execute("SELECT license_no FROM businesses").fetchall() if r[0])
conn.close()

missing_lcns = df[~df['인허가번호_str'].isin(db_all_licenses)]['인허가번호_str'].unique().tolist()
print(f"Missing licenses count: {len(missing_lcns)}")

async def check_api_history():
    async with ApiClient() as client:
        print("\n--- Checking I2861 history for 5 missing licenses ---")
        for lcns in missing_lcns[:5]:
            res = await client.fetch_data("I2861", 1, 50, LCNS_NO=lcns)
            rows = []
            if res and "I2861" in res:
                rows = res["I2861"].get("row", [])
            print(f" - License {lcns}: I2861 rows count = {len(rows)}")
            for r in rows:
                print(f"   * CHNG_DT: {r.get('CHNG_DT')} | Reason: {r.get('CHNG_PRVNS')} | BF: {r.get('CHNG_BF_CN')} | AF: {r.get('CHNG_AF_CN')}")

asyncio.run(check_api_history())
