"""SQLite-backed team registry.

Schema 极简: 一张表, 仅存 team_id + team_secret + 元数据.
Relay 重启后从这里重建团队列表; 连接状态全在内存, 不在 DB.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path


SCHEMA = """
CREATE TABLE IF NOT EXISTS teams (
    team_id      TEXT PRIMARY KEY,
    team_secret  TEXT NOT NULL,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


class TeamStore:
    """Thread-safe(ish) wrapper. SQLite handles its own locking; we just open one connection."""

    def __init__(self, db_path: str):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(db_path, check_same_thread=False)
        self.db.executescript(SCHEMA)
        self.db.commit()

    def register_team(self, team_id: str, secret: str) -> None:
        """Idempotent upsert."""
        self.db.execute(
            "INSERT INTO teams (team_id, team_secret) VALUES (?, ?) "
            "ON CONFLICT(team_id) DO UPDATE SET "
            "    team_secret = excluded.team_secret, "
            "    updated_at  = CURRENT_TIMESTAMP",
            (team_id, secret),
        )
        self.db.commit()

    def get_secret(self, team_id: str) -> str | None:
        row = self.db.execute(
            "SELECT team_secret FROM teams WHERE team_id = ?", (team_id,)
        ).fetchone()
        return row[0] if row else None

    def delete_team(self, team_id: str) -> bool:
        cur = self.db.execute("DELETE FROM teams WHERE team_id = ?", (team_id,))
        self.db.commit()
        return cur.rowcount > 0

    def list_teams(self) -> list[dict]:
        rows = self.db.execute(
            "SELECT team_id, created_at, updated_at FROM teams ORDER BY created_at"
        ).fetchall()
        return [
            {"team_id": r[0], "created_at": r[1], "updated_at": r[2]} for r in rows
        ]

    def close(self) -> None:
        self.db.close()
