"""
api_spec.json의 happyPath fixture가 endpoints[].rules를 실제로 다루는지 결정적으로
검사한다 (LLM 자기검토만으로는 못 잡는 "명백히 안 다룬 rule" 안전망).

CLI: python scripts/check_fixture_coverage.py generated/docs/api_spec.json

완벽한 의미론적 커버리지 검증은 아니다 - rules는 자연어 문장이라(`C1`/`BR-003`
같은 ID가 아니다, gen-docs SKILL.md 4단계에서 이미 원문 뜻으로 풀어 적음) 텍스트
매칭으로 "이 rule을 이 스텝이 검증한다"까지는 판정 못 한다. 대신 endpoint 단위로
아래 두 가지 명백한 구멍만 잡는다:
  1. rules가 있는 endpoint를 happyPath.steps가 단 한 번도 안 건드림
  2. 거부 조건처럼 읽히는 rule이 있는데 그 endpoint를 4xx로 찌르는 스텝이 없음
  3. (2와 대칭) 그 endpoint를 성공(2xx)으로 찌르는 스텝이 없음 - 무조건 거부하는
     구현("return 409만 있는 핸들러")도 통과시키지 않기 위함
"""

import argparse
import json
import re
import sys

_REJECTION_KEYWORDS = [
    "거부", "안되면", "안 되면", "없으면", "이미", "초과", "제한", "불가",
    "아니면", "아닐", "실패", "404", "409", "400", "401", "403",
]


def _path_segments(path: str) -> list[str]:
    return [s for s in path.split("/") if s != ""]


def _endpoint_matches_step(ep_method: str, ep_path: str, step_method: str, step_path: str) -> bool:
    if ep_method.upper() != step_method.upper():
        return False
    ep_segs = _path_segments(ep_path)
    step_segs = _path_segments(step_path.split("?")[0])
    if len(ep_segs) != len(step_segs):
        return False
    for ep_seg, step_seg in zip(ep_segs, step_segs):
        if ep_seg.startswith("{") and ep_seg.endswith("}"):
            continue
        if ep_seg != step_seg:
            return False
    return True


def _looks_like_rejection_rule(rule: str) -> bool:
    return any(kw in rule for kw in _REJECTION_KEYWORDS)


def _expect_codes(step: dict) -> list[int]:
    expect = step.get("expect")
    if expect is None:
        return []
    if isinstance(expect, list):
        return [int(e) for e in expect]
    return [int(expect)]


def check_coverage(api_spec: dict) -> list[str]:
    """빠진 커버리지를 사람이 읽을 문제 목록으로 돌려준다. 빈 리스트면 통과."""
    problems: list[str] = []
    steps = (api_spec.get("happyPath") or {}).get("steps") or []

    for ep in api_spec.get("endpoints", []):
        rules = ep.get("rules") or []
        if not rules:
            continue
        method, path = ep["method"], ep["path"]
        matched = [s for s in steps if _endpoint_matches_step(method, path, s.get("method", ""), s.get("path", ""))]

        if not matched:
            problems.append(
                f"{method} {path}: rules {len(rules)}개 있는데 happyPath에 이 endpoint를 건드리는 스텝이 없음: {rules}"
            )
            continue

        codes = {c for s in matched for c in _expect_codes(s)}
        has_success = any(c < 400 for c in codes)
        has_rejection = any(c >= 400 for c in codes)
        rejection_rules = [r for r in rules if _looks_like_rejection_rule(r)]

        if rejection_rules and not has_rejection:
            problems.append(
                f"{method} {path}: 거부 조건으로 보이는 rule이 있는데 4xx를 기대하는 스텝이 없음: {rejection_rules}"
            )
        if not has_success:
            problems.append(
                f"{method} {path}: 성공(2xx)을 기대하는 스텝이 없음 - 무조건 거부하는 구현도 통과해버림"
            )

    return problems


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("api_spec", help="generated/docs/api_spec.json 경로")
    args = p.parse_args()

    api_spec = json.loads(open(args.api_spec, encoding="utf-8").read())
    problems = check_coverage(api_spec)
    if problems:
        print("fixture 커버리지 부족:")
        for prob in problems:
            print(f"- {prob}")
        sys.exit(1)
    print("fixture 커버리지 OK - rules 있는 endpoint 전부 성공/거부 스텝이 있음.")
    sys.exit(0)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        main()
        sys.exit(0)

    # self-check: widgets 픽스처(알려진 정상 케이스) + 의도적으로 망가뜨린 케이스
    widgets = json.loads(open("tests/fixtures/widgets/api_spec.json", encoding="utf-8").read())
    assert check_coverage(widgets) == [], check_coverage(widgets)

    assert _endpoint_matches_step("PUT", "/widgets/{id}", "PUT", "/widgets/${widgetId}")
    assert _endpoint_matches_step("PUT", "/widgets/{id}", "PUT", "/widgets/999999")
    assert not _endpoint_matches_step("PUT", "/widgets/{id}", "GET", "/widgets/999999")
    assert not _endpoint_matches_step("GET", "/widgets", "GET", "/widgets/1")

    assert _looks_like_rejection_rule("name이 없으면 400") is True
    assert _looks_like_rejection_rule("수량은 자동으로 계산된다") is False

    no_reject = {
        "endpoints": [{"method": "POST", "path": "/x", "rules": ["y가 없으면 400"]}],
        "happyPath": {"steps": [{"method": "POST", "path": "/x", "expect": 201}]},
    }
    problems = check_coverage(no_reject)
    assert len(problems) == 1 and "4xx" in problems[0], problems

    no_success = {
        "endpoints": [{"method": "POST", "path": "/x", "rules": ["y가 없으면 400"]}],
        "happyPath": {"steps": [{"method": "POST", "path": "/x", "expect": 400}]},
    }
    problems = check_coverage(no_success)
    assert len(problems) == 1 and "성공" in problems[0], problems

    untouched = {
        "endpoints": [{"method": "POST", "path": "/x", "rules": ["규칙"]}],
        "happyPath": {"steps": []},
    }
    problems = check_coverage(untouched)
    assert len(problems) == 1 and "스텝이 없음" in problems[0], problems

    print("check_fixture_coverage.py: self-check 통과")
