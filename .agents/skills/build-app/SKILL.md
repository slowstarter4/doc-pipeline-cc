---
name: build-app
description: 기획문서(.md) 하나로 요구사항~API명세 문서화부터 백엔드·프론트 코드 생성·검증까지 전체 파이프라인을 돌리는 최상위 오케스트레이터. "이 기획문서로 앱 만들어줘", "/build-app <경로>" 같은 요청에 사용. doc-pipeline-cc 레포 안에서만 동작한다(다른 스킬이 참조하는 서브에이전트 정의가 이 레포 기준이라, Codex 세션을 이 레포 폴더에서 시작해야 한다).
---

# build-app: 기획문서 → 검증된 백엔드+프론트

이 스킬을 따르는 세션(너 자신)이 오케스트레이터다. 문서 생성은 직접 Write로,
코드 생성은 도메인 조각당 서브에이전트를 병렬 디스패치해서 한다. **어떤
단계도 LangGraph 같은 별도 상태 기계가 없다** - 이 대화 자체가 상태이고,
사람에게 물을 게 있으면 그냥 물어본다(대화 턴이 곧 멈춤/재개).

## 0. 입력 확인

인자로 기획문서 경로를 받는다(예: `examples/commerce_qwen_plan.md`). 없거나,
줬는데 실제로 그 파일이 없으면(오타든 신규 도메인이든) - 사람에게 완성된
문서를 새로 줄 건지 물어보지 말고 곧장 **`plan-intake` 스킬**을 따라 질의
응답으로 기획 초안을 새로 잡는다(6개 고정 질문 → 조립 → 최종승인 →
`examples/<파일명>.md` 저장). 그 스킬이 끝나면 나온 경로를 `plan_doc` 원본
경로로 삼아 아래를 이어간다.

그 다음 스택 선택을 AskUserQuestion으로 확인한다:
- **BACKEND_TARGET**: fastapi / spring / express / typescript
- **FRONTEND_TARGET**: vanilla / react / react-ts
- **DB_TARGET**: sqlite / postgres

`.Codex/skills/gen-backend-*`/`gen-frontend-*` 폴더가 곧 등록된 스택 목록이다
(스택이 늘면 폴더가 늘 뿐, 이 스킬은 안 바뀐다).

postgres를 골랐으면 사람에게 `cd db && docker compose up -d`를 직접 하라고
안내한다(이 스킬은 도커를 자동 기동하지 않는다).

**이전 산출물 백업 (스택·도메인 바꿔 재실행할 때 필수)**: 문서 생성으로
넘어가기 전에 **항상** 이 스크립트를 먼저 돌린다 - 손으로 `mv`를 짜지 않는다:

```bash
# 스택만 바꾸는 경우(같은 기획문서) - 문서는 그대로 재사용한다
python scripts/backup_generated.py

# 기획문서(도메인) 자체가 바뀐 경우에만
python scripts/backup_generated.py --include-docs
```

`generated/backend`·`frontend`가 이미 있으면 스택을 자동 감지해
`generated/backend_<스택>_<타임스탬프>/` 식으로 옮긴다(비어 있거나 없으면
아무것도 안 하므로 첫 실행에 그냥 돌려도 무해하다). **직접 `mv`로 백업하지
말 것** - 손으로 옮기면 나중에 그게 백업본인지 작업본인지 헷갈려서 지우는
사고가 난다(실측: 2026-07-29 세션에서 `mv`해둔 react-ts 프론트를 백업인 줄
알고 `rm -rf`로 날림). 스크립트는 이름 규칙이 항상 같아서 그 혼동이 없다.

**`generated/docs`는 기본적으로 백업 대상이 아니다** - 문서는 스택이 아니라
도메인에 종속이라, 같은 기획문서로 스택만 바꿔 돌릴 땐 그대로 재사용하는 게
맞다(1단계 gen-docs를 통째로 건너뛴다). 다시 뽑으면 LLM 단계라 비싸고, 매번
내용이 조금씩 달라져서 "스택을 바꿨더니 결과가 달라졌다"의 원인이 스택 탓인지
문서 탓인지 구분이 안 된다. dialect만 아래처럼 다시 맞추면 된다.

