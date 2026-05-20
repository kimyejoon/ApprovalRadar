<p align="center">
  <h1 align="center">🔍 인허가RADAR (ApprovalRadar)</h1>
  <p align="center">
    <b>식품안전나라 공공DB의 음식점업소 인허가 변동분을 실시간에 가깝게 포착하는 로컬 모니터링 시스템</b>
  </p>
  <p align="center">
    <img src="https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white" alt="Python">
    <img src="https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white" alt="FastAPI">
    <img src="https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black" alt="React">
    <img src="https://img.shields.io/badge/SQLite-003B57?logo=sqlite&logoColor=white" alt="SQLite">
    <img src="https://img.shields.io/badge/TypeScript-3178C6?logo=typescript&logoColor=white" alt="TypeScript">
  </p>
</p>

---

## 📌 개요

**인허가RADAR**는 식품안전나라 공공 데이터베이스의 변동분을 **실시간에 가깝게 포착**하여 웹 대시보드로 조회할 수 있는 로컬 데스크톱 프로그램입니다.

담당 공무원이 공공DB에 새로운 데이터를 올리면, **실시간 Live DB 우회 파라미터를 활용해 5분~25분(Oldest First Scan 1회전) 이내에** 즉시 포착되어 대시보드에 변동분으로 반영됩니다.

### 핵심 가치

| 💡 | 설명 |
|---|---|
| **실시간성 보장** | `SYS_SYNC=LIVE` 가짜 파라미터를 강제 동봉하여 19:00 당일 제한 우회 및 실시간 Live DB(View B) 조회 |
| **Oldest-First 롤링** | 각 페이지별 마지막 조회 타임스탬프를 보존, 1시간이 넘은 페이지 최우선 스캔 및 평시 5분 주기 순환 |
| **비용 최적화** | 이진탐색/Tail Ping/Sentinel 분석을 배제한 순수 Oldest First 롤링으로 API 호출 및 WAF 차단 최소화 |
| **완전 로컬** | 모든 데이터가 사용자 PC에만 저장, 외부 서버 전송 없음 |
| **무인 운영** | API 키 자동 교체, 장애 자가 복구, 자정 한도 리셋 — 한 번 켜두면 알아서 동작 |

---

## 🏗️ 아키텍처

```
┌────────────────────────────────────────────────────────────────────┐
│                         사용자 PC (localhost:8000)                   │
│                                                                     │
│  ┌──────────────┐     SSE (실시간 알림)     ┌──────────────────┐     │
│  │  React (FE)  │ ◄──────────────────────► │  FastAPI (BE)     │    │
│  │  Vite + TS   │     REST API             │  Python 3.11+     │    │
│  │  Dashboard   │ ◄──────────────────────► │  APScheduler      │    │
│  └──────────────┘                           │  httpx AsyncClient│    │
│        ↑ 동일 포트 서빙 (SPA)                └──────┬───────────┘    │
│                                                    │                │
│  ┌────────────────────────┐    ┌──────────────────────────────┐    │
│  │  SQLite (food_safety.db)│ ◄──│  DiffCrawlerEngine           │    │
│  │  · businesses           │    │  · I2861: Oldest First Scan  │    │
│  │  · crawler_state        │    │    (SYS_SYNC=LIVE 우회 강제)  │    │
│  │  · api_keys             │    │  · ChangeDetector             │    │
│  │  · raw_data / memos     │    │                              │    │
│  └────────────────────────┘    └──────────┬───────────────────┘    │
│                                           │                        │
│                                           ▼                        │
│                               식품안전나라 공공 API                    │
│                               (openapi.foodsafetykorea.go.kr)       │
│                               I2861 (변동감지) + I2500 (백필)         │
└────────────────────────────────────────────────────────────────────┘
```

---

## 🔬 핵심 알고리즘 — "어떻게 실시간 변동을 효과적으로 포착하나?"

음식점 인허가변경정보(`I2861`) 서비스는 24시간 실시간 조회를 위해 Live DB(View B, 약 4,800여 건 규모)를 타겟팅하며, API 호출 낭비를 방지하기 위한 이원화된 롤링 수집 구조를 사용합니다.

### 1단계: 실시간 Live DB(View B) 우회 파라미터 강제화

- 식품안전나라 API는 기본적으로 19:00 이후에만 당일 데이터(View A)를 병합해 제공합니다.
- `I2861` 서비스 호출 시, URL 끝에 가짜 파라미터(`SYS_SYNC=LIVE`)를 항상 동봉하여 강제로 호출함으로써 **19:00 이전에도 주간의 실시간 변동분(View B)을 24시간 강제 포착**합니다.

