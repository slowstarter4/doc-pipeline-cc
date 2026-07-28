---
name: verify-backend
description: 생성된 백엔드를 실제로 기동시켜 스모크·계약테스트·영속성을 검증한다. build-app 오케스트레이터가 gen-backend-*로 코드를 다 쓴 뒤 호출. "백엔드 검증", "실제로 떠보나 확인" 같은 요청에도 단독 사용 가능.
---

# 백엔드 실행 검증

`scripts/verify_backend.py`가 엔진이다(파이썬, 스택 무관 순수 HTTP 검증) - 이
스킬은 그걸 언제·어떻게 부르고, 실패 시 어떻게 재시도로 연결할지를 다룬다.

## 사전 조건

- `generated/backend/`에 코드가 이미 써져 있어야 한다(gen-backend-* 스킬이 먼저).
- postgres를 쓴다면 `cd db && docker compose up -d`가 이미 되어 있어야 한다 -
  **이 스킬도 도커를 자동 기동하지 않는다.** DB가 안 떠 있으면 커넥션 에러로
  실패하니, 그 실패 로그를 보고 도커부터 확인한다(코드 버그로 오판하지 않는다).
- `pip install requests`(스크립트 의존성)가 되어 있어야 한다.

## 실행

```bash
python scripts/verify_backend.py --target spring --db postgres \
  --api-spec generated/docs/api_spec.json
```

`--target`은 build-app이 선택한 백엔드 스택(fastapi/spring/express/typescript),
`--db`는 DB_TARGET(sqlite/postgres). 결과는 stdout에 JSON(`{"passed": bool,
"logs": str}`)으로 나오고, 실패면 종료코드 1이다.

## 검증 순서 (스크립트 내부, 참고용)

1. 빌드/설치(스택별: pip install / npm install / npm run build / gradlew는 빌드
   단계 없이 bootRun이 한 번에 함)
2. 서버 기동, `--api-spec`의 GET(경로 파라미터 없는 것) 하나로 응답 오는지 폴링
3. **스모크**: 경로 파라미터 없는 GET 전부가 200인지, 첫 POST가 201/200 또는
   도메인 규칙으로 거부(4xx)되는지 확인. 5xx나 요청 자체 실패만 문제로 친다.
4. **계약 테스트**: `generated/tests/`에 pytest 파일이 있으면 지금 뜬 서버에
   돌린다(BASE_URL 환경변수로 가리킴). 없으면 건너뛴다.
5. **영속성**: 항목 하나 만들고 서버를 껐다 켜서 남아있는지 확인. 더미 데이터가
   업무 규칙(enum·자릿수·외래키)에 막혀 생성 자체가 안 되면 이 단계는 건너뛰고
   note만 남긴다(실패로 안 침).

## 실패 시 - build-app으로 되돌리는 법

`report["passed"]`가 false면:
1. `report["logs"]`를 읽고 어느 도메인 조각(orders, payments 등)의 문제인지
   추정한다(로그에 있는 경로·엔드포인트로 판단).
2. 해당 gen-backend-*/SKILL.md의 방식대로, **그 조각만** 실패 로그를
   `[이전 시도 실패 로그]`로 넣어 재디스패치한다(전체 재생성 아님).
3. 재시도 후 다시 이 스킬을 돌린다. **같은 조각이 3회 실패하면 사람에게 로그를
   보여주고 멈춘다** - doc-pipeline의 `MAX_BACKEND_RETRIES=3`과 같은 상한.
4. 원인이 로그에서 명확히 다른 조각 소관이 아니라 공용 스캐폴드(schema.sql,
   application.properties 등) 문제로 보이면, 사람에게 알리고 gen-backend-*
   스킬의 결정적 스캐폴드 부분을 고친다 - 서브에이전트 재디스패치로 안 고쳐진다
   (그 파일들은 서브에이전트가 안 건드리므로).

## fastapi 외 스택은 프롬프트 수정 0회를 기대하지 않는다

새로 추가하는 스택(express/typescript)은 처음엔 실패가 날 수 있다 - 실패
로그를 보고 해당 `gen-backend-<stack>/references/gotchas.md`에 규칙을
승격시키는 방식으로 doc-pipeline 때와 같이 다룬다(spring도 그렇게 안정화됐다).
