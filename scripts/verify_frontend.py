"""
생성된 프론트엔드가 계약(api_spec)대로 호출하는지 검사한다. LLM 미사용.

CLI: python scripts/verify_frontend.py --api-spec generated/docs/api_spec.json [--design-target commerce-modernist]

doc-pipeline(OpenRouter판)의 verify_frontend 노드를 그대로 이식 - 정적 파일이라
서버를 안 띄우고 fetch() 호출 경로를 정규식으로 뽑아 api_spec과 대조한다.
같은 입력엔 항상 같은 결과가 나와야 하므로 규칙 기반 코드로만 짰다(LLM 미사용).

검사 3종: ①호출 경로 ↔ api_spec 경로 ②응답 모양(목록 wrapper key를 프론트가
푸는지) ③디자인 토큰 색. ①②는 계약이라 passed에 반영, ③은 진단만.
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

FRONTEND_OUT_DIR = Path("generated/frontend")
DESIGN_DIR = Path("design")

SOURCE_SUFFIXES = {".html", ".js", ".jsx", ".ts", ".tsx", ".css"}
IGNORED_DIRS = {"node_modules", "dist", "build", ".vite"}

_TEMPLATE_URL_RE = re.compile(r"`([^`]*\$\{\s*BASE\s*\}[^`]*)`")
_FETCH_RE = re.compile(r"""fetch\(\s*['"]([^'"]*)['"]""")
_METHOD_KEY_RE = re.compile(r"""method\s*:\s*['"`](GET|POST|PUT|PATCH|DELETE)['"`]""", re.IGNORECASE)
_AXIOS_VERB_RE = re.compile(r"""axios\s*\.\s*(get|post|put|patch|delete)\s*\(\s*$""", re.IGNORECASE)
_ASSIGNMENT_RE = re.compile(r"[=(]\s*$")  # 뒤에 오는 게 아니라 앞쪽 문맥 확인용
_VALID_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}


def _is_ignored(path: Path) -> bool:
    return any(part in IGNORED_DIRS for part in path.parts)


def _normalize(path: str) -> str:
    p = re.sub(r"\$\{\s*BASE\s*\}", "", path)
    p = re.sub(r"^https?://[^/]*", "", p)
    p = re.sub(r"(?<=/)\$\{[^}]*\}", "{}", p)
    p = re.split(r"\$\{", p)[0]
    p = re.split(r"[?#]", p)[0]
    p = re.sub(r"\{[^}]*\}", "{}", p)
    p = "/" + p.strip("/")
    return p


def _strip_comments(text: str) -> str:
    """주석(`//`, `/* */`, `<!-- -->`)만 걷어내고 문자열 리터럴은 그대로 둔다.

    왜 필요한가: 경로 추출이 원문을 통째로 훑으면 **주석에 적힌 예시 URL도
    실제 호출로 오인**한다 - 프론트 에이전트가 주석에 `` `${BASE}/...` `` 예시를
    썼다가 "명세에 없는 경로 호출(계약 위반)"로 잡혀 검사가 실패한 사례가
    두 번 있었다(2026-07-29). 반대로 정규식으로 대충 주석을 지우면
    `const BASE = "http://localhost:8080"`의 `//`에서 줄이 잘려 진짜 호출을
    놓친다(오탐보다 나쁜 미탐). 그래서 문자열 안/밖을 구분하는 작은 스캐너로
    처리한다 - 정규식으로는 이 구분이 안 된다.
    """
    out = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c in ('"', "'", "`"):  # 문자열·템플릿 리터럴은 통째로 보존
            out.append(c)
            i += 1
            while i < n:
                if text[i] == "\\":       # 이스케이프는 두 글자를 한 번에
                    out.append(text[i:i + 2])
                    i += 2
                    continue
                out.append(text[i])
                i += 1
                if text[i - 1] == c:
                    break
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                i += 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "*":
            end = text.find("*/", i + 2)
            i = n if end == -1 else end + 2
            continue
        if text.startswith("<!--", i):
            end = text.find("-->", i + 4)
            i = n if end == -1 else end + 3
            continue
        out.append(c)
        i += 1
    return "".join(out)


