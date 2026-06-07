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

startup_indices = []
for idx, line in enumerate(lines):
    if "Broadcaster main event loop initialized" in line:
        startup_indices.append(idx)

print(f"Found {len(startup_indices)} startups on June 1st.")

for i, start_idx in enumerate(startup_indices):
    end_idx = startup_indices[i+1] if i + 1 < len(startup_indices) else len(lines)
    print(f"\n=== Startup {i+1} at line {start_idx}: {lines[start_idx].strip()} ===")
    
    # Analyze errors in this startup block
    block_errors = []
    shutdown_errors_count = 0
    malformed_errors_count = 0
    other_errors = []
    success_count = 0
    
    for j in range(start_idx, end_idx):
        line = lines[j]
        if "cannot schedule new futures after shutdown" in line:
            shutdown_errors_count += 1
        elif "database disk image is malformed" in line:
            malformed_errors_count += 1
        elif "[ERROR]" in line or "Exception" in line or "Error" in line or "오류" in line:
            if len(other_errors) < 5:
                other_errors.append(line.strip())
        if "완료" in line or "Success" in line or "성공" in line:
            success_count += 1
            
    print(f"  Lines in this block: {end_idx - start_idx}")
    print(f"  Success logs: {success_count}")
    print(f"  Shutdown errors: {shutdown_errors_count}")
    print(f"  Malformed DB errors: {malformed_errors_count}")
    print(f"  Other errors (first 5):")
    for err in other_errors:
        sys.stdout.buffer.write(f"    {err}\n".encode('utf-8', errors='replace'))
