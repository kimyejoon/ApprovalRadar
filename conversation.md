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
* 엑셀 다운로드 시 직관적인 확인을 위해 기존 '인허가시각' 컬럼을 '최초인허가일'(`license_date`)과 '변동인허가일'(`last_event_date`) 두 개의 컬럼으로 분리하여 표기하도록 수정함.
* 데이터베이스 `businesses` 테이블에 `update_type`을 기반으로 추론된 데이터를 저장하는 `infer_update_type` 컬럼을 추가하고, 기존 데이터를 규칙에 맞게 업데이트함 (상태변경, 변경민원 등). 기타 다른 update_type 값들의 존재도 확인하여 보고함.
* `update_type`이 '변경민원'인 데이터 중 `prev_business_name`을 분석하여 '변경민원-성함:[성함]', '변경민원-주소:[주소]', '변경민원-상호명:[상호명]'으로 분류하여 `infer_update_type`에 저장하는 스크립트 작성 및 적용. 정규표현식을 사용하여 지역명 포함 상호명(예: 상계동 블루스)과 실제 주소를 정확히 구분하도록 알고리즘 설계.
* `update_type`이 NULL인 데이터 중 `last_event_date`와 `license_date`가 일치하는 1,312건에 대해 변경 이력이 없는 최초 등록 건으로 판단하여 `infer_update_type`을 '신규등록'으로 일괄 업데이트하는 로직 추가 및 실행 완료.
- 2026-05-13: 크롤러(scraper.py)가 향후 새로운 데이터를 수집할 때 자동으로 `infer_update_type`을 채워넣도록 로직 개선 반영 (신규등록, 초기수집, 명칭/대표자/상태 변경 자동 추론).
- 2026-05-13: scraper.py 에서 YYYY-MM-DD 형태의 날짜 데이터가 YYYY-MM- 으로 뒷부분이 잘리는 이슈(글자수 8자 자르기 로직 오류) 원인 분석 및 하이픈 제거 후 YYYYMMDD 포맷으로 변환되도록 수정.
- 2026-05-13: DB 스키마에 `last_event_time`, `license_time` 컬럼 추가 및 scraper.py에서 날짜 데이터의 상세 시각(시분초)을 추출해 개별 컬럼으로 저장하도록 수정.
- 2026-05-13: 가 비어있던 나머지 1,264건의 과거 데이터에 대해 추론 규칙(초기수집, 상속, 기타 등)을 일괄 적용하여 NULL 값을 모두 제거함.
- 2026-05-13: `infer_update_type`가 비어있던 나머지 1,264건의 과거 데이터에 대해 추론 규칙(초기수집, 상속, 기타 등)을 일괄 적용하여 NULL 값을 모두 제거함.
- 2026-05-13: 백엔드 프로젝트(ApprovalRadar-BE)의 전반적인 API 통신 방식과 데이터베이스(SQLite) 테이블 구조, 아키텍처 특이사항 등을 상세히 분석하여 유저에게 리포트함.
- 2026-05-13: DB의 `infer_update_type` 컬럼 값의 실제 분포를 조회하고, 정규화(카테고리/상세내용 분리) 및 지위승계 용어 통일에 대한 피드백 제공.
- 2026-05-13: `infer_update_type` 컬럼의 정규화(분류와 상세값을 `infer_update_type`과 `infer_update_detail`로 분리)를 수행하고 기존 3,421건의 데이터를 100% 보존하며 안전하게 마이그레이션 및 적용 완료함.
- 2026-05-13: `.gitignore`를 업데이트하여 로컬 SQLite DB 파일(`*.db`, `*.db-wal` 등)이 Git에 추적되지 않도록 설정하고 캐시를 제거함.
- 2026-05-13: `/approvals` API의 `sort_by` 파라미터가 `phone`, `date`로 들어올 경우 각각 `phone_number`, `last_event_date`로 자동 매핑되도록 정렬 로직을 수정함.
- 2026-05-13: Swagger(OpenAPI) 문서에서 `sort_by`, `sort_order` 파라미터가 드롭다운 메뉴로 제공되도록 Python `Enum`을 도입하여 명세를 고도화하고, `representative_name`, `business_status`, `license_no` 등 누락된 정렬 필드를 추가 허용하여 422 에러를 해결함.
- 2026-05-13: 식품안전나라 API 일일 호출 한도 초과로 인한 크롤러 자동 중단 로그의 원인 및 해결 방안(자정 리셋 또는 추가 키 발급)을 안내함.
- 2026-05-13: 프론트엔드 API 응답(`BusinessModel`)에서 `business_status` 필드를 제거하고 정규화된 `infer_update_type`, `infer_update_detail`을 기본으로 전달하도록 수정함.
- 2026-05-13: `/approvals/indicators` API 응답에 전체 누적 건수(`total_approvals`), 최근 1개월 건수(`monthly_approvals`), 오늘 건수(`today_approvals`)를 각각 분리하여 제공하도록 지표 산출 로직을 개선함.
- 2026-05-13: DB에서 `last_event_date` 기준 특정 일자(20260507, 20260508)의 데이터 수집 행(row) 개수를 조회하여 확인함.
- 2026-05-13: `/approvals` API 응답 스키마(`BusinessModel`)에 `industry_type`(업태명) 필드를 추가하여 클라이언트에 제공되도록 수정함.
- 2026-05-13: `/approvals` API의 `sort_by` 쿼리 파라미터 및 DB 정렬 기준에 `industry_type`을 추가하여 업태명 기준의 문자열 이름 정렬이 정상 작동하도록 허용함.
- 2026-05-13: `/approvals` 및 `/approvals/export` API에 `infer_update_type` 쿼리 파라미터를 추가하여 프론트엔드에서 데이터 유형(신규등록, 상태변경 등)별 필터링이 가능하도록 지원함. Swagger 문서에 허용되는 값 명세 완료.
- 2026-05-13: `GET /api/v1/approvals/detail` 라우트 신설 (`/{approval_id}` 삭제) 및 `license_date`, `business_name` 파라미터 기반 배열 조회 적용.
- 2026-05-13: `GET /api/v1/approvals` 및 `/export` API에 `industry_type`, `infer_update_type` 다중 필터(리스트 또는 콤마 구분자) 적용 및 Swagger 명세 강화.
- 2026-05-13: Swagger UI에서 배열 타입(`List[str]`) 파라미터가 비정상적으로 노출되거나 사라지는 이슈를 해결하기 위해 `regions` 파라미터와 동일한 의존성 파싱 구조(`Depends`)로 변경하여 단일 텍스트(콤마 구분) 입력 방식으로 수정함.
- 2026-05-13: `/api/v1/approvals` 응답 스키마(`BusinessModel`)에 `business_status`를 다시 추가하여 요청 시 정상적으로 반환되도록 수정함.
- 2026-05-13: `industry_type`(업종) 파라미터의 Swagger 문서 명세에 실제 데이터베이스에 존재하는 모든 업종(일반음식점, 휴게음식점, 제과점영업, 유흥주점영업, 단란주점, 위탁급식영업, 식품제조가공업)을 허용값으로 명시하도록 수정함.
- 2026-05-13: `businesses` 테이블에 사용자의 확인 여부를 나타내는 `is_read` (기본값 0) 컬럼과 읽은 시각을 기록하는 `read_at` 컬럼을 추가하고, 이를 상태로 업데이트할 수 있는 `PUT /api/v1/readInfo` API를 생성함. 또한 Swagger 문서에 명세를 추가하고 응답 스키마에도 반영함.
- 2026-05-13: 프론트엔드의 요청에 따라 `PUT /api/v1/readInfo` API를 `PUT /api/v1/readInfo/{license_no}` 형태의 Path 파라미터 방식으로 변경하여 RESTful 설계 규칙에 부합하도록 개선함.
- 2026-05-13: 프론트엔드가 실시간으로 크롤러의 업데이트를 감지할 수 있도록 `GET /api/v1/stream/updates` SSE(Server-Sent Events) 엔드포인트를 구축함. 크롤러(`APScheduler`)와 FastAPI 간의 메모리 공유를 활용하여 `asyncio.Queue`와 `call_soon_threadsafe`를 통해 동기-비동기 스레드 간 충돌 없이 신규 알림("신규 업데이트가 발생했다")을 즉각 전송하도록 브로드캐스터(Broadcaster) 아키텍처를 도입함. 또한 업데이트가 없을 시 5초마다 연결 정상 시그널("현재 정상 연결중임 (보낼 업데이트 없음)")을 보내는 Heartbeat 기능과 `cli.py --test-stream-update` 명령을 통한 가상 트리거 테스트 로직을 추가함.
- 2026-05-13: 프론트엔드 개발자가 SSE 연동 시 참고할 수 있도록 `GET /api/v1/stream/updates` API의 Swagger 문서에 시그널의 종류(Heartbeat 핑 및 신규 업데이트 알림), 발생 조건, 데이터 포맷, 프론트엔드 측 처리 방법 등을 상세하게 명세함.
- 2026-05-13: 프론트엔드의 요청에 따라 SSE 응답 데이터를 단순 문자열(Raw Text)에서 파싱하기 쉬운 JSON 포맷(`{"type": "...", "message": "..."}`)으로 변경함.
- 2026-05-20: 프로젝트 리팩토링을 위한 전반적인 분석 수행 및 LOC 300 이상 파일 목록/역할 도출
- 2026-05-20: diff_crawler.py 모듈 리팩토링 및 클래스 분리 작업을 완료함. 기존 917줄의 단일 파일을 TailExplorer, PivotAnalyzer, DiffBootstrapper 3개의 헬퍼 클래스로 분리 및 Facade 패턴을 적용하여 가독성과 유지보수성을 대폭 향상시킴.
- 2026-05-20: rolling_scanner.py 모듈 리팩토링 및 클래스 분리 작업을 완료함. 기존 815줄의 단일 파일을 rolling_scan_utils.py, rolling_scan_ops.py 로 분리하여 순수 유틸리티 함수와 DB 스캔 오퍼레이션을 캡슐화함으로써 가독성과 유지보수성을 대폭 향상시키고 LOC를 262줄로 줄임.
