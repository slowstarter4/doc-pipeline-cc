"""
생성된 프론트엔드를 실제 브라우저(Playwright)로 조작해 happyPath fixture가
UI로도 통과하는지 검증한다. `verify_frontend.py`(정적 계약검사)의 다음 단계 -
"경로를 맞게 부르는가"가 아니라 "화면을 실제로 조작하면 그 시나리오가 되는가".

CLI: python scripts/verify_frontend_e2e.py --api-spec generated/docs/api_spec.json --url http://localhost:5173

전제: `gen-frontend-*` 스킬의 data-testid 컨벤션(SKILL.md 참고)을 프론트가
지켰다는 것. api_spec.json의 method+path만으로 결정적으로 slug를 계산해
셀렉터를 만든다 - 화면 구조나 LLM 판단에 의존하지 않는다.

path parameter가 있는 엔드포인트(PUT/DELETE /x/{id})는 컨벤션상 목록 아이템
안에 인라인으로 존재한다고 본다. 그 id로 갈 항목이 화면에 없으면(예: 존재하지
않는 id로 404를 유도하는 스텝) 검증을 조용히 건너뛴다 - UI에 없는 대상을 UI로
조작할 방법이 없는 게 당연하기 때문이다(실패 아님).

`--backend-url`을 주면, path parameter 없는 생성(POST) 스텝인데 화면 어디에도
그 폼(`{slug}-form`)이 없는 경우(예: 관리자가 별도 등록 화면 없이 seed로만
넣는 참조 데이터 - 기차예약 도메인의 역 등록처럼) UI 조작 대신 백엔드에 직접
HTTP 요청을 보내 데이터를 만들고 capture까지 이어간다. 폼이 아예 없는 것과
폼은 있는데 특정 필드/버튼만 못 찾는 것은 다르게 취급한다 - 후자는 진짜 프론트
버그일 수 있어 여전히 실패로 잡는다.

**알려진 한계 - 다단계 선택 마법사 흐름**: 이 스크립트의 폼 모델은 "요청
필드 하나당 입력칸 하나"를 가정한다. "운행 검색 → 운행 선택 → 좌석 클릭"처럼
이전 화면의 선택 결과를 앱 상태로 들고 다음 화면에 반영하는 마법사형 흐름은
이 모델로 표현이 안 된다 - 그 화면의 tripId/seatId 같은 필드가 `readonly`
입력칸(선택 결과를 보여주기만 함)이면 채우려다 타임아웃난다(실측: 2026-08-04
기차예약 도메인 예약 생성 화면). 이런 필드는 지금은 실패로 남겨둔다 - 억지로
skip하면 빈 값으로 제출돼 다른 이유로 또 실패하고, 무엇보다 이 흐름 자체를
실제로 검증 못 한 채 조용히 넘어가는 게 더 위험하다. 다음에 같은 패턴을 또
만나면 그때 "이전 스텝에서 만든 항목을 목록에서 클릭해 선택"하는 별도 스텝
타입을 컨벤션에 추가할지 판단한다.
"""

import argparse
import json
import re
import sys
import uuid

import requests

_PLACEHOLDER_RE = re.compile(r"\$\{(\w+)\}")


def slug(method: str, path: str) -> str:
    method = method.lower()
    segs = [s for s in path.split("/") if s]
    out = [s[1:-1].lower() if s.startswith("{") and s.endswith("}") else s for s in segs]
    return "-".join([method] + out) if out else method


def has_path_param(path: str) -> bool:
    return "{" in path


def _path_segments(path: str) -> list[str]:
    return [s for s in path.split("/") if s]


def _endpoint_matches(ep_method: str, ep_path: str, method: str, path: str) -> bool:
    if ep_method.upper() != method.upper():
        return False
    ep_segs, segs = _path_segments(ep_path), _path_segments(path)
    if len(ep_segs) != len(segs):
        return False
    return all(e.startswith("{") and e.endswith("}") or e == s for e, s in zip(ep_segs, segs))


def find_endpoint(api_spec: dict, method: str, path: str) -> dict | None:
    for ep in api_spec.get("endpoints", []):
        if _endpoint_matches(ep["method"], ep["path"], method, path):
            return ep
    return None


