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
* 데이터베이스의 인허가 고유 ID가 API의 `LCNS_NO`에서 추출된 `license_no`와 동일한지(그리고 DB의 Primary Key로 쓰이는지) 확인 요청에 대해 일치함을 확인함.
* 프론트엔드에서 상세 정보 및 상태 변동 내역(Timeline) 조회를 위해 단일 인허가 건을 가져오는 `GET /api/v1/approvals/{approval_id}` API 엔드포인트 추가 (경로 파라미터 `approval_id`는 데이터베이스의 `license_no`와 매핑됨).
* Swagger UI를 통해 `GET /api/v1/approvals/{approval_id}` API 테스트 결과를 확인, 올바른 JSON 포맷과 200 상태 코드로 정상 작동함을 검증 완료.
* 프론트엔드 대시보드 시각화를 위해 상태 분포 및 일별 트렌드 데이터를 반환하는 `GET /api/v1/approvals/indicators` API를 추가함. 기존 필터 파라미터 연동 적용 완료.
* 사용자가 필터링된 데이터(대표자 변경분)를 엑셀 파일로 바로 다운로드할 수 있도록 `openpyxl`을 이용한 `excel_export.py`를 구현하고, 서버 저장 없이 클라이언트에 바로 스트리밍하는 `GET /api/v1/approvals/export` API 엔드포인트 추가 완료. 
  - 파일명 형식: `대표자변경분_YYYYMMDD(시작일)-YYYYMMDD(종료일).xlsx` (파라미터 부재 시 당일 날짜 기준 적용)
  - 10건 다운로드 제한을 해제하고 전체 건수 다운로드 허용
  - 엑셀 다운로드 시 데이터 내용 길이에 맞춰 열 너비가 자동으로 조정되는 로직 구현
* 전역 파이썬(global python)으로 서버를 실행하여 발생한 FastAPI 모듈 인식 오류 해결. 프로젝트의 가상환경(.venv)을 활성화하여 실행하도록 안내함.
* `git pull origin dev` 명령어 실행 중 발생한 "divergent branches" 오류 해결을 위해 `git config pull.rebase false` (Merge 방식) 설정 후 성공적으로 병합을 완료함.
* 새 터미널 창에서 가상환경 미활성화 및 경로 문제로 발생한 `uvicorn: command not found` 에러 해결을 위해 올바른 경로 이동(`ApprovalRadar-BE`) 및 `.venv` 활성화 방법을 안내함.
* `/api/v1/approvals` 관련 API 엔드포인트(`get_approvals`, `get_approval_indicators`, `export_approvals_excel`)의 날짜 파라미터 Swagger 문서 설명을 `(YYYY-MM-DD)`에서 실제 동작과 일치하도록 `(YYYYMMDD)`로 수정함.
* DB `licensing_history` JSON 데이터 구조 변경(type 내용만 남기기) 시 발생할 수 있는 백엔드 API 스키마(`BusinessModel`) 및 프론트엔드 연동 부분의 구조적 변경 가능성을 분석하여 안내함.
* 기존 JSON 형태의 컬럼을 제거하고 필요한 내용만 추출하여 단일 문자열(String)로 저장하는 방안의 영향도(데이터베이스, 스크래퍼, 레포지토리, 스키마, 프론트엔드 변경점)를 안내함.
* 프론트엔드 소스코드 분석 결과, 현재 `licensing_history`나 `representative_history` 컬럼은 데이터만 받아올 뿐 UI(상세 모달 등)에 전혀 노출 및 사용되지 않고 있음을 확인하여, 단일 문자열로 변경해도 프론트엔드 화면이 깨지는 부작용이 없음을 안내함.
* 기존 JSON 형태의 변경 이력(licensing_history, representative_history) 컬럼을 삭제하고, 변경 타입(update_type) 및 이전 상태값(prev_business_status, prev_representative_name, prev_business_name)을 담는 플랫(flat)한 문자열 컬럼들로 데이터베이스 구조를 최적화(정규화)함.
* 기존 JSON 데이터를 파싱하여 새 컬럼 구조에 맞게 데이터를 마이그레이션하는 스크립트 작성 및 실행 완료.
* 백엔드 API 스키마() 및 데이터 수집기()에서 JSON 업데이트 로직을 제거하고 새 컬럼 기반으로 즉시 업데이트되도록 로직 간소화 적용 완료.
* 기존 JSON 형태의 변경 이력(licensing_history, representative_history) 컬럼을 삭제하고, 변경 타입(update_type) 및 이전 상태값(prev_business_status, prev_representative_name, prev_business_name)을 담는 플랫(flat)한 문자열 컬럼들로 데이터베이스 구조를 최적화(정규화)함.
* 기존 JSON 데이터를 파싱하여 새 컬럼 구조에 맞게 데이터를 마이그레이션하는 스크립트 작성 및 실행 완료.
* 백엔드 API 스키마(BusinessModel) 및 데이터 수집기(scraper.py)에서 JSON 업데이트 로직을 제거하고 새 컬럼 기반으로 즉시 업데이트되도록 로직 간소화 적용 완료.
* 프론트엔드 대시보드의 매끄러운 30일 시각화를 위해 `GET /api/v1/approvals/indicators` API를 개선함. 파라미터가 비어있을 경우 백엔드 서버에서 자동으로 오늘 기준 최근 30일(시작일, 종료일)을 주입하며, 데이터가 없는 날짜도 차트에서 누락되지 않고 0건(`count: 0`)으로 명시적 반환되도록 Zero-Padding 로직을 추가함.
* 엑셀 다운로드 API(`/api/v1/approvals/export`) 호출 시 브라우저(프론트엔드)에서 `Content-Disposition` 헤더를 읽어 파일명을 제대로 처리할 수 있도록 `main.py`의 CORS 설정에 `expose_headers=["Content-Disposition"]`를 추가함.
* `GET /api/v1/approvals/indicators` API의 `total_approvals` 지표가 조회 기간 전체 합계가 아닌, 조회 종료일(또는 당일) 하루의 건수만 반환하도록 수정함.
* `GET /api/v1/approvals/indicators` API에서 30일 누적치(`total_approvals`)와 당일 변동 건수(`today_approvals`)를 모두 반환하도록 스키마 및 레포지토리 로직 분리 및 추가
* 포스트맨(Postman) 컬렉션에 없는 `/api/v1/approvals/export` API를 테스트하기 위해, 수동으로 새 GET Request를 추가하거나 cURL 명령어를 임포트하여 다운로드(Send and Download)하는 방법을 안내함.
* 엑셀 다운로드 API(`/api/v1/approvals/export`) 호출 시 필터링은 정상 동작(last_event_date 기준)하고 있었으나, 다운로드된 엑셀 파일 내의 '인허가시각'이 DB의 최초 인허가일(`license_date`)과 매핑되어 있어 날짜가 맞지 않는 것처럼 보이는 오류를 수정함.
* 사용자의 요청에 따라 엑셀의 '인허가시각' 항목이 DB의 `last_event_date`(최종변경일자)와 매핑되도록 연결값을 수정하여, 파라미터 필터 조건과 엑셀 결과값이 일치하도록 조치함.
* 대시보드와 동일한 데이터가 추출되도록 `/export` API 엔드포인트와 내부 엑셀 생성 로직(`generate_excel_export`)에 `search` (검색 키워드) 및 `regions` (지역) 파라미터 연동을 추가함.
