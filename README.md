# doc-pipeline-cc

문서 기반 개발 파이프라인 - **Claude Code 네이티브 재구현판**.

사람이 쓴 기획문서(`.md`) 하나로 요구사항정의서 → 화면설계서/ERD → API 명세 →
OpenAPI/DDL 문서를 생성하고, 그 문서를 기반으로 백엔드·프론트엔드 코드를
생성·기동·검증까지 하는 멀티에이전트 파이프라인이다.

자매 레포 [`doc-pipeline`](../doc-pipeline)(LangGraph + OpenRouter API 버전)의
후속작. OpenRouter 토큰 종량제 비용 문제로, 별도 API 키 없이 Claude Code
세션(오케스트레이터)과 그 세션이 띄우는 서브에이전트만으로 전체를 돌리도록
다시 짰다. 설계 배경·아키텍처 매핑·레포 구조·운영상 제약은 전부
[`CLAUDE.md`](./CLAUDE.md)에 있다.

## 빠른 시작

```
# 1. Claude Code를 이 레포 루트에서 시작한다 (필수 - 서브에이전트 정의가 세션
#    시작 경로 기준으로만 로드됨)
cd doc-pipeline-cc

# 2. DB 기동 (postgres 쓸 경우, 사람이 직접)
cd db && docker compose up -d && cd ..

# 3-a. 완성된 기획문서가 있으면 바로:
/build-app examples/commerce_qwen_plan.md

# 3-b. 기획문서가 없으면(아이디어만 있을 때) 질의응답으로 먼저 초안을 잡는다:
/plan-intake
```

`BACKEND_TARGET`(spring/express/fastapi/typescript), `FRONTEND_TARGET`
(vanilla/react/react-ts), `DB_TARGET`(sqlite/postgres) 조합은 `build-app`
스킬 실행 중 물어본다.

## 검증 현황

- **백엔드 4종(fastapi/spring/express/typescript) × 프론트 3종
  (vanilla/react/react-ts) = 12칸 페어링 전부 실행 검증 완료**(코드 생성 →
  `verify_backend.py`/`verify_frontend.py` → 대부분 브라우저 골든패스까지
  확인). DB는 sqlite/postgres 둘 다 여러 스택에서 확인됨.
- **`plan-intake` → `build-app` 전체 파이프라인 e2e 검증**: 6질문→조립→승인→
  저장부터 문서생성·병렬 코드생성·검증까지 실사용으로 한 바퀴 확인.
- **CI**(`.github/workflows/ci.yml`): 스크립트 self-check(pytest) + 백엔드
  4종×DB 2종 = 8콤보 실제 스캐폴드 생성→기동→`verify_backend.py` e2e 매트릭스
  (손으로 쓴 최소 `widgets` 도메인 픽스처 사용 - 도메인 생성 품질이 아니라
  스캐폴드 스크립트·검증 엔진 자체의 회귀를 잡는 용도).
- 실사용 중 발견한 버그·설계 결함과 그 수정 내역은 `docs/log.md`(날짜별
  상세 기록, `CLAUDE.md`에서 분리됨)와 각 스택 `gotchas.md`에 있다.

**자동 검증과 수동 검증의 경계** - 백엔드는 `verify_backend.py`가 happyPath
시나리오(정상 흐름 + 거부 케이스 + 역할별 호출)까지 실제로 HTTP 실행해서
검증한다. 프론트는 정적 계약검사(호출 경로·method·wrapper key·디자인 토큰)
까지만 자동이고, **실제 화면에서 클릭해보는 골든패스 확인은 여전히 사람
몫**이다 - `verify_frontend.py`가 통과해도 화면이 실제로 잘 동작하는지는
브라우저로 열어봐야 안다.

자세한 설계 근거, 각 스택별 함정(gotchas), 다음 할 일은 `CLAUDE.md`를 본다.
