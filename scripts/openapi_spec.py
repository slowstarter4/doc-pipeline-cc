"""
API 명세(내부 단순 스키마) → 정식 OpenAPI 3.0 문서 (결정적 변환, LLM 미사용)

CLI: python scripts/openapi_spec.py <api_spec.json> [--data-model data_model.json] [-o openapi.json]

doc-pipeline(OpenRouter판)의 openapi_spec 노드를 그대로 이식. 같은 입력이면 항상
같은 출력이어야 schemathesis 같은 계약검사 도구가 신뢰할 수 있다.

성공/에러 상태 코드는 REST 관례를 규칙으로 인코딩해서 채운다(LLM에 안 묻는다):
- POST는 201(Created), 그 외는 200.
- path에 {id} 같은 파라미터가 있으면 404를 문서화한다.
- request body가 있거나 path parameter가 있으면 400을 문서화한다.
"""

import argparse
import json
import re
import sys

_TYPE_MAP = {
    "string": {"type": "string"},
    "number": {"type": "number"},
    "boolean": {"type": "boolean"},
    "date": {"type": "string", "format": "date"},
}

# path parameter는 거의 항상 리소스 식별자(id)라서 정수로 취급한다 - 안 그러면
# schemathesis가 6.49e-205 같은 실수를 넣어보다 서버 정수 파싱 실패로 "명세는
# 통과인데 서버가 거부"하는 거짓 실패가 생긴다.
_PATH_PARAM_TYPE_MAP = {**_TYPE_MAP, "number": {"type": "integer"}}

_ERROR_SCHEMA = {"type": "object", "properties": {"message": {"type": "string"}}}


def _schema_for(value, required_map: dict | None = None) -> dict:
    if isinstance(value, list):
        item_schema = _schema_for(value[0], required_map) if value else {"type": "object"}
        return {"type": "array", "items": item_schema}

    if isinstance(value, dict):
        properties = {}
        required = []
        for name, sub in value.items():
            if isinstance(sub, (list, dict)):
                properties[name] = _schema_for(sub, required_map)
            else:
                properties[name] = _TYPE_MAP.get(sub, {"type": "string"})
            if required_map and required_map.get(name):
                required.append(name)
        schema = {"type": "object", "properties": properties}
        if required:
            schema["required"] = required
        return schema

    return _TYPE_MAP.get(value, {"type": "string"})


def _build_required_map(data_model: dict) -> dict:
    required_map: dict = {}
    for entity in data_model.get("entities", []):
        for field in entity.get("fields", []):
            name = field.get("name")
            if name is None:
                continue
            if field.get("required"):
                required_map[name] = True
            else:
                required_map.setdefault(name, False)
    return required_map


def _build_type_map(data_model: dict) -> dict:
    type_map: dict = {}
    for entity in data_model.get("entities", []):
        for field in entity.get("fields", []):
            name = field.get("name")
            if name is None:
                continue
            type_map.setdefault(name, field.get("type"))
    return type_map


def generate_openapi(api_spec: dict, data_model: dict | None = None) -> dict:
    data_model = data_model or {}
    endpoints = api_spec.get("endpoints", [])
    required_map = _build_required_map(data_model)
    type_map = _build_type_map(data_model)
    paths: dict = {}

    for ep in endpoints:
        method = ep["method"].lower()
        path = ep["path"]
        paths.setdefault(path, {})

        success_code = "201" if method == "post" else "200"
        success_desc = "생성됨" if success_code == "201" else "성공"

        responses = {
            success_code: {
                "description": success_desc,
                "content": {
                    "application/json": {
                        "schema": _schema_for(ep.get("response", {}), required_map)
                    }
                },
            }
        }

        has_path_param = bool(re.search(r"\{(\w+)\}", path))
        if has_path_param:
            responses["404"] = {
                "description": "리소스를 찾을 수 없음",
                "content": {"application/json": {"schema": _ERROR_SCHEMA}},
            }

        if ep.get("request") or has_path_param:
            responses["400"] = {
                "description": "잘못된 요청 (유효성 검증 실패)",
                "content": {"application/json": {"schema": _ERROR_SCHEMA}},
            }

        operation = {"summary": ep.get("summary", ""), "responses": responses}

        # 업무 규칙(rules)은 OpenAPI에 대응하는 자리가 없어 description으로 옮긴다.
        rules = ep.get("rules") or []
        if rules:
            operation["description"] = "업무 규칙:\n" + "\n".join(f"- {r}" for r in rules)

        for match in re.findall(r"\{(\w+)\}", path):
            param_schema = _PATH_PARAM_TYPE_MAP.get(type_map.get(match), {"type": "string"})
            operation.setdefault("parameters", []).append(
                {"name": match, "in": "path", "required": True, "schema": param_schema}
            )

        if ep.get("request"):
            operation["requestBody"] = {
                "required": True,
                "content": {
                    "application/json": {"schema": _schema_for(ep["request"], required_map)}
                },
            }

        paths[path][method] = operation

    return {
        "openapi": "3.0.3",
        "info": {"title": "Generated API (doc-pipeline-cc)", "version": "1.0.0"},
        "paths": paths,
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("api_spec_json")
    p.add_argument("--data-model", help="ERD JSON 경로 (path parameter 타입 추론용, 선택)")
    p.add_argument("-o", "--output", help="출력 파일 경로 (생략 시 stdout)")
    args = p.parse_args()

    api_spec = json.loads(open(args.api_spec_json, encoding="utf-8").read())
    data_model = (
        json.loads(open(args.data_model, encoding="utf-8").read()) if args.data_model else {}
    )
    doc = generate_openapi(api_spec, data_model)
    text = json.dumps(doc, ensure_ascii=False, indent=2)

    if args.output:
        open(args.output, "w", encoding="utf-8").write(text)
    else:
        print(text)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        main()
        sys.exit(0)

    spec = {
        "endpoints": [
            {
                "method": "POST",
                "path": "/todos",
                "request": {"title": "string", "dueDate": "date"},
                "response": {"id": "number", "title": "string"},
                "rules": ["title은 빈 문자열도 허용"],
            },
            {
                "method": "GET",
                "path": "/todos/{id}",
                "response": {"id": "number", "title": "string"},
            },
        ]
    }
    model = {
        "entities": [
            {
                "name": "todo",
                "fields": [
                    {"name": "id", "type": "number", "required": False},
                    {"name": "title", "type": "string", "required": True},
                ],
            }
        ]
    }
    doc = generate_openapi(spec, model)
    post_op = doc["paths"]["/todos"]["post"]
    get_op = doc["paths"]["/todos/{id}"]["get"]

    assert "201" in post_op["responses"]
    assert "400" in post_op["responses"]  # request body 있으므로
    assert "id" in post_op["responses"]["201"]["content"]["application/json"]["schema"]["properties"]
    assert post_op["requestBody"]["content"]["application/json"]["schema"]["required"] == ["title"]
    assert "업무 규칙" in post_op["description"]

    assert "200" in get_op["responses"]
    assert "404" in get_op["responses"]  # path parameter 있으므로
    # ERD에서 id가 number이므로 path parameter도 integer로 추론돼야 한다.
    assert get_op["parameters"][0]["schema"] == {"type": "integer"}

    print("openapi_spec self-check 통과")
