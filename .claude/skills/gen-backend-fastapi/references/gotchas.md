# FastAPI 백엔드 생성 함정 모음

`doc-pipeline`(구버전)에서 실제로 걸렸던 버그들을 프롬프트 규칙으로 승격시킨
목록이다. 새로 걸리는 버그도 여기 계속 추가한다.

## DB 접근

- ORM(SQLAlchemy 등)은 쓰지 않는다. SQL을 직접 실행한다.
- 커넥션은 `from db import get_conn`으로 얻는다(오케스트레이터가 이미
  `db.py`를 스캐폴드로 넣어뒀다). 직접 sqlite3/psycopg에 connect하지 않는다.
- **sqlite**: 요청마다 새로 연다(요청마다 열고 함수 끝에서 닫는다) - FastAPI는
  요청을 여러 스레드에서 처리하므로 전역 커넥션 하나를 공유하면 스레드 오류가
  난다. id는 INSERT 후 `cursor.lastrowid`. SQL 플레이스홀더는 `?`.
- **postgres**: 커넥션은 `with` 블록으로 닫는다. id는 INSERT 끝에 `RETURNING id`
  붙여서 `cursor.fetchone()`으로 받는다. SQL 플레이스홀더는 `?`가 아니라 `%s`
  (psycopg) - 리터럴 `%`가 필요하면 `%%`로 이스케이프.
- 테이블은 오케스트레이터가 `schema.sql`을 실행해 이미 만들어뒀다 - `CREATE
  TABLE`을 직접 짓지 않는다.
- id 및 외래키(memberId, bookId 등 이름이 엔티티명+Id 형태)는 정수(int)로
  다루고 JSON에도 숫자로 내보낸다. 명세/ERD가 "string"으로 적어놨어도 예외가
  아니다 - 자동증가 정수 PK를 참조하므로 int가 맞다.
- boolean 필드는 DB에 0/1 정수로 저장되므로 응답 시 `bool()`로 변환해서
  `true`/`false`로 나가게 한다.

## 검증 (pydantic)

- request/response 스키마는 pydantic 모델로 명세와 정확히 일치시킨다.
- 존재하지 않는 id로 요청 시 404.
- 새 리소스를 만드는 POST는 `status_code=status.HTTP_201_CREATED`.
- 처리되지 않은 예외가 500으로 그대로 노출되면 안 된다 - 각 핸들러를 try/except로
  감싸거나(전역 예외 핸들러는 오케스트레이터가 이미 등록했으니 자동으로 400이
  된다), 명백한 서버 버그일 때만 500이 나가게 둔다.
- FastAPI의 기본 검증 실패 응답은 422지만 이 계약은 400이다 - 오케스트레이터가
  등록한 `RequestValidationError` 핸들러가 이미 처리하므로 별도 작업 불필요.
- **pydantic은 관대해서 숫자 0을 날짜로 강제변환(coercion)해버릴 수 있다**(0을
  1970-01-01로 해석). `strict=True`는 정상 ISO 날짜 문자열까지 거부해버리니
  쓰지 않는다. 대신 date 타입 필드에 `@field_validator(필드명, mode='before')`로
  사전 검증기를 달아, 원본 값이 `str`이 아니면(int/float/bool) `ValueError`를
  던져 거부하고 `str`이면 통과시킨다.
- **required의 의미는 '필드가 존재해야 한다'는 뜻이지 '값이 비어있으면 안 된다'는
  뜻이 아니다.** title이 빈 문자열("")이어도 필드 자체는 있으므로 유효한
  요청이다. pydantic의 `Optional`이 아닌 `str` 타입은 이 구분을 기본으로 올바르게
  처리하니 별도의 빈 문자열 거부 검증을 넣지 않는다.

## 조각(라우터 모듈) 규칙

- 파일은 정확히 하나: `routers/{module}.py`. `router = APIRouter()`를 모듈
  최상위에 정의하고 엔드포인트를 `@router.get(...)` 형태로 단다. 경로는 명세의
  전체 경로 그대로 쓴다(prefix로 줄이지 않는다).
- **다음은 절대 만들지 않는다**: FastAPI() 앱 생성, CORS 설정, 예외 핸들러 등록,
  main.py, db.py, requirements.txt, schema.sql - 전부 오케스트레이터가
  `scripts/gen_fastapi_scaffold.py`로 결정적으로 넣는다.
- 다른 조각의 모듈을 import하지 않는다. 다른 도메인 데이터가 필요하면 SQL로
  직접 조회한다.

## 역할 기반 접근 제어

명세의 rules에 역할 제한이 있으면 헤더로 식별한다(spring과 같은 컨벤션 -
프론트가 이 값을 그대로 보낸다): `X-User-Type` 헤더값이 정확히 `"ADMIN"`인지
비교(대소문자 무시). 본인 확인이 필요하면 `X-User-Id` 헤더와 대상 buyerId/
sellerId를 비교하되, 헤더가 없으면 본인 확인을 건너뛴다.
