"""CI e2e 픽스처: LLM 서브에이전트가 만들 라우터를 대신하는 손으로 쓴 최소 구현.
scaffold+verify_backend.py 파이프라인 자체(스캐폴드/식별자/DB격리/happyPath 러너)를
회귀 검증하기 위한 것 - 실제 도메인 생성 품질과는 무관하다."""

import os

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from db import get_conn

router = APIRouter()
_PG = bool(os.environ.get("DATABASE_URL"))


class WidgetIn(BaseModel):
    name: str
    quantity: int


class WidgetUpdate(BaseModel):
    quantity: int


@router.post("/widgets", status_code=201)
def create_widget(body: WidgetIn):
    if not body.name:
        raise HTTPException(status_code=400, detail="name은 필수입니다")
    if body.quantity < 0:
        raise HTTPException(status_code=400, detail="quantity는 0 이상이어야 합니다")
    conn = get_conn()
    try:
        if _PG:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO widget (name, quantity) VALUES (%s, %s) RETURNING id",
                    (body.name, body.quantity),
                )
                new_id = cur.fetchone()[0]
            conn.commit()
        else:
            cur = conn.execute(
                "INSERT INTO widget (name, quantity) VALUES (?, ?)",
                (body.name, body.quantity),
            )
            conn.commit()
            new_id = cur.lastrowid
        return {"id": new_id, "name": body.name, "quantity": body.quantity}
    finally:
        conn.close()


@router.get("/widgets")
def list_widgets():
    conn = get_conn()
    try:
        if _PG:
            with conn.cursor() as cur:
                cur.execute("SELECT id, name, quantity FROM widget")
                rows = cur.fetchall()
        else:
            rows = conn.execute("SELECT id, name, quantity FROM widget").fetchall()
        return {"widgets": [{"id": r[0], "name": r[1], "quantity": r[2]} for r in rows]}
    finally:
        conn.close()


@router.put("/widgets/{id}")
def update_widget(id: int, body: WidgetUpdate):
    conn = get_conn()
    try:
        if _PG:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE widget SET quantity = %s WHERE id = %s RETURNING id, name, quantity",
                    (body.quantity, id),
                )
                row = cur.fetchone()
            conn.commit()
        else:
            conn.execute("UPDATE widget SET quantity = ? WHERE id = ?", (body.quantity, id))
            conn.commit()
            row = conn.execute(
                "SELECT id, name, quantity FROM widget WHERE id = ?", (id,)
            ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="위젯을 찾을 수 없습니다")
        return {"id": row[0], "name": row[1], "quantity": row[2]}
    finally:
        conn.close()
