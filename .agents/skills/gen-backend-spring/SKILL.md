---
name: gen-backend-spring
description: Java Spring Boot 백엔드를 도메인 조각별 서브에이전트로 생성한다. build-app 오케스트레이터가 BACKEND_TARGET=spring일 때 호출. 입력은 generated/docs/api_spec.json + data_model.json + schema.sql.
---

# Spring Boot 백엔드 생성 (도메인 조각화)

포트 **8080** 고정. 출력 폴더 `generated/backend/`.

## 왜 조각화하는가

큰 도메인(엔티티 10+개·엔드포인트 20+개)을 서브에이전트 하나에 통으로 맡기면
한 응답/한 파일 세션에 다 못 담아 코드가 잘리거나 파일이 뒤섞인다.
`scripts/endpoint_groups.py`로 API를 도메인별로 나누고, 조각마다
`backend-slice-writer` 서브에이전트를 하나씩 **병렬로** 디스패치한다(한
메시지에 여러 Agent 호출을 동시에 담는다). 조각끼리는 코드가 아니라 DB로
엮인다 - 서로 import하지 않고, 필요하면 SQL로 직접 조회한다.

## 절차

### 1. 결정적 스캐폴드 파일을 오케스트레이터가 직접 쓴다

**서브에이전트에게 시키지 않는다** - 조각마다 다시 만들면 충돌하고, 언어
보일러플레이트라 LLM 판단이 필요 없다. `{dialect}`는 `sqlite` 또는
`postgres`(build-app이 사용자에게 물어본 값).

`generated/backend/build.gradle`:
```gradle
plugins {
    id 'org.springframework.boot' version '3.3.4'
    id 'io.spring.dependency-management' version '1.1.6'
    id 'java'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    sourceCompatibility = '17'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    runtimeOnly 'ORG_XERIAL_OR_POSTGRESQL_LINE'
}

tasks.named('test') {
    useJUnitPlatform()
}
```
`ORG_XERIAL_OR_POSTGRESQL_LINE`을 dialect별로 치환:
- sqlite: `'org.xerial:sqlite-jdbc:3.46.1.3'` (서드파티라 버전 명시 필수)
- postgres: `'org.postgresql:postgresql'` (Spring Boot 의존성 관리가 버전을 잡아줌 - 버전 생략)

`generated/backend/settings.gradle`:
```gradle
rootProject.name = 'todo'
```

`generated/backend/src/main/resources/application.properties`:
- sqlite:
  ```properties
  server.port=8080
  spring.datasource.url=jdbc:sqlite:app.db
  spring.datasource.driver-class-name=org.sqlite.JDBC
  spring.sql.init.mode=always
  app.cors.allowed-origins=*
  ```
- postgres:
  ```properties
  server.port=8080
  spring.datasource.url=jdbc:postgresql://localhost:55432/doc
  spring.datasource.username=doc
  spring.datasource.password=doc
  spring.datasource.driver-class-name=org.postgresql.Driver
  spring.sql.init.mode=always
  app.cors.allowed-origins=*
  ```
  (운영 배포 시 환경변수 `APP_CORS_ALLOWED_ORIGINS`로 콤마구분 allowlist를 넣으면
  Spring Boot의 relaxed binding이 이 프로퍼티를 덮어쓴다 - `spring.datasource.url`도
  같은 방식으로 `SPRING_DATASOURCE_URL` 환경변수로 덮어쓸 수 있다.)

`generated/backend/src/main/resources/schema.sql`: `generated/docs/schema.sql`을
그대로 복사(내용 동일, 위치만 Spring Boot 관례 경로로).

`generated/backend/src/main/java/com/example/todo/TodoApplication.java`:
```java
package com.example.todo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TodoApplication {
    public static void main(String[] args) {
        SpringApplication.run(TodoApplication.class, args);
    }
}
```
(컴포넌트 스캔이 서브패키지의 `@RestController`/`@Configuration`을 자동으로
찾으므로, 조각이 늘어나도 이 파일은 안 바뀐다 - import 목록을 유지할 필요
없음.)

`generated/backend/src/main/java/com/example/todo/config/CorsConfig.java`:
```java
package com.example.todo.config;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class CorsConfig implements WebMvcConfigurer {
    @Value("${app.cors.allowed-origins:*}")
    private String allowedOrigins;

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/**")
            .allowedOrigins(allowedOrigins.split(","))
            .allowedMethods("*")
            .allowedHeaders("*");
    }
}
```

`generated/backend/src/main/java/com/example/todo/config/JacksonConfig.java`:
```java
package com.example.todo.config;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.databind.cfg.CoercionAction;
import com.fasterxml.jackson.databind.cfg.CoercionInputShape;
import com.fasterxml.jackson.databind.type.LogicalType;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class JacksonConfig {
    @Bean
    public ObjectMapper objectMapper() {
        ObjectMapper mapper = new ObjectMapper();
        mapper.registerModule(new JavaTimeModule());
        mapper.disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);
        mapper.coercionConfigFor(LogicalType.Boolean)
            .setCoercion(CoercionInputShape.String, CoercionAction.Fail);
        mapper.coercionConfigFor(LogicalType.Textual)
            .setCoercion(CoercionInputShape.Boolean, CoercionAction.Fail);
        return mapper;
    }
}
```

