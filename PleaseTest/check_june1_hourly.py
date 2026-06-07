import os
import sys

# UTF-8 output
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

log_path = r'c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\dist_release\logs\app_20260601.log'

if not os.path.exists(log_path):
    print("Log not found")
    exit(1)

hourly_errors = {}
hourly_success = {}

with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
    for line in f:
        if len(line) < 19:
            continue
        timestamp = line[:19]
        if not timestamp.startswith("2026-06-01 "):
            continue
        hour = timestamp[11:13]
        
        if "cannot schedule new futures after shutdown" in line:
            hourly_errors[hour] = hourly_errors.get(hour, 0) + 1
        if "완료" in line or "Success" in line or "성공" in line:
            hourly_success[hour] = hourly_success.get(hour, 0) + 1

print("Hour | Shutdown Errors | Success Logs")
print("-------------------------------------")
all_hours = sorted(list(set(hourly_errors.keys()) | set(hourly_success.keys())))
for h in all_hours:
    err = hourly_errors.get(h, 0)
    succ = hourly_success.get(h, 0)
    print(f" {h}  | {err:15d} | {succ:12d}")
