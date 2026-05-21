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
    
    hash_rows = [r for r in rows if r.get("BSSH_NM", "").startswith("#")]
    print(f"Rows starting with #: {len(hash_rows)}")
    for r in hash_rows[:5]:
        print(f"  {r.get('BSSH_NM')} | CHNG_DT: {r.get('CHNG_DT')}")
        
    parenthesis_rows = [r for r in rows if r.get("BSSH_NM", "").startswith("(")]
    print(f"\nRows starting with (: {len(parenthesis_rows)}")
    for r in parenthesis_rows[:5]:
        print(f"  {r.get('BSSH_NM')} | CHNG_DT: {r.get('CHNG_DT')}")

if __name__ == "__main__":
    main()
