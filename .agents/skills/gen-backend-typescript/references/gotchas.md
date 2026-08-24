# TypeScript(Express) 백엔드 생성 함정 모음

`gen-backend-express/references/gotchas.md`의 모든 규칙이 그대로 적용된다(DB
접근·검증·응답·역할 헤더 컨벤션 전부 동일) - 이 문서는 **TypeScript 고유의
추가 함정만** 다룬다.

## node:sqlite + TypeScript 타입 캐스팅

- sqlite일 때 `db.prepare(sql).all()`의 반환 타입은
  `Record<string, SQLOutputValue>[]`라 도메인 인터페이스(예: `Order[]`)와
  구조가 안 겹친다. `as Order[]`로 직접 캐스팅하면 **TS2352(Conversion ...
  may be a mistake) 컴파일 에러**가 난다. 반드시 `as unknown as Order[]`처럼
  `unknown`을 거쳐 이중 캐스팅한다.
- postgres(`pg`)를 쓸 때는 `result.rows`가 이미 `any[]`라 이중 캐스팅이 필요
  없다 - `as Order[]`로 바로 캐스팅해도 TS2352가 안 난다. **sqlite일 때만
  이중 캐스팅 규칙을 적용한다.**

## 타입 선언

- 요청/응답 DTO는 `interface`로 선언한다. ERD 필드명·타입을 정확히 반영한다
  (number 필드는 `number`, string은 `string`, boolean은 `boolean`, date는
  응답에서 `string`으로 나가므로 `string`).
- `tsconfig.json`은 오케스트레이터가 `strict: true`로 이미 만들어뒀다 -
  타입 에러 없이 컴파일돼야 한다(`any`로 도피하지 않는다. 불가피하면
  `unknown` 경유 캐스팅으로 제한적으로만).

## 빌드

- 조각은 `.ts` 파일만 쓴다(컴파일은 오케스트레이터/verify-backend가
  `npm run build`로 돌린다 - `tsc && node dist/server.js`).
- import는 ESM 스타일이 아니라 `tsconfig.json`의 `module: "commonjs"`에 맞춰
  기본 export/import 문법을 쓴다(오케스트레이터의 스캐폴드가 이미 그 스타일).
