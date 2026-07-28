"""
생성된 백엔드를 실제로 기동시켜 검증한다 (스모크 + 계약 테스트 + 영속성).

CLI: python scripts/verify_backend.py --target spring --db postgres [--api-spec generated/docs/api_spec.json]

doc-pipeline(OpenRouter판)의 verify_backend 노드를 그대로 이식 - "생성 → 서버 실행
→ curl로 확인 → 실패면 원인 진단"을 자동화한다. LaunchSpec 레지스트리만 스택마다
다르고, 검증 엔진(스모크·영속성·계약테스트)은 스택 무관한 순수 HTTP라 그대로 옮겼다.

오케스트레이터(build-app 스킬)가 gen-backend-*로 코드를 다 쓴 뒤 이 스크립트를
호출한다. 실패하면 stdout에 JSON({"passed": false, "logs": "..."})을 찍고 종료코드
1을 낸다 - 오케스트레이터는 그 logs를 실패한 도메인 조각의 재디스패치 프롬프트에
[이전 시도 실패 로그]로 넣는다.
"""

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import requests

BACKEND_DIR = Path("generated/backend")
TESTS_DIR = Path("generated/tests")
SERVER_LOG = Path("generated/server.log")
STARTUP_TIMEOUT = 20
POLL_INTERVAL = 0.5
TEST_TIMEOUT = 180


@dataclass
class LaunchSpec:
    build: list[list[str]]
    start: list[str]
    port: int
    timeout: float = STARTUP_TIMEOUT
    build_timeout: float = 120
    shell: bool = False
    start_shell: bool = False
    stop_by_port: bool = False


# 스택별 포트. 각 gen-backend-*/SKILL.md의 포트 상수와 반드시 일치해야 한다 -
# 숫자가 갈리면 여기서 붙는 서버와 스킬이 띄운 서버가 서로 다른 곳을 본다.
_PORTS = {"fastapi": 8000, "spring": 8080, "express": 5001, "typescript": 5002}


def _launcher(target: str, db: str) -> "LaunchSpec | None":
    if target == "fastapi":
        return LaunchSpec(
            build=[[sys.executable, "-m", "pip", "install", "-q", "-r", "requirements.txt"]],
            start=[sys.executable, "-m", "uvicorn", "main:app", "--port", str(_PORTS["fastapi"])],
            port=_PORTS["fastapi"],
        )
    if target == "express":
        start = ["node", "server.js"] if db == "postgres" else ["node", "--experimental-sqlite", "server.js"]
        return LaunchSpec(build=[["npm", "install"]], start=start, port=_PORTS["express"], shell=True)
    if target == "typescript":
        start = ["node", "dist/server.js"] if db == "postgres" else ["node", "--experimental-sqlite", "dist/server.js"]
        return LaunchSpec(
            build=[["npm", "install"], ["npm", "run", "build"]],
            start=start, port=_PORTS["typescript"], shell=True,
        )
    if target == "spring":
        # gradlew bootRun이 빌드+기동을 한 번에 한다. 배치파일이라 start_shell 필요,
        # gradle 데몬·java 자식이 포트를 쥐어 terminate로 안 죽으니 stop_by_port로
        # 트리 정리. 첫 빌드는 느려(의존성 다운로드+컴파일) timeout을 크게 잡는다.
        return LaunchSpec(
            build=[], start=[".\\gradlew.bat", "bootRun", "--console=plain"],
            port=_PORTS["spring"], timeout=180, start_shell=True, stop_by_port=True,
        )
    return None


def _wait_for_server(base_url: str, probe_path: str, timeout: float) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            requests.get(f"{base_url}{probe_path}", timeout=1)
            return True
        except requests.exceptions.RequestException:
            time.sleep(POLL_INTERVAL)
    return False


_SAMPLE_BY_TYPE = {"string": "테스트", "number": 1, "boolean": False, "date": "2026-01-01"}


def _plain_get_paths(api_spec: dict) -> list[str]:
    return [
        ep["path"] for ep in api_spec.get("endpoints", [])
        if ep.get("method", "").upper() == "GET" and "{" not in ep.get("path", "")
    ]


