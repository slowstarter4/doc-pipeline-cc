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


def _extract_calls(text: str) -> set:
    return {_normalize(m) for m in _TEMPLATE_URL_RE.findall(text) + _FETCH_RE.findall(text)}


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

    called = set()
    texts = []
    for src in sources:
        text = src.read_text(encoding="utf-8")
        texts.append(text)
        called |= _extract_calls(text)

    spec_paths = {_normalize(ep["path"]) for ep in api_spec.get("endpoints", [])}
    unknown = sorted(called - spec_paths)
    unused = sorted(spec_paths - called)

    logs = []
    if not called:
        logs.append("API 호출을 하나도 못 찾음 - 프론트가 백엔드를 안 부르고 있거나 URL을 리터럴로 안 씀.")
    if unknown:
        logs.append("명세에 없는 경로를 호출함 (계약 위반):\n" + "\n".join(f"  - {p}" for p in unknown))
    if unused:
        logs.append("명세에 있지만 화면에서 안 쓰는 경로 (참고):\n" + "\n".join(f"  - {p}" for p in unused))
    if not logs:
        logs.append(f"명세의 경로 {len(spec_paths)}개를 모두 정확히 호출함.")

    sources_text = "\n".join(texts)
    shape_logs, shape_ok = _check_response_shape(api_spec, sources_text)
    logs += shape_logs
    logs += _check_design_tokens(sources_text, design_target)

    return {"passed": bool(called) and not unknown and shape_ok, "logs": "\n".join(logs)}


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

    print("verify_frontend self-check 통과")
