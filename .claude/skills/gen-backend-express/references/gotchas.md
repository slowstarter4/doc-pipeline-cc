# Express(Node.js) 백엔드 생성 함정 모음

`doc-pipeline`(구버전)에서 실제로 걸렸던 버그들을 프롬프트 규칙으로 승격시킨
목록이다. 새로 걸리는 버그도 여기 계속 추가한다.

## DB 접근

- **sqlite**: Node 내장 `node:sqlite`만 쓴다(외부 DB 서버·ORM·better-sqlite3
  같은 서드파티 sqlite 패키지 금지 - npm 의존성·네이티브 빌드가 필요 없다).
  `const { DatabaseSync } = require('node:sqlite'); const db = new
  DatabaseSync('app.db');`로 연다(오케스트레이터가 db.js에 이미 넣어뒀다 - 조각은
  `require('../db')`로만 가져온다). **동기 API다** - async/await 없이
  `db.prepare(sql).run(...)/.get(...)/.all(...)`로 직접 호출한다. id는
  `lastInsertRowid`로 받는다(JS 카운터 금지). boolean은 1/0으로 바인딩,
  응답 시 `Boolean(value)`로 변환. **id·외래키를 `String()`으로 감싸지 않는다**
  - `lastInsertRowid`가 BigInt일까 걱정해서 문자열화하는 실수가 있었는데, 실제
    기본값은 이미 JS number다. number 그대로 응답.
- **postgres**: npm 패키지 `pg`(node-postgres)를 쓴다. **비동기 API다** - 모든
  라우트 핸들러를 `async`로 만들고 `pool.query(...)`에 `await`를 붙인다.
  플레이스홀더는 `?`가 아니라 `$1, $2, ...`, 결과는 `result.rows`(단건은
  `result.rows[0]`). id는 `RETURNING id`로 받는다.
- **테이블명·컬럼명에 큰따옴표(quoted identifier)를 쓰지 않는다.** schema.sql의
  `CREATE TABLE`이 unquoted라서 postgres가 테이블명·컬럼명을 전부 소문자로
  접어 저장한다(`Settlement` → `settlement`, `settlementId` → `settlementid`).
  SQL에서 `"Settlement"`, `"settlementId"`처럼 큰따옴표로 감싸면 대소문자를
  그대로 보존해서 찾으려 하므로 실제 소문자 테이블/컬럼과 매칭이 안 돼
  `relation "Settlement" does not exist` 에러가 난다(실측: commerce_qwen_plan
  express 1차 생성에서 settlements.js가 이 버그로 GET /settlements가 500대신
  postgres 에러 400을 반환 - `verify_backend.py`의 `_looks_like_bug` 휴리스틱은
  Java/Spring 예외 패턴만 잡아서 이 postgres 에러는 못 잡고 그냥 통과시켰다,
  수동 검토로 발견). 항상 unquoted로 쓰고 결과 row는 소문자 키로 읽는다
  (`row.settlementid` 등), 응답 JSON만 계약대로 camelCase로 매핑한다.
- 테이블은 오케스트레이터가 이미 만들어뒀다(schema.sql 실행) - `CREATE TABLE`을
  직접 짓지 않는다. ORM(Sequelize, Prisma 등)은 쓰지 않는다.
- id 및 외래키(memberId, bookId 등 이름이 엔티티명+Id 형태)는 **명세가 "string"
  으로 적어놨어도 무조건 number**로 다루고 응답에도 number로 내보낸다. 이 규칙을
  조건부("명세가 number라고 적었으면")로 두면 명세 생성 단계가 식별자를 전부
  "string"으로 뭉뚱그려 적어서 조건이 항상 거짓이 되는 사고가 있었다 - **무조건
  규칙**으로 취급한다.

## 검증 · 응답

- 존재하지 않는 id로 요청 시 404.
- 새 리소스를 만드는 POST는 201(`res.status(201).json(...)`).
- **도메인 규칙 위반(중복, 상태 불일치, 권한 없음 등)은 반드시 명시적으로
  `res.status(4xx).json({ message: "..." })`를 직접 응답한다.** try/catch로
  잡은 뒤 무조건 400을 씌우지 않는다 - DB 장애·타입 오류 같은 진짜 버그까지
  400으로 감추면 클라이언트 입력 문제로 오인되고 `verify_backend.py`도 도메인
  거부로 착각한다. 예상 못 한 예외는 그대로 던지거나 잡더라도 `console.error`로
  로그만 남기고 500 + `{"message": "internal server error"}`(내부 메시지·스택
  노출 금지)로 응답한다.
- request body 검증은 순수 JS 조건문으로 한다. **`if (!value)` 같은 falsy
  체크를 쓰지 않는다** - 빈 문자열("")이나 숫자 0처럼 존재하지만 falsy인 값까지
  잘못 거부한다. 반드시 `value === undefined || value === null`처럼 존재
  여부만 명시적으로 검사한다.
- CORS는 오케스트레이터가 이미 `app.use(cors())`로 열어뒀다 - 조각에서 다시
  설정하지 않는다.

## 조각(라우트 모듈) 규칙

- 파일은 정확히 하나: `routes/{module}.js`. `const router =
  express.Router();`를 선언하고 `module.exports = router;`로 export한다.
  경로는 명세의 전체 경로 그대로(prefix 생략 안 함).
- **다음은 절대 만들지 않는다**: `express()` 앱 생성, CORS 설정, `app.listen`,
  server.js, db.js, package.json, schema.sql - 전부 오케스트레이터가
  `scripts/gen_express_scaffold.py`로 결정적으로 넣는다.
- 다른 조각의 라우트 파일을 require하지 않는다. 다른 도메인 데이터가 필요하면
  DB에 직접 SQL로 조회한다.
- CommonJS(require/module.exports)로 작성한다.

## 역할 기반 접근 제어

명세의 rules에 역할 제한이 있으면 `X-User-Type` 헤더값이 정확히 `"ADMIN"`인지
비교(대소문자 무시, `req.headers['x-user-type']`). 본인 확인은 `X-User-Id`
헤더와 대상 buyerId/sellerId 비교, 헤더가 없으면 본인 확인을 건너뛴다(spring/
fastapi와 같은 컨벤션 - 프론트가 이 헤더들을 그대로 보낸다).
