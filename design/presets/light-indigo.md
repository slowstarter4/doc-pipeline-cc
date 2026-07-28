# 디자인 시스템 (토큰 + 컴포넌트 레시피)

이 파일 하나만 프론트엔드 생성 프롬프트에 실린다. 여기 없는 건 근거가 없는 것이고,
LLM이 매번 다르게 지어낸다.

**레이아웃은 여기서 정하지 않는다.** 화면 구성·요소 배치는 화면설계서가 정한다.
이 파일은 "어떻게 생겼는가"(톤앤매너 + 컴포넌트 생김새)만 고정한다. 완성된 페이지
HTML을 여기 붙여넣지는 않는다 - LLM이 레이아웃을 통째로 베끼면 기획문서를 바꿔도
같은 화면이 나오기 때문이다. 대신 **컴포넌트별 레시피**를 값으로 못박아, 배치는
화면설계서대로 하되 각 조각(버튼·카드·입력 등)의 생김새는 여기 스펙 그대로 나오게 한다.

목표 톤: **정돈되고 밀도 있는 프로덕트 UI.** 여백에 리듬이 있고, 상호작용에 상태
(hover/focus/disabled)와 짧은 전환이 있으며, 상태값은 색만이 아니라 배지·텍스트로
읽힌다. 밋밋한 기본 폼처럼 보이면 안 된다.

원본 프리뷰(컴포넌트 HTML)는 `design/reference/components/`에 있고, claude.ai/design
프로젝트에도 미러돼 있다. 이 파일엔 값·규칙만 옮겨 적는다.

---

## 색

**중립(neutral) 램프** — 배경·테두리·텍스트의 뼈대:

| 이름 | 값 | 용도 |
|---|---|---|
| bg | `#f6f7f9` | 페이지 배경 |
| surface | `#ffffff` | 카드·패널·입력 배경 |
| surface-2 | `#f1f3f5` | 안쪽 강조 배경(테이블 헤더, 선택 안 된 탭) |
| border | `#e3e6ea` | 구분선·테두리 |
| border-strong | `#cdd2d9` | 입력 테두리(더 또렷) |
| text | `#1a1d21` | 제목·본문 |
| text-muted | `#5c6672` | 부가 정보·라벨·비활성 |
| text-faint | `#8b94a0` | 플레이스홀더·아주 약한 메타 |

**강조(accent) + 의미(semantic)** — 각 색은 `_bg`(옅은 배경)와 진한 전경을 쌍으로 쓴다:

| 이름 | 값 | _bg(옅음) | 용도 |
|---|---|---|---|
| primary | `#4f46e5` | `#eef2ff` | 주요 버튼·링크·선택·포커스 |
| primary-hover | `#4338ca` | — | primary hover |
| success | `#0f9d58` | `#e7f6ee` | 완료·정상 상태 배지 |
| warning | `#c2790b` | `#fdf3e2` | 주의·경고 배지(연체 등) |
| danger | `#dc2626` | `#fdecec` | 삭제·오류 |

