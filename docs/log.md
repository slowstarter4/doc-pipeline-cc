# 진행 로그

`CLAUDE.md`에서 분리한 날짜별 상세 진행 기록. 누적 append-only라 매 세션
통째로 로드하면 컨텍스트 비용이 계속 올라가서 별도 파일로 뺐다(2026-07-30,
외부 리뷰 반영). 여기 기록된 교훈 중 재사용 가능한 건 이미 각 스킬의
`references/gotchas.md`나 CLAUDE.md 본문으로 승격돼 있다 - 이 로그는
그 승격 과정의 원본 기록(순수 히스토리)이지, 매번 다시 읽을 필요는 없다.

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

- **2026-07-29 (이어서 4)**: **외부 리뷰(codex) 반영 - happyPath fixture
  검증 + 검증 격리 안전성.** 두 가지를 구현:
  1. **검증 격리 (P0)**: `verify_backend.py`가 `stop_by_port`(spring 등)로
     정리할 때 포트를 쥔 프로세스를 통째로 taskkill하는데, 그게 우리가 안
     띄운 프로세스일 수 있었다(사전 확인 없음). `_port_in_use()` 사전 체크를
     추가해 서버 기동 전 포트가 이미 쓰이고 있으면 아예 시작을 거부하도록
     고쳤다 - 이 체크가 있으면 이후 그 포트에 나타나는 프로세스는 전부
     우리가 띄운 것이라 안전하게 가정할 수 있다(별도 프로세스 트리 추적
     없이 기존 kill-by-port 로직 그대로 안전해짐).
  2. **happyPath fixture (위 3번 항목의 정식 버전)**: `gen-docs` 5.5단계로
     `api_spec.json`에 `happyPath`(seed 로우 + 실제 통과하는 body)를 작성하는
     단계 추가. `verify_backend.py`는 서버 기동 후 sqlite면 직접 db 파일에,
     postgres면 psycopg3로 `doc:doc@localhost:55432/doc`에 접속해 seed를
     심고, fixture body로 POST해서 "진짜 통과"를 확인한다 - fixture가 있는데
     실패하면 이제 하드 실패(예전엔 4xx를 전부 "도메인 규칙일 수 있음"으로
     봐줬음). 영속성 재기동 검사도 이 happyPath 결과를 재사용하도록 바꿨다.
     구현 중 두 가지를 더 발견/수정: (a) `Idempotency-Key` 헤더가 BR-014로
     명세에 실제로 있는데 스크립트가 안 보내서 fixture가 거부됨 - happyPath
     POST엔 항상 UUID로 채운 Idempotency-Key를 같이 보내도록 고침. (b) 응답의
     id 필드가 관례상 `id`가 아니라 `orderId`처럼 엔티티별로 다른데
     `_list_ids`/영속성 검사가 `id`만 봤음 - `_id_field_name()`으로 api_spec의
     response 스키마에서 실제 id 필드명을 찾아 쓰도록 일반화(`orderId` 같은
     경우도 이제 정확히 잡는다). fastapi+sqlite, typescript+postgres 둘 다
     실측: happyPath로 실제 주문 생성(201) → 재기동 후에도 남아있음 확인
     (postgres는 psycopg3 라이브러리 사용, `sys.executable`로 인터프리터
     고정해야 함 - PATH에 python이 여러 개 걸려있으면 다른 인터프리터가
     골라져 `ModuleNotFoundError: psycopg`가 남).
  같은 세션에서 `doc-pipeline`(LangGraph 자매 레포)엔 `plan_intake` 노드를,
  `doc-pipeline-cc`엔 `plan-intake` 스킬을 각각 짰다(구현 방식이 서로 다름 -
  전자는 `interrupt()`+checkpointer+self-loop 조건부 엣지, 후자는 세션 자체가
  문맥을 들고 있어 그냥 순차 대화로 충분함). doc-pipeline 쪽은 아직 미커밋
  (사람이 보류 요청), doc-pipeline-cc의 `plan-intake`는 실제로 한 번 대화로
  질문 1개까지만 돌려보고 세션 중단(리밋) - 6개 질문 끝까지, markdown 조립,
  최종승인, 파일 저장까지는 아직 미검증.
  **작업 중 실수**: fastapi/typescript 백엔드를 번갈아 테스트하려고
  `generated/frontend`를 `frontend_reactts`로 `mv`했다가, 정리 과정에서 백업인 줄
  알고 `rm -rf`로 지워버렸다 - react-ts 프론트 산출물 유실(gitignore 대상이라
  git엔 영향 없음, `gen-frontend-react-ts` 재실행하면 복구 가능하지만 아직 안 함).
  **다음에 할 것**: `plan-intake` 스킬 전체 흐름(6질문+조립+승인+저장) e2e
  검증, react-ts 프론트 재생성 여부 판단, `verify_backend.py`의 happyPath를
  express/spring 스택에서도 검증(fastapi/typescript만 확인함).