`generated/backend/src/main/java/com/example/todo/config/GlobalExceptionHandler.java`:
```java
package com.example.todo.config;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.server.ResponseStatusException;

import java.util.Map;

@RestControllerAdvice
public class GlobalExceptionHandler {
    private static final Logger log = LoggerFactory.getLogger(GlobalExceptionHandler.class);

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<Map<String, String>> handleValidation(MethodArgumentNotValidException ex) {
        return ResponseEntity.status(HttpStatus.BAD_REQUEST)
            .body(Map.of("detail", ex.getMessage()));
    }

    @ExceptionHandler(ResponseStatusException.class)
    public ResponseEntity<Map<String, String>> handleStatus(ResponseStatusException ex) {
        return ResponseEntity.status(ex.getStatusCode())
            .body(Map.of("detail", String.valueOf(ex.getReason())));
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<Map<String, String>> handleOther(Exception ex) {
        log.error("unhandled error", ex);
        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
            .body(Map.of("detail", "internal server error"));
    }
}
```

(에러 응답 키는 `detail`로 통일 - 프론트 생성 스킬이 이 키를 최우선으로 읽는다.
도메인 규칙 위반은 `ResponseStatusException`으로 명시적 4xx를 던져야 한다 -
`handleOther`는 더 이상 400 안전망이 아니라 500 + 일반화 메시지다.)

gradle wrapper 복사:
```bash
mkdir -p generated/backend/gradle/wrapper
cp assets/gradle-wrapper/gradlew generated/backend/gradlew
cp assets/gradle-wrapper/gradlew.bat generated/backend/gradlew.bat
cp assets/gradle-wrapper/gradle/wrapper/gradle-wrapper.jar generated/backend/gradle/wrapper/
cp assets/gradle-wrapper/gradle/wrapper/gradle-wrapper.properties generated/backend/gradle/wrapper/
chmod +x generated/backend/gradlew
```

### 2. 도메인 조각으로 나눈다

```bash
python scripts/endpoint_groups.py generated/docs/api_spec.json \
  -o generated/backend/_slices
```
출력(manifest, stdout)에 조각마다 `group`/`module`/`class_prefix`/`file`
(슬라이스 JSON 경로)이 나온다.

### 3. 조각마다 `backend-slice-writer` 서브에이전트를 병렬 디스패치한다

**한 메시지에 조각 개수만큼 Agent 호출을 동시에 넣는다.** 각 호출의 프롬프트에
반드시 포함:

```
[이 조각이 맡은 엔드포인트]
<generated/backend/_slices/{module}.json 내용 또는 경로>

[출력 계약 - 정확히 지켜라]
파일은 정확히 하나: generated/backend/src/main/java/com/example/todo/{module}/{ClassPrefix}Controller.java
패키지 선언: package com.example.todo.{module};
클래스에 @RestController만 붙인다.
요청/응답 DTO가 필요하면 같은 파일 안에 package-private 정적 클래스나 record로.
DB 접근은 생성자로 주입받은 org.springframework.jdbc.core.JdbcTemplate 하나로만.
[다음은 절대 만들지 마라]: @SpringBootApplication 클래스, CORS 설정, 예외 처리기,
ObjectMapper 설정, build.gradle, settings.gradle, application.properties, schema.sql
- 전부 이미 만들어져 있다.

[반드시 먼저 Read할 것]
.Codex/skills/gen-backend-spring/references/gotchas.md
.Codex/skills/references/objections-protocol.md

[참고 자료]
ERD: generated/docs/data_model.json
DB 스키마(실행하지 않음, 테이블명 확인용): generated/docs/schema.sql

[이의제기]
계약(api_spec)에 정보가 없거나 모호해서 임의로 판단한 게 있으면
generated/objections/{module}.json에 기록한다 (위 objections-protocol.md의
형식/기준 그대로). 없으면 파일을 안 만들어도 된다.
```

### 4. 결과 확인

각 서브에이전트가 자기 파일을 다 썼다고 보고하면, `generated/backend/src/main/java/com/example/todo/`
아래에 조각 수만큼 서브패키지가 생겼는지 확인한다. 이후 컴파일·기동 검증은
`verify-backend` 스킬로 넘어간다.

## 재시도

`verify-backend`가 실패를 보고하면, **실패 원인이 속한 조각만** 다시
디스패치한다(전체 재생성 아님). 실패 로그를 해당 조각의 디스패치 프롬프트에
`[이전 시도 실패 로그]`로 추가해서 같은 실수를 반복하지 않게 한다. 같은
조각이 3회 실패하면 사람에게 보고하고 멈춘다.