**`schema.sql`은 항상 이번 DB_TARGET으로 재생성한다**(gen-docs 5단계에서
어차피 만들지만, 문서를 재사용하는 경우엔 이 단계에서 다시 뽑아야 한다):

```bash
python scripts/schema_ddl.py generated/docs/data_model.json \
  --dialect <DB_TARGET> -o generated/docs/schema.sql
```
빠르고 결정적이라 매번 다시 뽑아도 손해 없다 - postgres SERIAL vs sqlite
INTEGER AUTOINCREMENT처럼 dialect별로 문법이 달라, 이전 dialect 산출물을
그대로 재사용하면 컴파일/기동 단계에서야 발견되는 에러로 이어진다(실측:
2026-07-29 fastapi/sqlite 세션에서 실제로 겪음).

**DB_TARGET=postgres에서 도메인(기획문서)이 바뀌면 `doc` 데이터베이스도
초기화해야 한다.** `schema.sql`은 `CREATE TABLE IF NOT EXISTS`라 테이블이 이미
있으면 새 컬럼으로 안 바뀐다 - 이전 도메인이 만든 동명 테이블(예: `stock`)이
남아있으면 새 도메인의 컬럼이 없어 `column "x" does not exist`(postgres
42703)로 기동 후 조회 시점에야 터진다(실측: 2026-07-30, 커머스 도메인
재생성 시 이전 세션의 `stock` 테이블 컬럼이 그대로 남아 있었음).
`scripts/verify_backend.py`는 전용 `docverify` 데이터베이스를 매번 리셋해서
이 문제가 없지만, **사람이 브라우저로 직접 여는 `doc` 데이터베이스는 이
스킬도 verify도 손대지 않는다** - 도메인이 바뀌었으면 사람에게 다음을
직접 실행하라고 안내한다(파괴적 작업이라 자동 실행 안 함):
```bash
docker exec -i <postgres 컨테이너> psql -U doc -d doc -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
```
스택만 바꾸고 도메인(기획문서)이 그대로면 테이블 구조가 같으므로 이 리셋은
필요 없다.

## 1. 문서 생성 - `gen-docs` 스킬

`gen-docs` 스킬을 따라 순서대로 쓴다:
`generated/docs/requirements.md` → `screen_design.md` → `data_model.json` →
`api_spec.json` → (스크립트로) `openapi.json`, `schema.sql`(`--dialect`는
DB_TARGET - 재실행이면 위 재생성 스텝과 같은 것, 여기선 최초 생성).

**핵심 규칙: 매 단계 원본 기획문서를 다시 Read한다** - 직전 산출물 요약본만
보고 원본을 놓치는 구조를 만들지 않는다(`gen-docs` 스킬에 상세 이유 있음).

`gen-docs` 6단계(자기 검토)에서 이슈가 나오면, 판단이 애매한 것만 AskUserQuestion
으로 사람에게 물어보고 진행 여부를 정한다 - 명백한 건 그 자리에서 고친다.

## 2. 백엔드 + 프론트 생성 (병렬)

**디스패치 전에 `generated/objections/`를 비운다**(있으면) - 이전 실행의
이의가 이번 실행 결과에 섞이면 4단계에서 "이번에 뭐가 새로 나왔는지"를
못 가른다. 조각별 파일이라 매 실행 처음부터 새로 쌓는 게 맞다:
```bash
rm -rf generated/objections
```

**같은 메시지에 두 갈래를 동시에 진행한다** - 백엔드와 프론트는 `api_spec.json`
만 공유하고 서로를 안 본다(계약 공유형, 협상 없음):

- 백엔드: `.Codex/skills/gen-backend-<BACKEND_TARGET>/SKILL.md`를 따른다.
  이 안에서 다시 도메인 조각별 서브에이전트를 병렬 디스패치한다(중첩 병렬).
- 프론트: `.Codex/skills/gen-frontend-<FRONTEND_TARGET>/SKILL.md`를 따른다.
  서브에이전트 1개.

둘 다 `generated/docs/api_spec.json`만 근거로 삼는다. 프론트는 추가로
`screen_design.md`(레이아웃 참고, 계약 아님)를 본다.

## 3. 검증 + 자기 수정 루프

