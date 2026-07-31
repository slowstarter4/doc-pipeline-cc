---
name: verify-frontend
description: 생성된 프론트엔드가 API 명세대로 호출하는지 정적 분석으로 검사한다(LLM 미사용, 서버 안 띄움). build-app 오케스트레이터가 gen-frontend-*로 코드를 다 쓴 뒤 호출.
---

# 프론트엔드 계약 검사

`scripts/verify_frontend.py`가 엔진이다 - 파일을 읽어 `fetch()` 호출 경로를
정규식으로 뽑고 `api_spec.json`과 대조한다. 서버를 안 띄우므로 빠르고 결정적.

## 실행

```bash
python scripts/verify_frontend.py --api-spec generated/docs/api_spec.json \
  --design-target commerce-modernist
```

`--design-target`은 `DESIGN_TARGET`을 지정했을 때만(생략하면 정본
`design/design_system.md`). 결과는 stdout에 JSON, 실패면 종료코드 1.

## 검사 3종

1. **호출 (method, 경로) ↔ api_spec (method, 경로)** (계약, passed에 반영) -
   명세에 없는 경로를 부르거나, 경로는 맞는데 method가 다르거나(`POST /orders`를
   `GET`으로 호출), 호출 자체가 하나도 없으면 실패. `fetch(url, {method})`의
   method(미지정 시 GET)와 `axios.get/post/put/patch/delete(url)`의 동사를 읽는다.
   URL이 변수를 거치는 등 그 자리에서 method를 못 정하는 호출은 실패로 안 치고
   "검증 불가"로 따로 보고한다(수동 확인 필요).
2. **응답 모양**(계약, passed에 반영) - 목록 응답을 감싸는 wrapper key(예:
   `{"orders": [...]}`)가 프론트 소스에 없으면 배열을 못 푸는 것으로 판단.
3. **디자인 토큰 색** (진단만, passed에 반영 안 됨) - 색이 화면에 없는 요소용일
   수 있어 실패로 안 친다. 안 쓰인 색이 있으면 note로만 보고.

## 실패 시

`report["logs"]`를 읽고 해당 `gen-frontend-*` 스킬로 재디스패치한다(프론트는
도메인 조각화가 없으므로 전체를 다시 씀 - 백엔드처럼 부분 재시도가 없다).
3회 실패하면 사람에게 보고하고 멈춘다.

## e2e (선택, Playwright로 실제 브라우저 조작)

`scripts/verify_frontend_e2e.py`는 정적 검사보다 한 단계 더 나간다 - 실제
브라우저로 happyPath fixture를 UI 클릭으로 재현해 통과하는지 본다. `pip install
playwright && playwright install chromium` 1회 필요. 전제조건은
`gen-frontend-*` SKILL.md의 data-testid 컨벤션을 프론트가 지켰다는 것 -
안 지켰으면 셀렉터를 못 찾아 실패로 나온다(그 자체가 컨벤션 위반 신호).

```bash
python scripts/verify_frontend_e2e.py --api-spec generated/docs/api_spec.json \
  --url http://localhost:5173   # vanilla는 정적 서버(예: python -m http.server) 필요
```

`PUT/DELETE /x/{id}`처럼 path parameter가 있는 스텝은 목록 아이템 인라인으로
찾는다 - 존재하지 않는 id로 4xx를 유도하는 스텝(예: `/widgets/999999`)은 UI에
그 항목 자체가 없어 **자동으로 건너뛴다**(실패 아님, 정상 동작). 실행 전에
프론트(와 필요하면 백엔드)가 이미 떠 있어야 한다 - 이 스크립트는 서버를
안 띄운다(`verify-backend`/사람이 먼저 기동).

## 함께 확인할 것 (스크립트가 못 잡는 것)

- CORS: 계약(api_spec)에 안 적히지만 없으면 브라우저에서 연동이 안 된다.
  `gen-backend-*`의 결정적 스캐폴드가 이미 CORS를 열어뒀는지 확인한다(각
  스택 스킬의 2단계 참고) - 프론트 쪽에서 고칠 수 있는 문제가 아니다.
- 단건 응답의 개별 필드명 불일치(`book.name` vs `book.title`)는 이 스크립트가
  못 잡는다 - 실제로 브라우저에서 열어서 확인하거나, 필요가 증명되면 검사를
  확장한다(doc-pipeline이 이 판단을 미룬 채로 남겨뒀던 지점과 동일).
