# CLAUDE.md

문서 기반 개발 파이프라인 - **Claude Code 네이티브 재구현판**. 사람이 쓴
기획문서(.md)를 입력으로, 개발 문서를 생성하고 그에 맞춰 코드까지 생성·검증하는
멀티에이전트 시스템이다. 자매 레포 `doc-pipeline`(LangGraph + OpenRouter API 버전)의
후속작 - 토큰 종량제 비용 문제로 Claude Code 세션/서브에이전트 안에서 도는 구조로
다시 짰다. `doc-pipeline`은 그대로 두고 안 건드린다 - 레퍼런스로만 참고.

## 왜 다시 짰나

`doc-pipeline`은 OpenRouter API를 직접 호출해 토큰 단위로 과금됐다. 이 레포는
전체가 Claude Code 세션(오케스트레이터)과 그 세션이 띄우는 서브에이전트로만 돈다 -
별도 API 키·과금이 없다. 덤으로 두 가지가 설계 자체로 고쳐진다:

1. **코드 생성 잘림 문제.** `doc-pipeline`은 백엔드 코드를 `{"files":[...]}` JSON
   한 덩어리로 받았는데, 큰 도메인(엔티티 10+개)에서 한 응답에 다 안 담겨
   반복적으로 잘렸다. 여기선 서브에이전트가 자기 Write 도구로 파일을 직접 쓴다 -
   JSON 봉투 자체가 없어서 이 잘림 버그가 구조적으로 안 생긴다.
2. **문서 요약 정보손실 문제.** `doc-pipeline`의 `requirements` 노드가 원본
   기획문서의 상태전이표·권한매트릭스를 "N절 참고"식으로 요약했는데, 뒤 단계가
   원본을 다시 안 보고 요약본만 봐서 그 정보가 증발했다(실측: 상용 커머스
   기획문서 테스트에서 배송지 입력 필드·권한 조건이 통째로 날아감). 여기선
   문서 생성 단계마다 항상 원본 기획문서를 같이 준다 - 요약본에만 의존하지 않는다.

## 아키텍처 매핑 (doc-pipeline → 여기)

| doc-pipeline (LangGraph 노드) | 여기 | 비고 |
|---|---|---|
| `requirements`/`screen_design`/`data_model`/`api_spec` | 오케스트레이터(빌드 스킬을 따르는 이 세션)가 직접 Write | 서브에이전트 안 씀 - 순차적이고 가벼움, 문맥 연속성이 더 중요 |
| `schema_ddl`/`openapi_spec` (결정적 변환) | `scripts/`의 파이썬 스크립트, Bash로 호출 | 원래도 LLM 안 쓰던 부분이라 거의 그대로 |
| `review_gate` (interrupt+checkpointer) | 오케스트레이터가 AskUserQuestion으로 물음 | 대화 턴 자체가 멈춤/재개라 별도 기계장치 불필요 |
| `backend`/`frontend` (LLM 코드생성, JSON 봉투) | 도메인 조각당 서브에이전트 1개, 병렬 디스패치, 각자 Write로 파일 직접 씀 | JSON 봉투 제거 |
| `write_backend`/`write_frontend` | 불필요 - 서브에이전트가 이미 디스크에 씀 | |
| `verify_backend` (기동+스모크+영속성+계약테스트) | `verify-backend` 스킬, `backend-runtime-verifier`류 에이전트 패턴 재사용 | doc-pipeline에 이미 있던 패턴 이식 |
| `retry_count`/`MAX_BACKEND_RETRIES` | 오케스트레이터가 시도 횟수 추적(TaskCreate/TaskUpdate), 상한 3회 | 실패한 조각만 재디스패치 가능 |
| `verify_frontend` (정규식 계약검사) | 그대로 스크립트 포팅 | 무변경 |
| 백엔드/프론트 레지스트리 (파이썬 딕셔너리) | 스택별 `.claude/skills/gen-backend-<stack>/` 폴더 존재가 곧 등록 | 디자인 프리셋 스위처와 같은 "폴더 훑기" 패턴 |
| Claude Design 연동 (파일 경유 pull) | `DesignSync` 도구를 세션에서 직접 호출 | 브릿지 단계 제거 |

## 레포 구조

