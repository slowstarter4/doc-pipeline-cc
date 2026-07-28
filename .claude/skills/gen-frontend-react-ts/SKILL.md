---
name: gen-frontend-react-ts
description: React + Vite + TypeScript 프론트엔드를 생성한다. build-app 오케스트레이터가 FRONTEND_TARGET=react-ts일 때 호출. 서브에이전트 1개에게 전체를 맡긴다.
---

# React + TypeScript 프론트엔드 생성 (Vite)

`gen-frontend-react`와 동일한 규칙 + TypeScript 타입. 출력 `generated/frontend/`.

## 디스패치

`gen-frontend-react/SKILL.md`의 디스패치 프롬프트를 그대로 쓰되 다음을 더한다:

```
[추가 지시]
파일 확장자는 .tsx/.ts: src/main.tsx, src/App.tsx. package.json
devDependencies에 typescript, @types/react, @types/react-dom도 추가한다.
tsconfig.json을 strict: true로 만든다.
API 응답 타입은 interface로 선언하고 ERD/api_spec의 필드명·타입을 정확히
반영한다(number/string/boolean/date→string). any로 도피하지 않는다.
tsc --noEmit 기준으로 타입 에러가 없어야 한다(strict라 fetch 응답은 반드시
타입 단언하거나 인터페이스로 캐스팅한다: `await res.json() as Order[]`).
```

## 검증

`python scripts/verify_frontend.py --api-spec generated/docs/api_spec.json`.
추가로 `cd generated/frontend && npx tsc --noEmit`로 타입 에러 확인(사람이
`npm install` 먼저 돌려야 함 - 오케스트레이터는 자동 기동 안 함).
실패하면 로그를 실어 재디스패치(3회 상한).
