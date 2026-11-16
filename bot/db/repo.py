from datetime import datetime, timedelta, timezone
from pathlib import Path

import aiosqlite

from bot.services.safety import mask_pii


class Repository:
    def __init__(self, path: Path) -> None:
        self.path = path

    async def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.path) as db:
            await db.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    language TEXT NOT NULL DEFAULT 'kk',
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS questions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    question TEXT NOT NULL,
                    record_id INTEGER,
                    score REAL,
                    answered INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS unanswered (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    question TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    record_id INTEGER,
                    rating INTEGER NOT NULL,
                    reason TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS llm_usage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    tokens INTEGER NOT NULL DEFAULT 0,
                    cost_usd REAL NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_questions_user ON questions(user_id);
                CREATE INDEX IF NOT EXISTS idx_questions_date ON questions(created_at);
                CREATE INDEX IF NOT EXISTS idx_unanswered_date ON unanswered(created_at);
                """
            )
            await db.commit()
        await self.prune_logs(90)

    async def register_user(self, user_id: int) -> str:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT OR IGNORE INTO users(user_id, created_at) VALUES (?, ?)",
                (user_id, self._now()),
            )
            cursor = await db.execute("SELECT language FROM users WHERE user_id = ?", (user_id,))
            row = await cursor.fetchone()
            await db.commit()
            return row[0] if row else "kk"

    async def set_language(self, user_id: int, language: str) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT INTO users(user_id, language, created_at) VALUES (?, ?, ?) "
                "ON CONFLICT(user_id) DO UPDATE SET language=excluded.language",
                (user_id, language, self._now()),
            )
            await db.commit()

    async def get_language(self, user_id: int) -> str:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute("SELECT language FROM users WHERE user_id = ?", (user_id,))
            row = await cursor.fetchone()
            return row[0] if row else "kk"

    async def log_question(
        self,
        user_id: int,
        question: str,
        record_id: int | None,
        score: float | None,
        *,
        track_unanswered: bool = True,
    ) -> None:
        stamp = self._now()
        masked = mask_pii(question)
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT INTO questions(user_id, question, record_id, score, answered, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, masked, record_id, score, int(record_id is not None or not track_unanswered), stamp),
            )
            if record_id is None and track_unanswered:
                await db.execute(
                    "INSERT INTO unanswered(user_id, question, created_at) VALUES (?, ?, ?)",
                    (user_id, masked, stamp),
                )
            await db.commit()

    async def add_feedback(self, user_id: int, record_id: int | None, rating: int, reason: str | None = None) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT INTO feedback(user_id, record_id, rating, reason, created_at) VALUES (?, ?, ?, ?, ?)",
                (user_id, record_id, rating, mask_pii(reason or "") or None, self._now()),
            )
            await db.commit()

    async def delete_user_data(self, user_id: int) -> None:
        async with aiosqlite.connect(self.path) as db:
            for table in ("questions", "unanswered", "feedback", "llm_usage", "users"):
                await db.execute(f"DELETE FROM {table} WHERE user_id = ?", (user_id,))
            await db.commit()

    async def stats(self) -> dict[str, object]:
        async with aiosqlite.connect(self.path) as db:
            users = await (await db.execute("SELECT COUNT(*) FROM users")).fetchone()
            daily = await (await db.execute(
                "SELECT COUNT(*) FROM questions WHERE date(created_at)=date('now')"
            )).fetchone()
            unanswered = await (await db.execute(
                "SELECT COUNT(*) FROM questions WHERE answered=0"
            )).fetchone()
            total = await (await db.execute("SELECT COUNT(*) FROM questions")).fetchone()
            topics = await db.execute(
                "SELECT record_id, COUNT(*) AS n FROM questions WHERE record_id IS NOT NULL "
                "GROUP BY record_id ORDER BY n DESC LIMIT 10"
            )
            ratings = await db.execute("SELECT rating, COUNT(*) FROM feedback GROUP BY rating")
            usage = await (await db.execute(
                "SELECT COALESCE(SUM(tokens),0), COALESCE(SUM(cost_usd),0) FROM llm_usage "
                "WHERE date(created_at)=date('now')"
            )).fetchone()
            return {
                "users": users[0] if users else 0,
                "daily_questions": daily[0] if daily else 0,
                "unanswered": unanswered[0] if unanswered else 0,
                "total_questions": total[0] if total else 0,
                "top_records": await topics.fetchall(),
                "ratings": dict(await ratings.fetchall()),
                "daily_tokens": usage[0] if usage else 0,
                "daily_cost": usage[1] if usage else 0,
            }

    async def record_usage(self, user_id: int, tokens: int, cost_usd: float) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT INTO llm_usage(user_id, tokens, cost_usd, created_at) VALUES (?, ?, ?, ?)",
                (user_id, tokens, cost_usd, self._now()),
            )
            await db.commit()

    async def usage_today(self) -> tuple[int, float]:
        async with aiosqlite.connect(self.path) as db:
            row = await (await db.execute(
                "SELECT COALESCE(SUM(tokens),0), COALESCE(SUM(cost_usd),0) FROM llm_usage "
                "WHERE date(created_at)=date('now')"
            )).fetchone()
            return int(row[0]), float(row[1])

    async def unanswered_rows(self) -> list[tuple[int, str, str]]:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                "SELECT id, question, created_at FROM unanswered ORDER BY id DESC"
            )
            return await cursor.fetchall()

    async def user_ids(self) -> list[int]:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute("SELECT user_id FROM users")
            return [row[0] for row in await cursor.fetchall()]

    async def prune_logs(self, days: int) -> None:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        async with aiosqlite.connect(self.path) as db:
            for table in ("questions", "unanswered", "feedback", "llm_usage"):
                await db.execute(f"DELETE FROM {table} WHERE created_at < ?", (cutoff,))
            await db.commit()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()
