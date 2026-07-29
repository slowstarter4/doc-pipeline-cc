---
name: gen-docs
description: 기획문서(.md)를 요구사항정의서 → 화면설계서/데이터모델(ERD) → API 명세 → OpenAPI/DDL로 단계적으로 만든다. build-app 오케스트레이터가 문서 생성 단계에서 호출. "기획문서로 요구사항 만들어줘", "ERD/API 명세 생성" 같은 요청에도 단독 사용 가능.
---

# 문서 생성 (기획문서 → 요구사항 → 화면설계/ERD → API 명세)

이 스킬을 따르는 세션(오케스트레이터) 자신이 각 문서를 직접 `Write`한다.
서브에이전트를 띄우지 않는다 - 단계가 순차적이고 문맥 연속성이 더 중요하다.

## 반드시 지킬 규칙: 원본 기획문서를 매 단계 다시 본다

**`doc-pipeline`(구버전)에서 실제로 겪은 버그: `requirements.md`를 쓸 때 원본의
상태전이표·권한매트릭스·화면별 입력 항목을 "N절 참고"처럼 요약해버렸는데, 뒤
단계(ERD·API 명세)는 그 요약본만 보고 원본을 다시 안 봐서 그 정보가 통째로
사라졌다.** 실측: 커머스 기획문서 테스트에서 "배송지 입력" 요구사항과 권한
조건(C1~C29)이 원본엔 다 있었는데 최종 API 명세에서 빠졌다.

그래서 이 스킬은 각 단계마다 **원본 기획문서 파일을 다시 Read한다** - 직전
단계 산출물만 보고 쓰지 않는다. 아래 단계별 지시에 이미 반영돼 있다.

## 산출물 위치

```
generated/docs/
├── requirements.md
├── screen_design.md
├── data_model.json
├── api_spec.json
├── openapi.json         (scripts/openapi_spec.py로 결정적 생성)
└── schema.sql           (scripts/schema_ddl.py로 결정적 생성)
```

## 단계

### 1. requirements.md 작성

원본 기획문서를 처음부터 끝까지 Read한다. 번호가 매겨진 기능 요구사항
목록(FR-001, FR-002, ...)으로 정리한다.

**표·목록으로 된 상세 스펙(상태 전이표, 권한 매트릭스, 조건ID 정의, 화면별
입력 항목)은 "N절 참고"식으로 요약하지 말고 그 값 자체를 요구사항 항목 안에
옮겨 적는다.** 예:
- "RS-001 규칙에 따라 상태를 산출한다"가 아니라 그 규칙이 정의하는 실제
  상태값·조건까지 적는다.
