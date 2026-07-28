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

[반드시 먼저 Read] 없음(이 스킬 자체가 전체 지시)
```

## 검증

`python scripts/verify_frontend.py --api-spec generated/docs/api_spec.json`
(LLM 미사용, 정적 분석). 실패하면 로그를 실어 재디스패치(3회 상한).
