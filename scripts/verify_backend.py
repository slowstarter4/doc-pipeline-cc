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
import re
import socket
import sqlite3
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

import requests

BACKEND_DIR = Path("generated/backend")
TESTS_DIR = Path("generated/tests")
SERVER_LOG = Path("generated/server.log")
STARTUP_TIMEOUT = 20
POLL_INTERVAL = 0.5
TEST_TIMEOUT = 180

# gen_fastapi_scaffold.py/gen_express_scaffold.py가 생성 백엔드에 박아넣는 것과
# 같은 고정값(db/docker-compose.yml 참고) - 여기서도 그대로 접속해 happyPath
# fixture를 시딩한다.
_POSTGRES_URL = "postgresql://doc:doc@localhost:55432/doc"


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


def _port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


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


def _list_ids(payload, id_field: str = "id") -> list:
    items = payload
    if isinstance(payload, dict):
        lists = [v for v in payload.values() if isinstance(v, list)]
        items = lists[0] if lists else []
    if not isinstance(items, list):
        return []
    return [item.get(id_field) for item in items if isinstance(item, dict)]


def _id_field_name(api_spec: dict, method: str, path: str) -> str:
    """응답 스키마에서 id 역할을 하는 필드명을 찾는다. api_spec 컨벤션상 응답이
    항상 `id`인 건 아니다(예: 주문은 `orderId`) - 'id'가 있으면 그걸 쓰고, 없으면
    '...Id'로 끝나는 첫 필드를 쓴다. 못 찾으면 관례상 'id'로 폴백한다."""
    for ep in api_spec.get("endpoints", []):
        if ep.get("method", "").upper() != method.upper() or ep.get("path") != path:
            continue
        response = ep.get("response") or {}
        fields = response
        for v in response.values():
            if isinstance(v, list) and v and isinstance(v[0], dict):
                fields = v[0]
                break
        if "id" in fields:
            return "id"
        for k in fields:
            if k.lower().endswith("id"):
                return k
    return "id"


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
    # node/express + pg(postgres), fastapi/psycopg 계열
    "does not exist", "syntax error at or near", "typeerror", "referenceerror",
    "cannot read propert", "undefined is not", "at object.<anonymous>",
    "traceback (most recent call last)",
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


def _seed_rows(db: str, seed: list[dict]) -> str | None:
    """happyPath fixture의 seed 로우를 DB에 직접 심는다. 실패하면 에러 메시지
    문자열을 돌려주고(None이면 성공), 항상 unquoted identifier로 쓴다 - postgres는
    unquoted면 대소문자와 무관하게 항상 소문자로 접어서 schema.sql이 만든 실제
    테이블과 저절로 맞는다(gotchas.md의 quoted identifier 함정을 안 밟는다)."""
    try:
        if db == "sqlite":
            db_files = list(BACKEND_DIR.glob("*.db"))
            if not db_files:
                return "happyPath 시딩 실패: sqlite db 파일을 못 찾음(서버가 아직 스키마를 안 만들었을 수 있음)."
            conn = sqlite3.connect(db_files[0])
            try:
                for row in seed:
                    cols = list(row["columns"].keys())
                    placeholders = ", ".join(["?"] * len(cols))
                    conn.execute(
                        f"INSERT INTO {row['table']} ({', '.join(cols)}) VALUES ({placeholders})",
                        [row["columns"][c] for c in cols],
                    )
                conn.commit()
            finally:
                conn.close()
        else:
            import psycopg

            conn = psycopg.connect(_POSTGRES_URL)
            try:
                for row in seed:
                    cols = list(row["columns"].keys())
                    placeholders = ", ".join(["%s"] * len(cols))
                    conn.execute(
                        f"INSERT INTO {row['table']} ({', '.join(cols)}) VALUES ({placeholders})",
                        [row["columns"][c] for c in cols],
                    )
                conn.commit()
            finally:
                conn.close()
    except Exception as e:
        return f"happyPath 시딩 중 예외: {type(e).__name__}: {e}"
    return None


_PLACEHOLDER_RE = re.compile(r"\$\{(\w+)\}")


def _substitute(value, vars: dict):
    """문자열 안의 `${varname}`을 앞선 스텝이 capture한 값으로 바꾼다.
    문자열 전체가 딱 하나의 placeholder면 원래 타입(숫자 등)을 그대로 살린다 -
    `"${bookId}"`가 문자열 "3"이 아니라 숫자 3으로 들어가야 하는 백엔드가 있다."""
    if isinstance(value, str):
        exact = _PLACEHOLDER_RE.fullmatch(value)
        if exact:
            return vars.get(exact.group(1), value)
        return _PLACEHOLDER_RE.sub(lambda m: str(vars.get(m.group(1), m.group(0))), value)
    if isinstance(value, dict):
        return {k: _substitute(v, vars) for k, v in value.items()}
    if isinstance(value, list):
        return [_substitute(v, vars) for v in value]
    return value


