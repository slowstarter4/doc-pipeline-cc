"""
FastAPI 백엔드의 결정적 스캐폴드(main.py, db.py, requirements.txt) 생성.

CLI: python scripts/gen_fastapi_scaffold.py --groups orders,payments,shipments --dialect postgres -o generated/backend

진입점(main.py)은 조각(라우터) 개수만큼 import/include 문이 필요한데, 이걸
서브에이전트에게 맡기면 조각마다 파일명·모듈명이 어긋날 위험이 있다(spring은
컴포넌트 스캔이 자동으로 훑지만 fastapi/APIRouter는 수동 include가 필요).
그래서 doc-pipeline(OpenRouter판) backend.py의 _main_module/_db_module을
그대로 스크립트로 옮겼다 - endpoint_groups.py로 조각을 나눈 뒤, 조각별
서브에이전트를 디스패치하기 **전에** 이 스크립트로 진입점을 먼저 써 둔다.
"""

import argparse
from pathlib import Path

_DATABASE_URL = "postgresql://doc:doc@localhost:55432/doc"
PORT = 8000


def module_name(group: str) -> str:
    """endpoint_groups.py의 동명 함수와 반드시 같은 규칙을 유지한다 - 여기서 임포트
    안 하는 이유는 `python scripts/gen_fastapi_scaffold.py`를 저장소 루트에서 바로
    실행할 때 sys.path에 scripts/가 없어 임포트가 깨지기 때문(1줄짜리라 복제 비용이
    sys.path 조작보다 싸다)."""
    return group.replace("-", "_").replace(".", "_")


def db_module(dialect: str) -> str:
    if dialect == "postgres":
        return (
            "import os\n\n"
            "import psycopg\n\n"
            f'DATABASE_URL = os.environ.get("DATABASE_URL", "{_DATABASE_URL}")\n\n\n'
            "def get_conn():\n"
            "    return psycopg.connect(DATABASE_URL)\n"
        )
    return (
        "import sqlite3\n\n"
        'DB_PATH = "app.db"\n\n\n'
        "def get_conn():\n"
        "    # 요청마다 새로 연다 - FastAPI는 요청을 여러 스레드에서 처리하므로\n"
        "    # 전역 커넥션 하나를 공유하면 스레드 오류가 난다.\n"
        "    conn = sqlite3.connect(DB_PATH)\n"
        "    conn.row_factory = sqlite3.Row\n"
        "    return conn\n"
    )


def main_module(groups: list[str], dialect: str) -> str:
    mods = [module_name(g) for g in groups]
    imports = "\n".join(f"from routers import {m}" for m in mods)
    includes = "\n".join(f"app.include_router({m}.router)" for m in mods)
    if dialect == "postgres":
        init_body = (
            "    with get_conn() as conn:\n"
            "        with conn.cursor() as cur:\n"
            "            for stmt in SCHEMA_SQL.split(';'):\n"
            "                if stmt.strip():\n"
            "                    cur.execute(stmt)\n"
            "        conn.commit()\n"
        )
    else:
        init_body = (
            "    conn = get_conn()\n"
            "    try:\n"
            "        conn.executescript(SCHEMA_SQL)\n"
            "        conn.commit()\n"
            "    finally:\n"
            "        conn.close()\n"
        )
    return (
        "from pathlib import Path\n\n"
        "from fastapi import FastAPI, Request\n"
        "from fastapi.exceptions import RequestValidationError\n"
        "from fastapi.middleware.cors import CORSMiddleware\n"
        "from fastapi.responses import JSONResponse\n\n"
        "from db import get_conn\n"
        f"{imports}\n\n"
        '_SCHEMA_PATH = Path(__file__).with_name("schema.sql")\n'
        'SCHEMA_SQL = _SCHEMA_PATH.read_text(encoding="utf-8") if _SCHEMA_PATH.exists() else ""\n\n'
        "app = FastAPI()\n"
        "app.add_middleware(\n"
        '    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]\n'
        ")\n\n\n"
        "def init_db() -> None:\n"
        f"{init_body}\n\n"
        '@app.on_event("startup")\n'
        "def _startup() -> None:\n"
        "    init_db()\n\n\n"
        "@app.exception_handler(RequestValidationError)\n"
        "async def _validation_error(request: Request, exc: RequestValidationError):\n"
        '    return JSONResponse(status_code=400, content={"detail": str(exc)})\n\n\n'
        "@app.exception_handler(Exception)\n"
        "async def _unhandled(request: Request, exc: Exception):\n"
        '    return JSONResponse(status_code=400, content={"detail": str(exc)})\n\n\n'
        f"{includes}\n"
    )


def write_scaffold(out_dir: Path, groups: list[str], dialect: str) -> None:
    (out_dir / "routers").mkdir(parents=True, exist_ok=True)
    (out_dir / "routers" / "__init__.py").write_text("", encoding="utf-8")
    (out_dir / "db.py").write_text(db_module(dialect), encoding="utf-8")
    (out_dir / "main.py").write_text(main_module(groups, dialect), encoding="utf-8")
    deps = "fastapi\nuvicorn\n" + ("psycopg[binary]\n" if dialect == "postgres" else "")
    (out_dir / "requirements.txt").write_text(deps, encoding="utf-8")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--groups", required=True, help="쉼표구분 도메인 그룹 목록 (endpoint_groups.py 출력의 group 값들)")
    p.add_argument("--dialect", choices=["sqlite", "postgres"], default="sqlite")
    p.add_argument("-o", "--out-dir", default="generated/backend")
    args = p.parse_args()
    groups = [g.strip() for g in args.groups.split(",") if g.strip()]
    write_scaffold(Path(args.out_dir), groups, args.dialect)
    print(f"scaffold written to {args.out_dir} for groups: {groups}")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        main()
        sys.exit(0)

    main_src = main_module(["orders", "voice-samples"], "postgres")
    assert "from routers import voice_samples" in main_src
    assert "app.include_router(voice_samples.router)" in main_src
    for d in ("sqlite", "postgres"):
        compile(main_module(["orders"], d), "main.py", "exec")
        compile(db_module(d), "db.py", "exec")
    print("gen_fastapi_scaffold self-check 통과")
