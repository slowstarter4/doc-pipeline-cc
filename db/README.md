# db

`DB_TARGET=postgres`일 때 붙는 Postgres 컨테이너. 오케스트레이터(빌드 스킬)는 이걸
자동 기동하지 않는다 — 여기서 사람이 직접 올렸다 내린다(여러 환경 자동 기동은
깨지기 쉽다는 판단).

```bash
cd db
docker compose up -d      # 올리기 (postgres:16, 호스트 포트 55432)
docker compose down       # 내리기 (데이터 유지)
docker compose down -v    # 내리고 데이터까지 삭제
docker compose ps         # 상태
```

- 접속 규약(생성 백엔드가 읽는 표준): `postgresql://doc:doc@localhost:55432/doc`
- 호스트 포트 55432 — 5432·5433은 Windows WinNAT 예약범위(5346-5445)라 bind가 막힌다.
- 이 값(자격증명·포트)은 각 `.claude/skills/gen-backend-*/SKILL.md`가 지시하는
  DATABASE_URL/`application.properties`와 한 쌍이다. 바꾸면 스킬 쪽도 같이 바꿔야 한다.