def _first_create(api_spec: dict) -> "tuple[str, dict] | None":
    for ep in api_spec.get("endpoints", []):
        if ep.get("method", "").upper() != "POST" or "{" in ep.get("path", ""):
            continue
        request = ep.get("request") or {}
        if not isinstance(request, dict) or not request:
            continue
        # request 필드값은 대개 "string"/"number" 같은 타입 문자열이지만, 배열
        # 필드(예: items: [{"productId": "string", ...}])는 값이 리스트다 - 빈
        # 배열로 채운다. 실제 업무 규칙(빈 배열 거부 등)에 걸려 4xx가 나도
        # 스모크 테스트는 그걸 실패로 안 친다(도메인 규칙 위반은 서버 탓이 아님).
        body = {
            k: ([] if isinstance(v, list) else _SAMPLE_BY_TYPE.get(v, "테스트"))
            for k, v in request.items()
        }
        return ep["path"], body
    return None


def _start_server(spec: LaunchSpec):
    SERVER_LOG.parent.mkdir(parents=True, exist_ok=True)
    log = SERVER_LOG.open("w", encoding="utf-8", errors="replace")
    cmd = " ".join(spec.start) if spec.start_shell else spec.start
    proc = subprocess.Popen(cmd, cwd=BACKEND_DIR, stdout=log, stderr=subprocess.STDOUT, shell=spec.start_shell)
    proc._verify_log = log
    return proc


def _kill_port(port: int) -> None:
    try:
        out = subprocess.run(["netstat", "-ano"], capture_output=True, text=True, timeout=10).stdout
    except Exception:
        return
    pids = {line.split()[-1] for line in out.splitlines() if f":{port} " in line and "LISTENING" in line}
    for pid in pids:
        subprocess.run(["taskkill", "/F", "/T", "/PID", pid], capture_output=True)


def _stop_server(proc, spec: "LaunchSpec | None" = None) -> str:
    if spec is not None and spec.stop_by_port:
        _kill_port(spec.port)
    else:
        proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
    log = getattr(proc, "_verify_log", None)
    if log is not None and not log.closed:
        log.close()
    if not SERVER_LOG.exists():
        return ""
    return SERVER_LOG.read_text(encoding="utf-8", errors="replace")[-4000:]


def _list_ids(payload) -> list:
    items = payload
    if isinstance(payload, dict):
        lists = [v for v in payload.values() if isinstance(v, list)]
        items = lists[0] if lists else []
    if not isinstance(items, list):
        return []
    return [item.get("id") for item in items if isinstance(item, dict)]


# 이 헤더가 있으면 관리자 백오피스로 취급하는 컨벤션(gotchas.md 참고) - 스모크
# 요청도 이 헤더를 보내야 필터 파라미터 없이도 대부분의 목록 GET을 통과한다.
_SMOKE_HEADERS = {"X-User-Type": "ADMIN"}

# GlobalExceptionHandler는 미처리 예외까지 400으로 바꿔서 응답한다(500을 클라이언트에
# 노출하지 않는 설계) - 그래서 진짜 서버 버그(SQL 문법 오류, NPE 등)도 상태코드만
# 보면 "도메인 규칙 거부"와 구분이 안 된다. 메시지에 이런 기술적 예외 흔적이 있으면
# 상태코드가 4xx여도 문제로 친다.
_TECHNICAL_ERROR_MARKERS = (
    "sql grammar", "sqlexception", "nullpointerexception", "preparedstatementcallback",
    "classcastexception", "illegalstateexception", "runtimeexception", "stacktrace",
    "at java.", "at org.springframework", "at com.example",
)


def _looks_like_bug(body_text: str) -> bool:
    lower = body_text.lower()
    return any(marker in lower for marker in _TECHNICAL_ERROR_MARKERS)


