import pandas as pd
import sys

# UTF-8 출력 설정
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

xlsx_path = r"c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\PleaseTest\업소인허가 데이터 조회(2026-05-22) (3).xlsx"
try:
    df = pd.read_excel(xlsx_path, nrows=5)
    print("Columns found in Excel:")
    for col in df.columns:
        print(f" - {col}")
    print("\nFirst row sample:")
    print(df.iloc[0].to_dict() if len(df) > 0 else "Empty sheet")
except Exception as e:
    print(f"Error reading Excel: {e}")
