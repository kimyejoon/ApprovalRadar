import os
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

logs_dir = r"c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\ApprovalRadar-BE\logs"

def search_logs():
    targets = {
        "19810053045": "유가네 수유점",
        "20060114564": "우주횟집",
        "20000358305": "중독마라탕",
        "20200300646": "커피101스트릿(옥길점)",
        "20110313244": "미스터육회연어왕 안산점"
    }
    
    files = ["app_20260527.log", "app_20260528.log", "app_20260529.log", "app_20260530.log"]
    
    for filename in files:
        path = os.path.join(logs_dir, filename)
        if not os.path.exists(path):
            continue
            
        print(f"\n==========================================")
        print(f"SEARCHING IN {filename}")
        print(f"==========================================")
        
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for line_no, line in enumerate(f, 1):
                # Check if any target LCNS is in the line
                for lcns, name in targets.items():
                    if lcns in line:
                        print(f"  Line {line_no:5d} | {name} ({lcns}) | {line.strip()}")

if __name__ == "__main__":
    search_logs()
