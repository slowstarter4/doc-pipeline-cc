"""
데이터 모델(ERD) → SQL DDL (결정적 변환, LLM 미사용)

CLI: python scripts/schema_ddl.py <data_model.json> [--dialect sqlite|postgres] [-o out.sql]

doc-pipeline(OpenRouter판)의 schema_ddl 노드를 그대로 이식한 것 - LLM을 안 쓰는
순수 변환이라 원본 로직을 바꿀 이유가 없었다. 오케스트레이터(Claude Code 세션)가
data_model.json을 쓴 뒤 이 스크립트를 Bash로 호출해 schema.sql을 얻는다.

타입 매핑 근거 (sqlite 타입 어피니티):
- string → TEXT, date → TEXT (ISO 문자열)
- boolean → INTEGER (0/1)
- number → INTEGER (sqlite 어피니티는 실수를 강제 변환하지 않아 가격도 손실 없음)

한계: data_model에 관계(외래키) 정보가 없어 memberId 같은 필드는 INTEGER 컬럼으로만
만들고 FOREIGN KEY 제약은 안 건다 - 관계 규칙은 api_spec의 rules로 앱 레벨에서 강제.
"""

import argparse
import json
import sys

_DDL_TYPE_MAP = {
    "string": "TEXT",
    "number": "INTEGER",
    "boolean": "INTEGER",
    "date": "TEXT",
}

# 방언 분기는 PK 줄 하나뿐이다. 타입맵(boolean→INTEGER 0/1, date→TEXT)은 두 방언이
# 공유한다 - postgres 네이티브 BOOLEAN/DATE로 바꾸면 스택 앱 코드를 전부 고쳐야 해서
# "여러 스택이 같은 스키마 공유" 철학이 깨진다.
_DIALECT_PK = {
    "sqlite": "id INTEGER PRIMARY KEY AUTOINCREMENT",
    "postgres": "id SERIAL PRIMARY KEY",
}

# 엔티티명이 SQL 예약어와 겹치면 CREATE TABLE Order(...)가 postgres에서 문법 에러로
# 죽는다. 따옴표로 감싸는 대신(대소문자 구분 함정) 물리 테이블명에 밑줄을 붙여
# 충돌 자체를 없앤다 - 백엔드 서브에이전트는 이 DDL 텍스트를 그대로 보고 SQL을
# 쓰므로, 이름이 한 번만 바뀌면 전체가 일관되게 따라간다.
_SQL_RESERVED = {
    "order", "user", "group", "table", "select", "where", "from", "index",
    "key", "primary", "foreign", "check", "default", "column", "constraint",
}


def table_name(entity_name: str) -> str:
    """엔티티명 → 물리 테이블명. 예약어면 밑줄을 붙여 충돌을 피한다."""
    return f"{entity_name}_" if entity_name.lower() in _SQL_RESERVED else entity_name


def _table_ddl(entity: dict, pk: str) -> str:
    """엔티티 하나를 CREATE TABLE 문자열로. id는 ERD에 없어도 DB가 매기도록 자동 추가."""
    name = entity.get("name")
    if not name:
        return ""
    name = table_name(name)

    lines = [f"  {pk}"]
    for field in entity.get("fields", []):
        fname = field.get("name")
        if not fname or fname == "id":
            continue  # id는 위에서 이미 넣었다. ERD가 id를 또 선언해도 무시.
        sql_type = _DDL_TYPE_MAP.get(field.get("type"), "TEXT")
        null = " NOT NULL" if field.get("required") else ""
        lines.append(f"  {fname} {sql_type}{null}")

    body = ",\n".join(lines)
    return f"CREATE TABLE IF NOT EXISTS {name} (\n{body}\n);"


