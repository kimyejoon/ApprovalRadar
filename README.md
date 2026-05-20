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

담당 공무원이 공공DB에 새로운 데이터를 올리면, **실시간 Live DB 우회 파라미터를 활용해 최대 1시간(Oldest-First Scan 1회전) 이내에** 즉시 포착되어 대시보드에 변동분으로 반영됩니다.

### 핵심 가치

| 💡 | 설명 |
|---|---|
| **실시간성 보장** | `SYS_SYNC=LIVE` 가짜 파라미터를 강제 동봉하여 19:00 당일 제한 우회 및 실시간 Live DB(View B) 조회 |
| **Oldest-First 롤링** | 페이지별 마지막 조회 타임스탬프 영속 관리, 1시간 초과 전체 페이지 무제한 즉시 스캔 |
| **동적 범위 추적** | `last_total_count` 기반 총 페이지 수 자동 계산 + Tail Probe(+3p)로 신규 tail 확장 감지 |
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
│  │  · businesses          │    │  · I2861: Oldest-First Scan  │    │
│  │  · crawler_state       │    │    (953p, SYS_SYNC=LIVE 우회) │    │
│  │  · api_keys            │    │  · ChangeDetector            │    │
│  │  · raw_data / memos    │    │  · Tail Probe (+3p 자동 감지) │    │
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

음식점 인허가변경정보(`I2861`) 서비스는 24시간 실시간 조회를 위해 Live DB(View B, **약 95만 건 규모, 953페이지**)를 타겟팅하며, 효율적인 롤링 수집 구조를 사용합니다.

### 1단계: 실시간 Live DB(View B) 우회 파라미터 강제화

- 식품안전나라 API는 기본적으로 19:00 이후에만 당일 데이터(View A)를 병합해 제공합니다.
- `I2861` 서비스 호출 시, URL 끝에 가짜 파라미터(`SYS_SYNC=LIVE`)를 항상 동봉하여 강제로 호출함으로써 **19:00 이전에도 주간의 실시간 변동분(View B)을 24시간 강제 포착**합니다.

### 2단계: Oldest-First Scan (30분 주기) — 임계치 최대 1시간 보장

```
전체 DB 규모:   ~952,999건 (953페이지, 페이지당 1,000건)
스캔 주기:      30분
1시간 초과 시:  해당 페이지 전체 무제한 즉시 스캔 (MAX_PAGES_PER_CYCLE 제한 없음)
Tail Probe:     마지막 known page + 3p 추가 조회 (신규 tail 확장 자동 감지)
```

- **동적 총 페이지 계산**: SQLite `crawler_state`의 `last_total_count`에서 페이지 수를 실시간 계산합니다. 하드코딩 없음.
- **상태 영속 보존**: 페이지 번호별 최종 스캔 시각(`page_timestamps`)과 상호명 대역(`page_labels`, e.g. `가~나`)을 SQLite에 영속 관리합니다.
- **최우선(Oldest) 스캔**: 마지막 스캔 시점으로부터 **1시간(3,600초) 이상 지났거나** 기록이 없는 페이지는 스케줄러가 즉시 감지하여 **전체 무제한** 동시 스캔합니다.
- **평시 롤링 스캔**: 1시간을 초과한 페이지가 없으면, 전체 페이지 중 가장 오래된 1페이지를 롤링하여 순차 순회합니다.
- **Tail Probe +3**: 매 사이클마다 마지막 알려진 페이지 이후 3페이지를 추가 조회하여 신규 데이터 유입으로 인한 tail 확장을 자동 감지합니다.

### 3단계: 페이지 단위 실시간 SSE 발행

