# 디자인 시스템 — Nocturne (토큰 + 컴포넌트 레시피)

출처: claude.ai/design **"Nocturne"** 프로젝트(사람이 컨셉으로 생성). 원본은
`design/sources/claude-design/nocturne/`(theme.json, styles.css). 이 파일은 그 값을
파이프라인용으로 옮겨 적은 것이다 - **파이프라인이 프롬프트에 싣는 건 이 파일 하나뿐**.

**레이아웃은 여기서 정하지 않는다.** 화면 구성·요소 배치는 화면설계서가 정한다. 이
파일은 톤앤매너 + 컴포넌트 생김새만 고정한다(완성된 페이지를 안 실어 복사를 막는다).

**톤: 다크 · 저채도 보라 강조 · Inter.** 딥 네이비 배경 위 옅은 텍스트, 보라 accent는
아껴 쓴다(버튼 테두리·링크·포커스). 버튼은 **아웃라인 스타일**(채우지 않음). 구분선·
테이블 행 rule은 **양끝에서 투명하게 페이드**하는 게 Nocturne 시그니처. 밝은 기본 폼처럼
보이면 안 된다.

---

## 색 (다크)

| 이름 | 값 | 용도 |
|---|---|---|
| bg | `#161826` | 페이지 배경(딥 네이비) |
| surface | `#232532` | 카드·패널·입력 배경 |
| text | `#e9e9ed` | 본문·제목 |
| text-muted | `#9a9aa6` | 부가 정보·라벨(= text를 55% 불투명하게, `color-mix(in srgb, #e9e9ed 55%, transparent)`) |
| divider | `rgba(233,233,237,0.16)` | 구분선·테두리(= text 16%) |
| accent | `#9184d9` | 버튼 테두리·링크·선택·포커스(보라) |
| accent-2 | `#a7a1db` | 보조 강조 |

**톤 램프**(배지·상태용, 어두운 쪽이 배경·밝은 쪽이 글자):
- neutral: `#292b31`(900) … `#3f424d`(800) … `#9397ab`(500) … `#e4e7f5`(200) … `#f3f5fe`(100)
- accent: `#2b2741`(900) … `#423a6a`(800) … `#968ae0`(500) … `#e7e5fe`(200) … `#f5f4ff`(100)

