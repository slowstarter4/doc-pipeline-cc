"""
서브에이전트들이 조각별로 남긴 계약 이의(objections)를 모아 severity 순으로
출력한다. LLM 미사용 - 판정도 재디스패치도 안 한다, 사람이 읽고 판단한다.

CLI: python scripts/collect_objections.py [--objections-dir generated/objections]

왜 조각별 파일인가: 병렬 디스패치되는 서브에이전트들이 같은 파일에 동시에
append하면 충돌한다. 각자 `generated/objections/<slice>.json`에 자기 몫만 쓰고,
이 스크립트가 읽을 때 합친다 - 락이나 재시도 로직을 서브에이전트에 넣는 것보다
단순하다.

Level 2(중재자)로 갈지 말지는 이 출력이 실제로 쌓이는지 보고 사람이 정한다
(`CLAUDE.md`: 아직 안 일어난 문제는 안 고친다).
"""

import argparse
import json
import sys
from pathlib import Path

_SEVERITY_ORDER = {"blocking": 0, "workaround": 1, "question": 2}
_REQUIRED_FIELDS = ("from", "slice", "severity", "issue")


def load_objections(objections_dir: Path) -> tuple[list, list]:
    """generated/objections/*.json을 전부 읽어 하나로 합친다. 조각별 파일이라
    깨진 파일 하나가 있어도 나머지는 정상 수집한다 - 경고만 남기고 그 파일/항목만
    건너뛴다(한 조각의 실수로 전체 이의 수집이 죽으면 안 된다)."""
    items = []
    warnings = []
    if not objections_dir.exists():
        return items, warnings
    for path in sorted(objections_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            warnings.append(f"{path.name}: JSON 파싱 실패 ({e}) - 파일 건너뜀")
            continue
        if not isinstance(data, list):
            warnings.append(f"{path.name}: 최상위가 배열이 아님 - 파일 건너뜀")
            continue
        for i, entry in enumerate(data):
            if not isinstance(entry, dict):
                warnings.append(f"{path.name}[{i}]: 객체가 아님 - 항목 건너뜀")
                continue
            missing = [k for k in _REQUIRED_FIELDS if not entry.get(k)]
            if missing:
                warnings.append(f"{path.name}[{i}]: 필수 필드 누락({', '.join(missing)}) - 항목 건너뜀")
                continue
            items.append(entry)
    return items, warnings


def _sort_key(entry: dict):
    return (_SEVERITY_ORDER.get(entry["severity"], 99), entry["from"], entry["slice"])


def format_report(items: list) -> str:
    if not items:
        return "계약 이의 없음."
    ordered = sorted(items, key=_sort_key)
    lines = [f"계약 이의제기 {len(ordered)}건", ""]
    for e in ordered:
        lines.append(f"[{e['severity']}] {e['from']}/{e['slice']}")
        lines.append(f"  {e['issue']}")
        if e.get("assumed"):
            lines.append(f"  → 우회: {e['assumed']}")
        if e.get("suggestion"):
            lines.append(f"  → 제안: {e['suggestion']}")
        lines.append("")
    return "\n".join(lines).rstrip()


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--objections-dir", default="generated/objections")
    p.add_argument(
        "--self-check", action="store_true",
        help="자기점검만 돌리고 끝낸다(임시 디렉터리에서, 실제 generated/는 안 건드림).",
    )
    args = p.parse_args()

    if args.self_check:
        self_check()
        return

    items, warnings = load_objections(Path(args.objections_dir))
    for w in warnings:
        print(f"경고: {w}", file=sys.stderr)
    print(format_report(items))


# verify_frontend.py/backup_generated.py와 달리 이 스크립트는 인자 없는 정상
# 호출이 "objections 없음 = 정상 경로"를 뜻한다(문서 목적 그대로: objections가
# 계속 비어 있는 게 맞는 결과). self-check를 기본 경로에 걸면 그 정상 경로를
# 밟을 때마다 매번 self-check가 같이 도는 낭비가 생겨서, backup_generated.py의
# 교훈대로 --self-check 뒤로 뺐다.
def self_check() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)

        # 디렉터리 자체가 없으면 - 이의 없음, 정상 경로.
        items, warnings = load_objections(d / "nope")
        assert items == [] and warnings == []
        assert format_report(items) == "계약 이의 없음."

        (d / "loans.json").write_text(json.dumps([
            {"from": "frontend", "slice": "loans", "severity": "blocking",
             "issue": "회원명 없음", "assumed": "memberId 그대로 표시",
             "suggestion": "memberName 추가"},
        ]), encoding="utf-8")
        (d / "refunds.json").write_text(json.dumps([
            {"from": "backend", "slice": "refunds", "severity": "workaround",
             "issue": "환불 사유 코드 미정", "assumed": None, "suggestion": None},
        ]), encoding="utf-8")
        (d / "misc.json").write_text(json.dumps([
            {"from": "frontend", "slice": "misc", "severity": "question",
             "issue": "정렬 기준 불명확", "assumed": "생성일 내림차순으로 가정",
             "suggestion": None},
        ]), encoding="utf-8")

        items, warnings = load_objections(d)
        assert len(items) == 3 and warnings == []

        report = format_report(items)
        assert report.startswith("계약 이의제기 3건")
        # severity 순 정렬: blocking -> workaround -> question
        assert report.index("[blocking]") < report.index("[workaround]") < report.index("[question]")
        assert "assumed" not in report  # 필드명이 아니라 내용만 나와야 함
        assert "→ 우회: memberId 그대로 표시" in report
        assert "→ 제안: memberName 추가" in report

        # assumed/suggestion이 null이면 그 줄 자체가 안 나와야 한다.
        refunds_block = report.split("[workaround]")[1].split("[question]")[0]
        assert "→ 우회:" not in refunds_block
        assert "→ 제안:" not in refunds_block

        # 깨진 파일 - 그 파일만 건너뛰고 경고, 나머지는 정상 수집.
        (d / "broken.json").write_text("not json", encoding="utf-8")
        items2, warnings2 = load_objections(d)
        assert len(items2) == 3
        assert any("broken.json" in w for w in warnings2)

        # 필수 필드 누락 항목 - 그 항목만 건너뛰고 경고.
        (d / "partial.json").write_text(json.dumps([{"from": "frontend"}]), encoding="utf-8")
        items3, warnings3 = load_objections(d)
        assert len(items3) == 3
        assert any("partial.json" in w for w in warnings3)

        # 최상위가 배열이 아닌 경우도 그 파일만 건너뛴다.
        (d / "not_array.json").write_text(json.dumps({"oops": True}), encoding="utf-8")
        items4, warnings4 = load_objections(d)
        assert len(items4) == 3
        assert any("not_array.json" in w for w in warnings4)

    print("collect_objections self-check 통과")


if __name__ == "__main__":
    main()