- 각 페이지 스캔 완료 즉시 `PLAYGROUND_UPDATE` SSE를 발행합니다.
- 페이지별 통계 (오늘/어제/신규색인/미색인 건수), 사이클 메타정보 (소요 시간, API 호출 횟수, 예상 잔여 시간)가 함께 전송됩니다.
- 완료 로그 형식: `[I2861] ✅ P20/953 [가~가] 완료 | 조회 1,000건 | 오늘 2건 · 어제 0건 · 신규 2건 · 중복 998건 | 소요 4.5초 · API 1회 · 잔여 ~71.0분`

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
| **스캔 주기 초과** | 이전 Oldest-First 스캔이 30분을 초과하면 다음 주기 자동 스킵 (Lock 기반 재진입 방지) |

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
- **페이지 스캔 히스토리**: 953p 카드 그리드 — 페이지별 상호명 대역(`가~나`), 마지막 스캔 시각, 오늘/어제/신규/중복 건수
- **사이클 진행 패널**: 현재 사이클 소요 시간 · API 호출 횟수 · 예상 잔여 시간 실시간 표시
- **오늘 감지 이력**: 변동 감지 타임라인
- ⚠️ 개발자 안내 없이 수동 조작 지양

### 📥 엑셀 내보내기
- 조회 중인 데이터를 `.xlsx` 파일로 추출

### ⚙️ 설정 페이지
- API 키 CRUD (추가/삭제/활성화 전환)
- 키별 오늘 호출 수 / 한도 실시간 조회
- 알림 설정 (카카오톡 등)

---

## 🧱 기술 스택

| 구분 | 기술 |
|---|---|
| **Backend** | Python 3.11+, FastAPI, uvicorn, APScheduler |
| **Frontend** | React 18, TypeScript, Vite, Radix UI (shadcn/ui), TanStack Query, Zustand |
| **Database** | SQLite (food_safety.db) — 로컬 내장, WAL 모드 |
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
│   ├── database.py                # SQLite 스키마 초기화 + 유틸리티 (dist_release 경로 분기 포함)
│   ├── excel_export.py            # 엑셀 내보내기 생성
│   ├── backups/                   # 자동 DB 백업 파일 저장소 (7일 보존)
│   ├── app/
│   │   ├── api/                   # REST API 엔드포인트
│   │   │   └── endpoints/         # approvals, playground, settings, stream
│   │   ├── clients/               # 식품안전나라 API 클라이언트 + 키 관리
│   │   ├── core/                  # 설정, 스케줄러, 로거, 이벤트
│   │   ├── database/              # DB 스키마 + 유지보수 (backup_db, vacuum_db)
│   │   ├── repositories/          # DB 접근 계층 (business, state, memo, raw_data)
│   │   ├── schemas/               # Pydantic 요청/응답 모델
│   │   └── services/              # 핵심 비즈니스 로직
│   │       ├── diff_crawler/      # DiffCrawlerEngine (I2861 Oldest-First Scan 제어)
│   │       │   └── engine.py      # 953p 동적 롤링 스캔 코어 엔진
│   │       ├── playground/        # Playground 모니터링 서비스 (scanner, scheduler, stats)
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
│   │   └── store/                 # 상태 관리 (Zustand) — useScanProgressStore 등
│   └── dist/                      # 프로덕션 빌드 (정적 파일, FastAPI가 동일 포트에서 서빙)
├── dist_release/                  # 배포 패키지 (exe + .env + DB)
├── build.bat                      # Windows 빌드 스크립트
└── README.md                      # ← 이 문서
```

---

## ⚙️ 스케줄링 체계

| 잡 | 주기 | 역할 |
|---|---|---|
| **Scraper Job** | **30분** | DiffCrawlerEngine 실행 → I2861 Oldest-First Scan (1시간 초과 전체 페이지 무제한 스캔, 평시 1페이지 롤링) |
| **Key Recovery** | 10분 | 소진된 API 키 회복 여부 체크 → 회복 시 즉시 크롤링 재개 |
| **Industry Backfill** | 6시간 + 신규 INSERT 시 즉시 | I2500 API로 세부업종/대표자/연락처/인허가일(PRMS_DT) 보완 |
| **DB Vacuum** | 일요일 03:00 | SQLite VACUUM 최적화 |
| **DB Backup** | 매일 04:00 | `backups/` 디렉토리에 핫 백업 (7일 보존, dist_release 경로 안전 보장) |

---

## 📊 데이터 수집 파이프라인

```
신규 변동 감지 (Oldest-First Scan에 의한 격차 감지)
  ↓
