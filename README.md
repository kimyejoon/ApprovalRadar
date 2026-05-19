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

**인허가RADAR**는 식품안전나라 공공 데이터베이스(I2861 음식점업소 인허가변경정보)의 변동분을 **실시간에 가깝게 포착**하여 웹 대시보드로 조회할 수 있는 로컬 데스크톱 프로그램입니다.

담당 공무원이 공공DB에 새로운 데이터를 올리면, **약 30분 내에** 모두 포착 및 탐지되어 웹페이지에서 변동분을 확인할 수 있습니다.

### 핵심 가치

| 💡 | 설명 |
|---|---|
| **준실시간 감지** | 5분 간격 Tail Ping + 15분 주기 Rolling Scan으로 신규/변경 건을 신속 포착 |
| **제로 데이터 유실** | Fingerprint 기반 전체 대조 + 이진탐색으로 누락 없는 변동 추적 |
| **완전 로컬** | 모든 데이터가 사용자 PC에만 저장, 외부 서버 전송 없음 |
| **무인 운영** | API 키 자동 교체, 장애 자가 복구, 자정 한도 리셋 — 한 번 켜두면 알아서 동작 |

---

## 🏗️ 아키텍처

```
┌────────────────────────────────────────────────────────────────────┐
│                         사용자 PC (localhost:8001)                   │
│                                                                     │
│  ┌──────────────┐     SSE (실시간 알림)     ┌──────────────────┐     │
│  │  React (FE)  │ ◄──────────────────────► │  FastAPI (BE)     │    │
│  │  Vite + TS   │     REST API             │  Python 3.11+     │    │
│  │  Dashboard   │ ◄──────────────────────► │  APScheduler      │    │
│  └──────────────┘                           │  httpx AsyncClient│    │
│                                             └──────┬───────────┘    │
│                                                    │                │
│  ┌────────────────────────┐    ┌──────────────────────────────┐    │
│  │  SQLite (food_safety.db)│ ◄──│  DiffCrawlerEngine           │    │
│  │  · businesses           │    │  · TailPing (5분)             │    │
│  │  · crawler_state        │    │  · RollingScanner (15분)      │    │
│  │  · api_keys             │    │  · PivotManager               │    │
│  │  · raw_data             │    │  · ChangeDetector             │    │
│  └────────────────────────┘    └──────────┬───────────────────┘    │
│                                           │                        │
│                                           ▼                        │
│                               식품안전나라 공공 API                    │
│                               (openapi.foodsafetykorea.go.kr)       │
└────────────────────────────────────────────────────────────────────┘
```

---

## 🔬 핵심 알고리즘 — "어떻게 100만 건의 DB를 30분 안에 모니터링하나?"

식품안전나라 공공DB는 **약 95만 건**의 데이터가 존재하는 대규모 데이터베이스입니다. API는 1회 호출당 최대 1,000건만 반환하므로, 전체를 한 번 순회하려면 **약 950회의 API 호출**이 필요합니다. 일일 API 한도(키당 1,000회)와 WAF 차단을 고려하면, 단순한 전수 조사 방식은 불가능합니다.

인허가RADAR는 이 문제를 다음 **5단계 복합 알고리즘**으로 해결합니다:

### 1단계: Tail Ping (5분 주기) — 꼬리 감시

```
API 호출 비용: 서비스당 2~4회/주기
```

- 마지막으로 알려진 데이터 위치(`known_tail`) 바로 뒤를 찔러서 신규 삽입 여부를 즉시 판단
- **변동 감지 시**: 즉시 Scraper 트리거 → 5분 이내 신규 건 수집
- **변동 없음 시**: Multi-Point Sentinel로 중간 삽입도 검사 (랜덤 3개 피벗 fingerprint 비교)

### 2단계: Rolling Scan (15분 주기) — 순차 전면 스캔

```
API 호출 비용: 주기당 150페이지 (I2861 기준)
약 1.5시간에 전체 1회전 완료
```

- **Oldest-First 전략**: 가장 오래 전에 스캔한 페이지부터 우선 순회
- 각 페이지(1,000건)의 **MD5 Fingerprint**를 계산하여 이전 값과 비교
- 불일치 시 → DB에 없는 레코드를 batch SELECT로 즉시 식별 → 수집

### 3단계: Fingerprint 비교 — 변동 감지의 핵심

```python
fingerprint = MD5([(LCNS_NO₁, CHNG_DT₁), (LCNS_NO₂, CHNG_DT₂), ..., (LCNS_NO₁₀₀₀, CHNG_DT₁₀₀₀)])
```