def _extract_calls(text: str) -> set:
    text = _strip_comments(text)
    return {_normalize(m) for m in _TEMPLATE_URL_RE.findall(text) + _FETCH_RE.findall(text)}


def _preceding_kind(text: str, start: int) -> str:
    """매칭된 URL 리터럴 바로 앞 문맥을 본다 - `fetch(url, ...)`/`axios.post(url)`처럼
    호출의 인자로 바로 쓰였는지(call), `const url = ...`처럼 변수에 먼저 담겼는지
    (assign, method를 나중 문장에서 찾아야 해서 정적 분석으로는 못 쫓아간다) 구분한다."""
    j = start
    while j > 0 and text[j - 1] in " \t\n\r":
        j -= 1
    if j == 0:
        return "call"
    ch = text[j - 1]
    if ch in "(,":
        return "call"
    if ch == "=" and (j < 2 or text[j - 2] not in "=!<>"):
        return "assign"
    return "other"


def _extract_call_sites(text: str) -> list:
    """호출마다 (method, path, certain)을 뽑는다. `certain=False`는 URL이 변수를
    거치는 등 그 자리에서 method를 못 정하는 경우 - 조용히 GET으로 단정하지 않고
    '검증 불가'로 따로 보고한다."""
    text = _strip_comments(text)
    sites = []
    for regex in (_TEMPLATE_URL_RE, _FETCH_RE):
        for m in regex.finditer(text):
            path = _normalize(m.group(1))
            if _preceding_kind(text, m.start()) != "call":
                sites.append({"path": path, "method": None, "certain": False})
                continue
            window_before = text[max(0, m.start() - 40):m.start()]
            axios_m = _AXIOS_VERB_RE.search(window_before)
            if axios_m:
                sites.append({"path": path, "method": axios_m.group(1).upper(), "certain": True})
                continue
            window_after = text[m.end():m.end() + 400]
            stop = window_after.find(";")
            if stop != -1:
                window_after = window_after[:stop]
            method_m = _METHOD_KEY_RE.search(window_after)
            method = method_m.group(1).upper() if method_m else "GET"
            sites.append({"path": path, "method": method, "certain": True})
    return sites


def _list_wrapper_keys(api_spec: dict) -> set:
    keys = set()
    for ep in api_spec.get("endpoints", []):
        resp = ep.get("response")
        if isinstance(resp, dict):
            keys |= {k for k, v in resp.items() if isinstance(v, list)}
    return keys


def _check_response_shape(api_spec: dict, sources_text: str):
    keys = _list_wrapper_keys(api_spec)
    if not keys:
        return [], True
    missing = sorted(k for k in keys if not re.search(rf"\b{re.escape(k)}\b", sources_text))
    if missing:
        return (
            ["응답 모양 불일치 가능 (경로는 맞지만 wrapper key를 안 씀): 목록 응답을 "
             + ", ".join(f"'{k}'" for k in missing) + " 키로 감싸는데 프론트 소스에 없다."],
            False,
        )
    return [f"목록 응답 wrapper key {len(keys)}개 전부 프론트에서 참조됨."], True


def _design_system_path(design_target: str | None) -> Path:
    if not design_target:
        return DESIGN_DIR / "design_system.md"
    presets_dir = DESIGN_DIR / "presets"
    names = {p.stem for p in presets_dir.glob("*.md")} if presets_dir.exists() else set()
    if design_target not in names:
        raise SystemExit(f"디자인 프리셋 '{design_target}' 없음. 사용 가능: {sorted(names)}")
    return presets_dir / f"{design_target}.md"


def _token_colors(design_target: str | None) -> list:
    path = _design_system_path(design_target)
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    return sorted({m.lower() for m in re.findall(r"#[0-9a-fA-F]{6}\b", text)})


def _check_design_tokens(sources_text: str, design_target: str | None) -> list:
    colors = _token_colors(design_target)
    if not colors:
        return []
    lowered = sources_text.lower()
    missing = [c for c in colors if c not in lowered]
    used = len(colors) - len(missing)
    if used == 0:
        return [f"디자인 토큰의 색 {len(colors)}개가 하나도 안 쓰임: {', '.join(colors)}"]
    if missing:
        return [f"디자인 토큰 색 {used}/{len(colors)}개 사용됨. 안 쓰인 색: {', '.join(missing)}"]
    return [f"디자인 토큰 색 {len(colors)}개 전부 사용됨."]


