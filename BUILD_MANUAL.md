# ApprovalRadar — 빌드 매뉴얼 (개발자용)

> **대상:** 개발자 / 운영 담당자  
> **목적:** Mac/Windows 배포용 단일 실행 파일 (`dist_release/`) 생성  
> **최종 수정:** 2026-05-17

---

## 1. 사전 요구사항

| 항목 | 최소 버전 | 확인 명령 |
|------|-----------|-----------|
| Python | 3.11 이상 | `python3 --version` |
| Node.js | 18 이상 | `node --version` |
| npm | 9 이상 | `npm --version` |
| Git | 아무 버전 | `git --version` |

> **macOS 권장:** Homebrew로 설치된 Python 사용  
> **Windows 권장:** python.org 공식 installer 사용, "Add to PATH" 체크 필수

---

## 2. 빌드 전 체크리스트

빌드 전 아래 항목을 반드시 확인합니다.

### 2-1. DB 파일 준비 (핵심)

```
ApprovalRadar-BE/food_safety.db   ← 이 파일이 빌드에 포함됩니다
```

- **미러링 완료 상태**여야 합니다 (약 40만 건 이상)
- 미러링이 안 된 경우: `python cli.py --mirror` 실행 후 빌드
- DB가 없어도 빌드는 성공하지만, 배포 패키지에 빈 DB로 출시됩니다

### 2-2. `.env` 파일 확인

```
ApprovalRadar-BE/.env   ← API 키 포함, 반드시 존재해야 함
```

```env
FOOD_SAFETY_API_KEY_1=키1
FOOD_SAFETY_API_KEY_2=키2
# 또는 FOOD_SAFETY_API_KEY=키1 (단일 키)
```

### 2-3. 프론트엔드 소스 상태 확인

```bash
# FE 소스 최신 상태인지 확인
git status
git pull
```

---

## 3. macOS 빌드

### 3-1. 빌드 실행

프로젝트 루트(`ApprovalRadar/`)에서 실행합니다:

```bash
bash build.sh
```

### 3-2. 빌드 단계 설명

| 단계 | 내용 | 소요 시간 |
|------|------|-----------|
| STEP 1 | React 프론트엔드 빌드 (`npm run build`) | ~1분 |
| STEP 2 | FE dist → BE 폴더 복사 | ~5초 |
| STEP 3 | Python venv 생성 + 패키지 설치 + PyInstaller 설치 | ~2분 |
| STEP 4 | PyInstaller 단일 exe 빌드 | ~3~5분 |
| 마무리 | dist_release/ 패키지 정리 | ~5초 |

### 3-3. 결과 확인

```
dist_release/
├── ApprovalRadar       ← 실행 파일 (약 80~150MB)
├── .env                ← API 키 (편집 가능)
├── food_safety.db      ← 인허가 데이터 DB
└── 실행방법.txt        ← 사용자 안내
```

---

## 4. Windows 빌드

> ⚠️ **Windows에서 직접 빌드해야 합니다.** macOS에서 생성된 exe는 Windows에서 실행 불가.

### 4-1. 빌드 실행

`build.bat`를 **더블클릭** 하거나, cmd에서:

```bat
cd C:\경로\ApprovalRadar
build.bat
```

### 4-2. 주의사항

- **Python PATH:** 시스템 PATH에 Python이 등록되어 있어야 합니다
- **uvloop:** Windows 미지원 → 빌드 스크립트가 자동으로 제거 처리
- **Windows Defender:** 빌드 중 바이러스 스캔으로 빌드 속도 저하 가능 (정상)

### 4-3. 결과 확인

```
dist_release\
├── ApprovalRadar.exe   ← 실행 파일
├── .env
├── food_safety.db
└── 실행방법.txt
```

---

## 5. 자주 발생하는 빌드 오류

### 오류: `ModuleNotFoundError` (실행 시)

PyInstaller가 일부 모듈을 누락했을 때 발생합니다.

**원인:** `ApprovalRadar.spec`의 `hiddenimports`에 해당 모듈이 없음  
**해결:**

```python
# ApprovalRadar.spec 의 hiddenimports에 추가
'app.새로운.모듈이름',
```

이후 재빌드:
```bash
bash build.sh
```

### 오류: `[ERROR] FE 빌드 실패: dist/ 폴더가 없음`

```bash
cd ApprovalRadar-FE
npm install
npm run build
```

### 오류: macOS 보안 경고 (배포 후)

```bash
# 개발자 인증서 없이 배포 시 발생 - 아래 명령으로 해제
xattr -cr ./ApprovalRadar
```

### 오류: iCloud Drive 빌드 실패

iCloud 자동 동기화 경로에서 빌드 시 타이밍 충돌이 발생할 수 있습니다.

**해결:** `/tmp` 또는 iCloud 외부 경로에 프로젝트 복사 후 빌드

### 오류: `libexpat` 충돌 (macOS)

Homebrew Python 3.12+에서 발생. `build.sh`에 자동 해결 로직 내장됨 (정상 처리).

---

## 6. 배포 패키지 전달

### 6-1. 압축 (macOS)

```bash
cd dist_release
zip -r ApprovalRadar_v$(date +%Y%m%d)_mac.zip .
```

### 6-2. 압축 (Windows)

`dist_release` 폴더를 우클릭 → "압축 폴더로 보내기"

### 6-3. 고려사항

| 항목 | 내용 |
|------|------|
| 파일 크기 | ~100~200MB (DB 크기 포함) |
| DB 포함 여부 | 포함 (약 30~50MB, 40만 건 기준) |
| API 키 보안 | `.env` 파일에 평문 저장 — 내부 배포 시에만 사용 |
| 크로스 플랫폼 | Mac 빌드 → Mac 전용 / Windows 빌드 → Windows 전용 |

---

## 7. 버전 관리 권장 흐름

```
1. BE/FE 코드 변경
2. git commit & push
3. DB 최신 상태 확인 (python cli.py --mirror 필요 시)
4. bash build.sh (또는 build.bat)
5. dist_release/ 압축 → 배포
```

---

## 8. spec 파일 구조 참고

`ApprovalRadar-BE/ApprovalRadar.spec`

- **진입점:** `launcher.py` (Tkinter GUI 런처)
- **포함 데이터:** FE dist/, .env, app/, database.py, main.py, scraper.py, excel_export.py
- **DB 파일:** spec에 포함하지 않음 → exe 옆에 별도 파일로 배치 (쓰기 가능)
- **단일 파일 모드:** UPX 압축 적용