### 2단계: Oldest-First Scan (5분 주기) — 임계치 최대 1시간 보장

```
API 호출 비용: 실행 주기당 1~2페이지 (I2861 전체 5페이지 기준)
전체 페이지 순환 완료: 약 25분 (5분 주기 기준)
```

- **상태 보존**: SQLite `crawler_state`에 페이지 번호(1~5)별 최종 스캔 시각(`page_timestamps`)을 영속적으로 관리합니다.
- **최우선(Oldest) 스캔**: 마지막 스캔 시점으로부터 **1시간(3,600초) 이상 지났거나** 기록이 없는 페이지는 스케줄러가 즉시 감지하여 최우선 스캔 대상으로 강제 선정합니다.
- **평시 롤링 스캔**: 1시간을 초과한 페이지가 없으면, 전체 페이지 중 가장 오래전에 조회한 1개 페이지를 롤링하여 순차 순회합니다. 
- 이를 통해 매 주기마다 전체 페이지(5,000건)를 전부 긁어오는 무의미한 API 호출 낭비를 없애고, WAF 차단 위험을 원천 예방하며, 모든 페이지의 최신성을 1시간 이내로 완벽히 보장합니다.

### 3단계: 이진탐색 및 Sentinel 제거를 통한 단순화
- `I2861` 서비스는 전체 데이터 규모가 작으므로(~4,800건) 이진탐색, Tail Ping, Multi-Point Sentinel, 피벗 검증 및 Shift 분석 등 불필요한 레이턴시 유발 요소와 복잡한 분기 로직을 전면 배제했습니다.
- 단, 플레이그라운드 연동을 위한 **수동 Range Scan** 기능은 하위 호환성을 위해 유지되어 특정 범위의 데이터 재스캔을 보장합니다.

### 4단계: INFO-700 디버깅 및 자가 진단
- API 통신 중 파라미터 검증 오류를 뜻하는 `INFO-700` 응답이 감지되면, 호출 파라미터, 마스킹된 API 키 정보, 원본 메시지를 상세히 에러 로그에 남깁니다.
- 이를 통해 식품안전나라 API 서버 측의 실시간 우회 파라미터 차단 시도나 패치를 실시간으로 진단하고 신속하게 대응할 수 있습니다.

---

## 🛡️ 자가 복구 메커니즘

| 장애 유형 | 자동 대응 |
|---|---|
| **API 키 한도 초과** | 다음 활성 키로 즉시 교체 (Key Rotation). 전체 소진 시 10분마다 회복 체크 |
| **WAF 차단** | 키 전환 + 지수 백오프 재시도. Jitter(0.5~1.5초 랜덤 딜레이)로 인간적 패턴 유지 |
| **크롤러 연속 실패** | 5회 연속 실패 시 관리자 ALERT. API 키 회복 시 즉시 재가동 |
| **자정 한도 리셋** | 매일 자정 API 한도 자동 초기화, 소진 상태 클리어 |

---

## 🖥️ 주요 기능

### 📊 실시간 대시보드
- 수집된 인허가 변동 정보를 최신순으로 조회
- 미확인 항목은 **초록색 하이라이트**로 강조 (클릭 시 읽음 처리)
- 지역/날짜/업종/변동유형 필터링
- 트렌드 차트, 상태 분포 파이차트, 오늘/이번 달 지표

### 🔔 실시간 알림 (SSE)
- 변동 감지 즉시 → **알림음 + 토스트 팝업**
- UPDATE / ALERT / WARN 타입 별도 처리

### 📝 상세 정보 및 메모
- 업소별 상세 모달: `license_no`(인허가번호) 기반 이력 조회 — 상호변경/미색인과 무관하게 정확 매칭
- 연락처, 이전 대표자, 이전 영업상태, BF/AF 기반 변경사유 추론
- 메모장 기능: 진행 상황/연락 기록 저장 (CRUD)
- 외부 링크: 다이닝코드, 네이버지도, 카카오맵 바로가기

### 🔑 API 키 관리
- 런타임 중 키 추가/삭제 즉시 반영 (DB 기반, .env fallback)
- 키별 일일 사용량/상태(활성/소진) 실시간 모니터링
- 잔여량 경고 (900/950/990건 도달 시 SSE)

### 📋 시스템 모니터링 (Playground)
- 크롤러 동작 실시간 로그 조회 (WebSocket)
- 스케줄러 상태: 다음 실행 시각, 주기, 현재 상태
- 페이지 스캔 히스토리: 페이지별 마지막 스캔 시각 + 연식
- 오늘 감지 이력: 변동 감지 타임라인
- Tail 히스토리: 총건수 변동 추이

### 📥 엑셀 내보내기
- 조회 중인 데이터를 `.xlsx` 파일로 추출

