import sys
import os

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

log_path = r"c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\ApprovalRadar-BE\logs\app_20260601.log"

def check():
    if not os.path.exists(log_path):
        return
    licenses = ["20060114564", "20110313244", "20200300646"]
    with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            for l in licenses:
                if l in line:
                    print(line.strip())

if __name__ == "__main__":
    check()
