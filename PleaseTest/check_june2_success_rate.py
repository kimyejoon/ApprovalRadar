import os
import sys

# UTF-8 output
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

log_path = r'c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\dist_release\logs\app_20260602.log'

if not os.path.exists(log_path):
    print("Log not found")
    exit(1)

success_count = 0
success_by_service = {}
cannot_schedule_count = 0
error_count = 0
other_errors = {}

with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
    for line in f:
        # Check if success
        if "완료" in line or "Success" in line or "성공" in line:
            success_count += 1
            if "I2861" in line:
                success_by_service["I2861"] = success_by_service.get("I2861", 0) + 1
            elif "I2500" in line:
                success_by_service["I2500"] = success_by_service.get("I2500", 0) + 1
            elif "CHNG_DT Poller" in line:
                success_by_service["CHNG_DT Poller"] = success_by_service.get("CHNG_DT Poller", 0) + 1
            else:
                success_by_service["Other"] = success_by_service.get("Other", 0) + 1
        
        # Check for shutdown errors
        if "cannot schedule new futures after shutdown" in line:
            cannot_schedule_count += 1
        elif "[ERROR]" in line or "오류" in line or "Exception" in line or "Error" in line:
            error_count += 1
            # Group errors by message pattern
            msg = line.strip()
            # remove timestamp and log level
            if len(msg) > 30:
                msg = msg[30:]
            msg = msg[:100]
            other_errors[msg] = other_errors.get(msg, 0) + 1

print(f"Total Success logs on June 2nd: {success_count}")
print("Success logs by service:")
for k, v in success_by_service.items():
    print(f"  {k}: {v}")

print(f"\n'cannot schedule new futures after shutdown' count: {cannot_schedule_count}")

print(f"\nOther error logs count: {error_count}")
print("Other errors frequency (top 10):")
for k, v in sorted(other_errors.items(), key=lambda x: -x[1])[:10]:
    # safe print
    sys.stdout.buffer.write(f"  {v} times: {k}\n".encode('utf-8', errors='replace'))
