# ApprovalRadar 배포 가이드

> 인허가 변동 모니터링 시스템 — 로컬 실행 가이드

---

## 📦 일반 사용자 — 실행 방법

### macOS

1. `dist_release` 폴더에서 **`ApprovalRadar`** 파일을 더블클릭합니다.
2. 처음 실행 시 macOS 보안 경고가 뜰 수 있습니다:
   - **시스템 환경설정** → **개인정보 보호 및 보안** → "확인 없이 열기" 클릭
3. 런처 창이 뜨고, 잠시 후 브라우저가 자동으로 열립니다.
4. 프로그램 종료 시 런처 창의 **[종료]** 버튼을 클릭합니다.

### Windows

1. `dist_release` 폴더에서 **`ApprovalRadar.exe`** 파일을 더블클릭합니다.
2. Windows Defender 경고가 뜨면: **"추가 정보"** → **"실행"** 클릭
3. 런처 창이 뜨고, 잠시 후 브라우저가 자동으로 열립니다.
4. 프로그램 종료 시 런처 창의 **[종료]** 버튼을 클릭합니다.

---

## ⚙️ API 키 설정

`dist_release/.env` 파일을 메모장(Windows) 또는 텍스트 편집기(Mac)로 열어 수정합니다.

```dotenv
FOOD_SAFETY_API_KEY_1=여기에_키_입력
FOOD_SAFETY_API_KEY_2=여기에_키_입력
# ... 최대 9개까지 등록 가능
```

> API 키 발급: [공공데이터포털](https://www.data.go.kr) → 식품안전나라 API 신청

---

## 🔄 포트 충돌 안내

- 기본 포트: **8000**
- 포트가 이미 사용 중이면 자동으로 **8001 ~ 8010** 중 사용 가능한 포트로 변경됩니다.
- 런처 창에 노란색 알림으로 변경된 포트를 표시합니다.

---

## 🗄️ 데이터베이스

- DB 파일: 실행 파일과 같은 폴더에 `food_safety.db` 자동 생성
- DB를 초기화하려면: `food_safety.db` 파일을 삭제 후 재실행

---

## ❓ 문제 해결 FAQ

| 증상 | 해결 방법 |
|------|-----------|
| 브라우저가 자동으로 안 열림 | 런처 창의 [브라우저 열기] 버튼 클릭 |
| "포트를 찾을 수 없음" 오류 | 8000~8010 포트를 점유한 프로그램 종료 후 재시작 |
| 데이터가 안 불러와짐 | API 키가 `.env`에 올바르게 입력됐는지 확인 |
| Mac 보안 경고로 실행 불가 | 시스템 환경설정 → 개인정보 보호 및 보안 → 허용 클릭 |
| Windows에서 실행 파일 차단 | Windows Defender → 추가 정보 → 실행 클릭 |

---

---

## 👨‍💻 개발자 — 빌드 방법

### 사전 요구사항

| 도구 | 최소 버전 |
|------|-----------|
| Python | 3.11+ |
| Node.js | 18+ |
| npm | 9+ |

### macOS 빌드

```bash
# 프로젝트 루트에서 실행
bash build.sh
```

### Windows 빌드

```batch
:: 프로젝트 루트에서 실행 (cmd 또는 더블클릭)
build.bat
```

### 빌드 결과물

```
dist_release/
├── ApprovalRadar(.exe)   ← 단일 실행 파일
├── .env                  ← API 키 설정
└── 실행방법.txt          ← 사용자 안내
```

> **⚠️ 크로스 컴파일 주의**  
> PyInstaller는 크로스 컴파일을 지원하지 않습니다.  
> Mac용 실행 파일은 Mac에서, Windows용 실행 파일은 Windows PC에서 각각 빌드해야 합니다.

### 개발 환경 실행 (빌드 없이)

```bash
# 백엔드
cd ApprovalRadar-BE
source venv/bin/activate
uvicorn main:app --reload --port 8000

# 프론트엔드 (별도 터미널)
cd ApprovalRadar-FE
npm run dev
```

---

## 🗂️ 프로젝트 구조

```
ApprovalRadar/
├── build.sh                 ← Mac 빌드 스크립트
├── build.bat                ← Windows 빌드 스크립트
├── DEPLOY.md                ← 이 문서
├── dist_release/            ← 빌드 결과물 (gitignored)
├── ApprovalRadar-BE/
│   ├── launcher.py          ← PyInstaller 진입점 (Tkinter GUI)
│   ├── ApprovalRadar.spec   ← PyInstaller 스펙
│   ├── main.py              ← FastAPI 앱
│   ├── database.py          ← SQLite 관리
│   ├── .env                 ← API 키
│   └── app/
│       └── core/port_finder.py ← 포트 자동 탐지
└── ApprovalRadar-FE/
    ├── .env.production      ← 배포 빌드용 환경변수
    └── src/
```