def substitute(value, vars: dict):
    if isinstance(value, str):
        m = _PLACEHOLDER_RE.fullmatch(value)
        if m:
            return vars.get(m.group(1), value)
        return _PLACEHOLDER_RE.sub(lambda m: str(vars.get(m.group(1), m.group(0))), value)
    if isinstance(value, dict):
        return {k: substitute(v, vars) for k, v in value.items()}
    return value


def _id_token_from_path(ep_path: str, literal_path: str) -> str:
    """param이 마지막 세그먼트가 아닐 수 있다(`/members/{id}/points/add`) - 템플릿
    에서 `{...}`가 있던 자리를 찾아 그 자리의 실제 값을 꺼낸다."""
    ep_segs, segs = _path_segments(ep_path), _path_segments(literal_path)
    for ep_seg, seg in zip(ep_segs, segs):
        if ep_seg.startswith("{") and ep_seg.endswith("}"):
            return seg
    return segs[-1]


def _extract_id(text: str) -> str:
    """id 표시는 종종 꾸며진다(`#2`, `ID: 2` 등) - 컨벤션이 그걸 막을 이유가
    없으니 스크립트가 숫자만 뽑아 비교한다."""
    m = re.search(r"\d+", text)
    return m.group(0) if m else text.strip()


def _find_item_by_id(page, id_token: str):
    id_fields = page.locator('[data-field="id"]')
    for i in range(id_fields.count()):
        f = id_fields.nth(i)
        if _extract_id(f.inner_text()) == id_token:
            anc = f.locator('xpath=ancestor::*[contains(@data-testid, "-item")][1]')
            if anc.count() > 0:
                return anc.first
    return None


def _field_matches(item, field: str, value) -> bool:
    """정확히 같은 텍스트가 아니라 **포함**으로 본다 - `discountRate: 10`을
    화면이 `10%`로 꾸며 보여주는 것처럼 단위·기호를 덧붙이는 건 흔한 UI라
    엄격한 동등비교면 그런 값을 전부 놓친다. boolean은 이 방식으로도 못
    잡는다(예: `used: false`를 "미사용"처럼 로컬라이즈하면 부분일치도 안 됨) -
    알려진 한계로 남긴다."""
    text = _field_text(item, field)
    return text is not None and str(value).lower() in text.lower()


def _list_has_item(page, fields: dict) -> bool:
    items = page.locator('[data-testid$="-item"]')
    for i in range(items.count()):
        it = items.nth(i)
        if all(_field_matches(it, k, v) for k, v in fields.items()):
            return True
    return False


def _capture_indexed(page, s: str, field: str) -> str | None:
    """`"seats.0.id"`처럼 점표기 경로로 목록의 N번째 항목에서 값을 읽는다 -
    verify_backend.py의 JSON 응답 인덱싱과 같은 목적이지만 여기선 DOM에서
    `{slug}-item`을 순서대로 짚는다(생성 API 없이 다른 리소스의 부수효과로만
    생기는 항목 - 예: 열차 등록 시 자동생성되는 좌석 - 의 id를 목록 조회
    화면에서 얻어야 할 때 쓴다)."""
    parts = field.split(".")
    if len(parts) != 3 or not parts[1].isdigit():
        return None
    idx, subfield = int(parts[1]), parts[2]
    items = page.locator(f'[data-testid="{s}-item"]')
    if idx >= items.count():
        return None
    val = _field_text(items.nth(idx), subfield)
    if val is None:
        return None
    return _extract_id(val) if subfield == "id" else val


def _capture_field(page, body: dict, field: str) -> str | None:
    items = page.locator('[data-testid$="-item"]')
    match_fields = {k: v for k, v in body.items() if k != "__persist"}
    for i in range(items.count()):
        it = items.nth(i)
        if all(_field_matches(it, k, v) for k, v in match_fields.items()):
            val = _field_text(it, field)
            if val is not None:
                return _extract_id(val) if field == "id" else val
    # 폴백: FK id 필드를 화면이 사람이 읽는 라벨로 바꿔 보여주면(예:
    # departureStationId 대신 역이름) 원래 값이 텍스트 어디에도 없어 완전
    # 일치가 하나도 안 잡힌다(boolean 로컬라이즈 라벨과 같은 부류의 한계).
    # 방금 만든 항목은 거의 항상 목록 마지막이라는 가정으로 마지막 항목에서
    # 한 번 더 시도한다 - 실측: 기차예약 도메인 운행 등록(출발역/도착역이
    # 이름으로 표시됨).
    if items.count() > 0 and match_fields:
        val = _field_text(items.nth(items.count() - 1), field)
        if val is not None:
            return _extract_id(val) if field == "id" else val
    return None


