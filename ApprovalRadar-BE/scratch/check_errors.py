import re
import os
import sys
from collections import Counter

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

logs_dir = r"c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\ApprovalRadar-BE\logs"

def analyze_errors(filename):
    path = os.path.join(logs_dir, filename)
    if not os.path.exists(path):
        return
        
    print(f"\n==========================================")
    print(f"ERROR ANALYSIS FOR {filename}")
    print(f"==========================================")
    
    error_lines = []
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if "[ERROR]" in line:
                error_lines.append(line.strip())
                
    print(f"Total ERROR lines found: {len(error_lines)}")
    
    # Group errors by pattern
    patterns = []
    for line in error_lines:
        # Abstract the line to find common patterns
        # Replace numbers, hex codes, and dates
        pattern = re.sub(r'\d+', 'N', line)
        pattern = re.sub(r'0x[0-9a-fA-F]+', 'HEX', pattern)
        pattern = re.sub(r'\[I\d+ \| [a-f0-9\*\*\*]+\]', '[SVC | KEY]', pattern)
        # Take the message part after "ApprovalRadar - " or "uvicorn - "
        match = re.search(r'ApprovalRadar - (.*)', pattern)
        if match:
            msg = match.group(1)
        else:
            msg = pattern
        patterns.append(msg[:150])
        
    counter = Counter(patterns)
    print("\nError Pattern Counts:")
    for pat, cnt in counter.most_common(10):
        print(f"  Count: {cnt:4d} | {pat}")
        
    # Also show raw samples of the most common error types
    print("\nRaw Samples of Errors:")
    printed_samples = set()
    for line in error_lines:
        # Extract the core message to check for uniqueness
        core = ""
        match = re.search(r'ApprovalRadar - (.*)', line)
        if match:
            core = match.group(1)
        else:
            core = line
            
        # Get first 40 chars of core to categorize
        cat = core[:40]
        if cat not in printed_samples:
            print(f"  - {line}")
            printed_samples.add(cat)
            if len(printed_samples) >= 8:
                break

if __name__ == "__main__":
    analyze_errors("app_20260527.log")
    analyze_errors("app_20260528.log")
