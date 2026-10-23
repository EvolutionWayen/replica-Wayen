"""本地 SQLite 仓储：真文件、WAL、单命令单事务、提交后才广播。"""
from __future__ import annotations

import sqlite3
from typing import Dict, Optional


class Repository:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode = WAL")
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._listeners = []

    def get_task(self, task_id: str) -> Optional[Dict]:
        cur = self.conn.execute("SELECT * FROM TaskModel WHERE id = ?", (task_id,))
        row = cur.fetchone()
        return dict(row) if row else None

    def update_task(self, task_id: str, patch: Dict, expected_revision: int) -> bool:
        sets = ", ".join("%s = ?" % k for k in patch)
        values = list(patch.values())
        with self.conn:
            cur = self.conn.execute(
                "UPDATE TaskModel SET %s, revision = revision + 1 "
                "WHERE id = ? AND revision = ?" % sets,
                values + [task_id, int(expected_revision)])
            return cur.rowcount == 1

    def commit_all(self, pending) -> None:
        with self.conn:
            for item in pending:
                self.conn.execute(item["sql"], item["params"])

    def broadcast(self, event: str, payload: Dict) -> None:
        for fn in list(self._listeners):
            fn(event, payload)

    def subscribe(self, fn) -> None:
        self._listeners.append(fn)