### ⚙️ 설정 페이지
- 크롤링 주기 실시간 변경 (서버 재시작 불필요)
- Rolling Scan 페이지 수 조정
- API 키 CRUD

---

## 🧱 기술 스택

| 구분 | 기술 |
|---|---|
| **Backend** | Python 3.11+, FastAPI, uvicorn, APScheduler |
| **Frontend** | React 18, TypeScript, Vite, Radix UI (shadcn/ui), TanStack Query |
| **Database** | SQLite (food_safety.db) — 로컬 내장 |
| **HTTP Client** | httpx (AsyncClient, Keep-Alive, 키별 직렬화 Lock) |
| **실시간 통신** | Server-Sent Events (SSE) + WebSocket (로그 스트림) |
| **빌드/배포** | PyInstaller (단일 실행 파일), batch 스크립트 |
| **디자인 시스템** | Supabase 영감 다크 모드 (emerald green accent) |

---

## 📁 프로젝트 구조

```
ApprovalRadar/
├── ApprovalRadar-BE/              # 백엔드 (Python)
│   ├── main.py                    # FastAPI 앱 진입점 (포트 8000)
│   ├── cli.py                     # CLI 관리 도구 (bootstrap, mirror, backfill 등)
│   ├── scraper.py                 # 메인 스크래퍼 (DB 저장 + SSE 발행 + 즉시 Backfill)
│   ├── database.py                # SQLite 스키마 초기화 + 유틸리티
│   ├── excel_export.py            # 엑셀 내보내기 생성
│   ├── app/
│   │   ├── api/                   # REST API 엔드포인트
│   │   │   └── endpoints/         # approvals, playground, settings, stream
│   │   ├── clients/               # 식품안전나라 API 클라이언트 + 키 관리
│   │   ├── core/                  # 설정, 스케줄러, 로거, 이벤트
│   │   ├── repositories/          # DB 접근 계층 (business, state, memo, raw_data)
│   │   ├── schemas/               # Pydantic 요청/응답 모델
│   │   └── services/              # 핵심 비즈니스 로직
│   │       ├── diff_crawler/      # DiffCrawlerEngine (I2861 Oldest-First Scan 제어)
│   │       │   └── engine.py      # 메인 롤링 스캔 코어 엔진
│   │       ├── change_detector.py # 변동 유형 감지 (BF/AF 기반 추론)
│   │       └── industry_filler.py # I2500 세부업종/대표자/인허가일 Backfill
│   └── .env                       # API 키 + 환경 설정
├── ApprovalRadar-FE/              # 프론트엔드 (React + TypeScript)
│   ├── src/
│   │   ├── pages/                 # DashboardPage, SettingsPage, LogPage, PlaygroundPage
│   │   ├── components/            # UI 컴포넌트 (features, layout, ui)
│   │   │   └── features/          # ApprovalDetailModal, FilterPanel 등
│   │   ├── hooks/                 # React 커스텀 훅 (useSSE, useApprovals 등)
│   │   ├── lib/                   # API 클라이언트, 유틸리티, 상수
│   │   └── store/                 # 상태 관리 (Zustand)
│   └── dist/                      # 프로덕션 빌드 (정적 파일, FastAPI가 동일 포트에서 서빙)
├── dist_release/                  # 배포 패키지 (exe + .env + DB)
├── build.bat                      # Windows 빌드 스크립트
└── README.md                      # ← 이 문서
```

---

## ⚙️ 스케줄링 체계

| 잡 | 주기 | 역할 |
|---|---|---|
| **Scraper Job** | 5분 (기본값, 실시간 변경 가능) | DiffCrawlerEngine 실행 → I2861 Oldest First Scan 진행 (5분당 1~2개 페이지 롤링) |
| **Key Recovery** | 10분 | 소진된 API 키 회복 여부 체크 → 회복 시 즉시 크롤링 재개 |
| **Industry Backfill** | 6시간 + 신규 INSERT 시 즉시 | I2500 API로 세부업종/대표자/연락처/인허가일(PRMS_DT) 보완 |
| **DB Vacuum** | 일요일 03:00 | SQLite VACUUM 최적화 |
| **DB Backup** | 매일 04:00 | 자동 백업 |

---

## 📊 데이터 수집 파이프라인

```
신규 변동 감지 (Oldest-First Scan에 의한 격차 감지)
  ↓
_run_i2861_oldest_first_scan: 롤링 선정 페이지 Fetch 및 DB 비교
  ↓
flush_callback → run_scraper_for_service_with_rows
  ↓
필드 매핑 + BF/AF 기반 변경사유 추론 (infer_change_type_from_bf_af)
  ↓
batch SELECT 중복 확인 → DB INSERT (license_no + last_event_date 복합키)
  ↓
오늘 변동분 → SSE 발행 (UPDATE 타입) → 프론트 토스트 팝업
  ↓
즉시 Backfill (백그라운드 스레드) → I2500 API로 세부업종/인허가일 채움
```

