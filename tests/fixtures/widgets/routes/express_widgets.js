// CI e2e 픽스처: LLM 서브에이전트가 만들 라우터를 대신하는 손으로 쓴 최소 구현.
// scaffold+verify_backend.py 파이프라인 자체를 회귀 검증하기 위한 것 - 실제 도메인
// 생성 품질과는 무관하다.

const express = require('express');
const router = express.Router();
const isPg = !!process.env.DATABASE_URL;

let db, pool;
if (isPg) {
  ({ pool } = require('../db'));
} else {
  ({ db } = require('../db'));
}

router.post('/widgets', async (req, res) => {
  const { name, quantity } = req.body;
  if (name === undefined || name === null || name === '') {
    return res.status(400).json({ message: 'name은 필수입니다' });
  }
  if (quantity === undefined || quantity === null || quantity < 0) {
    return res.status(400).json({ message: 'quantity는 0 이상이어야 합니다' });
  }
  try {
    if (isPg) {
      const result = await pool.query(
        'INSERT INTO widget (name, quantity) VALUES ($1, $2) RETURNING id',
        [name, quantity],
      );
      return res.status(201).json({ id: result.rows[0].id, name, quantity });
    }
    const result = db.prepare('INSERT INTO widget (name, quantity) VALUES (?, ?)').run(name, quantity);
    return res.status(201).json({ id: result.lastInsertRowid, name, quantity });
  } catch (e) {
    console.error(e);
    return res.status(500).json({ message: 'internal server error' });
  }
});

router.get('/widgets', async (req, res) => {
  try {
    if (isPg) {
      const result = await pool.query('SELECT id, name, quantity FROM widget');
      return res.json({ widgets: result.rows });
    }
    const rows = db.prepare('SELECT id, name, quantity FROM widget').all();
    return res.json({ widgets: rows });
  } catch (e) {
    console.error(e);
    return res.status(500).json({ message: 'internal server error' });
  }
});

router.put('/widgets/:id', async (req, res) => {
  const id = Number(req.params.id);
  const { quantity } = req.body;
  try {
    if (isPg) {
      const result = await pool.query(
        'UPDATE widget SET quantity = $1 WHERE id = $2 RETURNING id, name, quantity',
        [quantity, id],
      );
      if (result.rows.length === 0) {
        return res.status(404).json({ message: '위젯을 찾을 수 없습니다' });
      }
      return res.json(result.rows[0]);
    }
    const info = db.prepare('UPDATE widget SET quantity = ? WHERE id = ?').run(quantity, id);
    if (info.changes === 0) {
      return res.status(404).json({ message: '위젯을 찾을 수 없습니다' });
    }
    const row = db.prepare('SELECT id, name, quantity FROM widget WHERE id = ?').get(id);
    return res.json(row);
  } catch (e) {
    console.error(e);
    return res.status(500).json({ message: 'internal server error' });
  }
});

module.exports = router;
