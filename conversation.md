# ApprovalRadar 프로젝트 대화 기록

## 2026-05-11
* 유저의 요청으로 `/ApprovalRadar-BE/.env` 파일에 API 키 입력 템플릿을 작성함.
* 타겟 API(I2861: 음식점업소 인허가 변경 정보)의 전체 컬럼 파악을 위해 1개의 레코드만 수집하는 `test_scraper.py`를 작성 및 실행함.
* 수집된 데이터를 바탕으로 동적 테이블을 생성하고 데이터를 저장하는 `test_food_safety.db` 생성 완료.
* 프론트엔드 개발자의 페이지네이션 요청에 대응하여 `main.py`의 `/api/businesses` 엔드포인트에 `page` 및 `limit` 쿼리 파라미터를 추가하고 DB 조회를 개선함.
* `/api/businesses` 엔드포인트에 프론트엔드 요구사항을 반영하여 `size`, `search`, `start_date`, `end_date`, `regions`(다중 지역 검색 지원), `sort_by`, `sort_order` 필터링 및 정렬 기능을 대폭 추가함.
* 프론트엔드 연동 명세 변경: `/api/businesses` 엔드포인트를 `/api/v1/approvals`로 변경 및 스웨거 응답 Pydantic 모델 적용.
* 프론트엔드에서 날짜 필터링 시 데이터가 반환되지 않는 문제 해결: `main.py`에서 조회 날짜 포맷(`YYYY-MM-DD`)을 DB 포맷(`YYYYMMDD`)과 일치시키도록 수정하고, `scraper.py`의 정규식을 개선하여 DB에 잘못 저장된 날짜 포맷을 업데이트함.
* 깃허브에 `.venv` 폴더를 업로드하지 않고 `requirements.txt`를 생성하여 패키지 의존성을 관리하도록 안내 및 파일 생성 완료.
* 프론트엔드 캐시 병합 최적화를 위해 변동된 최신 데이터만 반환하는 `/api/v1/approvals/delta` 엔드포인트 및 `DeltaResponse` 모델 추가. 백엔드 데이터베이스의 `updated_at` 시간대(KST ISO) 포맷 불일치 문제 해결.
* DB에 `created_at` 및 `updated_at` 저장 시, 그리고 API `server_time` 반환 시 서버 환경에 의존하지 않고 명시적으로 KST(UTC+9) 타임존을 사용하도록 로직 수정 완료.