- 1,000건의 `(인허가번호, 변경일자)` 복합키 순서 목록을 해시
- 동일한 1,000건이 동일 순서 → 반드시 같은 fingerprint
- **API 1회 호출**로 1,000건의 변동 여부를 한 번에 판정

### 4단계: 이진탐색 + 지수점프 — Tail 탐색

```
API 비용: O(log N) — 95만 건 기준 약 10~15회
```

- **지수점프(Exponential Jump)**: 1,000 → 2,000 → 4,000 → ... 데이터 없는 상한선을 빠르게 탐색
- **이진탐색(Binary Search)**: 정확한 마지막 데이터 페이지 경계를 O(log N)으로 확정
- **Gap 허용**: 연속 빈 페이지 3개 미만이면 Gap으로 간주하고 계속 탐색 (Gappy 인덱스 대응)

### 5단계: Shift 분석 + Pivot 검증

- **피벗(Pivot)**: 5,000건 간격으로 분포된 참조점. 각 피벗에 저장된 복합키로 데이터 이동을 추적
- **Shift 진단**: 불일치 피벗에서 저장된 레코드가 몇 칸 밀렸는지 청크 스캔으로 계산
- **2-Phase 재확인**: fingerprint 불일치 시 3초 후 재조회 → API 일시 노이즈(false positive) 제거
- **조기 중단**: 연속 5개 피벗 미발견 시 API 전체 재정렬로 판단 → 즉시 재부트스트랩

---

## 🛡️ 자가 복구 메커니즘

| 장애 유형 | 자동 대응 |
|---|---|
| **API 키 한도 초과** | 다음 활성 키로 즉시 교체 (Key Rotation). 전체 소진 시 10분마다 회복 체크 |
| **WAF 차단** | 키 전환 + 지수 백오프 재시도. Jitter(0.5~1.5초 랜덤 딜레이)로 인간적 패턴 유지 |
| **API 재정렬 감지** | known_tail 역방향 검증 실패 시 피벗 초기화 → 백그라운드 재부트스트랩 |
| **Circuit Breaker** | diff_count가 임계값(10,000건) 초과 시 해당 주기 중단 → ALERT SSE 발송 |
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
- 업소별 상세 모달: 연락처, 이전 대표자, 이전 영업상태, 변경 이력
- 메모장 기능: 진행 상황/연락 기록 저장

### 🔑 API 키 관리
- 런타임 중 키 추가/삭제 즉시 반영
- 키별 일일 사용량/상태(활성/소진) 실시간 모니터링
- 잔여량 경고 (900/950/990건 도달 시 SSE)

### 📋 시스템 로그
- 크롤러 동작 실시간 로그 조회
- 스캔 진행률, 커버리지, 최대연식 등 상세 지표

### 📥 엑셀 내보내기
- 조회 중인 데이터를 `.xlsx` 파일로 추출

---

## 🧱 기술 스택

| 구분 | 기술 |
|---|---|
| **Backend** | Python 3.11+, FastAPI, uvicorn, APScheduler |
| **Frontend** | React 18, TypeScript, Vite, shadcn/ui |
| **Database** | SQLite (food_safety.db) — 로컬 내장 |
| **HTTP Client** | httpx (AsyncClient, Keep-Alive, 키별 직렬화 Lock) |
| **실시간 통신** | Server-Sent Events (SSE) |
| **빌드/배포** | PyInstaller (단일 실행 파일), batch/shell 스크립트 |
| **디자인 시스템** | Supabase 영감 다크 모드 (emerald green accent) |

---

## 📁 프로젝트 구조

```
ApprovalRadar/
├── ApprovalRadar-BE/              # 백엔드 (Python)
│   ├── main.py                    # FastAPI 앱 진입점
│   ├── scraper.py                 # 메인 스크래퍼 (DB 저장 + SSE 발행)
│   ├── database.py                # SQLite 스키마 초기화 + 유틸리티
│   ├── app/
│   │   ├── api/                   # REST API 엔드포인트
│   │   ├── clients/               # 식품안전나라 API 클라이언트 + 키 관리
│   │   ├── core/                  # 설정, 스케줄러, 로거, 이벤트
│   │   ├── repositories/          # DB 접근 계층
│   │   ├── schemas/               # Pydantic 요청/응답 모델
│   │   ├── services/              # 핵심 비즈니스 로직
│   │   │   ├── diff_crawler.py    # DiffCrawlerEngine (Tail 탐색, Bootstrap, 델타 감지)
│   │   │   ├── rolling_scanner.py # Rolling Full Scan (Oldest-First / Hybrid)
│   │   │   ├── tail_ping_job.py   # Tail Ping + Multi-Point Sentinel
│   │   │   ├── pivot_manager.py   # 피벗 Fingerprint 관리 + Shift 진단
│   │   │   ├── change_detector.py # 변동 유형 감지 (대표자/상태/명칭)
│   │   │   └── industry_filler.py # I2500 세부업종 Backfill
│   │   └── utils/
│   └── tests/
├── ApprovalRadar-FE/              # 프론트엔드 (React + TypeScript)
│   ├── src/
│   │   ├── pages/                 # DashboardPage, SettingsPage, LogPage, PlaygroundPage
│   │   ├── components/            # UI 컴포넌트 (features, layout, ui)
│   │   ├── hooks/                 # React 커스텀 훅
│   │   └── store/                 # 상태 관리
│   └── dist/                      # 프로덕션 빌드 (정적 파일, FastAPI가 서빙)
├── build.bat / build.sh           # Windows/macOS 빌드 스크립트
├── 사용자매뉴얼.md                  # 사용자 가이드
└── README.md                      # ← 이 문서
```