---

## ⚠️ 프로그램 사용 시 주의할 점

### 1. 프로그램은 항상 켜두세요
프로그램 창을 닫으면 서버와 크롤러가 모두 종료됩니다. **최소화하여 백그라운드에 유지**해 주세요.

### 2. API 키 관리
- 공공데이터 API 키는 **키당 하루 1,000회 한도**입니다.
- 안정적인 모니터링을 위해 **10~12개의 API 키**를 등록하는 것을 권장합니다.
- 12개 키 기준: 일일 ~15,000회 호출로 약 95분에 전체 DB 1회전 가능

### 3. 초기 실행 시 시간 소요
- 최초 실행 시 **Bootstrap**이 필요하지 않으며, 단 1초 만에 베이스라인이 바로 수립됩니다.
- 초기 로드가 완료되면 즉시 5분 주기마다 롤링하며 변동 데이터 포착을 개시합니다.

### 4. 빌드 시 주의
- **빌드 전 반드시 ApprovalRadar.exe를 종료**해야 합니다.
- exe가 실행 중이면 `The process cannot access the file` 에러로 새 exe가 교체되지 않습니다.
- 앱 실행 중 DB를 외부에서 수정하면, 종료 시 메모리상의 데이터가 DB를 덮어씁니다.

### 5. 네트워크 환경
- 식품안전나라 API 서버의 일시적 장애 시 자동 재시도 (지수 백오프)
- WAF(웹 방화벽) 차단 방지를 위해 요청 간 **랜덤 딜레이(Jitter, 0.5~1.5초)** 적용

### 6. 데이터 안전
- 모든 데이터는 로컬 SQLite DB (`food_safety.db`)에만 저장됩니다.
- 외부 서버로 데이터가 전송되는 일은 없습니다.
- 매일 새벽 4시 자동 백업, 일요일 새벽 3시 DB 최적화

---

## 🚀 빠른 시작

### Windows (배포 버전)
```bash
# 1. dist_release 폴더의 ApprovalRadar.exe 더블클릭
# 2. 브라우저에서 자동으로 열리거나 http://localhost:8000 접속
```

### 개발 환경
```bash
# 백엔드
cd ApprovalRadar-BE
python -m venv venv && venv\Scripts\activate
pip install -r requirements.txt
python main.py
# → http://localhost:8000

# 프론트엔드 (별도 터미널, 개발 시에만)
cd ApprovalRadar-FE
npm install
npm run dev
# → http://localhost:5173 (HMR)
```

### CLI 관리 도구
```bash
cd ApprovalRadar-BE

python cli.py --check-keys          # API 키 상태 점검
python cli.py --test-tail            # 실시간 Tail 위치 조회
python cli.py --run-sync             # 수동 1회 크롤링
python cli.py --backfill             # 누락 세부업종 백필
python cli.py --full-scan-init       # DB 초기화 + 전체 Bootstrap
python cli.py --reset-state          # 피벗/Tail 상태만 리셋
python cli.py --mirror               # 전체 API 미러링 (~1,191회 호출)
```

자세한 설치 방법은 [INSTALL_MANUAL.md](INSTALL_MANUAL.md), 빌드 방법은 [BUILD_MANUAL.md](BUILD_MANUAL.md)를 참고하세요.

---

## 📊 성능 지표 (I2861 기준, 5분 실행 주기)

| 지표 | 수치 |
|---|---|
| 전체 Live DB 규모 (View B) | ~4,800건 (5개 페이지) |
| 전체 1회전 시간 | ~25분 (5분 주기당 1개 페이지 롤링 기준) |
| 신규 변동 감지 지연 | 최대 1시간 이내 100% 동기화 (1시간 초과 페이지 강제 스캔) |
| 주기당 API 호출 | 1~2회 (평시 1회, 1시간 경과 우선순위 페이지 존재 시 최대 2회) |
| 일일 API 호출 | 288회 ~ 576회 (초저비용 고효율) |
| WAF 차단 및 API 소진율 | 0%에 수렴 (키당 호출 횟수 극소량) |
| 스캔 소요 시간/주기 | ~5초 내외 (동작 지연 극소화) |
| DB 정합성 커버리지 | 1시간 이내 100% 전체 페이지 동기화 보장 |

---

<p align="center">
  <sub>Built with ❤️ for public data transparency</sub>
</p>
