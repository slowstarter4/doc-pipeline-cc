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
"""

import argparse
import json
import re
import sys

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


def _capture_field(page, body: dict, field: str) -> str | None:
    items = page.locator('[data-testid$="-item"]')
    for i in range(items.count()):
        it = items.nth(i)
        if all(_field_matches(it, k, v) for k, v in body.items() if k != "__persist"):
            val = _field_text(it, field)
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
    for role_testid in (None, "role-buyer", "role-admin"):
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


def run_happy_path(page, api_spec: dict, wait_ms: int = 800) -> tuple[list[str], list[str]]:
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
                scope = form.first if form.count() > 0 else page

            if method.upper() != "GET" or force_submit:
                missing_field = False
                for field, value in body.items():
                    input_loc = scope.locator(f'[data-testid="{s}-field-{field}"]')
                    if input_loc.count() == 0:
                        problems.append(f"[{label}] {method} {path}: 입력 필드 {s}-field-{field}를 못 찾음")
                        missing_field = True
                        continue
                    input_loc.first.fill(str(value))
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
                val = _capture_field(page, body, field)
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
        problems, notes = run_happy_path(page, api_spec)
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
