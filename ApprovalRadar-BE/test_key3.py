import requests
from app.core.config import settings

api_key = settings.API_KEYS[2] # Key 3
url = f"{settings.BASE_URL}/{api_key}/I2500/json/1/1/LCNS_NO=20190343399"
print(f"Testing URL: {url}")
response = requests.get(url, timeout=5)
print("Status:", response.status_code)
print("Response text:", response.text[:200])
