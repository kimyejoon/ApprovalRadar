# ApprovalRadar 크롤러 리팩토링 구현 계획서

> **작성일:** 2026-05-17
> **대상 파일:** `app/services/diff_crawler.py`, `app/services/pivot_manager.py`
> **목적:** 원본 설계 문서 대비 현재 구현 현황을 검토하고, 발견된 치명적 버그 1건을 제거한다.

---

## 1. 시스템 궁극적 목표

> **"사용자가 식품안전나라의 인허가 변경 정보 변동분을 실시간에 가깝게 모니터링하는 것"**

이를 위해 다음 3가지 파이프라인이 유기적으로 작동해야 한다.

1. **크롤링 레이어:** 식품안전나라 API를 최소 비용으로 스크래핑하여 변동분(Delta)을 캐치
2. **백엔드 레이어:** FastAPI가 데이터를 처리하고 프론트엔드에 SSE 알림을 Push
3. **프론트엔드 레이어:** 대시보드가 SSE를 수신하여 변동분을 즉시 사용자에게 표시

---

## 2. 도메인 제약 사항 (변경 불가능한 전제)

이 제약들이 현재 피벗(Pivot) + 이진탐색(Binary Search) 아키텍처를 선택하게 된 **근본적인 이유**이다.

| # | 제약 사항 | 내용 | 영향 |
|---|-----------|------|------|
| 1 | **API 일일 호출 제한** | Key 1개당 1일 최대 **1,000회** | 전체 스캔(Full-Scan) 방식은 1~2회 실행만으로도 즉시 Key 고갈 |
| 2 | **페이지당 최대 조회 건수** | 1회 Request당 최대 **1,000건** | 대량 데이터를 가져올 때 페이징 처리 필수 |
| 3 | **total_count 신뢰 불가** | API 응답의 `total_count` 값이 부정확하거나 API별 신뢰도가 다름 | Tail(꼬리) 탐색을 위해 직접 이진 탐색을 수행해야 함 |
| 4 | **상호명(가나다순) 정렬 삽입** | 신규 인허가 데이터가 꼬리가 아닌 **전체 DB 중간에 이름 순으로 Insert** | "최근 N건 조회"나 날짜 필터 불가. 중간 삽입을 피벗으로 유추해야 함 |
| 5 | **수정/삭제는 극히 드묾** | 인허가 변경 로그 테이블 특성상 Update/Delete가 거의 발생하지 않음 | 삭제/업데이트 역방향 동기화보다 신규 Insert 탐지에 집중 가능 |
| 6 | **WAF 및 DDoS 차단 위험** | 너무 빠른 요청은 패턴 감지로 Key 차단 또는 IP 차단 | 각 API 호출 사이에 반드시 Jitter(무작위 지연) 적용 필수 |
| 7 | **최소 탐색 주기** | 원본 설계 기준 **30분** | 지나치게 짧은 주기 설정은 WAF 차단 및 Key 고갈 유발 |

---

## 3. 원본 설계 의도 vs 현재 구현 현황 대조

원본 설계 문서와 현재 `diff_crawler.py` 코드를 기능별로 1:1 대조 분석한 결과이다.

