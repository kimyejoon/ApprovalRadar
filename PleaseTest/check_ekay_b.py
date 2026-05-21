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
    
    ekay_rows = [r for r in rows if "이케이" in r.get("BSSH_NM", "")]
    print(f"Total ekay rows: {len(ekay_rows)}")
    for idx, r in enumerate(ekay_rows):
        print(f"  {idx+1}: BSSH_NM: {r.get('BSSH_NM')} | CHNG_DT: {r.get('CHNG_DT')}")

if __name__ == "__main__":
    main()