- accent(#9184d9)를 넓은 면적에 채우지 않는다 - 테두리·글자·옅은 hover 채움(12%)으로만.
- 상태 배지는 `톤 램프의 800(어두운 배경) + 100(밝은 글자)` 조합.

## 타이포그래피

- 폰트: `"Inter", system-ui, sans-serif`. 웹폰트를 로드해도 된다(Google Fonts Inter) 또는
  시스템 폴백. 제목·본문 모두 Inter.
- 제목 굵기 `500`(700 아님), `letter-spacing: -0.015em`, 행간 `1.15`.
- 크기: 페이지 제목 `28~32`, 카드/섹션 제목 `17~20`, 본문 `14~15`(행간 1.55), 라벨 `12`,
  아주 작은 메타·kicker `10~11`.
- kicker/eyebrow·테이블 헤더는 `대문자 + letter-spacing 0.08~0.1em` text-muted.

## 간격 (density 0.7)

스케일(px): `2.8 / 5.6 / 8.4 / 11.2 / 16.8 / 22.4`. 촘촘한 편이다 - 반올림해서 `3/6/8/11/17/22`로 써도 된다.
- 관련 요소 사이 `6~8`, 그룹 사이 `11~17`, 섹션 사이 `22`
- 카드 안쪽 여백 `11~17`(Nocturne는 조밀하다 - 24px씩 넉넉히 주지 않는다)
- 콘텐츠 최대 너비 `760px` 가운데 정렬, 페이지 좌우 여백 `11~17`

## 모양·깊이·모션

- 반경: 입력·버튼 `8px`(md), 작은 태그 `6px`(md*0.75), 다이얼로그·큰 패널 `14px`(lg)
- 다크 elevation(그림자 대신 **헤어라인 테두리 + 은은한 암부**):
  - `shadow-sm` = `0 0 0 1px #3f424d` (테두리만)
  - `shadow-md` = `0 0 0 1px #595d6c, 0 6px 18px rgba(0,0,0,0.55)`
  - `shadow-lg` = `0 0 0 1px #9397ab, 0 16px 40px rgba(0,0,0,0.65)` (다이얼로그)
- 포커스: `outline: 2px solid accent; outline-offset: 2px`(다크라 링 대신 또렷한 외곽선).
- **페이드 rule(시그니처):** 독립 구분선·테이블 행 밑줄은 양끝 `48px`에서 투명하게 사라진다:
  `linear-gradient(to right, transparent, divider 48px, divider calc(100% - 48px), transparent)`.
  박스 외곽선·컨트롤 내부 구분선은 그냥 solid.
- 배경 이미지·그라데이션 채움 없음(페이드 rule 제외). 색은 위 팔레트에서만.

---

## 컴포넌트 레시피

각 컴포넌트는 아래 스펙 그대로. 배치만 화면설계서를 따른다.

### 버튼 (아웃라인 스타일)
inline-flex, gap 6px, 글자 `14/500`(제목 폰트), padding `6px 10px`, `radius 8px`,
`transition 120ms`. 기본 배경 투명·테두리 투명.
- **primary**: 글자 `accent`, 테두리 `1px accent`. hover 배경 = accent 12% 투명 채움,
  active = accent 22%. (채우지 않고 테두리로 표현 — Nocturne buttonStyle=outline)
- **secondary**: 테두리 `1px divider`, 글자 `text`. hover 배경 = text 7% 투명.
- **ghost**: 글자 `accent`, 테두리 없음, 좌우 여백 최소. hover = accent 10% 투명.
- **icon 버튼**: 36×36 정사각, padding 0.
- **disabled**: opacity 0.45, not-allowed.
- 포커스 시 accent outline.

### 입력 / 폼
- 필드: 라벨(위, `12`, text 70%) → 인풋 → 헬퍼(아래, `11`).
- 인풋: min-height `36px`, padding `6px 10px`, 배경 `surface`, `1px divider` 테두리,
  `radius 8px`, 글자 `14`, `caret-color: accent`. hover 시 테두리 text 45%, focus 시
  테두리 `accent`. 에러 시 테두리·헬퍼를 danger 톤으로.
- segmented(seg)·radio가 필요하면: 선택된 옵션은 accent 글자 + inset accent 테두리.

### 카드
flex-column, gap `6px`, padding `8~11px`, `radius 8px`, 배경 `surface`.
- **kicker**(선택): `10px 대문자 letter-spacing 0.1em accent`.
- **title**: 제목 폰트 `17/500`, 행간 1.2.
- **body**: `13px`, opacity 0.8.
- **meta**: `11px`, text 50%, 아이콘/구분점과 함께.
- 떠 보이게 할 카드만 `.elev-sm/md`(위 그림자).

### 태그 / 상태 배지
inline-flex, `11px`, letter-spacing 0.02em, padding `3px 10px`, radius `6px`.
- accent 상태 = accent-800(#423a6a) 배경 + accent-100(#f5f4ff) 글자
- 중립 = neutral-800(#3f424d) 배경 + neutral-100(#f3f5fe) 글자
- outline = `1px accent` 테두리 + accent 글자
색만으로 구분하지 않는다 - 배지 안에 항상 한국어 라벨 텍스트를 같이 넣는다.
(상태값: 대출중/반납완료/연체 등을 이 배지로 보여준다.)

### 네비게이션
flex 가로, 브랜드는 `18/500` 왼쪽(margin-right auto), 링크 `14` inherit 색,
hover·현재 페이지는 `accent` 글자. 밑줄 테두리 없음.

### 테이블
width 100%, border-collapse, 글자 `14`.
- 헤더: 왼쪽 정렬, `11px 대문자 letter-spacing 0.08em`, text 60%.
- 행 구분선은 **페이드 rule**(위 시그니처)로 - 각 행 아래 `to right` 그라데이션 밑줄
  (양끝 48px 투명). 행 hover 시 text 4% 옅은 채움을 그 위에 겹친다.
- 숫자 열은 `tabular-nums` 우측 정렬.

### 다이얼로그
backdrop = neutral-900 50% 투명. 패널 = `surface`, `radius 14px`, `shadow-lg`,
width min(440px,100%), padding `11px`, gap `8px`. 제목 `20/500`, 본문 `14` opacity 0.85,
액션 버튼은 하단 우측 정렬.

### 빈 상태 / 로딩 / 알림
- 빈 목록: 카드 안 가운데, text-muted "아직 없습니다" + 액션 버튼(넉넉한 여백).
- 로딩: "불러오는 중…" text-muted.
- 알림/에러 배너: 좌측 `3px` 의미색(accent 또는 danger 톤) 테두리 + 옅은 톤 배경 + 텍스트.
  콘솔이 아니라 화면에 보인다.

### 접근성·공통
- 상태를 색만으로 전달하지 않는다(항상 텍스트 동반).
- 대화형 요소는 포커스가 보인다(accent outline).
- 다크 배경 대비: text(#e9e9ed)가 bg(#161826) 위에서 충분히 밝다.