def verify(api_spec: dict, design_target: str | None = None) -> dict:
    sources = [p for p in FRONTEND_OUT_DIR.glob("**/*") if p.suffix in SOURCE_SUFFIXES and not _is_ignored(p)]
    if not sources:
        return {"passed": False, "logs": f"{FRONTEND_OUT_DIR}에 html/js 파일이 없음."}

    sites = []
    texts = []
    for src in sources:
        text = src.read_text(encoding="utf-8")
        texts.append(text)
        sites += _extract_call_sites(text)

    spec_pairs = {(ep.get("method", "").upper(), _normalize(ep["path"])) for ep in api_spec.get("endpoints", [])}
    spec_paths = {p for _, p in spec_pairs}

    known_calls = {(s["method"], s["path"]) for s in sites if s["certain"]}
    uncertain_paths = sorted({s["path"] for s in sites if not s["certain"]})
    called = known_calls | {(None, p) for p in uncertain_paths}

    method_mismatch = sorted((m, p) for m, p in known_calls if p in spec_paths and (m, p) not in spec_pairs)
    unknown = sorted((m, p) for m, p in known_calls if p not in spec_paths)
    # 불확실한 호출로만 쓰인 경로는 "안 쓰는 경로"로 잘못 보고하지 않는다.
    unused = sorted(pair for pair in spec_pairs if pair not in known_calls and pair[1] not in uncertain_paths)

    logs = []
    if not called:
        logs.append("API 호출을 하나도 못 찾음 - 프론트가 백엔드를 안 부르고 있거나 URL을 리터럴로 안 씀.")
    if method_mismatch:
        logs.append(
            "경로는 맞지만 HTTP method가 명세와 다름 (계약 위반):\n"
            + "\n".join(f"  - {m} {p}" for m, p in method_mismatch)
        )
    if unknown:
        logs.append(
            "명세에 없는 경로/method 조합을 호출함 (계약 위반):\n"
            + "\n".join(f"  - {m} {p}" for m, p in unknown)
        )
    if uncertain_paths:
        logs.append(
            "검증 불가 (URL이 변수를 거치거나 동적으로 조립돼 method를 못 정함 - 수동 확인 필요):\n"
            + "\n".join(f"  - {p}" for p in uncertain_paths)
        )
    if unused:
        logs.append(
            "명세에 있지만 화면에서 안 쓰는 경로 (참고):\n"
            + "\n".join(f"  - {m} {p}" for m, p in unused)
        )
    if not method_mismatch and not unknown and not uncertain_paths and not unused:
        logs.append(f"명세의 경로 {len(spec_pairs)}개를 모두 정확히 (method 포함) 호출함.")

    # wrapper key·디자인 토큰 검사도 주석을 뺀 본문으로 본다 - 주석에만 적힌
    # 키를 "쓰고 있다"고 오판하면 거짓 통과가 되어 경로 오탐보다 더 위험하다.
    sources_text = _strip_comments("\n".join(texts))
    shape_logs, shape_ok = _check_response_shape(api_spec, sources_text)
    logs += shape_logs
    logs += _check_design_tokens(sources_text, design_target)

    passed = bool(called) and not unknown and not method_mismatch and shape_ok
    return {"passed": passed, "logs": "\n".join(logs)}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--api-spec", default="generated/docs/api_spec.json")
    p.add_argument("--design-target", default=os.getenv("DESIGN_TARGET") or None)
    args = p.parse_args()
    api_spec = json.loads(open(args.api_spec, encoding="utf-8").read())
    report = verify(api_spec, args.design_target)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    sys.exit(0 if report["passed"] else 1)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        main()
        sys.exit(0)

    assert _normalize("${BASE}/todos/${id}") == "/todos/{}"
    assert _normalize("/todos/{id}") == "/todos/{}"
    assert _normalize("http://localhost:8000/todos?done=1") == "/todos"
    assert _normalize("${BASE}/books${qs ? '?' + qs : ''}") == "/books"

    html = """
      fetch(`${BASE}/todos`);
      fetch(`${BASE}/todos/${id}/complete`, {method: "PUT"});
      fetch('/api/legacy');
    """
    assert _extract_calls(html) == {"/todos", "/todos/{}/complete", "/api/legacy"}

    wrapped = """
      async function safeFetch(url, options) { return fetch(url, options); }
      const books = await safeFetch(`${BASE}/books`, undefined, setError);
    """
    assert _extract_calls(wrapped) == {"/books"}

    # 주석에 적힌 예시 URL은 실제 호출이 아니다 - 셋 다 무시돼야 한다.
    commented = """
      // 목록은 `${BASE}/fake-line`으로 부른다
      /* 상세는 `${BASE}/fake-block` 이었다 */
      <!-- `${BASE}/fake-html` -->
      fetch(`${BASE}/books`);
    """
    assert _extract_calls(commented) == {"/books"}

    # 반대로 문자열 안의 `//`(BASE 상수 등)에서 줄이 잘리면 진짜 호출을 놓친다 -
    # 오탐보다 나쁜 미탐이라 여기가 핵심이다.
    with_base = """
      const BASE = "http://localhost:8080"; // 백엔드 주소
      fetch(`${BASE}/members`);
    """
    assert _extract_calls(with_base) == {"/members"}
    assert 'http://localhost:8080' in _strip_comments(with_base)
    assert '백엔드 주소' not in _strip_comments(with_base)

    # 이스케이프된 따옴표가 문자열을 조기 종료시키면 그 뒤가 통째로 어긋난다.
    escaped = r"""
      const msg = "그는 \"안녕\" 이라 했다"; // 주석
      fetch(`${BASE}/loans`);
    """
    assert _extract_calls(escaped) == {"/loans"}

    lib_spec = {
        "endpoints": [
            {"method": "GET", "path": "/books", "response": {"books": [{"id": "number"}]}},
            {"method": "POST", "path": "/books", "response": {"id": "number"}},
        ]
    }
    assert _list_wrapper_keys(lib_spec) == {"books"}
    ok_src = "const {books} = await res.json();"
    logs, ok = _check_response_shape(lib_spec, ok_src)
    assert ok
    bad_src = "const d = data.items;"
    logs, ok = _check_response_shape(lib_spec, bad_src)
    assert not ok

    assert _is_ignored(Path("generated/frontend/node_modules/react/index.js"))
    assert not _is_ignored(Path("generated/frontend/src/App.jsx"))

    # method 추출: 옵션에 명시가 없으면 GET, 있으면 그 값.
    method_html = """
      fetch(`${BASE}/todos`);
      fetch(`${BASE}/todos/${id}/complete`, {method: "PUT"});
      axios.post(`${BASE}/books`, body);
      axios.delete(`${BASE}/books/${id}`);
    """
    sites = _extract_call_sites(method_html)
    got = {(s["method"], s["path"]) for s in sites if s["certain"]}
    assert got == {
        ("GET", "/todos"),
        ("PUT", "/todos/{}/complete"),
        ("POST", "/books"),
        ("DELETE", "/books/{}"),
    }

    # URL이 변수에 먼저 담기면 method를 못 정하니 uncertain으로 분리돼야 한다.
    indirect_html = """
      const url = `${BASE}/orders`;
      fetch(url, {method: "POST"});
    """
    indirect_sites = _extract_call_sites(indirect_html)
    assert any(s["path"] == "/orders" and not s["certain"] for s in indirect_sites)

    # verify(): 명세는 POST /orders인데 프론트가 GET으로 부르면 실패해야 한다.
    order_spec = {"endpoints": [{"method": "POST", "path": "/orders"}]}
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        FRONTEND_OUT_DIR = Path(tmp)
        (FRONTEND_OUT_DIR / "app.js").write_text(
            'fetch(`${BASE}/orders`);', encoding="utf-8"
        )
        mismatch_report = verify(order_spec)
        assert mismatch_report["passed"] is False
        assert "method" in mismatch_report["logs"]

        (FRONTEND_OUT_DIR / "app.js").write_text(
            'fetch(`${BASE}/orders`, {method: "POST"});', encoding="utf-8"
        )
        ok_report = verify(order_spec)
        assert ok_report["passed"] is True

    print("verify_frontend self-check 통과")
