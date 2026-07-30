// CI e2e 픽스처(postgres 전용) - db.ts가 `pool`만 export하므로 sqlite 픽스처와
// 파일을 분리했다(TS 정적 named import라 없는 심볼을 import하면 컴파일 에러).

import { Router } from 'express';
import { pool } from '../db';

const router = Router();

interface Widget {
  id: number;
  name: string;
  quantity: number;
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
    const result = await pool.query(
      'INSERT INTO widget (name, quantity) VALUES ($1, $2) RETURNING id',
      [name, quantity],
    );
    return res.status(201).json({ id: result.rows[0].id, name, quantity });
  } catch (e) {
    console.error(e);
    return res.status(500).json({ message: 'internal server error' });
  }
});

router.get('/widgets', async (req, res) => {
  try {
    const result = await pool.query('SELECT id, name, quantity FROM widget');
    return res.json({ widgets: result.rows as Widget[] });
  } catch (e) {
    console.error(e);
    return res.status(500).json({ message: 'internal server error' });
  }
});

router.put('/widgets/:id', async (req, res) => {
  const id = Number(req.params.id);
  const { quantity } = req.body;
  try {
    const result = await pool.query(
      'UPDATE widget SET quantity = $1 WHERE id = $2 RETURNING id, name, quantity',
      [quantity, id],
    );
    if (result.rows.length === 0) {
      return res.status(404).json({ message: '위젯을 찾을 수 없습니다' });
    }
    return res.json(result.rows[0] as Widget);
  } catch (e) {
    console.error(e);
    return res.status(500).json({ message: 'internal server error' });
  }
});

export default router;
