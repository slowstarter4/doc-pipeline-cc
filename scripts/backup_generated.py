"""
generated/backend, generated/frontend, generated/docs가 이미 있으면(이전 실행
산출물) 덮어쓰기 전에 자동으로 옆으로 옮겨 백업한다 (결정적, LLM 미사용).

CLI: python scripts/backup_generated.py [--generated-dir generated]

왜 필요한가: `build-app`이 스택이나 도메인을 바꿔 재실행할 때 지금까지는
오케스트레이터(사람 역할의 세션)가 매번 "이전 산출물 백업해야지"를 직접
판단해서 `mv` 명령을 손으로 짰다. 실제로 이 수동 과정에서 사고가 났다
(2026-07-29: `mv`로 옮긴 걸 백업 파일로 착각해 `rm -rf`로 지워버림 -
`generated/frontend_reactts`). 사람 판단이 낄 자리를 없애 이 스크립트가
항상 같은 규칙으로 처리한다 - 백업 위치·이름이 매번 똑같이 나오므로 "이게
백업인가 원본인가" 헷갈릴 여지가 없다.

백업 이름 규칙: `generated/<name>_<감지된스택>_<타임스탬프>/`
(예: `generated/backend_typescript_20260729_153000/`). 스택을 못 알아내면
`unknown`. 타임스탬프가 항상 붙으므로 여러 번 실행해도 이전 백업을 덮어쓰지
않는다 - 백업의 백업이 쌓이는 게, 백업인 줄 모르고 지우는 사고보다 낫다.
"""

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path


def detect_backend_stack(path: Path) -> str:
    if (path / "build.gradle").exists():
        return "spring"
    if (path / "tsconfig.json").exists() or (path / "server.ts").exists():
        return "typescript"
    if (path / "main.py").exists():
        return "fastapi"
    if (path / "server.js").exists():
        return "express"
    return "unknown"


def detect_frontend_stack(path: Path) -> str:
    has_package_json = (path / "package.json").exists()
    if not has_package_json:
        return "vanilla" if (path / "index.html").exists() else "unknown"
    if (path / "tsconfig.json").exists():
        return "react-ts"
    return "react"


def detect_docs_dialect(path: Path) -> str:
    """docs엔 스택이 없지만 schema.sql의 dialect는 결정적으로 읽어낼 수 있다 -
    문서를 재사용할 때 dialect가 안 맞아서 나는 버그가 실제로 있었으므로(2026-07-29),
    백업 이름만 보고 어느 DB용 문서였는지 알 수 있게 한다."""
    schema = path / "schema.sql"
    if not schema.exists():
        return "unknown"
    text = schema.read_text(encoding="utf-8", errors="replace")
    if "SERIAL PRIMARY KEY" in text:
        return "postgres"
    if "AUTOINCREMENT" in text:
        return "sqlite"
    return "unknown"


_DETECTORS = {
    "backend": detect_backend_stack,
    "frontend": detect_frontend_stack,
    "docs": detect_docs_dialect,
}


def backup_if_exists(generated_dir: Path, name: str, timestamp: str) -> str | None:
    """generated/<name>이 있으면 옆으로 옮기고 새 경로를 반환한다. 없거나 비어
    있으면 아무것도 안 하고 None을 반환한다(첫 실행에 불필요한 빈 백업 폴더가
    안 생기게)."""
    src = generated_dir / name
    if not src.exists() or not any(src.iterdir()):
        return None

    detector = _DETECTORS.get(name)
    tag = detector(src) if detector else "unknown"
    dest = generated_dir / f"{name}_{tag}_{timestamp}"
    shutil.move(str(src), str(dest))
    return str(dest)


def backup_all(generated_dir: Path, include_docs: bool = False) -> dict[str, str | None]:
    """기본은 backend/frontend만 백업한다 - `docs`는 스택이 아니라 **도메인**에
    종속이라, 같은 기획문서로 스택만 바꿔 돌릴 땐 그대로 재사용하는 게 맞다
    (문서 생성은 LLM 단계라 다시 뽑으면 비싸고 매번 내용이 조금씩 달라져서
    스택 간 비교도 흐려진다. dialect만 schema_ddl.py로 다시 뽑으면 된다).
    도메인 자체를 바꿀 때만 include_docs=True로 같이 치운다."""
    names = ("backend", "frontend", "docs") if include_docs else ("backend", "frontend")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return {
        name: backup_if_exists(generated_dir, name, timestamp)
        for name in names
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--generated-dir", default="generated")
    p.add_argument(
        "--include-docs", action="store_true",
        help="generated/docs도 같이 백업한다. 도메인(기획문서)을 바꿀 때만 쓴다 - "
             "스택만 바꿀 땐 문서를 재사용해야 하므로 붙이지 않는다.",
    )
    args = p.parse_args()

    results = backup_all(Path(args.generated_dir), include_docs=args.include_docs)
    moved = {k: v for k, v in results.items() if v}
    if not moved:
        print("백업할 이전 산출물 없음 (첫 실행이거나 이미 비어 있음).")
    else:
        for name, dest in moved.items():
            print(f"generated/{name} -> {dest}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        main()
        sys.exit(0)

    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "generated"
        backend = root / "backend"
        backend.mkdir(parents=True)
        (backend / "server.ts").write_text("x")
        (backend / "tsconfig.json").write_text("{}")

        frontend = root / "frontend"
        frontend.mkdir(parents=True)
        (frontend / "index.html").write_text("x")

        docs = root / "docs"
        docs.mkdir(parents=True)
        (docs / "schema.sql").write_text("CREATE TABLE Book (\n  id SERIAL PRIMARY KEY\n);")

        assert detect_backend_stack(backend) == "typescript"
        assert detect_frontend_stack(frontend) == "vanilla"
        assert detect_docs_dialect(docs) == "postgres"
        (docs / "schema.sql").write_text("CREATE TABLE Book (\n  id INTEGER PRIMARY KEY AUTOINCREMENT\n);")
        assert detect_docs_dialect(docs) == "sqlite"
        assert detect_docs_dialect(root / "nope") == "unknown"  # schema.sql 없으면
        (docs / "schema.sql").write_text("CREATE TABLE Book (\n  id SERIAL PRIMARY KEY\n);")

        # 기본: docs는 건드리지 않는다(스택만 바꾸는 경우 - 문서 재사용).
        stack_only = backup_all(root)
        assert stack_only["backend"] is not None and "typescript" in stack_only["backend"]
        assert stack_only["frontend"] is not None and "vanilla" in stack_only["frontend"]
        assert "docs" not in stack_only
        assert docs.exists() and (docs / "schema.sql").exists()
        assert not backend.exists()  # 원래 자리는 비워짐
        assert Path(stack_only["backend"]).exists()

        # --include-docs: 도메인을 바꿀 때만. 이때는 dialect 태그가 붙는다.
        with_docs = backup_all(root, include_docs=True)
        assert with_docs["docs"] is not None and "postgres" in with_docs["docs"]
        assert not docs.exists()

        # 이미 옮겨서 비어있는 상태에서 다시 돌리면 아무것도 안 한다(빈 폴더 무시).
        backend.mkdir(parents=True)
        again = backup_if_exists(root, "backend", "20260101_000000")
        assert again is None

    print("backup_generated self-check 통과")