- **2026-07-29 (이어서 5)**: **`plan-intake` → `build-app` 전체 파이프라인
  e2e 검증 완료** (도서 대출 관리 시스템, 도메인부터 완전히 새로 만듦).
  `plan-intake`: 6개 질문 순차 응답(도서/회원/대출 엔티티, 필드, 동작,
  제약 - 동시대출 3권/연체중 대출불가/연체반납시 1개월 제한, 화면 3개,
  제외범위) → 세션이 직접 markdown 조립 → 사람 승인 → `examples/
  library_plan_v2.md` 저장까지 문제없이 동작. 저장 직전 3-5 제약 목록에
  중복 문구가 있어 그 자리에서 고쳐 저장(자기 검토가 실제로 작동).
  `build-app`: spring+react-ts+postgres 선택, 기존 커머스 도메인 산출물은
  `generated/*_commerce_*`로 백업 후 완전히 새 도메인으로 gen-docs 전체
  단계(요구사항~happyPath fixture)를 처음부터 실행 - 도메인 조각 3개
  (books/members/loans) + 프론트 1개 병렬 디스패치, **버그 없이 1차 통과**
  (`verify_backend.py`가 happyPath까지 포함해 한 번에 통과). 브라우저로
  실제 골든패스 전부 확인: 도서 등록 → 회원 등록 → 과거 반납예정일로 대출
  처리 → 목록에서 연체 빨간 배경 표시 확인 → 반납 처리 → 회원
  `loanRestrictedUntil`이 정확히 오늘+1개월로 갱신됨 확인 → 그 회원으로
  재대출 시도하면 "대출 제한 기간 중입니다" 409 거부까지 확인(FR-012/C2
  둘 다 실제로 맞물려 동작). 네이티브 HTML `<input type="date">`/`<select>`
  는 claude-in-chrome 좌표 클릭으로 채우면 세그먼트가 자꾸 어긋나 실패했다
  - `javascript_tool`로 `Object.getOwnPropertyDescriptor(...).set` 호출 후
  `input`/`change` 이벤트를 직접 dispatch하는 방식으로 우회(날짜·셀렉트
  필드가 있는 화면을 자동화로 채울 때 다음에도 이 방식을 우선 쓸 것).
  **남은 것**: `verify_backend.py`의 happyPath를 express 스택에서도 검증
  (fastapi/typescript/spring 셋 다 확인됨). react-ts 프론트(커머스 도메인)
  유실분은 결국 재생성 안 함 - 필요해지면 그때 `gen-frontend-react-ts`로.
- **2026-07-29 (이어서 6)**: **express+sqlite happyPath 검증 완료 -
  4개 백엔드 스택(fastapi/typescript/spring/express) 전부 happyPath 실측
  확인됨.** 같은 도서 대출 도메인(library_plan_v2)으로 express 3조각
  (books/members/loans) 병렬 디스패치, 재디스패치 없이 1차 통과
  (`verify_backend.py --target express --db sqlite`, happyPath POST /books
  201 확인). 이걸로 4스택×happyPath 매트릭스가 다 채워졌다 - 앞으로 새
  도메인/스택 조합을 시험할 때 happyPath 관련 미검증 스택 걱정은 없다.
