import asyncio
import sys
import datetime

# Add project root to python path
sys.path.append(r"c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\ApprovalRadar-BE")

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from app.clients.foodsafety_api import ApiClient
from app.services.chng_dt_poller import poll_changes_for_date

async def test_today():
    today = (datetime.datetime.now() - datetime.timedelta(days=1)).strftime("%Y%m%d")
    print(f"Polling I2500 for date: {today}")
    
    async with ApiClient() as client:
        # Fetch first page (1-50) of I2500 for today
        res = await client.fetch_data("I2500", 1, 50, CHNG_DT=today)
        if not res or "I2500" not in res:
            print("No I2500 data for today.")
            return
            
        rows = res["I2500"].get("row", [])
        print(f"Fetched {len(rows)} rows from I2500 for today ({today}).")
        
        matches = 0
        for r in rows[:10]:
            prms_dt = r.get("PRMS_DT") or ""
            lcns = r.get("LCNS_NO") or ""
            name = r.get("BSSH_NM") or ""
            print(f"LCNS: {lcns} | PRMS_DT: {prms_dt} | Name: {name} | CHNG_DT: {r.get('CHNG_DT')}")
            if prms_dt == today:
                matches += 1
                
        print(f"Total rows: {len(rows)}, matches where PRMS_DT == {today}: {matches}")
        
if __name__ == "__main__":
    asyncio.run(test_today())