| # | 원본 설계 요구사항 | 구현 현황 | 비고 |
|---|--------------------|-----------|------|
| 1 | 이진 탐색으로 Tail 탐색 | ✅ 완전 구현 | `find_true_tail`: 지수 점프 + 이진 탐색 + Gap 허용 선형 스캔 |
| 2 | total_count 신뢰 서비스/불신 서비스 분기 | ✅ 완전 구현 | `RELIABLE_TOTAL_COUNT_SERVICES = {"I2861"}` — I2861은 전략A, I2859는 전략B |
| 3 | 다중 변동 감지 (Divide & Conquer) | ✅ 완전 구현 | 피벗별 독립 Shift 오프셋 계산 후 구간 분할 다운로드 |
| 4 | Insert + Delete 은폐 감지 | ✅ 완전 구현 | `pivot_manager.sample_check`: Tail 변동 없어도 20% 피벗 샘플 비교 |
| 5 | 피벗 Boundary 캐싱 (첫/마지막 상호명) | ✅ 완전 구현 | `LCNS_NO` (첫 행) + `LAST_LCNS_NO` (마지막 행) 양방향 저장 |
| 6 | Jitter (무작위 지연) | ✅ 완전 구현 | `asyncio.sleep(random.uniform(GAP_MIN, GAP_MAX))` 모든 API 호출 후 적용 |
| 7 | 비동기 HTTP 클라이언트 | ✅ 완전 구현 | `httpx.AsyncClient` 사용, Keep-Alive 세션 재사용 |
| 8 | API Key 회전 로직 | ✅ 완전 구현 | `rotate_key`, `switch_key`, Key별 Lock, 소진 상태 자동 초기화 |
| 9 | API Key 잔여량 경고 (Token Bucket) | ✅ 완전 구현 | 900/950/990회 사용 시 SSE `WARN` 이벤트 브로드캐스트 |
| 10 | SSE 알림 (신규 변동 발생 시) | ✅ 완전 구현 | 변동 감지 후 `broadcaster.broadcast_sync("UPDATE")` |
| 11 | 크롤러 연속 실패 시 ALERT SSE | ✅ 완전 구현 | 5회 연속 실패 시 `ALERT` 이벤트 브로드캐스트 |
| 12 | 세부 업종(Industry Type) Backfill | ✅ 완전 구현 | 신규 Insert 감지 즉시 별도 스레드로 `fill_industry_for_licenses` 실행 |
| 13 | Backfill 재시도 워커 (누락 방지) | ✅ 완전 구현 | 서버 시작 시 `fill_missing_industry_types` 백그라운드 스레드 자동 실행 |
| 14 | SSE 좀비 커넥션 정리 | ✅ 완전 구현 | `shutdown_event` 체크 및 `Request.is_disconnected()` 활용 |
| 15 | 모든 API 호출 로깅 및 호출 횟수 카운트 | ✅ 완전 구현 | `key_usage_repository`에 매 호출마다 DB upsert 및 로깅 |
| **16** | **장기 다운타임 시 Shift 탐색** | **⚠️ 치명적 버그** | `_compute_shift_offsets`에서 `_fetch_single` 단건 루프 사용 → 선형 폭발 |

---

## 4. 발견된 유일한 치명적 버그 (Critical Bug)

### 💣 `_compute_shift_offsets` — 선형 탐색 폭발 (API Key 자폭)

평소 짧은 주기로 돌 때(`diff_count <= 2`)는 완벽히 동작한다. 그러나 서버가 주말 동안 꺼져 있거나, 장애로 수일간 정지되어 **수백~수천 건의 변동분(`diff_count`)**이 누적될 경우 시스템이 즉각 자폭한다.

#### 현재 코드 (문제 구간)

```python
# diff_crawler.py - _compute_shift_offsets
for offset in range(current_shift, diff_count + 1):
    row = await self._fetch_single(p_idx + offset)  # 단건 API 1회씩 호출
    if row and row.get("LCNS_NO") == old_data["LCNS_NO"] ...:
        found_offset = offset
        break
```

#### 폭발 시나리오 (수학적 증명)

| 상황 | diff_count | 피벗 수 | API 호출 수 | 결과 |
|------|-----------|--------|------------|------|
| 정상 운영 | 2건 | 50개 | 50 × 2 = 100회 | 정상 |
| 주말 3일 다운 | 500건 | 50개 | 50 × 500 = **25,000회** | Key 즉각 고갈 |
| 1주일 다운 | 2,000건 | 50개 | 50 × 2,000 = **100,000회** | 영구 크래시 |

---

## 5. 리팩토링 구현 계획 (3단계)

### Phase 1: `_compute_shift_offsets` — 메모리 기반 청크 스캔으로 교체 (핵심)

**목표:** `_fetch_single` 단건 루프를 완전 제거하고, `_fetch_page` (1,000건 일괄) + 메모리 리스트 탐색으로 교체한다.

**개선 후 호출 수 비교:**