- **2026-07-29 (이어서 7)**: **이전 산출물 백업을 스크립트로 자동화**
  (`scripts/backup_generated.py` 신설). 그동안 `build-app` 스킬은 "재실행이면
  백업해라"는 지시문만 갖고 있었고, 실제 `mv`는 오케스트레이터가 매번 손으로
  짰다 - 그 수동 과정에서 실제로 사고가 났다(2026-07-29: `mv`로 옮겨둔
  react-ts 프론트를 백업본으로 착각해 `rm -rf`로 삭제). 이제 스크립트가
  `generated/backend`·`frontend`·`docs`를 스택/dialect 자동 감지해
  `<name>_<태그>_<타임스탬프>/`로 옮긴다(backend: build.gradle→spring,
  tsconfig/server.ts→typescript, main.py→fastapi, server.js→express /
  frontend: package.json 없으면 vanilla, tsconfig 있으면 react-ts, 아니면
  react / docs: schema.sql의 `SERIAL PRIMARY KEY`→postgres,
  `AUTOINCREMENT`→sqlite). 이름 규칙이 항상 같아서 "이게 백업본인가
  작업본인가" 혼동 자체가 없어진다. 비어있거나 없으면 아무것도 안 하므로
  첫 실행에 그냥 돌려도 무해 - `build-app` 0단계에서 무조건 먼저 호출한다.
  self-check로 3개 감지기 전 분기 + 빈 폴더 무시 + 원본 자리 비워짐까지 검사.
  **다음에 할 것**: 백엔드×프론트 조합을 바꿔가며 더 돌려보기 - 지금까지
  검증한 조합이 스택별로 1회씩이라, 조합을 섞으면(예: fastapi+react,
  spring+vanilla) 아직 안 드러난 계약·포트·에러키 불일치가 나올 수 있다.
  이 과정 자체가 새로 만든 `backup_generated.py`의 실사용 검증도 된다.
- **2026-07-29 (이어서 8)**: **조합 매트릭스 4회차 완주 - 백엔드×DB 8칸
  전부 커버.** 매 회차가 "미검증 DB 경로 + 미검증 프론트 페어링"을 동시에
  덮도록 설계해서 4번으로 끝냈다(도메인은 library_plan_v2 고정, 문서 재사용).
  ① fastapi+react+postgres ② spring+vanilla+sqlite ③ typescript+react+sqlite
  ④ express+react-ts+sqlite. 넷 다 골든패스(도서·회원 등록 → 과거 반납예정일로
  대출 → 연체 표시 → 반납 → 회원 제한 오늘+1개월 → 제한 중 재대출 409 거부)를
  브라우저로 확인했다.
  **발견한 실제 버그 1건(스캐폴드)**: ③에서 `npm run build`가
  `TS2307: Cannot find module 'node:sqlite'`로 실패. `gen_express_scaffold.py`가
  TS devDeps에 `@types/node@^20.14.0`을 박는데, `node:sqlite` 타입 선언은
  @types/node 22부터 들어온다(node:sqlite 자체가 Node 22.5+ 기능). 런타임은
  Node 22.19라 멀쩡한데 tsc만 막힌 케이스. `^22.10.0`으로 올려 고쳤고,
  **조각 코드는 한 줄도 안 고치고 스캐폴드 재생성만으로 통과**했다(결정적
  스캐폴드 버그는 gotchas.md가 아니라 스크립트에서 고친다는 원칙 재확인 -
  dist/schema.sql 복사 버그 때와 같은 패턴).
  나머지 3회차는 재디스패치 0회로 1차 통과. postgres 소문자 폴딩·sqlite
  GeneratedKeyHolder·node:sqlite 동기 API·에러키(`detail` vs `message`) 전부
  각 스택 gotchas가 이미 잡아주고 있었다.
  `backup_generated.py`도 매 회차 실사용으로 검증됨(fastapi/react,
  spring/vanilla, typescript/react 태그를 매번 정확히 감지). **다만 첫
  실사용에서 자체 버그가 하나 나왔다**: 다른 `scripts/*.py`의 "인자 없으면
  self-check" 관례를 그대로 따랐는데, 이 스크립트는 정상 호출이 인자 없는
  형태라 백업이 통째로 self-check로 새서 no-op이 됐다. self-check를
  `--self-check` 뒤로 빼서 고침(관례를 기계적으로 따르면 안 되는 반례).
  또 docs를 기본 백업 대상에서 뺐다 - docs는 스택이 아니라 도메인 종속이라
  스택만 바꿀 땐 재사용해야 한다(매번 재생성하면 gen-docs가 다시 돌아 비싸고,
  LLM 산출물이라 내용이 달라져 "스택을 바꿨더니 결과가 달라졌다"의 원인
  분리가 안 된다). 도메인 교체 시에만 `--include-docs`.
  **관측된 미해결 이슈(코드 아님)**: `verify_frontend.py`의 경로 추출 정규식이
  **주석 안의 백틱 리터럴도 실제 호출로 오인**한다 - 프론트 에이전트가
  주석에 `${BASE}/...` 예시를 썼다가 가짜 경로로 잡혀 검사가 실패한 사례가
  두 번 있었다(에이전트가 주석 문구를 바꿔 우회). 지금은 디스패치 프롬프트에
  "주석에 백틱 경로 쓰지 마라"를 넣어 회피 중인데, 근본적으로는 추출기가
  주석을 걸러야 한다.
  **남은 것**: 프론트 페어링 12칸 중 8칸 커버됨(미검증: fastapi+react-ts,
  spring+react, express+vanilla, typescript+vanilla) - 각 축이 개별 검증돼
  우선순위는 낮다. `verify_frontend.py`의 주석 오탐 수정.