```
doc-pipeline-cc/
├── CLAUDE.md
├── .claude/
│   ├── skills/
│   │   ├── build-app/              최상위 오케스트레이터 (/build-app <plan.md>)
│   │   ├── gen-docs/               요구사항~API명세 (+원본 plan.md 항상 동봉)
│   │   ├── gen-backend-<stack>/    스택별 도메인 조각 생성 지시 + references/gotchas.md
│   │   ├── gen-frontend-<variant>/ 프론트 스택별 생성 지시
│   │   ├── verify-backend/         기동+스모크+계약테스트
│   │   └── verify-frontend/        정적 계약검사(경로·wrapper key)
│   └── agents/
│       └── backend-slice-writer.md 도메인 조각 하나를 맡는 서브에이전트 정의
├── scripts/                        결정적 변환 (LLM 미사용)
│   ├── schema_ddl.py               ERD → CREATE TABLE (SQL 예약어 테이블명 처리 포함)
│   ├── openapi_spec.py             api_spec → OpenAPI 3.0
│   └── endpoint_groups.py          API 명세를 도메인 조각으로 분류
├── design/
│   ├── design_system.md            정본 (토큰+컴포넌트 레시피만, 원본 HTML 안 실음)
│   ├── presets/                    DESIGN_TARGET 스위처용 프리셋들
│   └── reference/                  출처 보존용, 프롬프트엔 안 실림
├── db/
│   └── docker-compose.yml          postgres:16, 사람이 직접 기동
├── examples/                       샘플 기획문서 (commerce_qwen_plan.md 등)
└── generated/                      gitignore, 빌드 산출물
```

## 핵심 설계 규칙

1. **결정적으로 할 수 있는 변환은 서브에이전트(LLM)를 안 쓴다.** `scripts/`의
   파이썬 스크립트가 그 경계 - 같은 입력엔 항상 같은 출력.
2. **문서 생성 단계는 항상 원본 기획문서를 같이 본다.** 이전 단계 산출물
   요약본만 보고 원본을 놓치는 구조를 만들지 않는다 - "왜 다시 짰나" 참고.
3. **코드 생성은 서브에이전트가 자기 Write로 직접 파일을 쓴다.** `{"files":[...]}`
   JSON 봉투 패턴을 쓰지 않는다.
4. **백엔드 도메인 조각마다 서브에이전트 1개, 병렬 디스패치.** 한 메시지에 여러
   Agent 호출을 동시에 담는다.
5. **재시도는 실패한 조각만 다시 디스패치한다.** 오케스트레이터가 시도 횟수를
   세고 상한(3회) 넘으면 사람에게 보고하고 멈춘다 - 무한 루프 방지.
6. **스택 추가 = 스킬 폴더 추가.** `build-app` 오케스트레이터는 스택 이름별
   if/elif를 안 쌓고 `.claude/skills/gen-backend-*`/`gen-frontend-*` 폴더를 훑는다.
7. **함정 지식은 스킬 reference 문서로 남긴다.** Jackson coercion, 람다 캡처
   final, is-접두사 JsonProperty, SQL 예약어 테이블명, `X-User-Type`/`X-User-Id`
   헤더 컨벤션, node:sqlite·psycopg3 함정 등 `doc-pipeline`에서 쌓인 것 전부
   각 스택 스킬의 `references/gotchas.md`에 옮긴다. 새로 걸리는 버그도 같은
   자리에 계속 승격시킨다(doc-pipeline의 반복 원칙 그대로).

**운영상 제약 (2026-07-28 실측):**
- **커스텀 `.claude/agents/*.md` 정의는 세션이 시작된 프로젝트 루트 기준으로만
  로드된다.** 다른 프로젝트에서 시작한 세션은 이 레포의 `backend-slice-writer`
  같은 에이전트를 못 찾는다("Agent type not found"). **`build-app`을 쓰려면
  Claude Code를 이 레포(`doc-pipeline-cc`) 폴더에서 새로 시작해야 한다.** 그
  전까지 급하면 `general-purpose`에 에이전트 파일 내용을 프롬프트로 인라인해서
  우회할 수 있지만(실측: 정상 동작), 정식 경로는 세션을 이 레포에서 시작하는 것.
- **`verify_backend.py`의 스모크 검사는 상태코드만으로 "도메인 규칙 거부"와
  "진짜 서버 버그"를 못 가른다.** `GlobalExceptionHandler`가 미처리 예외까지
  400으로 바꿔서 응답하는 설계(500을 클라이언트에 안 보여주기 위함)라, SQL
  문법 오류 같은 진짜 버그도 400으로 나온다. `_looks_like_bug()`가 응답
  메시지에 `bad SQL grammar`/`NullPointerException` 같은 기술적 예외 흔적이
  있으면 상태코드와 무관하게 문제로 잡는다 - 이 휴리스틱이 실제로 `refunds`·
  `stock` 조각의 SQL 파라미터 바인딩 버그(`WHERE (? IS NULL OR col = ?)` 패턴에서
  `?` 개수와 바인딩 값 개수 불일치)를 잡아냈다.

