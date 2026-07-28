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

1. **호출 경로 ↔ api_spec 경로** (계약, passed에 반영) - 명세에 없는 경로를
   부르거나, 호출 자체가 하나도 없으면 실패.
2. **응답 모양**(계약, passed에 반영) - 목록 응답을 감싸는 wrapper key(예:
   `{"orders": [...]}`)가 프론트 소스에 없으면 배열을 못 푸는 것으로 판단.
3. **디자인 토큰 색** (진단만, passed에 반영 안 됨) - 색이 화면에 없는 요소용일
   수 있어 실패로 안 친다. 안 쓰인 색이 있으면 note로만 보고.

## 실패 시

`report["logs"]`를 읽고 해당 `gen-frontend-*` 스킬로 재디스패치한다(프론트는
도메인 조각화가 없으므로 전체를 다시 씀 - 백엔드처럼 부분 재시도가 없다).
3회 실패하면 사람에게 보고하고 멈춘다.

## 함께 확인할 것 (스크립트가 못 잡는 것)

- CORS: 계약(api_spec)에 안 적히지만 없으면 브라우저에서 연동이 안 된다.
  `gen-backend-*`의 결정적 스캐폴드가 이미 CORS를 열어뒀는지 확인한다(각
  스택 스킬의 2단계 참고) - 프론트 쪽에서 고칠 수 있는 문제가 아니다.
- 단건 응답의 개별 필드명 불일치(`book.name` vs `book.title`)는 이 스크립트가
  못 잡는다 - 실제로 브라우저에서 열어서 확인하거나, 필요가 증명되면 검사를
  확장한다(doc-pipeline이 이 판단을 미룬 채로 남겨뒀던 지점과 동일).