- **2026-07-29 (이어서 9)**: **happyPath를 단발 호출 → 순차 시나리오(steps)로
  전환.** 조합 검증을 끝내고 "그래서 검증이 뭘 본 건가"를 실측해보니 심각했다:
  library 도메인 8개 엔드포인트 중 verify_backend가 만진 건 4개뿐이고,
  **안 만진 4개가 로직이 있는 전부**였다(POST /loans의 C1/C2, 반납 시 제재
  부여, DELETE). happyPath 대상 선정 규칙이 "request body 있는 **첫 번째**
  POST"였는데 명세 순서상 `POST /books`(FK 없는 등록)가 걸린 탓 - 커머스에선
  우연히 `/orders`가 첫 POST라 잘 걸렸을 뿐, **기준이 중요도가 아니라 순서**
  였다. 계약 테스트도 4회 전부 스킵됐다(`generated/tests` 없음, 이 레포엔
  test-gen 스킬 자체가 미이식). 즉 4조합 "LLM 조각 버그 0건"의 실제 근거는
  자동 검증이 아니라 **사람이 브라우저로 손수 클릭한 것**이었다.
  그래서 `happyPath`를 스텝 배열로 바꿨다 - 앞 스텝 응답에서 값을 `capture`해
  뒤 스텝의 path/body에 `${var}`로 꽂아 실제 사용 순서대로 여러 엔드포인트를
  엮는다. 추가된 것: `expect`에 4xx를 적어 **거부되어야 정상인 케이스**를
  검증(통과 케이스만 보면 규칙이 아예 없어도 초록불), `expectAnyItem`으로
  조회 시점 계산 필드(연체 여부 등)의 **값까지** 확인(200만 보면 필드가
  비어 있어도 통과), `__persist` 특수 capture로 재기동 영속성 대상 지정.
  구버전 fixture(targetPath 단발)는 스텝 1개로 감싸 그대로 도니 조용한
  회귀는 없다. library fixture를 7스텝(등록→등록→대출→연체확인→반납→
  제재로 인한 재대출 409→재반납 409)으로 다시 쓰니 **커버리지 4/8 → 7/8**,
  express+sqlite로 전부 통과. **러너가 실패를 실제로 잡는지도 확인**했다 -
  제재 거부 스텝의 기대값을 일부러 201로 뒤집으니 빨간불 + 실패 스텝 이름·
  기대/실제·응답 본문 + "여기까지는 통과" 목록까지 찍히고 종료코드 1.
  gen-docs 5.5절도 새로 썼다: **"첫 POST를 고르지 마라, 업무 규칙이 가장 많이
  걸린 엔드포인트가 시나리오 중심이어야 한다"**를 실패 사례와 함께 명시하고,
  거부 케이스·계산 필드 확인을 필수 항목으로 넣었다.
  **남은 것**: test-gen 이식(api_spec의 rules → pytest 계약 테스트, 실행 코드는
  verify_backend에 이미 있고 생성기만 없다). `verify_frontend.py` 주석 오탐.
