import os
import csv
from datetime import datetime

class CsvExporter:
    @staticmethod
    def export(data: list, log_callback=None) -> str:
        """주어진 데이터를 CSV로 저장하고 저장된 파일 경로를 반환합니다."""
        if not data:
            return ""
            
        os.makedirs("result", exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = os.path.join("result", f"approval_changes_{timestamp}.csv")
        
        try:
            with open(filename, mode='w', encoding='utf-8-sig', newline='') as f:
                writer = csv.writer(f)
                headers = list(data[0].keys())
                writer.writerow(headers)
                
                for row in data:
                    writer.writerow([row.get(h, "") for h in headers])
                    
            if log_callback:
                log_callback(f"CSV 저장 완료: {filename}")
            return filename
        except Exception as e:
            if log_callback:
                log_callback(f"CSV 저장 실패: {e}")
            return ""
