import csv
import sys

# UTF-8 출력 설정
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

csv_path = r"c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\PleaseTest\compare_result_0520.csv"

exists_y = 0
exists_n = 0
missed_y = 0
reasons = {}

with open(csv_path, "r", encoding="utf-8-sig") as f:
    reader = csv.DictReader(f)
    rows = list(reader)

for r in rows:
    if r["DB_EXISTS"] == "Y":
        exists_y += 1
    else:
        exists_n += 1
        
    if r["IS_MISSED"] == "Y":
        missed_y += 1
        reason = r["MISSED_REASON"]
        reasons[reason] = reasons.get(reason, 0) + 1

print(f"Total rows in CSV: {len(rows)}")
print(f"  DB_EXISTS = Y: {exists_y}")
print(f"  DB_EXISTS = N: {exists_n}")
print(f"  IS_MISSED = Y: {missed_y}")
print(f"  Reasons: {reasons}")

print("\nFirst 10 rows in CSV:")
for i, r in enumerate(rows[:10]):
    print(f"  {i+1}. LCNS: {r['LCNS_NO']} | Name: {r['BSSH_NM']} | API Date: {r['CHNG_DT']} | DB Date: {r['DB_LAST_EVENT_DATE']} | Missed: {r['IS_MISSED']} ({r['MISSED_REASON']})")
