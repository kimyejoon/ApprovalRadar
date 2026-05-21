import json
import sys

# UTF-8 출력 설정
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

json_path = r"c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\PleaseTest\0520_API_Response_B.json"

def main():
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    print("I2861 total_count in JSON B:")
    print(data.get("I2861", {}).get("total_count"))
    print("RESULT code in JSON B:")
    print(data.get("I2861", {}).get("RESULT"))

if __name__ == "__main__":
    main()