_run_i2861_oldest_first_scan: 1시간 초과 페이지 전체 + Tail Probe (+3p) 무제한 Fetch
  ↓
페이지 완료 즉시 → SQLite 상태 저장 (page_timestamps, page_labels) + SSE 발행
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
- 안정적인 모니터링을 위해 **10~13개의 API 키**를 등록하는 것을 권장합니다.
- 13개 키 기준: 일일 ~13,000회 호출 가능 (953페이지 전체 1회전 충분)

### 3. 초기 실행 및 첫 전체 스캔
- 최초 실행 시 `last_total_count` 기반으로 총 페이지 수(현재 953p)를 자동 계산합니다.
- 첫 번째 Oldest-First Scan 사이클에서 953개 페이지를 모두 스캔하며, 이때 상당한 API 호출이 발생합니다.
- 이후 사이클부터는 1시간 초과 페이지만 스캔하는 효율적인 롤링 모드로 전환됩니다.

### 4. 빌드 시 주의
- **빌드 전 반드시 ApprovalRadar.exe를 종료**해야 합니다.
- exe가 실행 중이면 `The process cannot access the file` 에러로 새 exe가 교체되지 않습니다.
- 앱 실행 중 DB를 외부에서 수정하면, 종료 시 메모리상의 데이터가 DB를 덮어씁니다.

### 5. 네트워크 환경
- 식품안전나라 API 서버의 일시적 장애 시 자동 재시도 (지수 백오프)
- WAF(웹 방화벽) 차단 방지를 위해 요청 간 **랜덤 딜레이(Jitter, 0.5~1.5초)** 적용

### 6. 데이터 안전 및 백업
- 모든 데이터는 로컬 SQLite DB (`food_safety.db`)에만 저장됩니다.
- 외부 서버로 데이터가 전송되는 일은 없습니다.
- 매일 새벽 4시 `backups/` 폴더에 자동 백업 (7일치 보존), 일요일 새벽 3시 DB VACUUM 최적화
- 백업 경로는 `DB_FILE` 기준으로 계산되어 dist_release(배포 환경)에서도 안전하게 동작합니다.

### 7. 플레이그라운드 주의
- 플레이그라운드 페이지의 수동 트리거 기능은 서버 상태에 직접적인 영향을 줍니다.
- **개발자의 안내 없이는 플레이그라운드 기능 사용을 지양**해 주세요.

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
uvicorn main:app --host 0.0.0.0 --port 8000
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
python cli.py --mirror               # 전체 API 미러링
```

자세한 설치 방법은 [INSTALL_MANUAL.md](INSTALL_MANUAL.md), 빌드 방법은 [BUILD_MANUAL.md](BUILD_MANUAL.md)를 참고하세요.

---

## 📊 성능 지표 (I2861 기준, 30분 실행 주기)

| 지표 | 수치 |
|---|---|
| 전체 Live DB 규모 (View B) | ~952,999건 (953페이지, 페이지당 1,000건) |
| 스캔 주기 | 30분 |
| 신규 변동 감지 지연 | 최대 1시간 이내 100% 동기화 (1시간 초과 페이지 전체 무제한 스캔) |
| Tail Probe | 마지막 알려진 페이지 +3p 자동 탐색 (tail 확장 자동 감지) |
| 주기당 API 호출 (평시) | 1회 (1시간 미초과, 롤링 1페이지) |
| 주기당 API 호출 (초기/복구) | 최대 953+ 회 (전체 페이지 무제한 스캔) |
| DB 백업 | 매일 04:00 자동 핫 백업 (7일 보존, dist/dev 경로 안전) |
| WAF 차단 및 API 소진율 | 평시 0%에 수렴 (Jitter + 키 로테이션) |

---

<p align="center">
  <sub>Built with ❤️ for public data transparency</sub>
</p>