## DB / 도커

`db/docker-compose.yml`이 postgres:16을 로컬 55432 포트로 띄운다(5432/5433은
Windows WinNAT 예약범위라 막힘). **오케스트레이터도 서브에이전트도 도커를 자동
기동하지 않는다** - 사람이 `cd db && docker compose up -d`로 직접 올린다
(`db/README.md` 참고). DB 방언(sqlite/postgres)은 `scripts/schema_ddl.py`의
`--dialect` 플래그로 고른다.

## 디자인 시스템

`design/design_system.md`가 정본이다. 프론트 생성 스킬은 이 파일(토큰+컴포넌트
레시피)만 프롬프트에 싣는다 - 완성된 HTML/CSS 원본을 주면 레이아웃을 그대로
베끼게 되므로 원본은 `design/reference/`에만 보존한다. 레이아웃 배치는 여전히
화면설계서가 정한다. 톤을 바꾸려면 `design/presets/<이름>.md`를 만들고 빌드 시
지정한다(정본은 안 건드림 - 영구 전환은 프리셋을 정본 위에 복사하는 것).

외부 디자인 도구(Claude Design)에서 받아오는 절차는 `DesignSync` 도구를 세션에서
직접 호출한다 - `doc-pipeline`처럼 pull→로컬 파일 저장→세션 재시작 없이, 같은
세션 안에서 pull하고 바로 `design_system.md`에 반영할 수 있다.

## 진행 상태

이 레포는 `doc-pipeline`의 재설계 초기 단계다. 진행 순서와 근거는
`.claude/plans/`에 남긴 설계 계획을 따른다. 완료된 것과 남은 것은 아래처럼
갱신한다(날짜별로 계속 추가):

- **2026-07-28**: 레포 뼈대 생성, 결정적 스크립트 3개(schema_ddl/openapi_spec/
  endpoint_groups) 포팅 + 자기점검 통과, db/design/examples 이식, 이 CLAUDE.md 작성.
- **2026-07-28 (이어서)**: **전체 스캐폴드 완성.** `gen-docs`(원본 기획문서 동봉
  규칙 포함), `gen-backend-spring`(+`backend-slice-writer` 에이전트+gotchas.md,
  commerce_qwen_plan.md로 실측 검증 - 도메인 10조각 병렬 디스패치, 컴파일 첫
  시도 성공, verify-backend가 진짜 SQL 버그 2건 잡아 재디스패치로 고침),
  `gen-backend-fastapi`/`express`/`typescript`(+각 gotchas.md, 미검증 - spring
  패턴 이식), `gen-frontend-vanilla`/`react`/`react-ts`, `verify-backend`/
  `verify-frontend` 스킬, `scripts/verify_backend.py`·`verify_frontend.py`·
  `gen_fastapi_scaffold.py`·`gen_express_scaffold.py` 전부 작성 + 자기점검 통과.
  마지막으로 `build-app` 오케스트레이터 스킬로 전체를 하나의 진입점(`/build-app
  <plan.md>`)으로 묶었다.
  **다음에 할 것**: express/typescript/vanilla/react/react-ts를 실제
  commerce_qwen_plan.md로 end-to-end 검증(spring만 해봤다) - 걸리는 버그는
  해당 gotchas.md에 승격. `build-app` 스킬 자체도 아직 처음부터 끝까지
  한 번에 돌려본 적은 없다(부분부분 스킬 단위로만 검증함).
