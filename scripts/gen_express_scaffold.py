"""
Express(Node.js) 백엔드의 결정적 스캐폴드(server.js, db.js, package.json) 생성.

CLI: python scripts/gen_express_scaffold.py --groups orders,payments --dialect postgres [--ts] -o generated/backend

doc-pipeline(OpenRouter판)의 backend_express.py는 도메인 조각화가 없었다(단일
호출) - 이 레포는 fastapi/spring과 같은 이유로 express도 처음부터 조각화한다.
조각(서브에이전트)은 `routes/{module}.js`(또는 --ts면 .ts) 하나씩만 쓰고,
`express.Router()`를 export한다. 진입점(server.js)이 조각마다 require/app.use
해야 하므로 fastapi와 같은 이유로 스크립트로 뺐다.

--ts 플래그를 주면 TypeScript 버전(gen-backend-typescript용) - 파일 확장자만
.ts로 바뀌고 db.ts에 타입이 붙는다. 로직은 express와 100% 같다(같은 스캐폴드
함수를 공유).
"""

import argparse
from pathlib import Path

_DATABASE_URL = "postgresql://doc:doc@localhost:55432/doc"
PORT_JS = 5001
PORT_TS = 5002


def module_name(group: str) -> str:
    return group.replace("-", "_").replace(".", "_")


def db_module(dialect: str, ts: bool) -> str:
    if dialect == "postgres":
        if ts:
            return (
                "import { Pool } from 'pg';\n\n"
                f"export const pool = new Pool({{ connectionString: process.env.DATABASE_URL || '{_DATABASE_URL}' }});\n"
            )
        return (
            "const { Pool } = require('pg');\n\n"
            f"const pool = new Pool({{ connectionString: process.env.DATABASE_URL || '{_DATABASE_URL}' }});\n\n"
            "module.exports = { pool };\n"
        )
    # sqlite: node:sqlite 내장, 동기 API
    if ts:
        return (
            "import { DatabaseSync } from 'node:sqlite';\n\n"
            "export const db = new DatabaseSync('app.db');\n"
        )
    return (
        "const { DatabaseSync } = require('node:sqlite');\n\n"
        "const db = new DatabaseSync('app.db');\n\n"
        "module.exports = { db };\n"
    )


def server_module(groups: list[str], dialect: str, ts: bool) -> str:
    mods = [module_name(g) for g in groups]
    ext = "" if not ts else ""  # import 문에는 확장자 안 붙임(둘 다 동일)
    port = PORT_TS if ts else PORT_JS
    if ts:
        imports = "\n".join(f"import {m}Router from './routes/{m}';" for m in mods)
        uses = "\n".join(f"app.use({m}Router);" for m in mods)
        db_import = "import { pool } from './db';" if dialect == "postgres" else "import { db } from './db';"
        init = (
            "  const ddl = readFileSync(join(__dirname, 'schema.sql'), 'utf-8');\n"
            + ("  await pool.query(ddl);\n" if dialect == "postgres" else "  db.exec(ddl);\n")
        )
        listen = f"app.listen({port}, () => console.log('listening on {port}'));"
        body = (
            "import express from 'express';\n"
            "import cors from 'cors';\n"
            "import { readFileSync } from 'fs';\n"
            "import { join } from 'path';\n"
            f"{db_import}\n"
            f"{imports}\n\n"
            "const app = express();\n"
            "// 운영 배포 시 CORS_ORIGIN(콤마구분)으로 allowlist를 지정한다 - 안 주면\n"
        "// 개발 편의상 전체 허용('*')으로 동작한다.\n"
        "app.use(cors({ origin: process.env.CORS_ORIGIN ? process.env.CORS_ORIGIN.split(',') : '*' }));\n"
            "app.use(express.json());\n\n"
            f"{uses}\n\n"
            "async function start() {\n"
            f"{init}"
            f"  {listen}\n"
            "}\n\n"
            "start();\n"
        )
        return body

    imports = "\n".join(f"const {m}Router = require('./routes/{m}');" for m in mods)
    uses = "\n".join(f"app.use({m}Router);" for m in mods)
    db_import = "const { pool } = require('./db');" if dialect == "postgres" else "const { db } = require('./db');"
    init = (
        "  const ddl = fs.readFileSync(path.join(__dirname, 'schema.sql'), 'utf-8');\n"
        + ("  await pool.query(ddl);\n" if dialect == "postgres" else "  db.exec(ddl);\n")
    )
    return (
        "const express = require('express');\n"
        "const cors = require('cors');\n"
        "const fs = require('fs');\n"
        "const path = require('path');\n"
        f"{db_import}\n"
        f"{imports}\n\n"
        "const app = express();\n"
        "// 운영 배포 시 CORS_ORIGIN(콤마구분)으로 allowlist를 지정한다 - 안 주면\n"
        "// 개발 편의상 전체 허용('*')으로 동작한다.\n"
        "app.use(cors({ origin: process.env.CORS_ORIGIN ? process.env.CORS_ORIGIN.split(',') : '*' }));\n"
        "app.use(express.json());\n\n"
        f"{uses}\n\n"
        "async function start() {\n"
        f"{init}"
        f"  app.listen({port}, () => console.log('listening on {port}'));\n"
        "}\n\n"
        "start();\n"
    )


