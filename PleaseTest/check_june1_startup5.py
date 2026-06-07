import os
import sys

# UTF-8 output
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

log_path = r'c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\dist_release\logs\app_20260601.log'

if not os.path.exists(log_path):
    print("Log not found")
    exit(1)

with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
    lines = f.readlines()

target_idx = -1
for idx, line in enumerate(lines):
    if "2026-06-01 09:09:31" in line:
        target_idx = idx
        break

if target_idx != -1:
    print(f"Printing logs around 09:09:31 startup (lines {target_idx-5} to {target_idx+40}):")
    for i in range(target_idx - 5, target_idx + 40):
        sys.stdout.buffer.write(f"{i}: {lines[i]}".encode('utf-8', errors='replace'))
else:
    print("09:09:31 startup not found in log")
