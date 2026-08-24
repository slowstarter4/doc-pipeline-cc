# Spring Boot 백엔드 생성 함정 모음

`doc-pipeline`(구버전)에서 실제로 걸렸던 버그들을 프롬프트 규칙으로 승격시킨
목록이다. 새로 걸리는 버그도 여기 계속 추가한다.

## DB 접근

- **옵셔널 쿼리 필터(예: sellerId나 status가 있으면 필터링, 없으면 전체 조회)는
  `WHERE (? IS NULL OR col = ?)` 패턴을 쓰지 않는다.** `?` 자리에서 파라미터
  타입을 못 정하거나 SQL 파싱에 걸려 "bad SQL grammar" 런타임 에러가 난다
  (sqlite-jdbc·postgres 드라이버 둘 다에서 재현됨). **대신 SQL 문자열을
  조건부로 조립한다**: `StringBuilder`로 `WHERE 1=1`에서 시작해서 필터 값이
  null이 아닐 때만 `AND col = ?`을 append하고, 그때만 그 값을
  `List<Object> args`에 넣는다. 필터가 없으면 그 조건절 자체가 SQL에 안
  생기므로 `IS NULL` 비교가 필요 없어진다. 마지막에
  `jdbcTemplate.query(sql.toString(), rowMapper, args.toArray())`로 바인딩한다.
- JPA/MyBatis/Hibernate는 쓰지 않는다. `org.springframework.jdbc.core.JdbcTemplate`
  하나로만 SQL을 직접 실행한다(무거운 ORM 대신 얇은 JDBC).
- 커넥션·DataSource 설정은 오케스트레이터가 이미 `application.properties`에
  넣어뒀다 - 너는 생성자로 주입받은 `JdbcTemplate`만 쓴다.
- 테이블은 오케스트레이터가 `schema.sql`을 이미 실행해 만들어뒀다 - `CREATE
  TABLE`을 직접 짓지 않는다.
- id는 DDL의 자동증가 PK(sqlite AUTOINCREMENT / postgres SERIAL)로 DB가
  매긴다. `GeneratedKeyHolder`로 생성된 id를 받는다. `AtomicLong` 같은 자바
  카운터로 채번하지 않는다(재기동하면 초기화되어 겹친다).
- **postgres에서는 PreparedStatement를 만들 때 생성키 컬럼을 반드시 명시해야
  한다** - `connection.prepareStatement(sql, new String[]{"id"})`처럼 id
  컬럼명을 넘긴다. `Statement.RETURN_GENERATED_KEYS`만 쓰면 postgres JDBC
  드라이버가 RETURNING *로 전체 행을 돌려줘 `keyHolder.getKey()`가 'single
  value가 아니다'로 예외가 난다(sqlite에선 안 나던 함정).
- id 및 외래키(memberId, bookId 등 이름이 엔티티명+Id 형태)는 Long 타입으로
  다루고 JSON에도 숫자로 내보낸다. ERD가 이 필드를 "string"으로 적어놨어도
  예외가 아니다 - 실제로는 자동증가 정수 PK를 참조하므로 Long이 맞다.
- date 컬럼은 TEXT라 ISO 'YYYY-MM-DD' 문자열로 저장한다. `LocalDate`는 저장 시
  `toString()`, 읽을 때 `LocalDate.parse(...)`로 되돌린다. boolean은 0/1
  정수로 저장하고 읽을 때 `(getInt(...) != 0)`으로 되돌린다(응답 JSON엔
  true/false로 나가야 함).

## 람다 캡처 (effectively final)

