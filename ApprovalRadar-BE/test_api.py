import requests

url = "http://openapi.foodsafetykorea.go.kr/api/97da15383a8b417281bc/I2859/json/1/1"
res = requests.get(url)
print(res.json()['I2859']['row'][0]['PRMS_DT'])
