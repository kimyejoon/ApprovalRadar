import json
import sys

# UTF-8 출력 설정
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

json_path = r"c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\PleaseTest\0520_API_Response_B.json"

def main():
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    rows = data.get("I2861", {}).get("row", [])
    print(f"Total rows in JSON B: {len(rows)}")
    
    print("\nFirst 10 rows:")
    for idx, r in enumerate(rows[:10]):
        print(f"  {idx+1:2d} | CHNG_DT: {r.get('CHNG_DT')} | BSSH_NM: {r.get('BSSH_NM')} | INDUTY: {r.get('INDUTY_CD_NM')}")
        
    print("\nLast 10 rows:")
    for idx, r in enumerate(rows[-10:]):
        print(f"  {len(rows)-9+idx:2d} | CHNG_DT: {r.get('CHNG_DT')} | BSSH_NM: {r.get('BSSH_NM')} | INDUTY: {r.get('INDUTY_CD_NM')}")

if __name__ == "__main__":
    main()
