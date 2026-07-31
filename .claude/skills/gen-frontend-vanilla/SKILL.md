---
name: gen-frontend-vanilla
description: 빌드 도구 없는 단일 index.html 프론트엔드를 생성한다. build-app 오케스트레이터가 FRONTEND_TARGET=vanilla일 때 호출. 서브에이전트 1개에게 전체를 맡긴다(화면 간 공유 상태·네비게이션이 있어 도메인 조각화보다 한 파일로 일관되게 쓰는 게 맞다).
---

# Vanilla 프론트엔드 생성 (단일 index.html)

출력 `generated/frontend/index.html` 하나. npm/번들러/프레임워크/CDN 스크립트
금지 - 브라우저로 파일을 바로 열면 동작해야 한다.

## 디스패치

서브에이전트 1개(`general-purpose`, 이 세션에서 커스텀 에이전트를 못 쓸 때의
대안 - `doc-pipeline-cc`에서 세션을 시작했다면 전용 에이전트도 가능)에게
아래 내용을 프롬프트로 준다:

```
[API 명세 - 계약]
generated/docs/api_spec.json

[화면설계서 - 레이아웃 참고용, 계약 아님]
generated/docs/screen_design.md

[백엔드 포트]
build-app이 선택한 BACKEND_TARGET에 맞는 포트 (fastapi=8000, spring=8080,
express=5001, typescript=5002)

[디자인 토큰]
design/design_system.md (또는 DESIGN_TARGET이 지정한 design/presets/<이름>.md)

[출력 계약]
파일 하나: generated/frontend/index.html. HTML/CSS/JS 전부 인라인.
- 백엔드 주소는 파일 맨 위 상수: const BASE = "http://localhost:포트번호";
- URL은 항상 백틱 템플릿 리터럴 `${BASE}/경로` 형태로 쓴다(계약 검사가 이 리터럴을
  정규식으로 찾아 api_spec과 대조하므로, 경로 조각을 변수로 조립하지 않는다).
  path parameter는 `${BASE}/books/${id}`.
- 요청 body·응답 필드는 API 명세의 필드명 그대로. 화면설계서에 있어도 대응
  엔드포인트가 없으면 구현하지 않는다.
- 모든 fetch 응답의 status를 확인, 실패 시 body의 메시지를 화면에 표시한다.
  에러 메시지 키는 detail/message/error 순서로 확인(백엔드 스택마다 다름).
- rules에 '운영자/관리자만' 같은 역할 제한이 있는데 화면설계서에 로그인 UI가
  없으면 운영자 백오피스로 간주하고 모든 요청에 X-User-Type: ADMIN 헤더를 보낸다.
- 백엔드 연결 실패(네트워크 에러)도 잡아서 안내를 띄운다.
- 목록 조회는 첫 렌더 시 한 번 호출하고 생성/수정/삭제 후 다시 호출한다. 단
  그 엔드포인트가 필수 쿼리 파라미터를 요구하면(예: sellerId) 값이 비어있는
  동안은 자동 호출하지 않는다 - 서버가 400을 돌려주고 그게 그대로 노출된다.
- 디자인 토큰(색·타이포·간격)을 CSS에 반영한다. 레이아웃은 화면설계서가 정한다.
- 코드는 그대로 실행 가능해야 한다.

- `data-testid` 부여 규칙(아래 섹션) 그대로 적용한다 - 나중에 Playwright e2e가
  화면 요소를 찾는 유일한 방법이라 임의로 바꾸면 안 된다.

[반드시 먼저 Read] 없음(이 스킬 자체가 전체 지시)
```

## data-testid 컨벤션 (Playwright e2e 선행조건)

api_spec.json의 method+path만으로 결정적으로 계산되는 slug를 쓴다 - 화면 구조를
몰라도 fixture(happyPath steps)와 동일한 규칙으로 셀렉터를 재계산할 수 있어야
Playwright e2e가 LLM 없이 자동으로 셀렉터를 만들 수 있다.

**slug 계산**: method를 소문자로, path 앞뒤 `/` 제거, 남은 `/`는 `-`로, `{id}`
같은 path parameter는 중괄호만 벗기고 소문자로(`{orderId}` → `orderid`).
예: `PUT /widgets/{id}` → `put-widgets-id`, `GET /orders/{orderId}/items` →
`get-orders-orderid-items`.

- 엔드포인트를 호출하는 폼: `data-testid="{slug}-form"`
- 폼의 각 입력 필드(request의 필드명 그대로, camelCase 유지): `data-testid="{slug}-field-{필드명}"`
- 제출 버튼: `data-testid="{slug}-submit"`
- 에러 메시지 영역: `data-testid="{slug}-error"`
- 목록(GET, 배열/wrapper 응답) 컨테이너: `data-testid="{slug}-list"`
- 목록의 각 항목 루트(여러 개 반복돼도 됨, 유일할 필요 없음): `data-testid="{slug}-item"`
- 항목 안에서 값을 확인해야 하는 필드: testid 대신 `data-field="{필드명}"` 속성
  (item이 여러 개라 testid를 고유하게 못 주므로 속성으로 스코프 좁힘)

한 화면이 API 명세에 없는 버튼·장식 요소를 더 갖는 건 상관없다 - 이 규칙은
API 계약과 직접 연결된 요소에만 적용한다.

## 검증

`python scripts/verify_frontend.py --api-spec generated/docs/api_spec.json`
(LLM 미사용, 정적 분석). 실패하면 로그를 실어 재디스패치(3회 상한).
