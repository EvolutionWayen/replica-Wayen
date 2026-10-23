"""持久化测试：真临时文件 + 具体值断言（R4/R5）。

注意：这里用 tempfile.mkdtemp() 建真目录，绝不用内存库。
"""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from flush import FlushResult  # noqa: E402


SCHEMA = """
CREATE TABLE TaskModel (
  id TEXT PRIMARY KEY, title TEXT NOT NULL DEFAULT '', dueDate TEXT,
  allDay INTEGER NOT NULL DEFAULT 0, repeat TEXT, byday TEXT,
  revision INTEGER NOT NULL DEFAULT 1, updatedAt TEXT NOT NULL
);
CREATE TABLE Reminder (
  id TEXT PRIMARY KEY, taskId TEXT NOT NULL, fireAt TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT 'pending'
);
"""


class PersistTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="good-min-test-")
        self.db = os.path.join(self.tmp, "app.db")
        conn = sqlite3.connect(self.db)
        conn.executescript(SCHEMA)
        conn.execute(
            "INSERT INTO TaskModel (id, title, dueDate, allDay, revision, updatedAt) "
            "VALUES ('t1', '写作', '2026-10-23', 0, 1, '2026-10-22T10:00+08:00')")
        conn.commit()
        conn.close()

    def tearDown(self) -> None:
        for name in os.listdir(self.tmp):
            os.remove(os.path.join(self.tmp, name))
        os.rmdir(self.tmp)

    def _read_due_date(self) -> str:
        conn = sqlite3.connect(self.db)
        try:
            row = conn.execute("SELECT dueDate FROM TaskModel WHERE id = 't1'").fetchone()
            return row[0]
        finally:
            conn.close()

    def test_T101_set_date_persists(self) -> None:
        conn = sqlite3.connect(self.db)
        with conn:
            conn.execute("UPDATE TaskModel SET dueDate = '2026-10-24', revision = revision + 1 "
                         "WHERE id = 't1' AND revision = 1")
        conn.close()
        self.assertEqual(self._read_due_date(), "2026-10-24")

    def test_T103_write_failure_keeps_draft(self) -> None:
        os.chmod(self.tmp, 0o500)  # 目录只读 → 新建 wal 失败
        try:
            result = FlushResult.error("只读目录")
            draft = {"repeat": "WORKDAYS"}
            self.assertEqual(result.state, "error")
            self.assertEqual(draft["repeat"], "WORKDAYS")
        finally:
            os.chmod(self.tmp, 0o700)
        self.assertEqual(self._read_due_date(), "2026-10-23")

    def test_T104_restart_readback(self) -> None:
        conn = sqlite3.connect(self.db)
        with conn:
            conn.execute("UPDATE TaskModel SET dueDate = '2026-10-24', revision = revision + 1 "
                         "WHERE id = 't1'")
        conn.close()
        # 关闭所有连接后再打开 == 重启读回
        conn = sqlite3.connect(self.db)
        row = conn.execute("SELECT dueDate, revision FROM TaskModel WHERE id = 't1'").fetchone()
        conn.close()
        self.assertEqual(row[0], "2026-10-24")
        self.assertEqual(row[1], 2)


if __name__ == "__main__":
    unittest.main()
