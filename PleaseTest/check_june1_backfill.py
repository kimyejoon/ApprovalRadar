import os
import sys

# UTF-8 output
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

log_path = r'c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\dist_release\logs\app_20260601.log'

if not os.path.exists(log_path):
    print("Log not found")
    exit(1)

print("Searching case-insensitively for backfill logs in June 1st log...")
with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
    for line in f:
        if "backfill" in line.lower() or "누락" in line:
            sys.stdout.buffer.write(line.encode('utf-8', errors='replace'))