def _first_list(payload):
    """응답에서 목록을 꺼낸다 - 그대로 배열이거나 wrapper dict({"loans": [...]}) 둘 다."""
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for v in payload.values():
            if isinstance(v, list):
                return v
    return []


def _legacy_to_steps(happy: dict) -> dict:
    """구버전 fixture(targetPath/body 하나짜리)를 스텝 1개로 감싼다 - 예전
    api_spec.json이 남아 있어도 조용히 건너뛰지 않고 그대로 검증되게 한다."""
    if "steps" in happy or "targetPath" not in happy:
        return happy
    return {
        "seed": happy.get("seed") or [],
        "steps": [{
            "name": "생성",
            "method": happy.get("targetMethod", "POST"),
            "path": happy["targetPath"],
            "body": happy.get("body"),
            "headers": happy.get("headers"),
            "expect": [200, 201],
            "capture": {"__persist": "id"},
        }],
    }


def _run_happy_path(base_url: str, api_spec: dict, db: str):
    """api_spec.happyPath 시나리오를 순서대로 실행한다.

    단발 생성 호출만 하던 예전 버전은 "정상 플로우가 되는가"를 사실상 검증하지
    못했다 - fixture 대상이 '명세의 첫 POST'로 정해져 있어서, 도메인의 핵심
    상태전이(대출→연체→반납→제재 같은 것)는 한 번도 안 타고 가장 단순한
    등록 엔드포인트만 찔렀다(실측 2026-07-29 library 도메인: 8개 중 4개만
    호출, 로직이 있는 4개는 전부 미검증). 그래서 스텝 배열로 바꿨다:
    앞 스텝의 응답에서 값을 capture해 뒤 스텝의 path/body에 `${var}`로 꽂아,
    실제 사용 순서대로 여러 엔드포인트를 엮어 때린다.

    스텝 하나의 형식:
      {"name": "대출", "method": "POST", "path": "/loans",
       "body": {"memberId": "${memberId}"}, "headers": {...},
       "expect": 201 (또는 [200,201]),
       "capture": {"loanId": "id"},          # 응답 필드 → 변수
       "expectAnyItem": {"overdue": true}}   # 목록 응답에 이런 항목이 있어야 함

    `expect`에 4xx를 적으면 '거부되어야 정상'인 케이스도 검증할 수 있다(예:
    제재 중 재대출이 409로 막히는지) - 통과 케이스만 보면 규칙이 아예 구현
    안 돼 있어도 초록불이 뜬다.

    fixture가 없으면 건너뛰되 그 사실을 note로 남긴다(통과로 위장하지 않는다).
    있는데 실패하면 하드 실패 - fixture는 통과하도록 설계된 값이라 "도메인
    규칙일 수 있다"는 여지가 없다."""
    happy = api_spec.get("happyPath")
    if not happy:
        return [], ["api_spec에 happyPath fixture가 없어 정상 플로우를 못 씀 (구버전 api_spec일 수 있음)."], None
    happy = _legacy_to_steps(happy)

    steps = happy.get("steps") or []
    if not steps:
        return ["happyPath fixture에 steps가 없다."], [], None

    seed = happy.get("seed") or []
    if seed:
        err = _seed_rows(db, seed)
        if err:
            return [err], [], None

    vars: dict = {}
    notes = []
    persist: "tuple[str, object, str] | None" = None

    for i, step in enumerate(steps, 1):
        label = step.get("name") or f"스텝 {i}"
        method = step.get("method", "POST").upper()
        path = _substitute(step.get("path", ""), vars)
        body = _substitute(step.get("body"), vars) if step.get("body") is not None else None
        # Idempotency-Key는 이 레포 생성 엔드포인트에 흔한 요구사항이라 매번 새로
        # 붙인다(안 쓰는 구현이면 무시될 뿐). fixture headers가 기본 헤더를 덮는다.
        headers = {**_SMOKE_HEADERS, **(step.get("headers") or {}), "Idempotency-Key": str(uuid.uuid4())}
        expect = step.get("expect", [200, 201])
        expect = [expect] if isinstance(expect, int) else list(expect)

        try:
            r = requests.request(method, f"{base_url}{path}", json=body, headers=headers, timeout=5)
        except Exception as e:
            return [f"[{label}] {method} {path} 요청 자체가 실패함: {e}"], notes, None

        if r.status_code not in expect:
            return [
                f"[{label}] {method} {path}: {expect} 를 기대했는데 {r.status_code} 반환 "
                f"(body: {r.text[:400]})"
            ], notes, None
        if _looks_like_bug(r.text):
            return [
                f"[{label}] {method} {path}: 상태코드는 {r.status_code}로 기대와 맞지만 "
                f"응답에 기술적 예외 흔적이 있다 (body: {r.text[:400]})"
            ], notes, None

        try:
            payload = r.json()
        except Exception:
            payload = None

        want = step.get("expectAnyItem")
        if want:
            items = _first_list(payload)
            if not any(all(item.get(k) == v for k, v in want.items()) for item in items if isinstance(item, dict)):
                return [
                    f"[{label}] {method} {path}: 응답 목록에 {want} 인 항목이 없다 "
                    f"(계산 필드가 안 채워졌거나 규칙이 반영 안 됐을 수 있음. body: {r.text[:400]})"
                ], notes, None

        for var, field in (step.get("capture") or {}).items():
            got = payload.get(field) if isinstance(payload, dict) else None
            if got is None:
                return [
                    f"[{label}] {method} {path}: 응답에서 '{field}'를 못 찾아 "
                    f"'{var}'를 capture할 수 없다 (body: {r.text[:400]})"
                ], notes, None
            if var == "__persist":
                # 재기동 후에도 남아있는지 확인할 대상(첫 생성 스텝 하나면 충분).
                if persist is None:
                    persist = (path, got, field)
            else:
                vars[var] = got

        notes.append(f"happyPath [{label}] {method} {path} → {r.status_code} OK")

    return [], notes, persist


