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
   자리에 계속 승격시킨다(doc-pipeline의 반복 원칙 그대로). **gotchas.md도
   append-only라 같은 성장 문제를 겪는다** - 스캐폴드 스크립트 수정으로
   더 이상 안 걸리는 항목(예: 예전에 필요했던 우회 지시가 스크립트 버그
   수정으로 무의미해진 경우)은 발견되는 대로 정리한다. 다만 "스택 자체
   특성"(node:sqlite 동기 API, Jackson coercion 등)은 스크립트로 못 없애는
   구조적 함정이라 계속 남아야 한다 - 정리 대상은 "스캐폴드가 이미 막아준
   것"으로 한정한다.
   **`X-User-Type`/`X-User-Id` 헤더 기반 권한은 "헤더값을 그대로 신뢰"하는
   프로토타입 전용 모델이다** - 실제 인증(서명된 토큰, 세션) 없이 클라이언트가
   자기 역할/ID를 자유롭게 주장할 수 있다는 뜻. 생성물을 실제 서비스에 쓰려면
   이 지점을 진짜 인증으로 교체해야 한다 - 지금은 빠른 검증 목적의 의도된
   단순화이지, 놓친 보안 요구사항이 아니다.

**운영상 제약 (2026-07-28 실측):**
- **커스텀 `.claude/agents/*.md` 정의는 세션이 시작된 프로젝트 루트 기준으로만
  로드된다.** 다른 프로젝트에서 시작한 세션은 이 레포의 `backend-slice-writer`
  같은 에이전트를 못 찾는다("Agent type not found"). **`build-app`을 쓰려면
  Claude Code를 이 레포(`doc-pipeline-cc`) 폴더에서 새로 시작해야 한다.** 그
  전까지 급하면 `general-purpose`에 에이전트 파일 내용을 프롬프트로 인라인해서
  우회할 수 있지만(실측: 정상 동작), 정식 경로는 세션을 이 레포에서 시작하는 것.
- **`verify_backend.py`의 `_looks_like_bug()`(응답 메시지에서 `bad SQL
  grammar`/`NullPointerException` 같은 기술적 예외 흔적을 찾는 휴리스틱)는
  2026-07-30 이후 주 방어선이 아니라 이중 안전망이다.** 원래는
  `GlobalExceptionHandler`류가 미처리 예외까지 400/domain-rejection처럼
  응답하는 설계라 상태코드만으론 "도메인 규칙 거부"와 "진짜 버그"를 못 갈라서
  만든 것이었는데(실측: `refunds`/`stock` 조각의 SQL 바인딩 버그를 이걸로
  잡음), 그 후 계약을 "미처리 예외=500+일반메시지, 도메인 거부=explicit
  4xx"로 바꿔서(codex 리뷰 반영) 이제 상태코드만으로도 원리적으로 구분된다.
  이 휴리스틱은 지우지 않고 남겨뒀다 - 스택별 서브에이전트가 실수로 예외를
  삼켜 4xx로 감싸버리는 경우까지 잡아주는 안전망 역할은 여전히 유효해서다.

**환경 노트 (이 개발 머신 한정, 다른 머신에선 안 나타날 수 있음):**
- Windows에서 5432/5433/5173~5180대 포트가 WinNAT 예약범위로 막혀있을 수
  있다 - `db/docker-compose.yml`은 55432, 프론트 vite는 3000/8081처럼
  대체 포트를 쓴다.
- postgres 연동 스크립트(`verify_backend.py` 등)는 `sys.executable`로
  파이썬 인터프리터를 고정한다 - PATH에 python이 여러 개 걸려있으면 다른
  인터프리터가 골라져 `ModuleNotFoundError: psycopg`가 날 수 있다.

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

## 진행 로그

날짜별 상세 진행 기록은 `docs/log.md`에 있다(2026-07-30, 외부 리뷰 반영 -
누적 append-only 로그를 매 세션 통째로 로드하면 컨텍스트 비용이 계속
올라져서 분리했다). 로그에서 반복 참조되는 교훈은 이미 각 스킬의
`references/gotchas.md`나 이 파일 본문으로 승격돼 있으니, 새 세션이 매번
로그를 읽을 필요는 없다 - 로그는 "언제 무엇을 왜 했는가"의 순수 기록용.
