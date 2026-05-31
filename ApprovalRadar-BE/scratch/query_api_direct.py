import asyncio
import sys

# Add project root to python path
sys.path.append(r"c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\ApprovalRadar-BE")

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from app.clients.foodsafety_api import ApiClient

licenses = {
    "유가네 수유점": "19810053045",
    "우주횟집": "20060114564",
    "미스터육회연어왕 안산점": "20110313244",
    "커피101스트릿(옥길점)": "20200300646"
}

async def query_api():
    print("=== Direct Query to Foodsafety OpenAPI (I2861) ===")
    async with ApiClient() as client:
        for name, lcns in licenses.items():
            print(f"\n[*] Querying: {name} (LCNS_NO: {lcns})")
            try:
                res = await client.fetch_data("I2861", 1, 50, LCNS_NO=lcns)
                if not res or "I2861" not in res:
                    print(f"  -> No data or invalid response from API. Response: {res}")
                    continue
                
                rows = res["I2861"].get("row", [])
                print(f"  -> Found {len(rows)} raw row(s) in API response:")
                for i, r in enumerate(rows, 1):
                    chng_dt = r.get("CHNG_DT")
                    chng_prvns = r.get("CHNG_PRVNS")
                    bf = r.get("CHNG_BF_CN")
                    af = r.get("CHNG_AF_CN")
                    bssh_nm = r.get("BSSH_NM")
                    prsdnt_nm = r.get("PRSDNT_NM")
                    print(f"     Row {i}: BSSH_NM: {bssh_nm} | PRSDNT_NM: {prsdnt_nm} | CHNG_DT: {chng_dt} | CHNG_PRVNS: {chng_prvns} | BF: {bf} -> AF: {af}")
            except Exception as e:
                print(f"  -> Error querying API: {e}")

if __name__ == "__main__":
    asyncio.run(query_api())