def _run_smoke_test(base_url: str, api_spec: dict) -> "tuple[list[str], list[str]]":
    problems, notes = [], []
    get_paths = _plain_get_paths(api_spec)
    if not get_paths:
        notes.append("명세에 path parameter 없는 GET이 없어 조회 검사를 건너뜀.")
    for path in get_paths:
        try:
            r = requests.get(f"{base_url}{path}", headers=_SMOKE_HEADERS, timeout=5)
            if r.status_code >= 500 or _looks_like_bug(r.text):
                problems.append(f"GET {path}: 서버 오류로 보임 (status {r.status_code}, body: {r.text[:300]})")
            elif r.status_code != 200:
                # 필수 쿼리 파라미터(sellerId 등)나 역할 제한 때문일 수 있다 - 명세의
                # rules가 그렇게 요구했다면 이건 서버가 계약대로 도는 것이지 버그가
                # 아니다. POST의 도메인 규칙 거부와 같은 처리.
                notes.append(f"GET {path}가 {r.status_code} 반환 - 필수 파라미터·권한 제약일 수 있어 실패로 치지 않는다 (body: {r.text[:150]})")
        except Exception as e:
            problems.append(f"GET {path} 요청 자체가 실패함: {e}")

    create = _first_create(api_spec)
    if create is None:
        notes.append("명세에 request body가 있는 POST가 없어 생성 검사를 건너뜀.")
        return problems, notes

    path, body = create
    try:
        r = requests.post(f"{base_url}{path}", json=body, headers=_SMOKE_HEADERS, timeout=5)
        if r.status_code in (200, 201):
            notes.append(f"POST {path} 생성 확인됨 (status {r.status_code}).")
        elif r.status_code >= 500 or _looks_like_bug(r.text):
            problems.append(f"POST {path}: 서버 오류로 보임 (status {r.status_code}, body: {r.text[:300]})")
        else:
            notes.append(f"POST {path}가 더미 데이터를 {r.status_code}로 거부함 - 도메인 규칙일 수 있어 실패로 치지 않는다.")
    except Exception as e:
        problems.append(f"POST {path} 중 예외 발생: {e}")
    return problems, notes


def _run_contract_tests(base_url: str) -> "tuple[list[str], list[str]]":
    if os.getenv("RUN_TESTS", "1") == "0":
        return [], ["계약 테스트 실행 꺼짐 (RUN_TESTS=0)."]
    if not any(TESTS_DIR.rglob("test_*.py")):
        return [], [f"{TESTS_DIR}에 테스트 파일이 없어 계약 테스트를 건너뜀."]
    try:
        run = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", str(TESTS_DIR)],
            capture_output=True, text=True, timeout=TEST_TIMEOUT,
            env={**os.environ, "BASE_URL": base_url},
        )
    except subprocess.TimeoutExpired:
        return [f"계약 테스트가 {TEST_TIMEOUT}초 안에 안 끝남."], []
    except Exception as e:
        return [], [f"계약 테스트 실행 불가: {type(e).__name__}: {e}"]

    summary = (run.stdout or "").strip().splitlines()[-1:] or [""]
    if run.returncode == 0:
        return [], [f"계약 테스트 통과 ({summary[0]})"]
    if run.returncode == 5:
        return [], ["계약 테스트가 0개 수집됨 - 건너뜀."]
    return ["계약 테스트 실패:\n" + (run.stdout or "")[-3000:] + (f"\n[stderr]\n{run.stderr[-500:]}" if run.stderr else "")], []


def _check_persistence(base_url: str, api_spec: dict, proc, spec: LaunchSpec):
    create = _first_create(api_spec)
    if create is None:
        return [], ["생성 엔드포인트가 없어 영속성 검사를 건너뜀."], proc

    path, body = create
    new_id = None
    try:
        r = requests.post(f"{base_url}{path}", json=body, headers=_SMOKE_HEADERS, timeout=5)
        if r.status_code in (200, 201):
            new_id = r.json().get("id")
    except Exception:
        pass

    _stop_server(proc, spec)

    if new_id is None:
        note = f"영속성 왕복 검사는 못 함 (더미 데이터가 POST {path}에서 거부됨). 별도로 실제 데이터로 재확인 권장."
        return [], [note], None

    problems = []
    new_proc = _start_server(spec)
    if not _wait_for_server(base_url, path, spec.timeout):
        _stop_server(new_proc, spec)
        problems.append(f"영속성 검사를 위해 서버를 재기동했는데 {spec.timeout}초 안에 안 떴음.")
        return problems, [], None

    try:
        r = requests.get(f"{base_url}{path}", headers=_SMOKE_HEADERS, timeout=5)
        if new_id not in _list_ids(r.json()):
            problems.append("서버를 껐다 켜니 방금 만든 항목이 사라짐 - 데이터를 메모리에만 들고 있다는 뜻이다.")
    except Exception as e:
        problems.append(f"재기동 후 목록 조회 중 예외: {e}")

    return problems, [], new_proc


