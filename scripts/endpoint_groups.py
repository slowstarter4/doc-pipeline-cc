"""
API 명세를 도메인 조각으로 나누는 결정적 분류 (LLM 미사용)

CLI: python scripts/endpoint_groups.py <api_spec.json> [-o groups/]

한 번의 서브에이전트 호출에 백엔드 전체를 맡기면 큰 도메인(엔티티 10+개·경로
20+개)에서 출력이 길어져 다중 파일을 놓치거나 뒤섞을 위험이 커진다. 오케스트레이터가
이 스크립트로 먼저 엔드포인트를 도메인별로 나누고, 조각마다 서브에이전트를 하나씩
병렬 디스패치한다 - doc-pipeline(OpenRouter판)의 endpoint_groups()를 그대로 이식.

조각끼리는 코드가 아니라 DB로 엮인다: 스키마는 schema_ddl이 한 벌로 뽑으므로,
한 조각이 다른 도메인 데이터가 필요하면 import가 아니라 SELECT로 직접 조회한다.
"""

import argparse
import json
import sys
from pathlib import Path


def endpoint_groups(api_spec: dict) -> dict[str, list[dict]]:
    """엔드포인트를 경로 첫 세그먼트로 묶는다 (`/orders/{id}/cancel` → `orders`)."""
    groups: dict[str, list[dict]] = {}
    for ep in api_spec.get("endpoints", []):
        path = ep.get("path", "/")
        segments = [s for s in path.split("/") if s and not s.startswith("{")]
        groups.setdefault(segments[0] if segments else "root", []).append(ep)
    return groups


def module_name(group: str) -> str:
    """경로 세그먼트를 식별자로. `voice-samples` 같은 kebab-case도 받는다."""
    return group.replace("-", "_").replace(".", "_")


def pascal_case(module: str) -> str:
    """module_name() 결과를 클래스명 접두사로 (`voice_samples` -> `VoiceSamples`)."""
    return "".join(part.capitalize() for part in module.split("_")) or "Root"


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("api_spec_json", help="API 명세 JSON 파일 경로")
    p.add_argument(
        "-o", "--out-dir",
        help="지정하면 조각마다 <out-dir>/<module>.json으로 따로 저장. "
             "생략하면 전체 그룹을 stdout에 JSON으로 출력.",
    )
    args = p.parse_args()

    api_spec = json.loads(open(args.api_spec_json, encoding="utf-8").read())
    groups = endpoint_groups(api_spec)

    if args.out_dir:
        out = Path(args.out_dir)
        out.mkdir(parents=True, exist_ok=True)
        manifest = []
        for group, endpoints in groups.items():
            module = module_name(group)
            slice_path = out / f"{module}.json"
            slice_path.write_text(
                json.dumps({"endpoints": endpoints}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            manifest.append({
                "group": group,
                "module": module,
                "class_prefix": pascal_case(module),
                "endpoint_count": len(endpoints),
                "file": str(slice_path),
            })
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
    else:
        out_obj = {
            g: {
                "module": module_name(g),
                "class_prefix": pascal_case(module_name(g)),
                "endpoints": eps,
            }
            for g, eps in groups.items()
        }
        print(json.dumps(out_obj, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    if len(sys.argv) > 1:
        main()
        sys.exit(0)

    spec = {
        "endpoints": [
            {"method": "GET", "path": "/orders"},
            {"method": "POST", "path": "/orders"},
            {"method": "POST", "path": "/orders/{orderId}/cancel"},
            {"method": "GET", "path": "/payments/{paymentId}"},
            {"method": "GET", "path": "/voice-samples"},
            {"method": "GET", "path": "/"},
        ]
    }
    groups = endpoint_groups(spec)
    assert list(groups) == ["orders", "payments", "voice-samples", "root"], list(groups)
    assert len(groups["orders"]) == 3
    assert module_name("voice-samples") == "voice_samples"
    assert pascal_case("voice_samples") == "VoiceSamples"
    assert pascal_case("orders") == "Orders"
    print(f"endpoint_groups self-check 통과 - 그룹 {len(groups)}개")
