import sys
import os

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

log_path = r"c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\ApprovalRadar-BE\logs\app_20260601.log"

def find_lines():
    print("=== Searching for CHNG_DT Poller entries in app_20260601.log ===")
    if not os.path.exists(log_path):
        print("Log file doesn't exist.")
        return
        
    with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if "CHNG_DT" in line or "3중" in line or "전략C" in line:
                # Print only lines related to May 29 (D-3)
                if "20260529" in line or "완료" in line or "필터" in line:
                    print(line.strip())

if __name__ == "__main__":
    find_lines()
