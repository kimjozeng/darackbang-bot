import os
import aiosqlite

DB_PATH = os.getenv("DB_PATH", "darackbang.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS recruits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    channel_id INTEGER NOT NULL,
    message_id INTEGER,
    thread_id INTEGER,
    creator_id INTEGER NOT NULL,
    raid TEXT NOT NULL,
    difficulty TEXT NOT NULL,
    experience TEXT NOT NULL,
    min_item_level INTEGER NOT NULL DEFAULT 0,
    dealer_limit INTEGER NOT NULL DEFAULT 6,
    support_limit INTEGER NOT NULL DEFAULT 2,
    start_time TEXT NOT NULL,
    memo TEXT,
    status TEXT NOT NULL DEFAULT 'open',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS recruit_members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recruit_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    position TEXT NOT NULL CHECK(position IN ('dealer', 'support')),
    joined_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(recruit_id, user_id),
    FOREIGN KEY(recruit_id) REFERENCES recruits(id) ON DELETE CASCADE
);
"""

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(SCHEMA)
        await db.commit()

async def create_recruit(**data):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """INSERT INTO recruits
            (guild_id, channel_id, creator_id, raid, difficulty, experience,
             min_item_level, dealer_limit, support_limit, start_time, memo)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                data["guild_id"], data["channel_id"], data["creator_id"], data["raid"],
                data["difficulty"], data["experience"], data["min_item_level"],
                data["dealer_limit"], data["support_limit"], data["start_time"], data.get("memo")
            )
        )
        await db.commit()
        return cur.lastrowid

async def set_message_refs(recruit_id: int, message_id: int, thread_id: int | None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE recruits SET message_id=?, thread_id=? WHERE id=?",
            (message_id, thread_id, recruit_id),
        )
        await db.commit()

async def get_recruit(recruit_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM recruits WHERE id=?", (recruit_id,))
        row = await cur.fetchone()
        return dict(row) if row else None

async def list_open_recruits():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM recruits WHERE status='open' AND message_id IS NOT NULL")
        return [dict(r) for r in await cur.fetchall()]

async def list_members(recruit_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT user_id, position FROM recruit_members WHERE recruit_id=? ORDER BY id ASC",
            (recruit_id,),
        )
        return [dict(r) for r in await cur.fetchall()]

async def join_recruit(recruit_id: int, user_id: int, position: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO recruit_members (recruit_id, user_id, position) VALUES (?, ?, ?)",
            (recruit_id, user_id, position),
        )
        await db.commit()

async def leave_recruit(recruit_id: int, user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM recruit_members WHERE recruit_id=? AND user_id=?",
            (recruit_id, user_id),
        )
        await db.commit()

async def close_recruit(recruit_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE recruits SET status='closed' WHERE id=?", (recruit_id,))
        await db.commit()


async def update_recruit(
    recruit_id: int,
    *,
    experience: str,
    min_item_level: int,
    dealer_limit: int,
    support_limit: int,
    start_time: str,
    memo: str,
):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """UPDATE recruits
            SET experience=?, min_item_level=?, dealer_limit=?, support_limit=?,
                start_time=?, memo=?
            WHERE id=?""",
            (
                experience,
                min_item_level,
                dealer_limit,
                support_limit,
                start_time,
                memo,
                recruit_id,
            ),
        )
        await db.commit()
