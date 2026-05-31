import os
import sys

# UTF-8 출력 설정
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

log_path = r"c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\ApprovalRadar-BE\logs\app_20260525.log"

def analyze_log():
    if not os.path.exists(log_path):
        print(f"❌ 로그 파일이 존재하지 않습니다: {log_path}")
        return

    # 인코딩 후보 시도 (cp949, utf-8, utf-16)
    encodings = ['cp949', 'utf-8', 'utf-16', 'euc-kr']
    content = None
    for enc in encodings:
        try:
            with open(log_path, 'r', encoding=enc) as f:
                lines = f.readlines()
            print(f"✅ 성공적으로 {enc} 인코딩으로 로그 파일 로드 완료. (총 {len(lines)}라인)")
            content = lines
            break
        except Exception:
            continue

    if not content:
        print("❌ 로그 파일의 인코딩을 감지하지 못했습니다.")
        return

    # 1. 에러 및 예외 키워드 수집
    error_keywords = ['error', 'exception', 'nameerror', 'fail', 'error:', '❌', 'traceback']
    errors = []
    
    # 2. Poller 흐름 분석
    poller_cycles = []
    
    # 3. Oldest-First Scan 흐름 분석
    scan_cycles = []
    
    # 4. WAF 차단 및 API 한도 초과
    waf_blocks = 0
    key_rotations = 0

    for idx, line in enumerate(content):
        line_num = idx + 1
        line_lower = line.lower()
        
        # 에러 검출 (단, [INFO] 레벨 로그 중 'fail' 단어 포함된 일반 로그는 필터링)
        has_err_kw = any(kw in line_lower for kw in error_keywords)
        is_real_err = has_err_kw and ('[error]' in line_lower or '[warning]' in line_lower or 'exception' in line_lower or 'traceback' in line_lower)
        if is_real_err:
            errors.append((line_num, line.strip()))

        # Poller 분석
        if '[전략c]' in line_lower or 'chng_dt poller' in line_lower:
            if '폴링 시작' in line:
                poller_cycles.append({'type': 'START', 'line': line_num, 'text': line.strip()})
            elif '폴링 완료' in line:
                poller_cycles.append({'type': 'END', 'line': line_num, 'text': line.strip()})
            elif '완료: CHNG_DT=' in line:
                poller_cycles.append({'type': 'SUMMARY', 'line': line_num, 'text': line.strip()})

        # Oldest-First Scan 분석
        if '[i2861]' in line_lower or 'oldest first scan' in line_lower:
            if '사이클 시작' in line:
                scan_cycles.append({'type': 'START', 'line': line_num, 'text': line.strip()})
            elif 'oldest first scan 완료' in line:
                scan_cycles.append({'type': 'END', 'line': line_num, 'text': line.strip()})

        # WAF 및 한도 초과 집계
        if 'waf' in line_lower and '차단' in line:
            waf_blocks += 1
        if '키 회전' in line or '키를 전환' in line or '임시 키 전환' in line:
            key_rotations += 1

    print("\n==================================================")
    print(f"🔥 [1] 에러/경고 로그 발견 건수: {len(errors)}건")
    print("==================================================")
    for num, err in errors[-30:]:  # 최근 30개 에러만 출력
        print(f"  Line {num:5d} | {err}")

    print("\n==================================================")
    print(f"🔄 [2] CHNG_DT Poller 3중 폴링 주기 흐름 (최근 15개 이벤트)")
    print("==================================================")
    for p in poller_cycles[-15:]:
        print(f"  Line {p['line']:5d} | {p['text']}")

    print("\n==================================================")
    print(f"🚀 [3] I2861 Oldest-First Scan 차분 동기화 흐름 (최근 10개 이벤트)")
    print("==================================================")
    for s in scan_cycles[-10:]:
        print(f"  Line {s['line']:5d} | {s['text']}")

    print("\n==================================================")
    print(f"🔑 [4] API 키 및 방화벽 우회 모니터링")
    print("==================================================")
    print(f"  - WAF 임시 차단 쿨다운 감지 횟수: {waf_blocks}회")
    print(f"  - API 키 자동 교체/로테이션 횟수: {key_rotations}회")
    print("==================================================")

if __name__ == "__main__":
    analyze_log()
