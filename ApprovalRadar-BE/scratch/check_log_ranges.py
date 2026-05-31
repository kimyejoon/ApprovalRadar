import os
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

logs_dir = r"c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\ApprovalRadar-BE\logs"

def check_log_ranges():
    files = sorted([f for f in os.listdir(logs_dir) if f.startswith("app")])
    for filename in files:
        path = os.path.join(logs_dir, filename)
        if os.path.isdir(path) or os.path.getsize(path) < 100:
            continue
            
        first_line = ""
        last_line = ""
        
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if line.strip():
                    first_line = line.strip()
                    break
                    
        # Read from end to find last line with timestamp
        with open(path, "rb") as f:
            try:
                f.seek(-1000, 2)
            except OSError:
                pass
            lines = f.readlines()
            if lines:
                for line in reversed(lines):
                    decoded = line.decode("utf-8", errors="ignore").strip()
                    if decoded and any(decoded.startswith(str(yr)) for yr in range(2020, 2030)):
                        last_line = decoded
                        break
                        
        print(f"File: {filename:<30} | Size: {os.path.getsize(path):10,} bytes")
        print(f"  First: {first_line[:100]}")
        print(f"  Last : {last_line[:100]}")
        print()

if __name__ == "__main__":
    check_log_ranges()