def _field_text(item, field: str) -> str | None:
    loc = item.locator(f'[data-field="{field}"]')
    return loc.first.inner_text().strip() if loc.count() > 0 else None


def _reveal_screen(page, ep_path: str, target_selector: str, wait_ms: int) -> bool:
    """역할 토글/사이드 nav처럼 화면이 나뉜 앱에서 이 엔드포인트를 다루는 화면을
    드러낸다. 화면키는 경로 세그먼트와 일치한다는 컨벤션(SKILL.md)을 이용해
    `nav-{세그먼트}` 버튼을 찾아 클릭한다. **같은 화면키가 역할마다 다른 화면을
    가리킬 수 있어서**(예: "orders"가 구매자용 생성 폼과 관리자용 상태변경
    화면 둘 다일 수 있음) 클릭 후 `target_selector`가 실제로 나타났는지 확인하고,
    아니면 역할을 바꿔가며 계속 시도한다. 끝내 못 찾으면 False - 원래 화면
    그대로 다음 단계에서 실패 보고된다."""
    segs = [s for s in _path_segments(ep_path) if not (s.startswith("{") and s.endswith("}"))]
    # 역할 토글 버튼 이름은 도메인마다 다르다(buyer/admin, passenger/admin 등) -
    # `role-buyer`/`role-admin`으로 하드코딩하면 다른 이름을 쓰는 도메인에서
    # 역할 전환 자체가 안 먹혀 화면을 못 찾는다(실측: 기차예약 도메인은
    # `role-passenger`를 쓰는데 하드코딩된 `role-buyer`만 찾아서 승객 전용
    # 화면 전환이 조용히 실패했다). `role-`로 시작하는 testid를 전부 훑는다.
    role_testids = [None] + [
        page.locator('[data-testid^="role-"]').nth(i).get_attribute("data-testid")
        for i in range(page.locator('[data-testid^="role-"]').count())
    ]
    for role_testid in role_testids:
        if role_testid:
            role_btn = page.locator(f'[data-testid="{role_testid}"]')
            if role_btn.count() == 0:
                continue
            role_btn.first.click()
            page.wait_for_timeout(wait_ms // 3)
        if page.locator(target_selector).count() > 0:
            return True
        for seg in segs:
            nav_btn = page.locator(f'[data-testid="nav-{seg.lower()}"]')
            if nav_btn.count() > 0:
                nav_btn.first.click()
                page.wait_for_timeout(wait_ms // 2)
                if page.locator(target_selector).count() > 0:
                    return True
    return False


def _seed_via_backend(backend_url: str, method: str, path: str, body: dict, headers: dict) -> "tuple[int, dict | None]":
    req_headers = {**headers, "Content-Type": "application/json", "Idempotency-Key": str(uuid.uuid4())}
    r = requests.request(method, f"{backend_url}{path}", json=body, headers=req_headers, timeout=5)
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, None


def run_happy_path(page, api_spec: dict, wait_ms: int = 800, backend_url: "str | None" = None) -> tuple[list[str], list[str]]:
    problems: list[str] = []
    notes: list[str] = []
    vars: dict = {}
    steps = (api_spec.get("happyPath") or {}).get("steps") or []

    for i, step in enumerate(steps, 1):
        label = step.get("name") or f"스텝 {i}"
        method = step["method"]
        path = step["path"]
        try:
            path = substitute(step["path"], vars)
            body = substitute(step.get("body") or {}, vars)

            unresolved = [v for v in ([path] + list(body.values())) if isinstance(v, str) and _PLACEHOLDER_RE.search(v)]
            if unresolved:
                problems.append(
                    f"[{label}] {method} {path}: 이전 스텝에서 capture 못한 변수가 남아있음: {unresolved} "
                    f"(현재 변수: {vars})"
                )
                continue

            ep = find_endpoint(api_spec, method, path)
            if ep is None:
                problems.append(f"[{label}] {method} {path}: api_spec에 매칭되는 endpoint가 없음")
                continue
            s = slug(ep["method"], ep["path"])
            target_selector = f'[data-testid="{s}-list"]' if method.upper() == "GET" else f'[data-testid="{s}-submit"]'
            _reveal_screen(page, ep["path"], target_selector, wait_ms)

            codes = step.get("expect")
            codes = codes if isinstance(codes, list) else [codes]
            want_success = all(c < 400 for c in codes)
            want_failure = all(c >= 400 for c in codes)

            force_submit = False
            if has_path_param(ep["path"]):
                id_token = _id_token_from_path(ep["path"], path)
                own_form = page.locator(f'[data-testid="{s}-form"]')
                own_id_field = own_form.locator(f'[data-testid="{s}-field-id"]') if own_form.count() > 0 else own_form
                if own_form.count() > 0 and own_id_field.count() > 0:
                    # 이 엔드포인트 전용 "독립 id입력 폼"이 있다 - 다른 리소스가
                    # 우연히 같은 id 값을 써서(예: 운행 id와 예약대상 id가 같은
                    # 숫자) 목록에서 잘못된 항목을 집어오는 것보다 이쪽이 항상
                    # 우선이다(실측: 기차예약 도메인 좌석조회 폼).
                    own_id_field.first.fill(str(id_token))
                    scope = own_form.first
                    force_submit = True
                else:
                    scope = _find_item_by_id(page, id_token)
                if scope is None:
                    # 인라인할 목록 자체가 없는 화면(예: 이 역할은 전체 목록을 못 봄)은
                    # "독립 id입력 폼" 패턴을 쓴다 - 화면에 보이는 `*-field-id` 아무거나
                    # 채운다(같은 화면의 형제 액션과 id 입력을 공유하는 경우도 있어서
                    # 이 엔드포인트 전용 필드로 한정하지 않는다).
                    standalone_id = page.locator('[data-testid$="-field-id"]')
                    if standalone_id.count() > 0:
                        standalone_id.first.fill(str(id_token))
                        scope = page
                        force_submit = True
                    elif want_failure:
                        notes.append(f"[{label}] UI에 id={id_token} 항목이 없어 건너뜀 (정상 - 거부 케이스)")
                        continue
                    else:
                        problems.append(f"[{label}] {method} {path}: id={id_token} 항목을 목록에서도, 독립 id입력 폼에서도 못 찾음")
                        continue
            else:
                form = page.locator(f'[data-testid="{s}-form"]')
                if form.count() == 0 and method.upper() != "GET" and backend_url:
                    # 화면 어디에도 이 생성 폼이 없다 - screen_design.md상 이
                    # 엔드포인트는 UI가 아니라 참조 데이터 seed용으로만 존재하는
                    # 경우다(예: 별도 등록 화면 없는 역). UI 조작 대신 백엔드에
                    # 직접 호출해 데이터를 만들고 capture를 이어간다.
                    status, payload = _seed_via_backend(
                        backend_url, method, path, body, step.get("headers") or {"X-User-Type": "ADMIN"}
                    )
                    if status not in codes:
                        problems.append(
                            f"[{label}] {method} {path}: UI에 폼이 없어 API로 직접 호출했는데 "
                            f"{codes}를 기대했는데 {status} 반환"
                        )
                        continue
                    for var, field in (step.get("capture") or {}).items():
                        if var == "__persist" or payload is None:
                            continue
                        if field in payload:
                            vars[var] = payload[field]
                    # 프론트가 이 데이터를 보통 최초 마운트 시점에 한 번만
                    # fetch해서 상태에 들고 있다 - 화면 뒤에서 API로 몰래
                    # 만들었으니 새로고침해서 다시 읽어오게 한다(실측: 안 하면
                    # 뒤 스텝의 select 옵션에 방금 만든 역이 안 보임).
                    page.reload()
                    page.wait_for_timeout(wait_ms)
                    notes.append(f"[{label}] {method} {path} - UI에 폼 없어 API로 직접 seed함 (설계상 의도)")
                    continue
                scope = form.first if form.count() > 0 else page

            # 인라인 항목 수정(PUT/DELETE /x/{id})은 화면에 안 보이는 필드를
            # 앱이 기존 값과 merge해서 채우는 경우가 흔하다(예: 열차 수정 폼이
            # 이름/좌석수만 노출하고 나머지는 그대로 유지) - 새로 만드는 폼과
            # 달리 이런 필드가 없다고 실패로 치지 않는다(merge할 원본이 있으니
            # UI가 그 필드를 아예 안 보여줘도 정상 동작일 수 있다).
            is_inline_edit = has_path_param(ep["path"]) and not force_submit

            if method.upper() != "GET" or force_submit:
                missing_field = False
                for field, value in body.items():
                    input_loc = scope.locator(f'[data-testid="{s}-field-{field}"]')
                    if input_loc.count() == 0:
                        if is_inline_edit:
                            notes.append(f"[{label}] 입력 필드 {s}-field-{field} 없음 - 앱이 기존값 유지할 것으로 보고 건너뜀")
                        else:
                            problems.append(f"[{label}] {method} {path}: 입력 필드 {s}-field-{field}를 못 찾음")
                            missing_field = True
                        continue
                    el = input_loc.first
                    if el.evaluate("e => e.tagName") == "SELECT":
                        el.select_option(value=str(value))
                    else:
                        el.fill(str(value))
                submit_loc = scope.locator(f'[data-testid="{s}-submit"]')
                if submit_loc.count() == 0:
                    problems.append(f"[{label}] {method} {path}: 제출 버튼 {s}-submit을 못 찾음")
                    continue
                if missing_field:
                    continue
                if submit_loc.first.is_disabled():
                    if want_failure:
                        notes.append(f"[{label}] 제출 버튼이 비활성화돼 있어 건너뜀 (정상 - UI가 이미 막음)")
                    else:
                        problems.append(f"[{label}] {method} {path}: 제출 버튼이 비활성화돼 있어 성공 케이스를 실행 못 함")
                    continue
                submit_loc.first.click()
                page.wait_for_timeout(wait_ms)

            error_loc = scope.locator(f'[data-testid="{s}-error"]')
            if error_loc.count() == 0:
                error_loc = page.locator(f'[data-testid="{s}-error"]')
            error_visible = (
                error_loc.count() > 0
                and error_loc.first.is_visible()
                and error_loc.first.inner_text().strip() != ""
            )

            if want_failure and not error_visible:
                problems.append(f"[{label}] {method} {path}: 거부(4xx)를 기대했는데 에러 표시가 없음")
                continue
            if want_success and error_visible:
                problems.append(
                    f"[{label}] {method} {path}: 성공을 기대했는데 에러가 표시됨: {error_loc.first.inner_text()}"
                )
                continue

            expect_any = step.get("expectAnyItem")
            if expect_any and not _list_has_item(page, expect_any):
                problems.append(f"[{label}] {method} {path}: expectAnyItem {expect_any}에 맞는 항목이 목록에 없음")
                continue

            for var, field in (step.get("capture") or {}).items():
                if var == "__persist":
                    continue
                val = _capture_indexed(page, s, field) if "." in field else _capture_field(page, body, field)
                if val is None:
                    notes.append(f"[{label}] '{var}' capture 실패(필드 {field}) - 이후 스텝이 이 변수를 못 씀")
                else:
                    vars[var] = val

            notes.append(f"[{label}] {method} {path} OK")
        except Exception as e:
            problems.append(f"[{label}] {method} {path}: 예외 발생 {type(e).__name__}: {e}")

    return problems, notes


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--api-spec", default="generated/docs/api_spec.json")
    p.add_argument("--url", required=True, help="프론트 서버 URL (file:// 도 가능)")
    p.add_argument("--backend-url", default=None, help="화면에 폼이 아예 없는 생성 스텝을 API로 직접 seed할 백엔드 URL (예: http://localhost:8080)")
    p.add_argument("--headed", action="store_true")
    args = p.parse_args()

    api_spec = json.loads(open(args.api_spec, encoding="utf-8").read())
    if not (api_spec.get("happyPath") or {}).get("steps"):
        print(json.dumps({"passed": False, "logs": "api_spec에 happyPath.steps가 없음."}, ensure_ascii=False))
        sys.exit(1)

    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not args.headed)
        page = browser.new_page()
        page.goto(args.url)
        problems, notes = run_happy_path(page, api_spec, backend_url=args.backend_url)
        browser.close()

    logs = "\n".join(f"- {n}" for n in notes)
    if problems:
        logs += "\n\n실패:\n" + "\n".join(f"- {p}" for p in problems)
    report = {"passed": not problems, "logs": logs}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    sys.exit(0 if report["passed"] else 1)


_WIDGETS_MOCK_HTML = """
<!doctype html><html><body>
<div data-testid="post-widgets-form">
  <input data-testid="post-widgets-field-name" />
  <input data-testid="post-widgets-field-quantity" type="number" />
  <button data-testid="post-widgets-submit">Add</button>
  <div data-testid="post-widgets-error" style="display:none"></div>
</div>
<div data-testid="get-widgets-list"></div>
<script>
let widgets = [];
let nextId = 1;
function render() {
  const list = document.querySelector('[data-testid="get-widgets-list"]');
  list.innerHTML = '';
  widgets.forEach(w => {
    const item = document.createElement('div');
    item.setAttribute('data-testid', 'get-widgets-item');
    item.innerHTML = `
      <span data-field="id">#${w.id}</span>
      <span data-field="name">${w.name}</span>
      <span data-field="quantity">${w.quantity}</span>
      <input data-testid="put-widgets-id-field-quantity" type="number" />
      <button data-testid="put-widgets-id-submit">Update</button>
      <div data-testid="put-widgets-id-error" style="display:none"></div>
    `;
    list.appendChild(item);
    item.querySelector('[data-testid="put-widgets-id-submit"]').addEventListener('click', () => {
      const errEl = item.querySelector('[data-testid="put-widgets-id-error"]');
      const qty = Number(item.querySelector('[data-testid="put-widgets-id-field-quantity"]').value);
      if (isNaN(qty)) { errEl.textContent = 'invalid'; errEl.style.display = 'block'; return; }
      w.quantity = qty;
      errEl.style.display = 'none'; errEl.textContent = '';
      render();
    });
  });
}
document.querySelector('[data-testid="post-widgets-submit"]').addEventListener('click', () => {
  const errEl = document.querySelector('[data-testid="post-widgets-error"]');
  const name = document.querySelector('[data-testid="post-widgets-field-name"]').value;
  const qty = Number(document.querySelector('[data-testid="post-widgets-field-quantity"]').value);
  if (!name) { errEl.textContent = 'name required'; errEl.style.display = 'block'; return; }
  if (qty < 0) { errEl.textContent = 'quantity must be >= 0'; errEl.style.display = 'block'; return; }
  errEl.style.display = 'none'; errEl.textContent = '';
  widgets.push({id: nextId++, name, quantity: qty});
  render();
});
render();
</script>
</body></html>
"""


if __name__ == "__main__":
    if len(sys.argv) > 1:
        main()
        sys.exit(0)

    assert slug("GET", "/widgets") == "get-widgets"
    assert slug("PUT", "/widgets/{id}") == "put-widgets-id"
    assert slug("GET", "/orders/{orderId}/items") == "get-orders-orderid-items"
    assert has_path_param("/widgets/{id}") is True
    assert has_path_param("/widgets") is False
    assert _endpoint_matches("PUT", "/widgets/{id}", "PUT", "/widgets/999999")
    assert not _endpoint_matches("GET", "/widgets", "GET", "/widgets/1")
    assert substitute("${bookId}", {"bookId": "3"}) == "3"
    assert substitute("/widgets/${id}", {"id": "9"}) == "/widgets/9"
    assert substitute("${nope}", {}) == "${nope}"
    assert _extract_id("#2") == "2"
    assert _extract_id("ID: 42") == "42"
    assert _id_token_from_path("/widgets/{id}", "/widgets/9") == "9"
    assert _id_token_from_path("/members/{id}/points/add", "/members/2/points/add") == "2"

    # self-check: 위젯 픽스처(tests/fixtures/widgets/api_spec.json)를 실제
    # Playwright 브라우저로 file:// 목업 프론트에 돌려서 e2e 스크립트 자체가
    # 맞게 동작하는지 확인한다. 목업은 위 data-testid 컨벤션을 그대로 지킨다.
    import tempfile
    from pathlib import Path

    from playwright.sync_api import sync_playwright

    api_spec = json.loads(Path("tests/fixtures/widgets/api_spec.json").read_text(encoding="utf-8"))

    with tempfile.TemporaryDirectory() as tmp:
        html_path = Path(tmp) / "index.html"
        html_path.write_text(_WIDGETS_MOCK_HTML, encoding="utf-8")

        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page()
            page.goto(html_path.resolve().as_uri())
            problems, notes = run_happy_path(page, api_spec, wait_ms=50)
            browser.close()

    assert problems == [], problems
    assert any("건너뜀" in n for n in notes), notes  # 존재하지 않는 id 스텝은 스킵돼야 함
    assert len([n for n in notes if n.endswith("OK")]) == 4  # 5스텝 중 1개는 스킵

    print("verify_frontend_e2e self-check 통과")