- **2026-07-28 (이어서 2)**: **`build-app` 오케스트레이터 첫 통짜 실행 성공**
  (BACKEND_TARGET=express, FRONTEND_TARGET=react, DB_TARGET=postgres,
  commerce_qwen_plan.md). gen-docs는 spring 검증 때 만든 산출물이 스택 무관이라
  재사용(문서 재생성 스킵). express 도메인 10조각 병렬 디스패치 → 컴파일/기동
  1차 성공, `verify_backend.py`가 `passed: true`를 냈지만 수동 브라우저 검증
  중 **settlements 조각 버그를 스크립트가 놓친 것**을 발견 - SQL에서
  quoted identifier(`"Settlement"`, `"settlementId"`)를 썼는데 schema.sql의
  unquoted CREATE TABLE 때문에 postgres가 테이블/컬럼명을 전부 소문자로 접어
  실제로는 안 맞는 상태였다(`relation "Settlement" does not exist`). 원인은
  `verify_backend.py`의 `_looks_like_bug()` 휴리스틱이 Java/Spring 예외
  패턴(`sql grammar`, `nullpointerexception` 등)만 잡고 postgres/node 에러
  패턴은 안 잡아서 400을 "도메인 규칙 거부"로 오판했기 때문 - 이 갭을
  `_TECHNICAL_ERROR_MARKERS`에 postgres(`does not exist`, `syntax error at or
  near`)·node(`typeerror`, `referenceerror`, `traceback` 등) 패턴 추가로 메움.
  settlements.js는 재디스패치로 고치고 `gen-backend-express/references/
  gotchas.md`에 "quoted identifier 쓰지 말 것" 규칙 승격. 이후 재검증 통과,
  프론트도 `verify_frontend.py` 통과(디자인 토큰 14/15, wrapper key 10/10).
  브라우저로 실제 주문 생성(구매자 화면 → DB 저장)까지 확인함 - 배송비
  안분(BR-010)까지 정상 반영(상품 10,000 + 배송비 3,000 = 13,000).
  spring 백엔드는 `generated/backend_spring/`로 백업해두고 express로 덮어씀
  (같은 `generated/backend/` 경로를 스택별로 재사용하는 구조라 스택 바꿔
  돌릴 땐 이전 결과 백업 필요 - build-app 스킬에 아직 이 백업 스텝이 없다,
  다음에 스킬 자체에 반영할지 검토).
  **환경 이슈(로컬 머신 한정, 코드 문제 아님)**: 이 개발 머신에서 5173~5180대
  포트가 vite/node/python 무관하게 시스템 레벨에서 EACCES(WinWSAEACCES 10013)
  로 막힘 - WinNAT/Hyper-V/도커 관련 포트 예약으로 추정(docker postgres 기동
  이후 발생, CLAUDE.md의 5432/5433 케이스와 같은 부류일 가능성). 8081/3000은
  정상 바인딩됨 - `generated/frontend/vite.config.js`에 `server: { port: 3000,
  host: "127.0.0.1" }`로 우회해뒀다. 원인 미해결(winnat 재시작 등 admin 권한
  필요한 조치 안 해봄) - 다른 머신/세션에서는 안 나타날 수 있다.
  **다음에 할 것**: typescript/vanilla/react-ts 나머지 3스택 조합도
  commerce_qwen_plan.md로 검증. `build-app`의 "스택 재실행 시 이전
  generated/backend 백업" 스텝 보강 검토.
- **2026-07-29**: **fastapi + vanilla + sqlite 조합 검증 완료** - 이번엔
  버그 없이 1차 통과(도메인 10조각+프론트 1개, 재디스패치 0회). gen-docs
  산출물은 재사용했지만 `schema.sql`은 이전 실행이 postgres dialect로
  만든 것이라 `python scripts/schema_ddl.py generated/docs/data_model.json
  --dialect sqlite -o generated/docs/schema.sql`로 다시 뽑아야 했다 - **스택
  재실행 시 DB_TARGET이 바뀌면 schema.sql도 재생성 필요**, `build-app`
  스킬 0단계에 이 스텝이 명시돼 있지 않아 놓치기 쉽다(다음에 스킬 문서에
  반영 검토). `verify_backend.py`가 스모크(8건)는 통과시켰지만 유효한
  주문 생성 케이스까지는 안 건드려서(전부 잘못된 데이터 거부 확인용) 브라우저
  수동 검증으로 실제 골든패스를 봐야 했다 - sqlite DB(`generated/backend/
  app.db`)에 Stock 로우가 하나도 없어 주문 생성이 막혔던 것도 스크립트가
  안 잡았다(재고 사전 시딩이 필요하다는 게 검증 스크립트 범위 밖). 수동으로
  `Stock` 1행 심고 브라우저에서 주문서 작성 → `주문 생성됨: order_...
  (총 결제금액 13000)` 확인, DB 직접 조회로 영속(status=CREATED,
  totalPaymentAmount=13000)까지 확인 - BR-010 배송비 안분 정상(상품 10,000 +
  배송비 3,000). 프론트는 vanilla 특성상 로컬 file://을 브라우저 확장이 막아서
  `python -m http.server`로 띄워 열었다(파일 직접 열기 안내는 여전히 유효하나
  claude-in-chrome로 열 땐 이 우회가 필요).
  기존 express/react 산출물은 `generated/backend_express/`,
  `generated/frontend_react/`로 백업 후 덮어씀(수동 - 여전히 스킬 자체
  백업 스텝은 없음, 이번에도 오케스트레이터가 매뉴얼로 처리).
  **남은 것**: typescript/react-ts 조합 미검증. `build-app` 보강 항목 2가지
  누적됨(① 재실행 시 backend/frontend 백업 자동화, ② DB_TARGET 변경 시
  schema.sql 재생성 스텝 명시).
