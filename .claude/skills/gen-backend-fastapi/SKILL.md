---
name: gen-backend-fastapi
description: Python FastAPI 백엔드를 도메인 조각별 서브에이전트로 생성한다. build-app 오케스트레이터가 BACKEND_TARGET=fastapi일 때 호출. 입력은 generated/docs/api_spec.json + data_model.json + schema.sql.
---

# FastAPI 백엔드 생성 (도메인 조각화)

포트 **8000** 고정. 출력 폴더 `generated/backend/`. 원리는
`gen-backend-spring`과 같다(도메인별 병렬 서브에이전트, 결정적 스캐폴드
분리) - 차이는 언어·프레임워크 세부사항뿐이다.

## 절차

### 1. 도메인 조각으로 나눈다

```bash
python scripts/endpoint_groups.py generated/docs/api_spec.json -o generated/backend/_slices
```

### 2. 결정적 스캐폴드를 스크립트로 쓴다 (서브에이전트에게 안 시킴)

FastAPI는 진입점(main.py)이 조각마다 `from routers import X` / `app.include_router`
줄이 필요해서(spring처럼 컴포넌트 스캔이 자동으로 안 훑는다) 이 조립을
서브에이전트에게 맡기면 조각 수만큼 어긋날 위험이 크다. 그래서 스크립트로 뺐다:

```bash
python scripts/gen_fastapi_scaffold.py \
  --groups orders,payments,shipments,... \
  --dialect postgres \
  -o generated/backend
```
`--groups`는 1단계 manifest의 `group` 값들을 쉼표로 이어붙인다. 이 명령이
`generated/backend/main.py`, `db.py`, `requirements.txt`,
`routers/__init__.py`를 전부 쓴다.

`generated/docs/schema.sql`도 `generated/backend/schema.sql`로 복사해둔다
(main.py가 시작 시 그 경로에서 읽어 실행한다).

### 3. 조각마다 서브에이전트 병렬 디스패치

한 메시지에 조각 개수만큼 Agent 호출을 동시에 넣는다. 각 프롬프트에 포함:

```
[이 조각이 맡은 엔드포인트]
generated/backend/_slices/{module}.json

[출력 계약 - 정확히 지켜라]
파일은 정확히 하나: generated/backend/routers/{module}.py
`router = APIRouter()`를 모듈 최상위에 정의, 엔드포인트는 `@router.get(...)` 등으로.
DB 커넥션은 `from db import get_conn`으로만 얻는다.
[다음은 절대 만들지 마라]: FastAPI() 앱 생성, CORS 설정, 예외 핸들러, main.py,
db.py, requirements.txt, schema.sql - 전부 이미 만들어져 있다.

[반드시 먼저 Read할 것]
.claude/skills/gen-backend-fastapi/references/gotchas.md

[참고 자료]
ERD: generated/docs/data_model.json
DB 스키마(실행하지 않음, 테이블명 확인용): generated/docs/schema.sql
```

### 4. 결과 확인

`generated/backend/routers/`에 조각 수만큼 파일이 생겼는지 확인한 뒤
`verify-backend` 스킬로 넘어간다(`--target fastapi`).

## 재시도

`verify-backend`가 실패를 보고하면 실패 원인이 속한 조각만 재디스패치한다
(spring과 같은 방식). 3회 실패하면 사람에게 보고.