def generate_ddl(data_model: dict, dialect: str = "sqlite") -> str:
    pk = _DIALECT_PK.get(dialect, _DIALECT_PK["sqlite"])
    tables = [
        ddl
        for entity in (data_model or {}).get("entities", [])
        if (ddl := _table_ddl(entity, pk))
    ]
    return "\n\n".join(tables)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("data_model_json", help="ERD(data_model) JSON 파일 경로")
    p.add_argument("--dialect", choices=["sqlite", "postgres"], default="sqlite")
    p.add_argument("-o", "--output", help="출력 파일 경로 (생략 시 stdout)")
    args = p.parse_args()

    data_model = json.loads(open(args.data_model_json, encoding="utf-8").read())
    ddl = generate_ddl(data_model, args.dialect)

    if args.output:
        open(args.output, "w", encoding="utf-8").write(ddl)
    else:
        sys.stdout.write(ddl + "\n")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        main()
        sys.exit(0)

    # 인자 없이 실행하면 자기 점검만 한다 (도서 대출 3엔티티).
    model = {
        "entities": [
            {
                "name": "book",
                "fields": [
                    {"name": "title", "type": "string", "required": True},
                    {"name": "isbn", "type": "string", "required": True},
                    {"name": "publishedYear", "type": "number", "required": False},
                    {"name": "isAvailable", "type": "boolean", "required": True},
                ],
            },
            {
                "name": "loan",
                "fields": [
                    {"name": "memberId", "type": "number", "required": True},
                    {"name": "bookId", "type": "number", "required": True},
                    {"name": "dueDate", "type": "date", "required": True},
                    {"name": "id", "type": "number", "required": False},  # 무시돼야
                ],
            },
        ]
    }
    ddl = generate_ddl(model, "sqlite")
    print(ddl)

    assert "CREATE TABLE IF NOT EXISTS book (" in ddl
    assert "id INTEGER PRIMARY KEY AUTOINCREMENT" in ddl
    assert "title TEXT NOT NULL" in ddl
    assert "publishedYear INTEGER" in ddl and "publishedYear INTEGER NOT NULL" not in ddl

    # SQL 예약어(Order)와 겹치는 엔티티명은 물리 테이블명이 밑줄로 갈려야 한다.
    assert table_name("Order") == "Order_"
    assert table_name("book") == "book"
    order_model = {"entities": [{"name": "Order", "fields": [{"name": "status", "type": "string", "required": True}]}]}
    order_ddl = generate_ddl(order_model, "sqlite")
    assert "CREATE TABLE IF NOT EXISTS Order_ (" in order_ddl
    assert "CREATE TABLE IF NOT EXISTS Order (" not in order_ddl
    assert "isAvailable INTEGER NOT NULL" in ddl
    assert "memberId INTEGER NOT NULL" in ddl
    assert "dueDate TEXT NOT NULL" in ddl
    # ERD가 id를 또 선언해도 컬럼이 중복 생기면 안 된다 (loan에 id INTEGER 줄 없어야).
    assert ddl.count("id INTEGER PRIMARY KEY AUTOINCREMENT") == 2  # book, loan 각 1개
    assert "\n  id INTEGER,\n" not in ddl and "  id INTEGER\n" not in ddl
    # 빈 입력은 빈 문자열.
    assert generate_ddl({}, "sqlite") == ""
    assert generate_ddl({"entities": []}, "sqlite") == ""

    # postgres 방언: PK만 SERIAL로 갈리고 타입맵(INTEGER 0/1, TEXT)은 그대로여야 한다.
    pg = generate_ddl(model, "postgres")
    print("\n" + pg)
    assert pg.count("id SERIAL PRIMARY KEY") == 2
    assert "AUTOINCREMENT" not in pg
    assert "isAvailable INTEGER NOT NULL" in pg  # boolean 여전히 INTEGER (0/1 앱코드 유지)
    assert "dueDate TEXT NOT NULL" in pg          # date 여전히 TEXT (ISO 문자열 유지)
    print("\nschema_ddl self-check 통과 (sqlite + postgres)")
