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
  찾는다). path parameter는 `${BASE}/books/${id}`.
- 요청 body·응답 필드는 API 명세 필드명 그대로.
- 모든 fetch 응답 status 확인, 실패 시 body 메시지 표시(detail/message/error
  순서로 확인 - 백엔드 스택마다 키가 다르다).
- rules에 역할 제한이 있고 로그인 UI가 화면설계서에 없으면 운영자 백오피스로
  간주, 모든 요청에 X-User-Type: ADMIN 헤더.
- 네트워크 에러도 잡아서 "백엔드에 연결할 수 없습니다" 안내.
- 목록 조회는 첫 렌더 useEffect로 한 번, 생성/수정/삭제 후 재호출. **단 필수
  쿼리 파라미터(sellerId 등)가 비어있으면 첫 렌더에서 자동 호출하지 않는다** -
  서버 400이 그대로 노출된다. 필수값 입력 후 버튼으로만 호출하거나 값이
  채워졌을 때만 자동 호출.
- CSS는 src/index.css 하나에 최소한으로. 외부 이미지 금지, 폰트는 토큰이
  지정한 것만(웹폰트면 index.html <link> 또는 css @import).
- 코드는 그대로 빌드·실행 가능해야 한다.

[반드시 먼저 Read] 없음(이 스킬 자체가 전체 지시)
```

## 검증

`python scripts/verify_frontend.py --api-spec generated/docs/api_spec.json`.
실패하면 로그를 실어 재디스패치(3회 상한).