def package_json(dialect: str, ts: bool) -> str:
    deps = ['"express": "^4.19.2"', '"cors": "^2.8.5"']
    if dialect == "postgres":
        deps.append('"pg": "^8.12.0"')
    if ts:
        script = "node --loader ts-node/esm server.ts" if False else "tsc && node dist/server.js"
        # @types/node는 22.x여야 한다 - sqlite 방언에서 db.ts가 `node:sqlite`를
        # import하는데 그 타입 선언이 @types/node 22부터 들어왔다(node:sqlite 자체가
        # Node 22.5+ 기능). 20.x로 두면 런타임은 되는데 tsc가
        # `TS2307: Cannot find module 'node:sqlite'`로 빌드를 막는다(실측 2026-07-29).
        dev_deps = ['"typescript": "^5.5.4"', '"@types/express": "^4.17.21"', '"@types/cors": "^2.8.17"', '"@types/node": "^22.10.0"']
        if dialect == "postgres":
            dev_deps.append('"@types/pg": "^8.11.6"')
        copy_schema = '"tsc && node -e \\"require(\'fs\').copyFileSync(\'schema.sql\',\'dist/schema.sql\')\\""'
        build = f'"build": {copy_schema},\n    "start": "node --experimental-sqlite dist/server.js"' if dialect != "postgres" else f'"build": {copy_schema},\n    "start": "node dist/server.js"'
        return (
            "{\n"
            '  "name": "backend",\n'
            '  "version": "1.0.0",\n'
            '  "scripts": {\n'
            f"    {build}\n"
            "  },\n"
            '  "dependencies": {\n    ' + ",\n    ".join(deps) + "\n  },\n"
            '  "devDependencies": {\n    ' + ",\n    ".join(dev_deps) + "\n  }\n"
            "}\n"
        )
    start = "node --experimental-sqlite server.js" if dialect != "postgres" else "node server.js"
    return (
        "{\n"
        '  "name": "backend",\n'
        '  "version": "1.0.0",\n'
        '  "scripts": {\n'
        f'    "start": "{start}"\n'
        "  },\n"
        '  "dependencies": {\n    ' + ",\n    ".join(deps) + "\n  }\n"
        "}\n"
    )


def env_example(dialect: str) -> str:
    lines = ["CORS_ORIGIN=https://example.com"]
    if dialect == "postgres":
        lines.append(f"DATABASE_URL={_DATABASE_URL}")
    return "\n".join(lines) + "\n"


def write_scaffold(out_dir: Path, groups: list[str], dialect: str, ts: bool) -> None:
    ext = "ts" if ts else "js"
    (out_dir / "routes").mkdir(parents=True, exist_ok=True)
    (out_dir / f"db.{ext}").write_text(db_module(dialect, ts), encoding="utf-8")
    (out_dir / f"server.{ext}").write_text(server_module(groups, dialect, ts), encoding="utf-8")
    (out_dir / "package.json").write_text(package_json(dialect, ts), encoding="utf-8")
    (out_dir / ".env.example").write_text(env_example(dialect), encoding="utf-8")
    if ts:
        (out_dir / "tsconfig.json").write_text(
            '{\n  "compilerOptions": {\n    "target": "ES2020",\n    "module": "commonjs",\n'
            '    "outDir": "dist",\n    "rootDir": ".",\n    "strict": true,\n'
            '    "esModuleInterop": true,\n    "skipLibCheck": true\n  }\n}\n',
            encoding="utf-8",
        )


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--groups", required=True)
    p.add_argument("--dialect", choices=["sqlite", "postgres"], default="sqlite")
    p.add_argument("--ts", action="store_true", help="TypeScript 버전으로 생성 (gen-backend-typescript용)")
    p.add_argument("-o", "--out-dir", default="generated/backend")
    args = p.parse_args()
    groups = [g.strip() for g in args.groups.split(",") if g.strip()]
    write_scaffold(Path(args.out_dir), groups, args.dialect, args.ts)
    print(f"scaffold written to {args.out_dir} for groups: {groups} (ts={args.ts})")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        main()
        sys.exit(0)

    js = server_module(["orders", "voice-samples"], "postgres", ts=False)
    assert "require('./routes/orders')" in js
    assert "app.use(voice_samplesRouter)" in js
    ts = server_module(["orders"], "sqlite", ts=True)
    assert "import ordersRouter from './routes/orders';" in ts
    assert "db.exec(ddl)" in ts
    pkg = package_json("postgres", ts=True)
    assert '"pg"' in pkg and '"@types/pg"' in pkg

    assert "app.use(cors());" not in js
    assert "CORS_ORIGIN" in js
    assert "DATABASE_URL=" in env_example("postgres")
    assert "DATABASE_URL=" not in env_example("sqlite")

    print("gen_express_scaffold self-check 통과")
