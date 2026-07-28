---
name: gen-backend-express
description: Node.js + Express(JavaScript) 백엔드를 도메인 조각별 서브에이전트로 생성한다. build-app 오케스트레이터가 BACKEND_TARGET=express일 때 호출. 입력은 generated/docs/api_spec.json + data_model.json + schema.sql.
---

# Express 백엔드 생성 (도메인 조각화)

포트 **5001** 고정. 출력 폴더 `generated/backend/`. 구조는 `gen-backend-fastapi`와
같다(진입점 조립이 결정적이라 스크립트로 뺌, 조각은 서브에이전트 병렬 디스패치).

**참고: doc-pipeline(구버전)의 express는 조각화가 없었다(단일 호출).** 이
레포는 fastapi/spring과 같은 이유로 처음부터 조각화한다 - 아직 실전 검증
전이므로(spring만 commerce_qwen_plan으로 실측함), 실패가 나면 그 로그를
`references/gotchas.md`에 규칙으로 승격시켜 나간다.

## 절차

### 1. 도메인 조각으로 나눈다

```bash
python scripts/endpoint_groups.py generated/docs/api_spec.json -o generated/backend/_slices
```

### 2. 결정적 스캐폴드를 스크립트로 쓴다

```bash
python scripts/gen_express_scaffold.py --groups orders,payments,... --dialect postgres -o generated/backend
```
`generated/backend/server.js`, `db.js`, `package.json`을 쓴다.
`generated/docs/schema.sql`도 `generated/backend/schema.sql`로 복사해둔다.

### 3. 조각마다 서브에이전트 병렬 디스패치

```
[이 조각이 맡은 엔드포인트]
generated/backend/_slices/{module}.json

[출력 계약 - 정확히 지켜라]
파일은 정확히 하나: generated/backend/routes/{module}.js
`const router = express.Router();` 선언, `module.exports = router;`로 export.
DB는 `require('../db')`로만 접근(sqlite면 { db }, postgres면 { pool }).
[다음은 절대 만들지 마라]: express() 앱 생성, CORS 설정, app.listen, server.js,
db.js, package.json, schema.sql - 전부 이미 만들어져 있다.

[반드시 먼저 Read할 것]
.claude/skills/gen-backend-express/references/gotchas.md

[참고 자료]
ERD: generated/docs/data_model.json
DB 스키마(실행하지 않음, 테이블명 확인용): generated/docs/schema.sql
```

### 4. 설치 + 검증

`npm install`은 `verify-backend` 스킬이 빌드 단계에서 자동으로 돌린다(스크립트
내부 LaunchSpec). `--target express`로 호출한다.

## 재시도

`verify-backend` 실패 시 원인 조각만 재디스패치(3회 상한, spring과 동일 규칙).
