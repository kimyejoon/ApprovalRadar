import sys
import os

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

log_path = r"c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\ApprovalRadar-BE\logs\app_20260601.log"

def check():
    if not os.path.exists(log_path):
        print("Log file doesn't exist.")
        return
        
    print("=== Checking logs for 19810053045 ===")
    with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()
        
    # Search for license
    found = False
    for line in lines:
        if "19810053045" in line:
            print(line.strip())
            found = True
            
    if not found:
        print("No log lines mention 19810053045.")

if __name__ == "__main__":
    check()
