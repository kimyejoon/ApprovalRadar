import os
import sys

# UTF-8 output
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

log_path = r'c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\dist_release\logs\app_20260601.log'

if not os.path.exists(log_path):
    print("Log not found")
    exit(1)

print("Searching for the first occurrences of key errors with context...")
first_shutdown_err = None
first_malformed_err = None

with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
    lines = f.readlines()

for idx, line in enumerate(lines):
    if first_shutdown_err is None and "cannot schedule new futures after shutdown" in line:
        first_shutdown_err = idx
    if first_malformed_err is None and "database disk image is malformed" in line:
        first_malformed_err = idx

def print_context(idx, label):
    if idx is None:
        print(f"\n--- {label} not found ---")
        return
    print(f"\n--- Context of {label} (line {idx}) ---")
    start = max(0, idx - 5)
    end = min(len(lines), idx + 15)
    for i in range(start, end):
        sys.stdout.buffer.write(f"{i}: {lines[i]}".encode('utf-8', errors='replace'))

print_context(first_shutdown_err, "First 'cannot schedule new futures' error")
print_context(first_malformed_err, "First 'database disk image is malformed' error")
