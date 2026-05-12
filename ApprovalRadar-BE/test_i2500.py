import requests
import urllib.parse
from app.core.config import settings
from database import get_db

with get_db() as conn:
    cursor = conn.cursor()
    cursor.execute("SELECT license_no FROM businesses WHERE industry_type IS NULL OR industry_type = '' LIMIT 5")
    records = cursor.fetchall()

print("Missing licenses:", [r['license_no'] for r in records])

api_key = settings.API_KEYS[1] # Key 2
print(f"Using API Key: {api_key}")

for r in records:
    lcns = r['license_no']
    # URL encode if necessary?
    url = f"{settings.BASE_URL}/{api_key}/I2500/json/1/10/LCNS_NO={lcns}"
    print(f"Testing URL: {url}")
    response = requests.get(url, timeout=5)
    print("Status:", response.status_code)
    try:
        data = response.json()
        if "I2500" in data:
            print("CODE:", data["I2500"]["RESULT"]["CODE"])
        elif "RESULT" in data:
            print("RESULT:", data["RESULT"])
        else:
            print("DATA keys:", list(data.keys()))
    except Exception as e:
        print("JSON Error:", e)
        print("Response Text Snippet:", response.text[:200])
