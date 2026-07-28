# design/reference

`design/design_system.md`(파이프라인이 읽는 토큰·레시피 정본)의 **근거·미러**를 둔다.
파이프라인은 이 폴더를 안 읽는다 - 프롬프트에 실리는 건 `design/design_system.md` 텍스트뿐.

## components/
컴포넌트 프리뷰 HTML(+ `_tokens.css`). design_system.md의 레시피가 실제로 어떻게 보이는지
사람이 눈으로 확인하는 용도. 브라우저로 각 .html을 열면 렌더된다.

## Claude Design 미러
같은 컴포넌트 라이브러리를 claude.ai/design 프로젝트로 미러해 둔다:
- 프로젝트: **doc-pipeline design system** (`projectId: e348c163-aea2-49b1-bbc9-a3437fe474c0`)
- `DesignSync` 도구(Claude Code)로 `components/`를 push했다.

**동기 방향:** 지금은 로컬 → Claude Design(로컬에서 만들어 push). 나중에 Claude Design에서
컴포넌트를 편집하면, 그 값을 다시 `design_system.md`에 옮겨 적는다(사람이 가끔). 파이프라인은
언제나 `design_system.md`만 보므로 자기 완결적이다 - schemathesis·docker를 파이프라인 밖에
둔 것과 같은 판단.

## v1 백업
`design_system_v1_tokens_only.md` = 토큰만 있던 예전 버전(레시피 없이 밋밋하게 나오던 것).

## 갈아끼울 톤은 여기 없다
예전에 여기 있던 `design_system_v2_light_indigo.md`·`v3_nocturne_dark.md`는
`design/presets/`로 옮겼다(`DESIGN_TARGET`으로 고르는 대상). 이 폴더는 **근거·백업**만
둔다 - 고를 수 있는 것과 보관만 하는 것이 같은 폴더에 있으면 뭘 골라야 할지 흐려진다.