### 백엔드
```bash
python scripts/verify_backend.py --target <BACKEND_TARGET> --db <DB_TARGET> \
  --api-spec generated/docs/api_spec.json
```
실패하면 `verify-backend` 스킬의 지시대로 **원인이 속한 도메인 조각만**
재디스패치(실패 로그를 `[이전 시도 실패 로그]`로 프롬프트에 포함). 재검증.
**같은 조각이 3회 실패하면 사람에게 로그를 보여주고 멈춘다.** 시도 횟수는
TaskCreate/TaskUpdate로 조각별로 추적한다(예: task subject
"backend-orders-retry", 실패마다 코멘트에 시도 번호 기록).

### 프론트
```bash
python scripts/verify_frontend.py --api-spec generated/docs/api_spec.json
```
실패하면 `verify-frontend` 스킬대로 전체 재디스패치(3회 상한, 조각화 없음).

## 4. 계약 이의제기 확인

서브에이전트들이 구현 중 계약(api_spec)에 정보가 부족해서 임의 판단한 게
있으면 `generated/objections/<slice>.json`에 남겼을 것이다(형식은
`.Codex/skills/references/objections-protocol.md`). 판정도 재디스패치도
여기서 안 한다 - 모아서 보여주기만 한다:

```bash
python scripts/collect_objections.py
```

비어 있으면("계약 이의 없음.") 그냥 다음 단계로 넘어간다 - 계약이 구현에
충분했다는 뜻이고, 이 자체가 정상 결과다. 이의가 있으면 출력을 그대로
사람에게 보여준다(이미 severity 순 - blocking → workaround → question).
**여기서 자동으로 코드를 고치거나 재디스패치하지 않는다** - Level 1은
기록만 한다, 사람이 읽고 다음을 판단한다.

## 5. 완료 보고

사람에게 알려줄 것:
- 문서 위치(`generated/docs/`), 백엔드/프론트 위치(`generated/backend`,
  `generated/frontend`)
- 백엔드 실행 명령(스택별로 다름 - `verify-backend` 스킬의 LaunchSpec 참고:
  fastapi=`uvicorn main:app --port 8000`, spring=`./gradlew bootRun`,
  express=`npm install && node server.js`(sqlite면 `--experimental-sqlite`
  플래그), typescript=`npm install && npm run build && node dist/server.js`)
- 프론트 실행 명령: `cd generated/frontend && npm install && npm run dev`
  (vanilla는 index.html을 브라우저로 바로 열기 - 단 Codex-in-chrome
  같은 브라우저 자동화 도구로 열 때는 확장이 `file://`을 막으므로
  `python -m http.server <포트>`로 띄운 뒤 `http://localhost:<포트>/
  index.html`로 열어야 한다)
- postgres면 도커가 떠 있어야 한다는 점 재확인
- 검증 결과 요약(스모크·계약·영속성 통과 여부, 남은 note) - **스모크는
  대부분 "잘못된 데이터 거부" 케이스 위주라 재고 미시딩처럼 정상 플로우를
  막는 문제는 못 잡는다.** 브라우저로 실제 확인할 때 주문 생성 등이 막히면
  먼저 `Stock` 같은 선행 테이블에 테스트 로우가 있는지 확인한다.

**여기까지는 자동 검증(스모크+계약+영속성)이고, 브라우저로 실제 열어서 확인은
사람 몫이다** - doc-pipeline과 같은 판단(여러 스택 자동 기동은 안 함).

## 재시도 상한과 사람 에스컬레이션

- 백엔드 조각·프론트 전체 모두 **3회** 상한.
- 상한 도달 시: 실패 로그 전문을 보여주고, 계속할지/다른 스택으로 바꿀지/
  수동으로 고칠지 AskUserQuestion으로 묻는다. 조용히 포기하거나 무한 재시도
  하지 않는다.

## 알려진 제약

- 프론트는 도메인 조각화가 없다(화면 간 공유 상태·네비게이션 때문에 한 파일
  세트로 일관되게 쓰는 게 맞다고 판단). 실패 시 전체 재생성.
- express/typescript 백엔드는 아직 spring만큼 실전 검증되지 않았다(spring만
  commerce_qwen_plan으로 end-to-end 검증됨) - 새로 걸리는 버그는 해당
  `gen-backend-*/references/gotchas.md`에 승격시켜 나간다.
