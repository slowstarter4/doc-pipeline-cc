// CI e2e 픽스처(sqlite 전용) - db.ts가 `db`만 export하므로 postgres 픽스처와
// 파일을 분리했다(TS 정적 named import라 없는 심볼을 import하면 컴파일 에러).

import { Router } from 'express';
import { db } from '../db';

const router = Router();

interface Widget {
  id: number;
  name: string;
  quantity: number;
}

router.post('/widgets', (req, res) => {
  const { name, quantity } = req.body;
  if (name === undefined || name === null || name === '') {
    return res.status(400).json({ message: 'name은 필수입니다' });
  }
  if (quantity === undefined || quantity === null || quantity < 0) {
    return res.status(400).json({ message: 'quantity는 0 이상이어야 합니다' });
  }
  try {
    const result = db.prepare('INSERT INTO widget (name, quantity) VALUES (?, ?)').run(name, quantity);
    return res.status(201).json({ id: result.lastInsertRowid, name, quantity });
  } catch (e) {
    console.error(e);
    return res.status(500).json({ message: 'internal server error' });
  }
});

router.get('/widgets', (req, res) => {
  try {
    const rows = db.prepare('SELECT id, name, quantity FROM widget').all() as unknown as Widget[];
    return res.json({ widgets: rows });
  } catch (e) {
    console.error(e);
    return res.status(500).json({ message: 'internal server error' });
  }
});

router.put('/widgets/:id', (req, res) => {
  const id = Number(req.params.id);
  const { quantity } = req.body;
  try {
    const info = db.prepare('UPDATE widget SET quantity = ? WHERE id = ?').run(quantity, id);
    if (info.changes === 0) {
      return res.status(404).json({ message: '위젯을 찾을 수 없습니다' });
    }
    const row = db.prepare('SELECT id, name, quantity FROM widget WHERE id = ?').get(id) as unknown as Widget;
    return res.json(row);
  } catch (e) {
    console.error(e);
    return res.status(500).json({ message: 'internal server error' });
  }
});

export default router;
