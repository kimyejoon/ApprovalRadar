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
    outback_rows = [r for r in rows if "아웃백" in r.get("BSSH_NM", "")]
    print(f"Total outback rows: {len(outback_rows)}")
    for idx, r in enumerate(outback_rows):
        print(f"  {idx+1}: BSSH_NM: {r.get('BSSH_NM')} | CHNG_DT: {r.get('CHNG_DT')} | LCNS_NO: {r.get('LCNS_NO')}")

if __name__ == "__main__":
    main()
