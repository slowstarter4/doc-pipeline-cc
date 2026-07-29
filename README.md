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

# 3. 오케스트레이터 실행
/build-app examples/commerce_qwen_plan.md
```

`BACKEND_TARGET`(spring/express/fastapi/typescript), `FRONTEND_TARGET`
(vanilla/react/react-ts), `DB_TARGET`(sqlite/postgres) 조합은 `build-app`
스킬 실행 중 물어본다.

## 검증 현황

- **spring + (프론트 미검증) + postgres**: 도메인 10조각 병렬 생성, 컴파일 1차
  성공, `verify-backend` 통과.
- **express + react + postgres**: `build-app` 전체 파이프라인 첫 통짜 실행
  성공(문서~백엔드~프론트~검증~브라우저 수동 확인까지). 과정에서 발견한 버그와
  수정 내역은 `CLAUDE.md`의 진행 상태 로그 참고.
- **fastapi/typescript/vanilla/react-ts**: 스캐폴드는 있으나 end-to-end 미검증.

자세한 설계 근거, 각 스택별 함정(gotchas), 다음 할 일은 `CLAUDE.md`를 본다.
