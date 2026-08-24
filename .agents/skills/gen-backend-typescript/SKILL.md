---
name: gen-backend-typescript
description: Node.js + Express + TypeScript 백엔드를 도메인 조각별 서브에이전트로 생성한다. build-app 오케스트레이터가 BACKEND_TARGET=typescript일 때 호출. 입력은 generated/docs/api_spec.json + data_model.json + schema.sql.
---

# TypeScript 백엔드 생성 (도메인 조각화)

포트 **5002** 고정. 출력 폴더 `generated/backend/`. `gen-backend-express`와
구조가 100% 같다(같은 스캐폴드 스크립트를 `--ts` 플래그로 씀) - 차이는
파일 확장자(.ts)와 타입 캐스팅 함정뿐.

## 절차

### 1. 도메인 조각으로 나눈다

```bash
python scripts/endpoint_groups.py generated/docs/api_spec.json -o generated/backend/_slices
```

### 2. 결정적 스캐폴드 (TypeScript 버전)

```bash
python scripts/gen_express_scaffold.py --groups orders,payments,... --dialect postgres --ts -o generated/backend
```
`server.ts`, `db.ts`, `package.json`(devDependencies에 typescript·@types/*
포함), `tsconfig.json`(`strict: true`)을 쓴다. `generated/docs/schema.sql`도
`generated/backend/schema.sql`로 복사.

### 3. 조각마다 서브에이전트 병렬 디스패치

```
[이 조각이 맡은 엔드포인트]
generated/backend/_slices/{module}.json

[출력 계약 - 정확히 지켜라]
파일은 정확히 하나: generated/backend/routes/{module}.ts
express.Router()를 default export한다.
DB는 `import { db } from '../db'`(sqlite) 또는 `import { pool } from '../db'`(postgres)로만 접근.
[다음은 절대 만들지 마라]: express() 앱 생성, CORS 설정, app.listen, server.ts,
db.ts, package.json, tsconfig.json, schema.sql - 전부 이미 만들어져 있다.

[반드시 먼저 Read할 것 - 특히 sqlite 타입 캐스팅 규칙]
.Codex/skills/gen-backend-typescript/references/gotchas.md
.Codex/skills/gen-backend-express/references/gotchas.md (DB·검증·응답 공통 규칙)
.Codex/skills/references/objections-protocol.md

[참고 자료]
ERD: generated/docs/data_model.json
DB 스키마(실행하지 않음): generated/docs/schema.sql

[이의제기]
계약(api_spec)에 정보가 없거나 모호해서 임의로 판단한 게 있으면
generated/objections/{module}.json에 기록한다 (위 objections-protocol.md의
형식/기준 그대로). 없으면 파일을 안 만들어도 된다.
```

### 4. 빌드 + 검증

`verify-backend --target typescript`가 `npm install && npm run build`(tsc)
후 `node dist/server.js`로 기동한다. **컴파일 에러는 재시도 사유** - 로그에
TS 에러 메시지가 그대로 나오므로 원인 조각을 특정하기 쉽다.

## 재시도

`verify-backend` 실패 시 원인 조각만 재디스패치(3회 상한).
