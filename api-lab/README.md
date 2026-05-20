# api-lab — 식품안전나라 API 역공학 실험실

## 목적

식품안전나라 OpenAPI의 이상한 동작을 **로컬 SQLite + Python**으로 재현하여 패턴을 역추적한다.

## 관찰된 이상 현상

| 현상 | 관찰 내용 |
|------|----------|
| total_count 불신뢰 | 4, 491, 1378 — 같은 조건에도 다름 |
| 첫 레코드 불일치 | `1/1000` vs `1/100` vs `1/1` 마다 첫 레코드 다름 |
| 정렬 기준 불명 | LCNS_NO 오름/내림차순 어떤 페이지는 다름 |
| CHNG_DT 시간 제한 | 19:00 이전 오늘 날짜 응답에서 제거 |
| 페이지 Gap | 1001~2000 요청 시 1000건이 아닌 경우 존재 |

## 구조

```
api-lab/
├── README.md
├── requirements.txt
├── db/
│   ├── setup.py          ← 실제 food_safety.db에서 5,000건 샘플링하여 lab.db 생성
│   └── lab.db            ← (setup.py 실행 후 생성됨)
├── mock_api.py           ← 식품안전나라 API 동작을 모방하는 Python 함수 모음
└── experiments/
    ├── exp1_total_count.py   ← total_count 계산 방식 역추적
    ├── exp2_sort_order.py    ← 정렬 기준 역추적
    ├── exp3_shift.py         ← 삽입 시 쉬프팅 패턴
    └── exp4_chng_dt.py       ← CHNG_DT 필터 의미
```

## 빠른 시작

```bash
cd api-lab

# 1. 실험 DB 생성 (실제 DB 경로 필요)
python db/setup.py --source ../ApprovalRadar-BE/food_safety.db

# 2. 각 실험 실행
python experiments/exp1_total_count.py
python experiments/exp2_sort_order.py
python experiments/exp3_shift.py
python experiments/exp4_chng_dt.py
```

## 가설

### Exp-1: total_count의 정체
- **가설 B**: `total_count = rowid BETWEEN startIdx AND endIdx 범위 내 실제 레코드 수`
  - 삭제된 rowid가 있으면 Gap 발생 → total < 요청 범위
  - `start=1, end=1 → total=1`
  - `start=1, end=999999 → total=실제 전체 건수`

### Exp-2: 정렬 기준
- SQLite는 ORDER BY 없으면 B-Tree 내부 순서 (rowid 오름차순)로 반환
- 근데 `1/1000` 첫 레코드가 최신 CHNG_DT — ORDER BY chng_dt DESC 가능성

### Exp-3: 쉬프팅
- 신규 레코드가 앞쪽 rowid에 삽입되면 전체가 밀림
- 어느 rowid 위치에 삽입되느냐가 핵심

### Exp-4: CHNG_DT "이후" 의미
- `CHNG_DT=20260101` → "2026년 1월 1일 **이후**" (해당일 포함) 누적 필터
- → total_count = 해당일 이후 전체 레코드 수