- 링크·선택 상태 배경은 `primary_bg`(#eef2ff)를 쓴다. 강한 색을 넓은 면적에 안 쓴다.
- 상태 배지는 `의미색_bg` 배경 + `의미색` 글자 조합(예: 연체 = #fdf3e2 배경 + #c2790b 글자).

## 타이포그래피

- 폰트: `-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif` (웹폰트 로드 금지)
- 스케일: `12 / 13 / 14 / 16 / 20 / 28`px. 이 밖의 크기는 안 쓴다.
  - 페이지 제목 `28/700`, letter-spacing `-0.02em`
  - 섹션/카드 제목 `20/600`, letter-spacing `-0.01em`
  - 본문 `14/400`, 행간 `1.55`
  - 라벨·메타 `13/500`, text-muted 색
  - 배지·아주 작은 메타 `12/600`
- 굵기는 `400/500/600/700`만. 700은 페이지 제목에만.
- 숫자가 세로로 정렬돼야 하는 표·목록엔 `font-variant-numeric: tabular-nums`.

## 간격

`4px` 배수 스케일: `2 / 4 / 8 / 12 / 16 / 20 / 24 / 32 / 48`.

- 관련 요소 사이 `8~12px`, 그룹 사이 `20~24px`, 섹션 사이 `32px`
- 카드 안쪽 여백 `20px`(모바일) ~ `24px`
- 페이지 좌우 여백 `20px`, 콘텐츠 최대 너비 `760px` 가운데 정렬
- 위아래로 쌓이는 요소는 간격을 `margin`이 아니라 부모의 `gap`(flex/grid)으로 준다

## 깊이·모양·모션

- 반경: 버튼·입력·배지 `8px`, 카드·패널 `14px`, pill(상태 배지) `999px`
- 테두리: `1px solid border`. 입력은 `border-strong`.
- 그림자(2단계, 하나만 쓰지 말 것):
  - `shadow-sm` = `0 1px 2px rgba(16,24,40,0.06)` — 카드 기본
  - `shadow-md` = `0 4px 12px rgba(16,24,40,0.08)` — hover되는 카드, 떠 있는 요소
- 포커스 링: `0 0 0 3px rgba(79,70,229,0.25)`(primary 25%). outline 대신 box-shadow로.
- 전환: 상호작용 요소는 `transition: 120ms ease` (background/border/box-shadow/transform).
- 배경 그라데이션·이미지 없음. 색은 위 팔레트에서만.

---

## 컴포넌트 레시피

각 컴포넌트는 아래 스펙 **그대로** 만든다. 배치(어디에 몇 개 놓는지)만 화면설계서를 따른다.

### 버튼
높이 `40px`, 좌우 여백 `16px`, `radius 8px`, 글자 `14/600`, `transition 120ms`.
아이콘이 있으면 텍스트와 `8px` 간격. 커서 pointer. 누를 때 `transform: translateY(1px)`.
- **primary**: 배경 `primary`, 흰 글자, `shadow-sm`. hover 배경 `primary-hover`.
- **secondary**: 배경 `surface`, `1px border-strong`, 글자 `text`. hover 배경 `surface-2`.
- **ghost**: 투명 배경, 글자 `text-muted`. hover 배경 `surface-2`, 글자 `text`.
- **danger**: 투명 배경, 글자 `danger`. hover 배경 `danger_bg`(#fdecec).
- **작은 버튼**(테이블 행 등): 높이 `32px`, 좌우 `12px`, 글자 `13/600`.
- **disabled**: opacity `0.5`, 커서 not-allowed, hover 변화 없음.
- 포커스 시 포커스 링.

### 입력 / 폼
- 필드는 **라벨(위, `13/500` text-muted) → 인풋 → 헬퍼/에러(아래, `12`)** 세로 스택, `gap 6px`.
- 인풋 높이 `40px`, 좌우 `12px`, `radius 8px`, `1px border-strong`, 배경 `surface`, 글자 `14`.
  - 플레이스홀더 `text-faint`. focus 시 테두리 `primary` + 포커스 링.
  - 에러 상태: 테두리 `danger`, 아래 헬퍼 텍스트 `danger`(`12`).
- 폼 그리드: 라벨된 필드들을 `gap 16px`로 배치. 제출 버튼은 폼 하단 우측.

### 카드 / 패널
`surface` 배경, `radius 14px`, `1px border`, `shadow-sm`, 안쪽 여백 `24px`.
- 헤더가 있으면: 제목(`20/600`) + 선택적 부제(`13` text-muted), 그 아래 `1px border` 구분선,
  본문과 `16px` 간격.
- 클릭 가능한 카드(목록 항목 카드 등)만 hover에서 `shadow-md` + 테두리 `border-strong`.

### 목록 / 테이블
- **목록 행**: 좌우 여백 `16px`, 위아래 `12px`, 아래쪽에만 `1px border` 구분선(마지막 행 없음).
  hover 시 배경 `surface-2`. 주 텍스트(`14/500`)는 왼쪽, 메타·상태·액션은 오른쪽 정렬.
- **테이블**: 헤더 행 배경 `surface-2`, 글자 `12/600` text-muted, letter-spacing `0.03em`.
  셀 여백 `12px 16px`, 행 사이 `1px border`, 행 hover 배경 `surface-2`. 숫자 열은 tabular-nums 우측 정렬.

### 상태 배지 (pill)
상태값(대출중/반납완료/연체, 활성/비활성 등)은 **배지로** 보여준다.
높이 `22px`, 좌우 `10px`, `radius 999px`, 글자 `12/600`.
- 정상·완료 = `success_bg` 배경 + `success` 글자
- 주의·연체 = `warning_bg` 배경 + `warning` 글자
- 오류·차단 = `danger_bg` 배경 + `danger` 글자
- 중립·기본 = `surface-2` 배경 + `text-muted` 글자
색만으로 구분하지 않는다 - 배지 안에 항상 한국어 라벨 텍스트를 같이 넣는다.

### 페이지 헤더
페이지 상단: 제목(`28/700`) + 선택적 부제(`14` text-muted)가 왼쪽, 주요 액션 버튼이 오른쪽
(`justify-content: space-between`, `align-items: center`). 아래 `24px` 간격.

### 빈 상태 / 로딩 / 알림
- **빈 목록**: 카드 안 가운데 정렬, `text-muted`로 "아직 없습니다" 한 줄 + 선택적 액션 버튼. 여백 넉넉히(`48px 24px`).
- **로딩**: "불러오는 중…" 텍스트(text-muted). 스피너 라이브러리 쓰지 않는다.
- **알림/에러 배너**: 좌측 `3px` 의미색 두꺼운 테두리 + 옅은 `의미색_bg` 배경 + 텍스트.
  성공은 success, 오류는 danger 계열. 콘솔에만 찍지 말고 항상 화면에 보인다.

### 접근성·공통
- 상태·정보를 색만으로 전달하지 않는다(항상 텍스트 동반).
- 대화형 요소는 키보드 포커스가 보여야 한다(포커스 링).
- 대비: 본문 text 대 배경이 충분히 진하게(위 팔레트가 이미 만족).