def _check_persistence(base_url: str, api_spec: dict, proc, spec: LaunchSpec, db: str, precreated: "tuple[str, object, str] | None" = None):
    if precreated is not None:
        path, new_id, id_field = precreated
    else:
        # happyPath fixture가 없던 구버전 경로 - 더미 데이터로 대체(예전 그대로,
        # 4xx 거부는 실패로 안 침 - 그 값이 뭘 뜻하는지 알 방법이 없어서다).
        create = _first_create(api_spec)
        if create is None:
            return [], ["생성 엔드포인트가 없어 영속성 검사를 건너뜀."], proc
        path, body = create
        id_field = _id_field_name(api_spec, "POST", path)
        new_id = None
        try:
            r = requests.post(f"{base_url}{path}", json=body, headers=_SMOKE_HEADERS, timeout=5)
            if r.status_code in (200, 201):
                new_id = r.json().get(id_field)
        except Exception:
            pass

    _stop_server(proc, spec)

    if new_id is None:
        note = f"영속성 왕복 검사는 못 함 (POST {path}에서 데이터를 못 만듦). 별도로 실제 데이터로 재확인 권장."
        return [], [note], None

    problems = []
    new_proc = _start_server(spec)
    if not _wait_for_server(base_url, path, spec.timeout):
        _stop_server(new_proc, spec)
        problems.append(f"영속성 검사를 위해 서버를 재기동했는데 {spec.timeout}초 안에 안 떴음.")
        return problems, [], None

    try:
        r = requests.get(f"{base_url}{path}", headers=_SMOKE_HEADERS, timeout=5)
        if new_id not in _list_ids(r.json(), id_field):
            problems.append("서버를 껐다 켜니 방금 만든 항목이 사라짐 - 데이터를 메모리에만 들고 있다는 뜻이다.")
    except Exception as e:
        problems.append(f"재기동 후 목록 조회 중 예외: {e}")

    return problems, [], new_proc