---

## ⚙️ 스케줄링 체계

| 잡 | 주기 | 역할 |
|---|---|---|
| **Scraper Job** | 15분 | DiffCrawlerEngine 실행 → Tail 탐색 + Rolling Scan + 델타 수집 |
| **Tail Ping** | 5분 | 독립적 Tail 변동 감지 → 변동 시 즉시 Scraper 트리거 |
| **Key Recovery** | 10분 | 소진된 API 키 회복 여부 체크 → 회복 시 즉시 크롤링 재개 |
| **Industry Backfill** | 6시간 | I2500 API로 세부업종/대표자/인허가일자 보완 |
| **Daily Bootstrap** | 매일 09:00 | 야간 API 재정렬 반영 → 피벗 재생성 |
| **DB Vacuum** | 일요일 03:00 | SQLite VACUUM 최적화 |
| **DB Backup** | 매일 04:00 | 자동 백업 |

---

## ⚠️ 프로그램 사용 시 주의할 점

### 1. 프로그램은 항상 켜두세요
프로그램 창을 닫으면 서버와 크롤러가 모두 종료됩니다. **최소화하여 백그라운드에 유지**해 주세요.

### 2. API 키 관리
- 공공데이터 API 키는 **키당 하루 1,000회 한도**입니다.
- 안정적인 모니터링을 위해 **5~12개의 API 키**를 등록하는 것을 권장합니다.
- 12개 키 기준: 일일 12,000회 예산으로 약 1.5시간에 전체 DB 1회전 가능

### 3. 초기 실행 시 시간 소요
- 최초 실행 시 **Bootstrap** 과정에서 전체 데이터 구조를 파악합니다.
- 약 95만 건 기준 10~20분 소요 → 이후부터는 변동분만 빠르게 감지

### 4. 네트워크 환경
- 식품안전나라 API 서버의 일시적 장애 시 자동 재시도 (지수 백오프)
- WAF(웹 방화벽) 차단 방지를 위해 요청 간 **랜덤 딜레이(Jitter)** 적용

### 5. 데이터 안전
- 모든 데이터는 로컬 SQLite DB (`food_safety.db`)에만 저장됩니다.
- 외부 서버로 데이터가 전송되는 일은 없습니다.
- 매일 새벽 4시 자동 백업, 일요일 새벽 3시 DB 최적화

---

## 🚀 빠른 시작

### Windows
```bash
# 배포된 실행 파일 사용
dist_release/ApprovalRadar.exe 더블클릭 → 브라우저에서 http://localhost:8001 접속
```

### 개발 환경
```bash
# 백엔드
cd ApprovalRadar-BE
python -m venv venv && venv\Scripts\activate
pip install -r requirements.txt
python main.py

# 프론트엔드 (별도 터미널)
cd ApprovalRadar-FE
npm install
npm run dev
```

자세한 설치 방법은 [INSTALL_MANUAL.md](INSTALL_MANUAL.md), 빌드 방법은 [BUILD_MANUAL.md](BUILD_MANUAL.md)를 참고하세요.

---

## 📊 성능 지표 (12키 기준)

| 지표 | 수치 |
|---|---|
| 전체 DB 규모 | ~950,000건 (약 950 페이지) |
| 전체 1회전 시간 | ~1.5시간 |
| Tail 변동 감지 지연 | ~5분 (Tail Ping 주기) |
| 주기당 API 호출 | ~154회 (Rolling 150 + Tail 4) |
| 일일 API 호출 | ~14,000회 (12키 × 1,000회 한도의 ~80% 활용) |
| DB 커버리지 | 150p/950p ≈ 15.8%/주기, 100%/1.5시간 |

---

<p align="center">
  <sub>Built with ❤️ for public data transparency</sub>
</p>
