# design/presets

갈아끼울 수 있는 디자인 톤 보관소. `.env`의 `DESIGN_TARGET`으로 고른다.

```bash
DESIGN_TARGET=nocturne      # design/presets/nocturne.md 를 읽는다
# 미지정                     # design/design_system.md (정본, 지금 적용된 디자인)
```

파일을 하나 떨구면 프리셋이 하나 는다 - 코드를 안 고친다. 백엔드·프론트 스택
레지스트리와 같은 성격인데, 구현체가 코드가 아니라 문서라서 딕셔너리가 아니라
폴더를 훑는다(`src/design_system.py`의 `design_system_path()`).

없는 이름을 주면 사용 가능한 목록을 보여주며 죽는다 - 조용히 정본으로 새면
"바꿨는데 왜 그대로지"를 디버깅하게 된다(`BACKEND_TARGET`과 같은 규칙).

## 정본과의 관계

| | 파일 | 언제 |
|---|---|---|
| 정본 | `design/design_system.md` | 지금 이 프로젝트에 적용된 디자인 |
| 프리셋 | `design/presets/*.md` | 정본을 안 건드리고 한 번 다르게 뽑아볼 때 |

**영구 전환은 프리셋을 정본 위에 복사하는 것**이다 - 외부 디자인 수령 흐름
(Claude Design/Stitch → 변환 → `design_system.md`)이 끝나는 자리가 정본이므로,
그 자리를 둘로 만들지 않는다.

## 지금 있는 것

- `nocturne.md` — 다크·보라(Inter, 아웃라인 버튼). 출처: claude.ai/design "Nocturne".
  원본은 `design/sources/claude-design/nocturne/`.
- `commerce-modernist.md` — 라이트·각진 스위스 모더니즘(Archivo 800, 반경 0, 2px rule,
  주홍 accent). 커머스 운영 백오피스용 — 상태 배지 6종·데이터 테이블·금액 표기 레시피
  포함. 출처: claude.ai/design "Modernist", 원본은 `design/sources/claude-design/modernist/`.
- `light-indigo.md` — 라이트·인디고. 레시피 확장 시점의 기본 톤.

### 소스에 없어서 보강한 값

Modernist는 mono 팔레트라 강조색이 주홍 하나뿐인데, 커머스는 주문·배송·결제·환불
상태가 20종을 넘어 서로 구분돼야 한다. `commerce-modernist.md`의 **상태 색 6종**은
원본과 같은 밝기대로 맞춰 파이프라인 쪽에서 더한 값이고, 파일 안에 그렇게 표시해 뒀다.
디자인 도구가 준 것과 사람이 더한 것을 섞어 적으면 나중에 출처를 못 되짚는다.

정본(`design_system.md`)은 현재 **Librarian's Ledger**(크림·그린, Google Stitch).