def verify(target: str, db: str, api_spec: dict) -> dict:
    spec = _launcher(target, db)
    if spec is None:
        return {"passed": True, "logs": f"(자동 검증 미등록 스택: {target})"}

    base_url = f"http://127.0.0.1:{spec.port}"

    # 포트가 이미 쓰이고 있으면 그게 우리가 띄운 서버인지 남의 프로세스인지 알 방법이
    # 없다. stop_by_port(spring 등)는 정리할 때 그 포트를 쥔 프로세스를 통째로
    # taskkill하므로, 우리가 안 띄운 프로세스를 잘못 죽이지 않으려면 시작 전에
    # 포트가 비어있다는 걸 확인해야 한다 - 이 사전 체크가 있어야 이후 그 포트에
    # 나타나는 프로세스는 전부 우리가 띄운 것이라고 안전하게 가정할 수 있다.
    if _port_in_use(spec.port):
        return {
            "passed": False,
            "logs": f"포트 {spec.port}이 이미 사용 중입니다 - 다른 프로세스가 떠 있을 "
            "수 있어 검증을 건너뜁니다(남의 프로세스를 잘못 종료하지 않기 위함). "
            "그 포트를 쓰는 프로세스를 직접 확인/종료한 뒤 재실행하세요.",
        }

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

        # happyPath: fixture로 "진짜 통과하는" 생성 1건을 검증한다 - 더미 데이터는
        # FK/재고 같은 선행조건이 없어 거부되기 쉬워 정상 플로우 자체가 안 됐는지를
        # 못 잡았다(스모크의 POST 검사는 4xx를 "도메인 규칙일 수 있음"으로 봐준다).
        # fixture가 있는데 실패하면 하드 실패 - fixture는 통과하도록 설계된 값이다.
        hp_problems, hp_notes, precreated = _run_happy_path(base_url, api_spec, db)
        if hp_problems:
            return {
                "passed": False,
                "logs": "happyPath 검증 실패:\n" + "\n".join(f"- {p}" for p in hp_problems)
                + ("\n[여기까지는 통과]\n" + "\n".join(f"- {n}" for n in hp_notes) if hp_notes else ""),
            }
        notes += hp_notes

        test_problems, test_notes = _run_contract_tests(base_url)
        if test_problems:
            return {"passed": False, "logs": "\n".join(test_problems)}
        notes += test_notes
        problems, persist_notes, proc = _check_persistence(base_url, api_spec, proc, spec, db, precreated)
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

    # happyPath fixture가 없는 (구버전) api_spec은 실패로 안 치고 note만 남긴다 -
    # DB/서버 없이도 이 분기는 순수하게 검사할 수 있다.
    hp_problems, hp_notes, hp_persist = _run_happy_path("http://x", {}, "sqlite")
    assert hp_problems == [] and hp_persist is None
    assert "happyPath" in hp_notes[0]

    # steps가 비면 문제로 잡는다.
    bad_problems, _, _ = _run_happy_path("http://x", {"happyPath": {"steps": []}}, "sqlite")
    assert bad_problems and "steps" in bad_problems[0]

    # `${var}` 치환: 문자열 전체가 placeholder면 원래 타입(숫자)을 살린다.
    v = {"bookId": 3, "name": "홍길동"}
    assert _substitute("${bookId}", v) == 3          # 문자열 "3"이 아니라 숫자 3
    assert _substitute("/loans/${bookId}/return", v) == "/loans/3/return"
    assert _substitute({"a": "${bookId}", "b": ["${name}"]}, v) == {"a": 3, "b": ["홍길동"]}
    assert _substitute("${nope}", v) == "${nope}"    # 없는 변수는 그대로 둔다

    # 응답에서 목록 꺼내기: 배열 그대로 / wrapper dict 둘 다.
    assert _first_list([{"id": 1}]) == [{"id": 1}]
    assert _first_list({"loans": [{"id": 2}]}) == [{"id": 2}]
    assert _first_list({"count": 0}) == []

    # 구버전 fixture는 스텝 1개로 감싸서 그대로 검증되게 한다(조용히 건너뛰지 않음).
    legacy = _legacy_to_steps({"targetPath": "/books", "body": {"title": "x"}})
    assert len(legacy["steps"]) == 1
    assert legacy["steps"][0]["path"] == "/books"
    assert legacy["steps"][0]["capture"] == {"__persist": "id"}

    # 응답 필드명이 'id'가 아니라 '...Id'로 끝나는 경우(예: orderId) 그걸 찾는다.
    id_spec = {"endpoints": [
        {"method": "POST", "path": "/orders", "response": {"orderId": "string", "status": "string"}},
        {"method": "GET", "path": "/orders", "response": {"orders": [{"orderId": "string"}]}},
        {"method": "GET", "path": "/books", "response": {"id": "number", "title": "string"}},
    ]}
    assert _id_field_name(id_spec, "POST", "/orders") == "orderId"
    assert _id_field_name(id_spec, "GET", "/orders") == "orderId"
    assert _id_field_name(id_spec, "GET", "/books") == "id"
    assert _id_field_name(id_spec, "GET", "/nope") == "id"  # 못 찾으면 폴백

    assert _list_ids([{"orderId": "a"}, {"orderId": "b"}], "orderId") == ["a", "b"]

    # 도메인 규칙 거부(400, 깨끗한 메시지)와 진짜 서버 버그(400인데 SQL/스택트레이스
    # 흔적)를 상태코드만으로 구분 못 하므로, 메시지 내용으로 버그를 잡아야 한다.
    assert _looks_like_bug('{"detail":"buyerId는 필수입니다"}') is False
    assert _looks_like_bug('{"detail":"bad SQL grammar [SELECT ...]"}') is True
    assert _looks_like_bug('{"detail":"java.lang.NullPointerException"}') is True

    print("verify_backend self-check 통과")
