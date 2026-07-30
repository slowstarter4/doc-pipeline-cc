"""
scripts/*.py의 내장 자기점검(assert 기반)을 pytest로 묶어 CI에서 자동 실행되게 한다.

각 스크립트는 인자 없이 실행하면 자기점검을 돈다(관례) - `backup_generated.py`만
반대로 정상 호출이 인자 없는 형태라 `--self-check`이 따로 필요하다.

새 검증 로직(P1~P4 개선)이 실제로 걸리는지는 각 스크립트의 자기점검 안에 이미
assert로 들어있다 - 여기서 그 로직을 다시 베끼지 않고, "자기점검이 통과했는가"만
확인한다(중복 유지 비용을 피한다).
"""

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

_NO_ARG_SELF_CHECK = [
    "schema_ddl.py",
    "endpoint_groups.py",
    "openapi_spec.py",
    "gen_fastapi_scaffold.py",
    "gen_express_scaffold.py",
    "verify_backend.py",
    "verify_frontend.py",
]


@pytest.mark.parametrize("script", _NO_ARG_SELF_CHECK)
def test_self_check_no_args(script: str) -> None:
    result = subprocess.run(
        [sys.executable, f"scripts/{script}"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "통과" in result.stdout


def test_backup_generated_self_check() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/backup_generated.py", "--self-check"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "통과" in result.stdout
