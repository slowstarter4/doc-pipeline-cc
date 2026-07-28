# 디자인 시스템 — Librarian's Ledger (토큰 + 컴포넌트 레시피)

출처: **Google Stitch** "Librarian's Ledger"(사람이 컨셉으로 생성 → zip export).
원본은 `design/sources/stitch/stitch_/`(DESIGN.md + 화면 code.html). 이 파일은 그 값을
파이프라인용으로 옮겨 적은 것 - **파이프라인이 프롬프트에 싣는 건 이 파일 하나뿐**.

**레이아웃은 여기서 정하지 않는다.** 화면 구성·배치는 화면설계서가 정한다(복사 방지).

**톤: 라이트 · 크림 종이 배경 · 딥 그린 · Hanken Grotesk.** "Modern Curator" - 도서관의
정돈되고 신뢰감 있는 관리 UI. 순백 대신 크림(#fdfcf5)으로 눈 피로를 줄이고, 딥 그린을
주요 동작·브랜드에 쓴다. 카드는 그림자 없이 1px 테두리로 납작하게(tonal + outline).

---

## 색 (라이트)

| 이름 | 값 | 용도 |
|---|---|---|
| background | `#fdfcf5` | 페이지 배경(크림 종이) |
| surface | `#ffffff` | 카드·패널·입력 배경 |
| surface-alt | `#f3f4f6` | 테이블 헤더 등 옅은 강조 배경 |
| text | `#121c28` | 제목·본문(on-surface) |
| text-muted | `#4b5563` | 부가 정보·라벨·보조 텍스트(슬레이트) |
| border | `#e5e7eb` | 카드·구분선 테두리 |
| border-input | `#d1d5db` | 입력 필드 테두리(조금 더 진함) |
| primary | `#2d5a27` | 주요 버튼·브랜드·네비 강조(딥 그린) |
| primary-hover | `#23501e` | primary hover(더 진한 그린) |
| on-primary | `#ffffff` | primary 위 글자 |

**상태 색**(soft 배경 + dark 글자, 배지·배너용):
- 대출중(정보/파랑): 배경 `#d8e2ff` + 글자 `#00367a`
- 반납완료(정상/초록): 배경 `#dcfce7` + 글자 `#23501e`
- 연체(경고/빨강): 배경 `#ffdad6` + 글자 `#93000a`

- primary(딥 그린)를 주요 동작·브랜드에만. 넓은 배경은 크림/화이트로.
- 상태는 색만이 아니라 배지 텍스트로도 읽힌다.

## 타이포그래피

- 폰트: **Hanken Grotesk** (Google Fonts 로드 허용) + 폴백 `system-ui, sans-serif`.
  데이터 밀집 관리 화면용 고가독 그로테스크. 제목·본문 모두 이 폰트.
- 스케일(px): display `36/700`(-0.02em) · headline-lg `28/600`(-0.01em) ·
  headline-md `20/600` · body-lg `18/400` · body-md `16/400` · body-sm `14/400` ·
  label-lg `14/600` · label-md `12/600`.
  - 페이지 제목 = display 또는 headline-lg, 카드/섹션 제목 = headline-md, 본문 = body-md,
    보조 = body-sm, 라벨·버튼 = label.
- 테이블 헤더·메타 라벨은 **작은 대문자**(label-md, letter-spacing 0.04em) text-muted.
- 굵기: 상호작용·강조 요소는 500~600, 본문·설명은 400.

## 간격 (4px 베이스)

- 베이스 그리드 `4px`. 스택: 좁게 `8px`, 보통 `16px`, 넓게 `32px`. 그리드 gutter `24px`.
- **카드·컨테이너 안쪽 여백 `24px`**(정보 밀집해도 숨 쉬게 - 넉넉히).
- 콘텐츠는 가운데 정렬, 데스크톱 최대폭 넓게(관리 도구 느낌). 모바일 좌우 여백 `16px`.
- 입력↔라벨은 타이트하게(4px 리듬).

## 모양·깊이

- 반경: 버튼·입력 `4px`(0.25rem), 카드·모달 `8px`(0.5rem), **상태 배지만 pill(full)**.
- **납작한 구조 - 그림자 대신 tonal 레이어 + 1px 테두리:**
  - Level 0 배경(크림), Level 1 카드(화이트 + `1px border`, **그림자 없음**),
    Level 2 모달·팝오버(화이트 + soft 12% 중립 그림자).
- 상호작용(버튼·클릭 카드)은 hover에서 아주 옅은 lift(미세 그림자)로 클릭 가능함을 알린다.
- 입력 focus: 테두리가 primary 그린으로 + 바깥 `2px` 옅은 그린 글로우.

---

## 컴포넌트 레시피

각 컴포넌트는 아래 스펙 그대로. 배치만 화면설계서를 따른다.

### 버튼
label 글자(`14/600`), `radius 4px`, `transition 120ms`.
- **primary**: 배경 `primary`(#2d5a27) 솔리드 + `on-primary`(흰) 글자. hover 배경 `primary-hover`.
  단호하고 권위 있게 - 화면에서 가장 중요한 동작(도서 추가 등)에.
- **secondary(ghost)**: 투명 배경 + `1px primary` 테두리 + `primary` 글자. hover 시 옅은
  그린 배경(primary 8% 투명). 덜 급한 동작(내보내기·필터)에.
- disabled: opacity 0.5, not-allowed.
- 포커스 시 그린 글로우.

### 액션 바
페이지 상단 지속 바 - 왼쪽 제목(headline-lg), 오른쪽 전역 동작(검색·"도서 추가").
가장 중요한 버튼은 primary 그린. 아래로 `16~24px` 간격.

### 입력 / 폼
- 필드: 라벨(위, label-md, text-muted) → 인풋 → 헬퍼(아래, body-sm).
- 인풋: 아웃라인 스타일, `1px border-input`(#d1d5db), 배경 `surface`, `radius 4px`,
  글자 body-md. focus 시 테두리 `primary` + 바깥 2px 옅은 그린 글로우.
  에러 시 테두리·헬퍼를 연체 빨강(#ba1a1a 계열)로.
- 폼 필드 간 `16px`, 라벨↔인풋 타이트.

### 카드 (납작)
`surface` 배경, `1px border`(#e5e7eb), `radius 8px`, **그림자 없음**, 안쪽 여백 `24px`.
- 헤더: 제목(headline-md) + 선택적 부제(body-sm text-muted), 아래 `16px` 간격.
- 책 상세·회원 프로필 묶는 데 쓴다. 클릭 가능한 카드만 hover에서 미세 lift.

### 상태 배지 (pill)
`radius full`, 작은 글자(label-md, `12/600`), 좌우 여백 `10px`, 높이 `22px`.
- 대출중 = `#d8e2ff` 배경 + `#00367a` 글자
- 반납완료 = `#dcfce7` 배경 + `#23501e` 글자
- 연체 = `#ffdad6` 배경 + `#93000a` 글자
버튼과 구분되게 pill 모양. 색만으로 구분하지 않고 항상 한국어 라벨 텍스트 포함.

### 테이블 (고밀도)
width 100%, 글자 body-sm(`14`). 도서 목록·대출 현황 같은 데이터 뷰의 기본.
- 헤더 행: 배경 `surface-alt`(#f3f4f6), 글자 label-md **대문자** letter-spacing 0.04em text-muted.
  세로 공간 아끼되 가독성 유지.
- 행: 높이 조밀하게, 셀 여백 `12px 16px`, 행 사이 **옅은 가로 구분선**(`1px border`).
  숫자 열(대출 수·ISBN)은 tabular-nums 우측 정렬. 행 hover 시 옅은 surface-alt 채움.
- 제목 vs ISBN처럼 위계가 다른 정보는 굵기·크기로 구분(제목 500, ISBN 400 text-muted).

### 네비게이션
좌측 사이드 레일 또는 상단 바. 브랜드(headline-md) + 링크. 현재 페이지·hover는 primary 그린.
태블릿에선 레일로 축소, 모바일에선 단일 컬럼.

### 빈 상태 / 로딩 / 알림
- 빈 목록: 카드 안 가운데, text-muted "아직 없습니다" + 액션 버튼(넉넉한 여백).
- 로딩: "불러오는 중…" text-muted.
- 알림/에러 배너: 좌측 `3px` 상태색 테두리 + 옅은 상태색 배경 + 텍스트. 연체·오류는 빨강,
  성공은 그린. 콘솔이 아니라 화면에 보인다.

### 접근성·공통
- 상태를 색만으로 전달하지 않는다(항상 텍스트 동반).
- 대화형 요소는 포커스가 보인다(그린 글로우).
- 크림 배경 대비: text(#121c28)가 충분히 진하다.