- "C1~C29 조건에 따라 접근을 제어한다"가 아니라 각 조건ID의 실제 뜻(예:
  "C5: seller_id가 인증된 판매자 본인이고 주문에 해당 판매자 상품이 있어야
  한다")까지 옮긴다.
- 화면정의에 "배송지 입력" 같은 필드가 있으면 관련 FR 항목에 그 필드명까지
  명시한다.

기획에 없는 기능은 지어내지 않는다.

**분량이 커질 수 있다.** 한 번에 다 쓰려다 응답이 잘리면(문장이 중간에서
끊기면) 섹션을 나눠 여러 번의 Write/Edit로 이어 쓴다 - 절대 요약해서 줄이지
않는다. 원본 기획문서가 여러 장(§)으로 나뉘어 있으면, requirements.md도 같은
장 구조로 나눠서 장별로 쓰는 것을 권장한다(한 번에 몰아쓰다 잘리는 것 방지).

### 2. screen_design.md 작성 (markdown, 사람이 읽는 문서)

`requirements.md`를 근거로 삼되, **원본 기획문서의 화면 정의 section도 다시
Read해서** 화면별 입력 항목·표시 데이터·액션을 빠짐없이 옮긴다. 화면 단위로
나눠 정리한다. 요구사항에 없는 화면·기능을 추가하지 않는다.

### 3. data_model.json 작성 (ERD, JSON)

`requirements.md`(+ 필요하면 원본 기획문서의 데이터모델/도메인개념 section도
다시 확인)를 근거로 엔티티·필드를 설계한다. 스키마:

```json
{
  "entities": [
    {
      "name": "엔티티명",
      "fields": [
        {"name": "필드명", "type": "string|number|boolean|date", "required": true}
      ]
    }
  ]
}
```

- `entity.name`/`field.name`은 반드시 영문 camelCase (예: title, dueDate,
  memberId). 원본이 한글이어도 한글 항목명을 필드명으로 쓰지 않는다 - 이 ERD가
  API 명세로, API 명세가 백엔드·프론트 코드로 그대로 이어지므로 실행마다
  한글/영문이 갈리면 요청이 전부 거부된다.
- 요구사항에 나온 데이터만 포함한다.
- **screen_design.md가 언급한 입력 항목(예: 배송지·주소)이 이 ERD에 필드로
  없으면 반드시 추가한다** - 화면이 요구하는데 저장할 곳이 없으면 그 요구사항은
  구현될 수 없다.

### 4. api_spec.json 작성 (계약, JSON)

`requirements.md` + `screen_design.md` + `data_model.json` 셋 다 근거로 삼는다
(fan-in). 스키마:

```json
{
  "endpoints": [
    {
      "method": "GET|POST|PUT|DELETE",
      "path": "/resource",
      "summary": "이 엔드포인트가 하는 일",
      "request": {"필드명": "타입"},
      "response": {"필드명": "타입"},
      "rules": ["이 엔드포인트가 지켜야 할 업무 규칙", "..."]
    }
  ]
}
```

- request/response 필드명은 ERD의 영문 필드명 그대로. 한글로 옮기지 않는다.
- `rules`는 필드·타입으로 표현 안 되는 제약(거부 조건, 자동 계산·기록되는 값,
  상태 전이 제한, **역할 기반 접근 제어**)을 적는 자리 - 코드 생성 단계는 이
  명세만 보고 원본 기획문서를 안 보므로, 여기 안 적히면 구현에 반영 안 된다.
  **원본 기획문서의 권한 매트릭스(5.1/5.2절 등)를 다시 확인해서, 해당
  엔드포인트에 관련된 역할 제한(예: "운영자만 조회 가능", "판매자는 본인
  소유만")을 rules에 명시적으로 옮긴다** - "C1~C29 조건 참고"식으로 남기지
  않는다.
- 목록 조회 GET은 response를 배열로 감싼다(예: `{"orders": [...]}`). 단일
  리소스 반환(생성/단건조회/수정)만 필드를 바로 나열한다.
- path parameter(`{id}` 등)로 이미 받는 필드는 request body에 중복으로 넣지
  않는다.
- 화면이 필요로 하는 데이터는 반드시 ERD에 실제 존재하는 필드여야 한다. ERD에
  없는 필드를 지어내지 않는다.

**엔드포인트가 많으면(20개+) 도메인별로 나눠 여러 Write/Edit로 이어 쓴다** -
한 번에 다 쓰려다 잘리지 않게 한다.

### 5. openapi.json / schema.sql 생성 (결정적, LLM 미사용)

Bash로 스크립트를 호출한다 - 직접 작성하지 않는다(같은 입력엔 항상 같은
출력이어야 schemathesis 같은 계약검사 도구가 신뢰할 수 있다):

```bash
python scripts/openapi_spec.py generated/docs/api_spec.json \
  --data-model generated/docs/data_model.json \
  -o generated/docs/openapi.json

python scripts/schema_ddl.py generated/docs/data_model.json \
  --dialect sqlite \
  -o generated/docs/schema.sql
```

`--dialect`는 `build-app`이 사용자에게 물어본 DB_TARGET(`sqlite`|`postgres`)을
그대로 전달한다.

### 5.5. happyPath fixture 작성 (`api_spec.json`에 Edit로 추가)

**왜 필요한가**: `verify-backend`의 스모크 테스트는 더미 데이터(문자열
"테스트", 숫자 1 등)로 생성 엔드포인트를 찔러본다. 더미 값은 재고·쿠폰 같은
선행 데이터를 가리키는 FK가 실제로 존재할 리 없어서, 정상적인 구현이라도
거부(4xx)하는 게 맞다 - 그래서 스모크는 그 거부를 "도메인 규칙일 수 있음"으로
봐주고 실패로 안 친다. 문제는 그러면 **"정상적인 값을 넣었을 때 진짜로
성공하는가"가 아예 검증이 안 된다**는 것 - 재고 시딩 자체를 깜빡한 버그도
이 구멍으로 통과해버린다(실측: 2026-07-29 fastapi/sqlite, typescript/postgres
세션 둘 다 브라우저 수동 확인에서 Stock 미시딩으로 주문이 막힌 걸 뒤늦게
발견). happyPath fixture는 "이 값을 이 순서로 넣으면 실제로 통과해야 한다"는
ground truth를 명세에 박아서, `verify-backend`가 더미 대신 이걸로 진짜 성공
케이스를 확인하게 한다.

**대상 고르기 - 여기가 제일 중요하다**: fixture는 단발 호출이 아니라 **순차
시나리오(steps)** 다. "이 도메인이 실제로 하는 일"의 한 바퀴를 고른다:

> 선행 데이터를 만들고 → **상태를 바꾸는 핵심 엔드포인트**를 때리고 →
> 그 결과를 조회로 확인하고 → **규칙에 걸리는 요청이 제대로 거부되는지**까지 본다.

**"명세의 첫 번째 POST"를 고르지 마라.** 실측(2026-07-29 library 도메인)에서
그렇게 골랐다가 가장 단순한 등록 엔드포인트(`POST /books`, FK 없음)만 검증됐고,
정작 이 도메인의 전부인 대출/연체/반납/제재 로직은 8개 엔드포인트 중 4개가
한 번도 안 불린 채 초록불이 떴다. 판단 기준은 **명세 순서가 아니라 업무
중요도**다 - `requirements.md`의 업무 규칙(제약·상태 전이)이 가장 많이 걸린
엔드포인트가 시나리오의 중심이어야 한다.

**반드시 넣을 것**:
- **거부 케이스 최소 1개.** 통과 케이스만 보면 규칙이 아예 구현 안 돼 있어도
  전부 초록불이다. 상태 전이 제약이나 권한 제한이 있으면 그게 409/403으로
  막히는 스텝을 넣는다(`expect: 409`).
- **계산 필드 확인.** 저장하지 않고 조회 시점에 계산하는 값(연체 여부, 합계
  금액 등)이 있으면 그걸 조회해서 `expectAnyItem`으로 값까지 확인한다 -
  200만 보면 필드가 통째로 비어 있어도 통과한다.

**작성 순서**:
1. `generated/docs/schema.sql`을 Read한다. 시나리오가 건드릴 엔드포인트들의
   request body 필드 중 다른 엔티티를 가리키는 FK가 있는지 확인한다.
2. FK 중 **API로 만들 수 있는 것은 스텝으로 만들고**(예: 도서/회원 등록),
   API가 없는 선행 데이터만 `seed`로 DB에 직접 넣는다(예: 커머스의 `Stock` -
   재고 등록 API가 없으면 seed로).
3. 앞 스텝의 응답에서 id를 `capture`하고 뒤 스텝에서 `${변수}`로 참조한다.
4. **테이블·컬럼명은 반드시 `schema.sql`에 나온 그대로, 큰따옴표 없이 적는다**
   (postgres는 unquoted면 대소문자 무관하게 항상 소문자로 접어서 스키마와
   저절로 맞는다 - `gen-backend-*/references/gotchas.md`의 quoted identifier
   함정과 같은 이유).
5. `api_spec.json` 최상위에 Edit로 추가한다:

```json
{
  "endpoints": [ ... ],
  "happyPath": {
    "seed": [],
    "steps": [
      {"name": "도서 등록", "method": "POST", "path": "/books",
       "body": {"title": "verify-book-001", "publisher": "verify-pub",
                "publishDate": "2020-01-01", "genre": "소설"},
       "expect": 201, "capture": {"bookId": "id", "__persist": "id"}},

      {"name": "회원 등록", "method": "POST", "path": "/members",
       "body": {"name": "verify-member-001", "phone": "010-0000-0000"},
       "expect": 201, "capture": {"memberId": "id"}},

      {"name": "대출(반납예정일 과거 → 연체 유발)", "method": "POST", "path": "/loans",
       "body": {"memberId": "${memberId}", "bookId": "${bookId}", "dueDate": "2020-01-01"},
       "expect": 201, "capture": {"loanId": "id"}},

      {"name": "연체 계산 확인", "method": "GET", "path": "/loans",
       "expect": 200, "expectAnyItem": {"overdue": true}},

      {"name": "반납 처리", "method": "POST", "path": "/loans/${loanId}/return",
       "expect": [200, 201]},

      {"name": "연체 반납 → 제재 부여 확인(재대출 409 거부)", "method": "POST", "path": "/loans",
       "body": {"memberId": "${memberId}", "bookId": "${bookId}", "dueDate": "2027-01-01"},
       "expect": 409},

      {"name": "이미 반납한 건 재반납 거부", "method": "POST", "path": "/loans/${loanId}/return",
       "expect": 409}
    ]
  }
}
```

**스텝 필드**
- `name` — 실패 로그에 그대로 찍힌다. 무엇을 확인하려던 스텝인지 적는다.
- `method`/`path`/`body` — `${변수}`로 앞 스텝의 capture 값을 꽂는다.
  문자열 전체가 `"${bookId}"`면 원래 타입(숫자)이 유지된다.
- `expect` — 기대 상태코드. 정수 하나 또는 배열. **4xx를 적으면 "거부되어야
  정상"인 검증이 된다.**
- `capture` — `{"변수명": "응답필드"}`. 특수 변수 `__persist`를 한 번 쓰면
  그 스텝이 만든 데이터로 **서버 재기동 후 영속성 검사**를 한다(생성 스텝
  하나에만 붙이면 된다).
- `expectAnyItem` — 목록 응답(배열이든 `{"loans":[...]}` wrapper든)에 이
  필드값들을 가진 항목이 최소 1개 있어야 한다.
- `headers` — **선택**. 기본값은 `{"X-User-Type": "ADMIN"}`이고, rules가 특정
  역할만 허용하면(예: "호출자는 BUYER 본인이어야 한다") 그 스텝에만 덮어쓴다.
  `X-User-Id`를 body의 buyerId 등과 같은 값으로 맞춰야 "본인 소유만" 규칙도
  통과한다.
- `Idempotency-Key`는 넣지 않는다 - `verify-backend`가 매 호출마다 새 UUID로
  자동으로 붙인다(fixture에 고정값을 넣으면 재검증 때 중복키로 막힌다).

**기타**
- id 값은 `verify-` 접두사를 붙여 실사용 데이터와 안 섞이게 한다.
- `seed`는 API로 만들 수 없는 선행 데이터만. 없으면 `[]`.

### 6. 자기 검토 (원본 대조)

api_spec.json을 다 쓴 뒤, **원본 기획문서를 한 번 더 훑어서** 다음을 스스로
점검한다:
- 화면정의에 있는 입력 항목이 ERD·API 요청 스키마에 다 반영됐는가
- 권한 매트릭스의 역할 제한이 관련 엔드포인트의 rules에 다 반영됐는가
- 상태 전이표의 상태값들이 ERD의 status 필드 설명이나 rules에 반영됐는가
- `happyPath.seed`의 테이블·컬럼명이 `schema.sql`과 정확히 일치하는가
- **happyPath.steps가 이 도메인의 핵심 업무 규칙을 실제로 통과하는가** - 규칙이
  가장 많이 걸린 엔드포인트(상태 전이·제약 검사)가 스텝에 들어 있는지, 거부
  케이스(`expect: 4xx`)가 최소 1개 있는지, 조회 시점 계산 필드가 있으면
  `expectAnyItem`으로 값까지 확인하는지 본다. 등록 엔드포인트만 나열돼 있으면
  다시 짠다 - 그건 아무것도 검증하지 못한다.
- `${변수}`가 앞선 스텝의 `capture` 이름과 정확히 일치하는가, `__persist`를
  생성 스텝 하나에 붙였는가(오타 하나로 fixture 전체가 실패한다)

빠진 게 있으면 그 자리에서 고친다(재생성 아니라 Edit로 보완). 발견한 이슈가
있고 판단이 애매하면 AskUserQuestion으로 사람에게 진행 여부를 확인한다
(`doc-pipeline`의 `review_gate`와 같은 역할 - 여기선 대화 턴이 곧 그 멈춤이다).