`jdbcTemplate.update(connection -> {...})`(PreparedStatementCreator 람다)로
생성키를 받을 때, 람다 안에서 쓰는 지역변수는 반드시 effectively final이어야
한다. `long sum = 0; sum += ...;`처럼 루프로 값을 누적한 변수를 그대로 람다
안에서 쓰면 "local variables referenced from a lambda expression must be
final or effectively final" 컴파일 에러가 난다. **람다 직전에 `final long
결과 = sum;`처럼 final 변수로 한 번 복사한 뒤 그 변수를 람다 안에서 쓴다.**
루프로 계산되는 모든 지역변수(합계, 플래그 등)에 똑같이 적용한다.

## 테이블명 (SQL 예약어)

`schema_ddl.py`가 `Order`/`User` 같은 SQL 예약어와 겹치는 엔티티명은 이미
물리 테이블명 뒤에 밑줄을 붙여 냈다(예: `Order_`). **schema.sql에 적힌 테이블명을
그대로 SQL 문자열에 쓴다** - 원래 엔티티명(`Order`)으로 되돌려 쓰지 않는다.
큰따옴표로 감싸서 대소문자를 맞추는 방식은 쓰지 않는다(케이스 구분 함정).

## 응답 직렬화 (Jackson)

- boolean 필드는 Jackson이 getter의 'is' 접두사를 자동으로 떼고 직렬화한다
  (`isCompleted` 필드의 getter `isCompleted()` → JSON에서는 `completed`로
  나감). API 명세의 필드명을 JSON에서 그대로 유지해야 하므로, **is로 시작하는
  boolean 필드에 한해서만** `@com.fasterxml.jackson.annotation.JsonProperty
  ("isCompleted")`처럼 필드 위에 붙인다(값은 반드시 API 명세의 필드명 그대로).
- **is로 시작하지 않는 필드에는 `@JsonProperty`를 붙이지 않는다.** camelCase로
  이름을 지으면(title, isbn, memberId 등) Jackson이 자동으로 맞는 JSON 키를
  쓴다. 요구사항정의서의 한글 라벨(예: "제목")을 `@JsonProperty` 값으로 절대
  넣지 않는다 - 클라이언트가 보낸 필드가 "인식할 수 없는 필드"로 거부되어 API가
  마비된다.
- ObjectMapper의 boolean/문자열 강제변환(coercion)은 오케스트레이터가 이미
  전역 설정(`JacksonConfig`)으로 막아뒀다 - 조각마다 다시 설정하지 않는다.

## 검증 (jakarta.validation)

- ERD의 required 필드가 빠졌거나 타입이 안 맞으면 400을 반환해야 한다. 요청
  DTO(레코드 또는 클래스) 필드에 `@NotNull`을 붙이고(필드 존재만 검사 - 빈
  문자열 ""은 유효한 값이므로 `@NotBlank`는 쓰지 않는다), 컨트롤러 메서드
  파라미터에 `@Valid`를 붙인다. `MethodArgumentNotValidException`은
  오케스트레이터가 이미 전역 처리기(`GlobalExceptionHandler`)로 400 응답을
  만들게 해뒀다 - 조각에서 직접 잡지 않는다.
- 404는 `throw new ResponseStatusException(HttpStatus.NOT_FOUND, "메시지")`로
  던지기만 하면 전역 처리기가 응답을 만든다. 업무 규칙 위반(400)도 마찬가지로
  `ResponseStatusException(HttpStatus.BAD_REQUEST, "메시지")`를 던진다.
- 새 리소스를 만드는 POST는 200이 아니라 201(Created)로 응답한다
  (`@ResponseStatus(HttpStatus.CREATED)` 또는
  `ResponseEntity.status(HttpStatus.CREATED)`).

## 역할 기반 접근 제어

명세의 rules에 "운영자만", "판매자는 본인 소유만" 같은 역할 제한이 있으면,
호출자 식별은 **반드시 다음 두 헤더로만** 한다(다른 이름을 쓰면 조각마다
값이 갈려 서로 안 맞는다 - 실제로 조각 3개가 `ADMIN`/`admin`/`OPERATOR`를
제각각 써서 한 조각만 막힌 사고가 있었다):
- 운영자 여부: `@RequestHeader(value = "X-User-Type", required = false) String
  userType`을 받아 **정확히 문자열 `"ADMIN"`과 `equalsIgnoreCase`로 비교**한다.
  프론트는 항상 `X-User-Type: ADMIN`을 보낸다(운영 백오피스 전제).
- 판매자/구매자 본인 확인: `@RequestHeader(value = "X-User-Id", required =
  false) String requesterId`를 받아 요청의 sellerId/buyerId와 비교하되,
  **이 헤더가 비어있으면 본인 확인 자체를 건너뛴다**(관리자가 X-User-Id 없이
  X-User-Type: ADMIN만 보내는 호출을 막지 않기 위함).

## 클래스/패키지

- 패키지는 `com.example.todo.<module>`(디스패치 프롬프트가 지정한 module명).
- 컨트롤러 클래스에 `@RestController`만 붙인다. `@CrossOrigin`은 붙이지 않는다
  (전역 CORS 설정이 이미 열려 있다).
- java.util.Map, List, Set 등 JDK 클래스가 필요하면 반드시 import로 가져와
  쓴다. **JDK 클래스와 같은 이름(Map, List 등)의 클래스를 직접 정의하지
  않는다** - 같은 파일 안에 이름이 겹치는 클래스를 새로 선언하면 그 이름을
  쓰는 모든 자리가 JDK 클래스 대신 그 선언을 가리키게 되어(shadowing) 컴파일이
  깨진다.

## 빌드 (오케스트레이터가 이미 처리, 조각은 신경 안 씀)

- `build.gradle`/`settings.gradle`/`application.properties`/gradle wrapper
  파일은 오케스트레이터가 결정적으로 만들거나 복사해둔다. 조각은 절대 이
  파일들을 만들거나 고치지 않는다.
- gradle wrapper(`gradlew`, `gradlew.bat`, `gradle/wrapper/*`)는 바이너리 파일
  (`gradle-wrapper.jar`)이 껴있어 서브에이전트가 만들 수 없다 - 오케스트레이터가
  `assets/gradle-wrapper/`에서 복사한다.