def verify(target: str, db: str, api_spec: dict) -> dict:
    spec = _launcher(target, db)
    if spec is None:
        return {"passed": True, "logs": f"(자동 검증 미등록 스택: {target})"}

    base_url = f"http://127.0.0.1:{spec.port}"
    proc = None
    try:
        for cmd in spec.build:
            build = subprocess.run(
                " ".join(cmd) if spec.shell else cmd, cwd=BACKEND_DIR,
                capture_output=True, text=True, timeout=spec.build_timeout, shell=spec.shell,
            )
            if build.returncode != 0:
                return {"passed": False, "logs": f"빌드/설치 실패 ({' '.join(cmd)}):\n{build.stderr[-2000:]}"}

        for db_file in BACKEND_DIR.glob("*.db"):
            try:
                db_file.unlink()
            except PermissionError:
                pass

        probe = (_plain_get_paths(api_spec) or ["/"])[0]
        proc = _start_server(spec)

        if not _wait_for_server(base_url, probe, spec.timeout):
            stderr = _stop_server(proc, spec)
            return {"passed": False, "logs": f"서버가 {spec.timeout}초 안에 기동하지 못함. stderr:\n{stderr[-2000:]}"}

        problems, notes = _run_smoke_test(base_url, api_spec)
        if problems:
            return {"passed": False, "logs": "스모크 테스트 실패:\n" + "\n".join(f"- {p}" for p in problems)}

        test_problems, test_notes = _run_contract_tests(base_url)
        if test_problems:
            return {"passed": False, "logs": "\n".join(test_problems)}
        notes += test_notes

        problems, persist_notes, proc = _check_persistence(base_url, api_spec, proc, spec)
        if problems:
            return {"passed": False, "logs": "영속성 검사 실패:\n" + "\n".join(f"- {p}" for p in problems)}

        logs = [f"스모크 테스트 통과 (조회 {len(_plain_get_paths(api_spec))}개 경로 확인)"]
        logs += [f"- {n}" for n in notes + persist_notes]
        return {"passed": True, "logs": "\n".join(logs)}

    except Exception as e:
        import traceback
        return {"passed": False, "logs": f"verify 실행 중 예외: {type(e).__name__}: {e}\n{traceback.format_exc()[-2000:]}"}

    finally:
        if proc is not None and proc.poll() is None:
            _stop_server(proc, spec)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--target", required=True, choices=list(_PORTS.keys()))
    p.add_argument("--db", default="sqlite", choices=["sqlite", "postgres"])
    p.add_argument("--api-spec", default="generated/docs/api_spec.json")
    args = p.parse_args()

    api_spec = json.loads(open(args.api_spec, encoding="utf-8").read())
    report = verify(args.target, args.db, api_spec)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    sys.exit(0 if report["passed"] else 1)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        main()
        sys.exit(0)

    assert _list_ids([{"id": 1}, {"id": 2}]) == [1, 2]
    assert _list_ids({"todos": [{"id": 3}]}) == [3]
    assert _list_ids({}) == []
    assert _list_ids(None) == []

    spec = {
        "endpoints": [
            {"method": "GET", "path": "/books"},
            {"method": "GET", "path": "/books/{id}"},
            {"method": "POST", "path": "/books", "request": {"title": "string", "count": "number"}},
        ]
    }
    assert _plain_get_paths(spec) == ["/books"]
    assert _first_create(spec) == ("/books", {"title": "테스트", "count": 1})
    assert _launcher("spring", "postgres").port == 8080
    assert _launcher("unknown-stack", "sqlite") is None

    # request에 배열 필드(예: items)가 있어도 죽지 않고 빈 배열로 채워야 한다.
    array_spec = {"endpoints": [{"method": "POST", "path": "/orders", "request": {"buyerId": "string", "items": [{"productId": "string"}]}}]}
    assert _first_create(array_spec) == ("/orders", {"buyerId": "테스트", "items": []})

    # 도메인 규칙 거부(400, 깨끗한 메시지)와 진짜 서버 버그(400인데 SQL/스택트레이스
    # 흔적)를 상태코드만으로 구분 못 하므로, 메시지 내용으로 버그를 잡아야 한다.
    assert _looks_like_bug('{"detail":"buyerId는 필수입니다"}') is False
    assert _looks_like_bug('{"detail":"bad SQL grammar [SELECT ...]"}') is True
    assert _looks_like_bug('{"detail":"java.lang.NullPointerException"}') is True

    print("verify_backend self-check 통과")
