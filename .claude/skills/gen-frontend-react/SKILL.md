---
name: gen-frontend-react
description: React + Vite 프론트엔드를 생성한다. build-app 오케스트레이터가 FRONTEND_TARGET=react일 때 호출. 서브에이전트 1개에게 전체를 맡긴다.
---

# React 프론트엔드 생성 (Vite)

출력 `generated/frontend/`. vanilla와 다른 점은 빌드 단계가 생긴다는 것뿐 -
`npm install && npm run dev`는 사람이 돌린다(오케스트레이터는 자동 기동 안 함).

## 디스패치

서브에이전트 1개에게 아래를 프롬프트로 준다:

```
[API 명세 - 계약]
generated/docs/api_spec.json

[화면설계서 - 레이아웃 참고용]
generated/docs/screen_design.md

[백엔드 포트]
build-app이 선택한 BACKEND_TARGET에 맞는 포트

[디자인 토큰]
design/design_system.md (또는 DESIGN_TARGET 프리셋)

[출력 계약]
Vite + React 최소 구성: package.json, vite.config.js, index.html, src/main.jsx,
src/App.jsx, src/index.css. 의존성은 react/react-dom(dependencies), vite/
@vitejs/plugin-react(devDependencies)만 - UI 라이브러리·상태관리·라우터·axios
추가 금지. package.json에 "type": "module" 명시(안 넣으면 vite.config.js의
import 구문이 안 돈다).

- 상태는 useState/useEffect만.
- 백엔드 주소: src/App.jsx 맨 위 const BASE = "http://localhost:포트번호";
- URL은 항상 백틱 템플릿 리터럴 `${BASE}/경로`(계약 검사가 이 리터럴을 정규식으로
  찾는다). path parameter는 `${BASE}/books/${id}`. **각 호출부에 전체 경로가 그
  자리에서 그대로 보여야 한다** - 공용 fetch 헬퍼(`apiFetch(path, ...)`처럼)를
  만들 때 절대 `path`를 별도 매개변수로 받아 헬퍼 내부에서 `` `${BASE}${path}` ``로
  합치지 않는다(실측: 이렇게 짜면 각 호출부는 `apiFetch("/stocks", ...)`처럼
  일반 문자열만 인자로 넘기게 되는데, 계약 검사기는 `${BASE}`가 붙은 백틱
  리터럴만 호출로 인식하므로 모든 호출을 놓쳐 "명세 경로를 하나도 안 부름"으로
  실패한다). 공용 헬퍼를 쓰고 싶으면 호출부에서 `` apiFetch(`${BASE}/stocks`, ...) ``
  처럼 완성된 백틱 리터럴을 그대로 넘긴다.
- 요청 body·응답 필드는 API 명세 필드명 그대로.
- 모든 fetch 응답 status 확인, 실패 시 body 메시지 표시(detail/message/error
  순서로 확인 - 백엔드 스택마다 키가 다르다).
- rules에 역할 제한이 있고 로그인 UI가 화면설계서에 없으면 운영자 백오피스로
  간주, 모든 요청에 X-User-Type: ADMIN 헤더.
- 네트워크 에러도 잡아서 "백엔드에 연결할 수 없습니다" 안내.
- 액션(취소/거부 등)의 결과를 그 액션 버튼과 같은 상태 조건(예: `status === "확정"`일 때만 버튼+결과 배너를 같이 렌더)으로 묶지 않는다 - 액션이 성공해서 목록을 재조회하면 그 항목의 status가 바로 바뀌어 조건이 깨지고, 응답으로 받은 결과(예: 환불금액)가 화면에 뜨자마자 사라진다(실측: 기차예약 도메인, 취소 버튼과 환불금액 배너를 `status === "확정"` 블록 안에 같이 뒀다가 취소 직후 status가 "취소"로 바뀌면서 방금 응답으로 받은 환불금액이 렌더링될 새도 없이 사라짐). 결과 배너는 그 액션의 결과 state(예: `cancelResult[id]`)만으로 독립 조건을 건다.
- 목록 조회는 첫 렌더 useEffect로 한 번, 생성/수정/삭제 후 재호출. **단 필수
  쿼리 파라미터(sellerId 등)가 비어있으면 첫 렌더에서 자동 호출하지 않는다** -
  서버 400이 그대로 노출된다. 필수값 입력 후 버튼으로만 호출하거나 값이
  채워졌을 때만 자동 호출.
- CSS는 src/index.css 하나에 최소한으로. 외부 이미지 금지, 폰트는 토큰이
  지정한 것만(웹폰트면 index.html <link> 또는 css @import).
- 코드는 그대로 빌드·실행 가능해야 한다.
- `data-testid` 부여 규칙(아래 섹션) 그대로 적용한다 - 나중에 Playwright e2e가
  화면 요소를 찾는 유일한 방법이라 임의로 바꾸면 안 된다.

[반드시 먼저 Read]
.claude/skills/references/objections-protocol.md

[이의제기]
계약(api_spec)에 정보가 없거나 모호해서 임의로 판단한 게 있으면
generated/objections/frontend.json에 기록한다 (위 objections-protocol.md의
형식/기준 그대로, from은 "frontend", slice도 "frontend"). 없으면 파일을 안
만들어도 된다.
```