| 상황 | diff_count | 피벗 수 | 개선 후 API 호출 수 | 결과 |
|------|-----------|--------|-------------------|------|
| 주말 3일 다운 | 500건 | 50개 | 피벗 50회 + 다운로드 약 500회 = **550회** | 안전 |
| 1주일 다운 | 2,000건 | 50개 | 피벗 100회 + 다운로드 약 2,000회 → Phase 3 발동 | Circuit Breaker |

**구현 방향:**

1. 각 피벗(`p_idx`)의 탐색 범위를 `[p_idx + current_shift, p_idx + diff_count]`로 한정
2. 해당 범위를 `PAGE_SIZE`(1,000) 단위로 페이징하여 `_fetch_page` 비동기 호출 (최대 2회)
3. 가져온 메모리 리스트 내부에서 `LCNS_NO + CHNG_DT`가 일치하는 레코드의 정확한 위치 인덱스를 탐색
4. 탐색된 위치를 기반으로 `found_offset` 계산 후 `current_shift` 업데이트
5. **안전망(Fallback):** 삭제 등으로 피벗 레코드를 찾지 못할 경우, `current_shift`를 그대로 유지하고 다음 피벗으로 진행

---

### Phase 2: `_update_pivots` — 피벗 생성 효율화 (API 호출 50% 절감)

**목표:** 새 꼬리(Tail) 구간에 피벗을 추가할 때, 양방향 Boundary를 2번의 단건 호출 대신 1번의 페이지 호출로 처리한다.

**현재 방식 (비효율):**
```python
row = await self._fetch_single(next_pivot)                       # API 1회
last_row = await self._fetch_single(next_pivot + PAGE_SIZE - 1) # API 1회 추가
```

**개선 방식:**
```python
rows = await self._fetch_page(next_pivot, next_pivot + PAGE_SIZE - 1)  # API 1회만
row, last_row = rows[0], rows[-1]  # 메모리에서 첫/마지막 추출
```

---

### Phase 3: Circuit Breaker — 초과 트래픽 방어막 도입

**목표:** 물리적으로 일일 API 한도 내에서 처리 불가능한 수준의 `diff_count`가 감지되면, 시스템을 보호하고 관리자에게 즉각 알림을 보낸다.

**동작 방식:**

1. `find_true_tail` 수행 직후 `diff_count > CIRCUIT_BREAKER_THRESHOLD` (예: 10,000)이면 즉시 Abort
2. 프론트엔드로 `ALERT` SSE 이벤트 발송:
   - "크롤러 긴급 중단: 변동분 N,000건 감지 — API 한도 초과 위험. 수동 조치 필요."
3. 해당 주기를 Skip하고 다음 주기에 재시도

---

## 6. 작업 순서 및 검증 계획

### 작업 순서

```
Phase 1 구현 → 단위 테스트 → Phase 2 구현 → Phase 3 구현 → 통합 테스트
```

### 검증 방법

- `diff_count = 500` 시뮬레이션으로 총 API 호출 수가 600회 이내임을 로그로 확인
- 피벗 탐색 결과와 기존 로직의 결과가 동일함을 확인 (회귀 테스트)
- 서킷 브레이커 임계값 초과 시 `ALERT` SSE가 정상 발송되는지 확인

---

## 7. 기대 효과 요약

| 항목 | 리팩토링 전 | 리팩토링 후 |
|------|-----------|-----------|
| 주말 3일 다운타임 후 구동 | Key 즉각 고갈, 크래시 | 약 550회 호출로 완전 동기화 |
| 피벗 1개당 최대 API 호출 수 | diff_count 회 (최악 500+회) | 1~2회 (페이지 호출) |
| 초과 트래픽 방어 | 없음 (그대로 자폭) | Circuit Breaker로 즉시 Abort + ALERT |
| 피벗 생성(Boundary) 호출 수 | 2회/피벗 (fetch_single x2) | 1회/피벗 (fetch_page x1) |

> **결론:** 현재 아키텍처(이진 탐색 + 피벗 Shift)는 해당 도메인 제약 하에서 유일하게 가능한 최선의 설계이다. 이번 리팩토링은 이 완벽한 설계에서 발생한 단 하나의 구현 버그(선형 탐색 폭발)를 외과적으로 제거하는 작업이다.
