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
    
    print("Exact positions of rows starting with #:")
    found = 0
    for idx, r in enumerate(rows):
        nm = r.get("BSSH_NM", "")
        if nm.startswith("#"):
            found += 1
            print(f"  Match {found}: Index {idx+1} | BSSH_NM: {nm} | CHNG_DT: {r.get('CHNG_DT')}")

if __name__ == "__main__":
    main()