## data-testid 컨벤션 (Playwright e2e 선행조건)

api_spec.json의 method+path만으로 결정적으로 계산되는 slug를 쓴다 - 화면 구조를
몰라도 fixture(happyPath steps)와 동일한 규칙으로 셀렉터를 재계산할 수 있어야
Playwright e2e가 LLM 없이 자동으로 셀렉터를 만들 수 있다.

**slug 계산**: method를 소문자로, path 앞뒤 `/` 제거, 남은 `/`는 `-`로, `{id}`
같은 path parameter는 중괄호만 벗기고 소문자로(`{orderId}` → `orderid`).
예: `PUT /widgets/{id}` → `put-widgets-id`, `GET /orders/{orderId}/items` →
`get-orders-orderid-items`.

**path parameter 없는 엔드포인트** (컬렉션 단위 - 목록 조회, 생성):
- 호출하는 폼: `data-testid="{slug}-form"`
- 폼의 각 입력 필드(request의 필드명 그대로, camelCase 유지): `data-testid="{slug}-field-{필드명}"`
- 제출 버튼: `data-testid="{slug}-submit"`
- 에러 메시지 영역: `data-testid="{slug}-error"`
- 목록(GET, 배열/wrapper 응답) 컨테이너: `data-testid="{slug}-list"`
- 목록의 각 항목 루트(여러 개 반복돼도 됨, 유일할 필요 없음): `data-testid="{slug}-item"`
- 항목 안에서 값을 확인해야 하는 필드: testid 대신 `data-field="{필드명}"` 속성
  (item이 여러 개라 testid를 고유하게 못 주므로 속성으로 스코프 좁힘). **id
  필드는 항상 `data-field="id"`로 노출한다** - e2e가 "방금 만든 게 몇 번
  아이템인지" 알 방법이 이것뿐이다.

**path parameter 있는 엔드포인트** (`{id}` 등 - 개별 수정/삭제): 전용 폼을 따로
안 만들고, **그 리소스의 목록 아이템(위 `{slug}-item`) 안에** 인라인으로 둔다 -
사용자가 실제로 "이 항목을 수정한다"고 클릭하는 자리이지 별도 화면이 아니기
때문이다. `{slug}`는 이 엔드포인트 자신의 method+path로 계산한다(목록 엔드포인트
slug와 다름 - 예: 목록은 `get-widgets-item`, 수정 액션은 `put-widgets-id-*`):
- 그 아이템 안의 입력 필드: `data-testid="{slug}-field-{필드명}"`
- 그 아이템 안의 제출(또는 삭제) 버튼: `data-testid="{slug}-submit"`
- 에러 메시지: `data-testid="{slug}-error"` (아이템 안 또는 전역, 아이템 안 우선)

**인라인할 목록 자체가 없으면**(예: 이 화면의 역할은 전체 목록을 볼 권한이
없어서 - "구매자는 본인 회원ID로 적립금을 조회"처럼 대상을 목록에서 고르는 게
아니라 직접 입력받는 경우) - **독립 id입력 폼**으로 대신한다: `data-testid="{slug}-form"`
안에 id를 직접 입력하는 필드 `data-testid="{slug}-field-id"`를 둔다(나머지
필드·제출·에러는 위와 동일한 규칙). **같은 화면에서 연관된 여러 path parameter
엔드포인트가 하나의 id 입력을 공유해도 된다**(예: "회원ID로 조회" 폼에 입력한
id를 "그 회원 적립금 사용" 폼도 그대로 쓰는 식) - 이 경우 공유되는 폼에만
`{slug}-field-id`를 두면 되고, e2e는 화면에 보이는 `*-field-id`를 아무거나
찾아 채운다.

존재하지 않는 id를 대상으로 한 거부 케이스(예: `PUT /widgets/999999` → 404)는
UI에 그 id로 갈 항목 자체가 없으므로 **e2e가 자동으로 검증을 건너뛴다** - 정상
동작이다, 별도 조치 불필요.

**화면이 여러 개로 나뉘어 있으면**(역할 토글, 사이드 nav 등 - 한 번에 모든
엔드포인트가 DOM에 안 잡히는 구조): 그 전환 버튼에도 testid를 준다.
- 역할 토글 버튼: `data-testid="role-{역할명소문자}"` (예: `role-buyer`, `role-admin`)
- 화면 전환(사이드 nav 등) 버튼: `data-testid="nav-{화면키}"`. 화면키는 자유롭게
  정하되, **그 화면이 다루는 엔드포인트 경로의 세그먼트 중 하나와 반드시
  일치시킨다**(예: `PUT /shipments/{id}`를 다루는 화면이면 화면키에 `shipments`가
  있어야 한다) - e2e가 경로 세그먼트를 그대로 nav testid 후보로 써서 클릭해보기
  때문에, 화면키가 API 경로와 무관한 이름(예: "배송화면"의 화면키를 `delivery`로)이면
  e2e가 그 화면을 못 찾는다.

한 화면이 API 명세에 없는 버튼·장식 요소를 더 갖는 건 상관없다 - 이 규칙은
API 계약과 직접 연결된 요소에만 적용한다.

## 검증

`python scripts/verify_frontend.py --api-spec generated/docs/api_spec.json`.
실패하면 로그를 실어 재디스패치(3회 상한).