- **2026-07-29 (이어서 10)**: **verify_frontend 주석 오탐 수정 + happyPath로
  rules 커버리지 확보(test-gen은 안 만들기로 결정).**
  ① `verify_frontend.py`가 경로 추출을 원문 전체에 돌려서 **주석에 적은
  `${BASE}/...` 예시를 실제 호출로 오인**했다(프론트 에이전트가 두 번 걸려
  주석 문구를 바꿔 우회했던 것). 정규식으로 주석을 지우면
  `const BASE = "http://..."`의 `//`에서 줄이 잘려 진짜 호출을 놓치므로
  (오탐보다 나쁜 미탐), 문자열 안/밖을 구분하는 작은 스캐너(`_strip_comments`)로
  처리했다. wrapper key·디자인 토큰 검사에도 적용 - 주석에만 있는 키를
  "쓰고 있다"고 오판하면 **거짓 통과**라 더 위험해서다.
  ② **test-gen은 만들지 않기로 했다.** happyPath가 시나리오를 돌게 된 뒤로
  겹치는 범위가 커졌고, LLM이 만든 테스트가 틀린 기대를 담으면 거짓 실패로
  조각 재생성 루프(3회)를 태운다 - "그 테스트는 누가 검증하나" 문제가 남는다.
  대신 fixture가 rules를 다 훑게 만드는 쪽을 택했다(이미 도는 기계장치 재사용,
  새 실패 모드 없음).
  ③ 실측해보니 7스텝 fixture가 **11개 rules 중 5개**만 덮었고 **C1(동시 대출
  3권 제한)이 통째로 미검증**이었다. 18스텝으로 늘려 C1 경계(3건 성공 →
  4번째 409), C2(제재 거부)와 **그 반대 케이스(정상 반납 뒤엔 제재 없이 재대출
  성공)**, status/overdue 값 단언까지 넣었다. 반대 케이스가 중요한 이유:
  거부 스텝만 있으면 **무조건 409를 뱉는 구현도 통과**한다.
  ④ 새 fixture가 실제로 위반을 잡는지 확인 - 백엔드의 `activeCount >= 3`을
  `>= 999`로 무력화하니 정확히 `[C1: 4번째 동시 대출은 거부]` 스텝에서
  "409를 기대했는데 201 반환"으로 빨간불이 떴다.
  gen-docs 5.5절에 **"rules는 하나도 빠짐없이 최소 한 스텝이 타야 한다"**를
  커버리지 기준으로 못박고, 거부 규칙의 반대 케이스·한도 규칙의 경계 검증을
  필수 항목으로 넣었다. 6단계 자기검토도 "rules를 하나씩 짚으며 몇 번 스텝이
  검증하나 적어보라"로 바꿨다.
  **남은 것**: 프론트 페어링 4칸(fastapi+react-ts, spring+react, express+vanilla,
  typescript+vanilla) - 우선순위 낮음. 커머스 도메인 api_spec의 happyPath는
  아직 구버전(단발) 형식이라, 그 도메인을 다시 돌릴 땐 스텝으로 재작성 필요
  (구버전은 스텝 1개로 감싸져 돌긴 하지만 커버리지가 예전 그대로다).
