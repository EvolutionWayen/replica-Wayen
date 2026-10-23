"""最小 CLI（竖切证据用）：create / show。"""
from __future__ import annotations

import argparse
import os
import sys
import uuid
from datetime import datetime

from .repository import Repository

DB_HOME = os.path.join(os.path.expanduser("~"), "Library", "Application Support", "good-min")
DB_PATH = os.environ.get("GOOD_MIN_DB") or os.path.join(DB_HOME, "app.db")


def _repo() -> Repository:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    return Repository(DB_PATH)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="app.cli")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create")
    c.add_argument("--title", required=True)
    c.add_argument("--due", required=True)
    c.add_argument("--all-day", action="store_true")
    s = sub.add_parser("show")
    s.add_argument("--id")
    s.add_argument("--last", action="store_true")
    a = ap.parse_args(argv)
    repo = _repo()
    if a.cmd == "create":
        tid = str(uuid.uuid4())[:8]
        repo.conn.execute(
            "INSERT INTO TaskModel (id, title, dueDate, allDay, revision, updatedAt) "
            "VALUES (?, ?, ?, ?, 1, ?)",
            (tid, a.title, a.due, 1 if a.all_day else 0,
             datetime.now().astimezone().isoformat(timespec="seconds")))
        repo.conn.commit()
        print("created id=%s dueDate=%s allDay=%d revision=1" % (tid, a.due, int(a.all_day)))
        return 0
    row = None
    if a.id:
        row = repo.get_task(a.id)
    elif a.last:
        cur = repo.conn.execute("SELECT * FROM TaskModel ORDER BY updatedAt DESC LIMIT 1")
        found = cur.fetchone()
        row = dict(found) if found else None
    if row is None:
        print("not found", file=sys.stderr)
        return 1
    print("id=%s dueDate=%s allDay=%s revision=%s"
          % (row["id"], row["dueDate"], row["allDay"], row["revision"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
