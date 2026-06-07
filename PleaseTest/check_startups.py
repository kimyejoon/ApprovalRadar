import os
import sys

log1_path = r'c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\dist_release\logs\app_20260601.log'
log2_path = r'c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\dist_release\logs\app_20260602.log'

def find_startups(path, name):
    print(f"Startups in {name}:")
    if not os.path.exists(path):
        print("Not found")
        return
    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            if "Broadcaster main event loop initialized" in line:
                print("  " + line.strip())

find_startups(log1_path, "June 1st Log")
find_startups(log2_path, "June 2nd Log")