- **2026-07-30**: **codex 리뷰 6건 반영 + plan-intake e2e + 백엔드×프론트
  12칸 페어링 완주 + CI 실행 매트릭스 8콤보 구축.**
  ① 별도 리뷰 문서(`IMPROVEMENT_PLAN.md`, 이후 반영 완료돼 삭제)의 지적 6건을
  전부 고쳤다: fastapi/spring/express 미처리 예외를 500+일반메시지로(도메인
  거부는 explicit 4xx만 인정, 전역 핸들러는 더 이상 400 안전망이 아님) -
  `gen_fastapi_scaffold.py`·`gen-backend-spring/SKILL.md`·`gen-backend-express`
  gotchas 갱신. `verify_backend.py`는 postgres 검증을 전용 `docverify` DB로
  완전 격리(매 실행마다 스키마 리셋, 사람이 쓰는 `doc` DB는 절대 안 건드림),
  sqlite 삭제도 `*.db` 글롭 대신 `app.db` 하나로 좁혔다. `schema_ddl.py`에
  식별자 정규식 검증+테이블명 충돌 검사 추가, happyPath seed도 SQL 삽입 전
  검증하게 함. `verify_frontend.py`는 (method, path) 단위 계약 비교로
  확장하고(POST를 GET으로 잘못 부르면 이제 잡는다), URL이 변수를 거쳐 method를
  못 정하는 호출은 "검증 불가"로 분리 보고. `tests/test_scripts_selfcheck.py`
  (pytest로 8개 스크립트 self-check 묶음)와 `.github/workflows/ci.yml` 신설.
  CORS를 fastapi/express/typescript는 `CORS_ORIGINS` env, spring은
  `app.cors.allowed-origins` 프로퍼티로 바꾸고 `.env.example` 생성.
  ② **`plan-intake` 스킬을 실제 대화로 6질문→조립→승인→저장까지 처음부터
  끝까지 e2e 검증**(이전엔 질문 1개까지만 해봤었음) - 커머스 주문/정산
  도메인(상품재고·주문·회원·배송·환불·쿠폰·적립금·정산 8엔티티)을 새로
  만들어 `examples/commerce_intake_plan.md`로 저장, 그대로 `build-app`
  (typescript+react-ts+postgres)까지 이어 돌려 실제 브라우저 골든패스 확인.
  이 과정에서 실버그 2건 발견해 gotchas 승격: coupon `used`(boolean) 컬럼을
  JS boolean 그대로 postgres에 바인딩해 42804 에러(0/1 정수 바인딩 필요는
  sqlite뿐 아니라 postgres도 마찬가지라고 명시), 프론트 `apiFetch(path, role)`
  헬퍼가 BASE와 path를 헬퍼 내부에서 합쳐서 계약검사기가 호출을 하나도 못 찾음
  (호출부에 완성된 백틱 URL을 그대로 넘기라고 `gen-frontend-react` 갱신).
  ③ **postgres 도메인 전환 시 실 데이터 잔존 문제 발견**: `doc` DB에 예전
  도메인(`stock` 테이블 등)이 남아있으면 `CREATE TABLE IF NOT EXISTS`가
  새 스키마로 안 바뀌어 `column "x" does not exist`로 브라우저 실사용 중
  터졌다 - `build-app` 0단계에 "도메인 바뀌고 postgres면 `doc` DB도
  `DROP SCHEMA public CASCADE`로 리셋하라"는 안내(파괴적 작업이라 자동화
  안 함, 사람에게 안내만) 추가.
  ④ **gen-docs 역할범위 판단 버그 실측**: requirements.md의 "관리자는 재고
  목록을 조회할 수 있다"만 보고 `GET /stocks` rules를 ADMIN 전용으로
  좁혔는데, 화면설계서엔 구매자 화면도 주문 전 재고를 봐야 해서 403으로
  막혔다. gen-docs에 "원문이 명시적으로 배제할 때만 단일 역할로 좁힌다,
  screen_design.md에서 그 데이터를 보는 다른 역할이 있는지 먼저 확인" 규칙과
  6단계 자기검토에 "화면별 호출 엔드포인트 vs rules 허용 역할 대조" 체크,
  happyPath에 "비-ADMIN 역할 화면은 최소 한 스텝을 그 역할 헤더로 호출"
  요구를 추가했다.
  ⑤ **백엔드×프론트 12칸 페어링 전부 실행 검증 완주**(fastapi+react-ts,
  spring+react, express+vanilla, typescript+vanilla - 나머지 8칸은 이전
  세션들에서 이미 검증됨). library_plan_v2 도메인(3엔티티, 18스텝
  happyPath) 재사용으로 비용 절감. express+vanilla 페어링에서 실버그 1건:
  `members.js`가 `const db = require('../db')`로 `{ db }` 모듈 전체를
  통째로 받아 `db.prepare is not a function` - `gen-backend-express` gotchas에
  "반드시 `const { db } = require('../db')`로 구조분해" 명시.
  ⑥ **`generated/docs_commerce`(예전 commerce_qwen 도메인)의 happyPath를
  단발→24스텝으로 재작성**(주문 생성 거부/성공, C1/C5/C7/C9/C20/C21/C22
  role 체크, 재고부족·금액불일치·버전충돌 거부케이스). 이 도메인은 백엔드가
  없어 실행 검증은 못 하고 JSON 스키마 유효성만 확인 - 아이템 단위
  취소/반품/교환, 배송상태 PUT, PG 웹훅 서명, 정산 hold/release는 상태값·
  서명 인프라가 문서에 없어 스텝으로 못 만들어 커버리지에서 뺐다(정직하게
  기록).
  ⑦ **CI e2e 매트릭스를 fastapi/express 2스택→4스택(+spring/typescript) x
  2DB = 8콤보로 확장.** spring은 스캐폴드가 파이썬 스크립트가 아니라 스킬
  문서를 오케스트레이터가 손으로 여러 파일 써서 만드는 구조라
  `tests/fixtures/spring_scaffold/`에 build.gradle(dialect별)·
  application.properties(dialect별)·TodoApplication.java·config 3종을
  픽스처로 만들어 CI에서 복사한다. typescript는 db.ts가 dialect별로
  `db` 또는 `pool` 중 하나만 export하는데(TS 정적 named import라 없는
  심볼은 컴파일 에러) `widgets_sqlite.ts`/`widgets_postgres.ts`로 파일을
  아예 분리했다. 8콤보 전부 로컬에서 먼저 통과 확인 후 CI에 반영.
  ⑧ `generated/` 안에 쌓여있던 백업 폴더(스택 전환 스냅샷) 27개+로그
  11개를 정리 - 활성 `backend`/`frontend`/`docs`(커머스 도메인)만 남김.
  **남은 것**: 없음 - 이번 리뷰·개선 사이클로 다룰 항목은 전부 마무리됨.
  다음은 새 도메인/스택 조합을 실제로 써보면서 나오는 이슈를 그때그때
  gotchas에 승격시키는 통상 운영 사이클.
