import os
import sys

# UTF-8 output
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

log_path = r'c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\dist_release\logs\app_20260601.log'

if not os.path.exists(log_path):
    print("Log not found")
    exit(1)

print("Printing first 120 lines of June 1st log...")
with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
    for idx, line in enumerate(f):
        if idx < 120:
            sys.stdout.buffer.write(f"{idx}: {line}".encode('utf-8', errors='replace'))
        else:
            break