- **2026-07-29 (이어서)**: **typescript + react-ts + postgres 조합 검증 완료**
  - 6스택 조합(backend 4종×frontend 3종 중 실측 검증 대상) 전부 커버.
  도메인 조각 자체는 버그 없이 1차 통과했지만 **`gen_express_scaffold.py`의
  TS 빌드 스크립트 버그를 하나 발견해 원인 수정**: `"build": "tsc"`가
  `dist/`로 컴파일만 하고 `schema.sql`은 안 옮겨서, `server.ts`가
  `readFileSync(join(__dirname, 'schema.sql'))`로 찾을 때 실행 위치가
  `dist/`라 `ENOENT`로 기동 자체가 실패했다(express의 plain JS는 `dist`
  분리가 없어서 이 버그가 없었다 - TS 전용 갭). `scripts/gen_express_scaffold.py`
  의 `build` 스크립트를 `tsc && node -e "...copyFileSync('schema.sql',
  'dist/schema.sql')..."`로 고쳐 다음부터 생성되는 모든 TS 백엔드에 반영
  (LLM 서브에이전트 잘못이 아니라 결정적 스캐폴드 스크립트 버그라 스크립트
  레벨에서 고침 - gotchas.md에 안 올림). 이후 재검증 통과, react-ts 프론트도
  `tsc --noEmit`/`vite build`/`verify_frontend.py` 전부 1차 통과(디자인 토큰
  14/15, wrapper key 10/10). 브라우저로 주문 생성까지 확인 - `결제예정액
  13000원`(BR-010 정상), postgres `order_` 테이블에 영속 확인.
  기존 fastapi/vanilla 산출물은 `generated/backend_fastapi/`,
  `generated/frontend_vanilla/`로 백업.
  **build-app 보강항목 최종 리스트(2세션 누적)**:
  1. **DB_TARGET 재선택 시 schema.sql 재생성 스텝 누락** - 0단계에서
     DB_TARGET을 물어본 뒤, 기존 `generated/docs/schema.sql`이 다른
     dialect로 만들어졌으면 `schema_ddl.py --dialect <DB_TARGET>`로
     다시 뽑으라는 안내가 스킬 문서에 없다. dialect 불일치를 스킬이
     자동 감지하지도 않는다.
  2. **스택 재실행 시 이전 backend/frontend 산출물 백업 자동화 없음** -
     `generated/backend`, `generated/frontend`를 스택별로 매번 오케스트레이터가
     수동 `mv`로 백업(`backend_<이전스택>/`)해야 했다. 2번 다 이렇게 처리함 -
     스킬 0단계나 4단계에 "재실행 감지 시 기존 산출물 타임스탬프/스택명으로
     이동" 스텝을 넣을지 검토.
  3. **`verify_backend.py`가 유효 데이터 골든패스를 검증하지 않음** - 스모크는
     전부 "잘못된 데이터 거부" 케이스 위주라, 재고 미시딩처럼 정상 플로우를
     막는 문제(DB에 Stock row 없음)를 못 잡는다. 두 세션 다 브라우저 수동
     검증에서 재고를 수동 시딩해야 주문이 성사됐다 - 검증 스크립트에 최소
     시딩 데이터를 넣고 "정상 주문 1건 생성" 케이스를 추가할지 검토.
  4. **vanilla 프론트는 file://을 claude-in-chrome 확장이 막는다** - 브라우저
     자동화로 열 때는 `python -m http.server`로 띄워야 한다(사람이 직접 여는
     안내 자체는 유효, 자동화 검증 절차에만 해당).

  **보강 반영 현황 (2026-07-29, 이어서 3)**: ①②④ `build-app` 스킬 문서에
  반영 완료(0단계 재실행 감지+백업+dialect 재생성 안내, 4단계 vanilla
  http.server 우회 안내 + 재고 시딩 확인 안내). ③(`verify_backend.py`에
  정상 주문 골든패스 자동검증 추가)은 **보류** - 스택마다 launch/스키마 접근
  방식이 달라 제너릭 시딩 로직을 짜려면 스크립트를 상당 부분 다시 읽고
  설계해야 해서 토큰 소모가 크다(세션당 컨텍스트 85% 넘게 쓴 시점에 판단).
  다음 세션에서 이어서 할 것 - `scripts/verify_backend.py` 구조 파악부터
  시작, 최소 1스택(fastapi 추천 - 가장 단순)으로 먼저 검증 후 나머지 확장.