- **2026-08-04**: **새 도메인(기차표 예약) 생성 + spring+react-ts+postgres
  조합 처음부터 끝까지 실측(문서생성→백엔드5조각 병렬생성→프론트→검증→
  브라우저 골든패스→Playwright e2e) + 도구/문서 버그 다수 발견·수정.**
  ① `plan-intake` 스킬로 기차표 예약 도메인(8엔티티: 열차/역/운행/좌석/
  승객/예약/결제/취소환불) 새로 만들어 `examples/train_ticket_plan.md`로
  저장 - 종전 도메인(library/commerce/todo)과 겹치지 않는 제약 종류(좌석
  중복예약 금지, 취소시점별 환불율 3단계, 결제 미완료 자동취소)를 의도적
  으로 골랐다.
  ② `build-app`으로 spring+react-ts+postgres 조합 전체 파이프라인 완주,
  `verify_backend.py`/`verify_frontend.py` 둘 다 통과, 브라우저로 골든패스
  직접 클릭 확인(운행검색→좌석선택→예약→결제→내예약 취소+환불배너→
  관리자 예약/결제현황).
  ③ **실측 중 발견해 고친 진짜 버그 2건**: (a) `verify_backend.py`의
  happyPath `capture`가 최상위 응답 필드만 읽어서, 생성 API 없이 다른
  리소스 등록의 부수효과로만 생기는 자식 리소스(열차 등록 시 자동생성되는
  좌석)의 id를 알아낼 방법이 없었다 - `"seats.0.id"` 같은 점표기(목록
  인덱싱) 지원 추가, `gen-docs/SKILL.md`에도 "자동생성 리소스 id를 순번
  으로 가정하지 마라" 문서화. (b) `gen-frontend-react` 프론트가 액션
  버튼(취소)과 결과 배너(환불금액)를 같은 상태 조건(`status === "확정"`)
  블록에 묶어서, 취소 성공 직후 status가 바뀌며 조건이 깨져 방금 받은
  응답이 화면에 안 보였다 - `gen-frontend-react/SKILL.md`에 패턴 gotcha로
  승격.
  ④ **`verify_frontend_e2e.py`를 이 도메인으로 처음 돌리며 도메인 무관
  스크립트 버그 5건 발견·수정**(전부 다른 도메인/스택에도 재발 가능했던
  것들): `--backend-url` 옵션 추가(화면에 폼 자체가 없는 생성 엔드포인트는
  API로 직접 seed), `<select>` 드롭다운에 `.fill()` 쓰던 버그를
  `.select_option()`으로, `_find_item_by_id`가 페이지 전체에서 id만 보고
  매칭해 다른 리소스가 우연히 같은 id면 엉뚱한 항목을 집어오던 버그(이
  엔드포인트 전용 독립폼 우선으로 순서 변경), 역할 토글 버튼 이름이
  `role-buyer`로 하드코딩돼 다른 이름(`role-passenger` 등) 쓰는 도메인은
  역할전환이 조용히 실패하던 버그(`role-`로 시작하는 testid 전부 훑게
  수정), `capture`에 점표기 지원(백엔드 쪽과 같은 기능의 DOM 버전).
  ⑤ **새로 발견해 문서화만 하고 고치지 않은 한계**: "운행 선택 → 좌석
  클릭"처럼 이전 화면의 선택 결과를 다음 화면 `readonly` 필드에 반영하는
  마법사형(wizard) 흐름은 "요청 필드 하나당 입력칸 하나"라는 e2e 스크립트의
  폼 모델로 표현이 안 된다(억지로 채우려다 타임아웃). `verify_frontend_e2e.py`
  docstring에 남겨둠 - 다음에 같은 패턴 만나면 그때 "이전 스텝에서 만든
  항목을 목록에서 클릭해 선택"하는 별도 스텝 타입을 컨벤션에 추가할지 판단.
  커밋: `cb259fd`(도메인+문서 버그 2건), `b0cfc93`(e2e 스크립트 버그 5건).
  **남은 것**: (1) 예약 생성 같은 다단계 선택 마법사 흐름을 e2e로 검증하는
  방법 - 컨벤션 확장 필요, 아직 설계 안 함. (2) CI 8콤보 매트릭스에
  Playwright e2e 편입 여부 - 여전히 미결정(2026-07-31과 같은 이유:
  브라우저 설치+서버 동시 기동으로 CI 시간 증가). (3) build-app이
  gen-frontend-* 후 e2e 자동호출 여부 - 여전히 미결정(서버 자동기동 금지
  원칙과 충돌). (4) 다른 도메인/스택 조합으로 e2e 실측 계속 쌓기(통상
  운영 사이클, 특히 spring 외 스택 x 이 도메인, 또는 마법사형 흐름이 있는
  다른 도메인).
