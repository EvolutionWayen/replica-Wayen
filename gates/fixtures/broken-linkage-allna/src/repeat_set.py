"""重复规则设置（示例实现）。

byday 用 1..7 表示周一..周日；WORKDAYS 固定为 1,2,3,4,5。
"""
from __future__ import annotations

from .repository import Repository
from .flush import FlushResult

RULES = ("NONE", "WEEKLY", "WORKDAYS", "CUSTOM")


class RepeatCommand:
    def __init__(self, repo: Repository) -> None:
        self.repo = repo

    def set_workdays(self, task_id: str, revision: int) -> FlushResult:
        return self._write(task_id, "WORKDAYS", "1,2,3,4,5", revision)

    def set_weekly(self, task_id: str, byday, revision: int) -> FlushResult:
        days = [int(d) for d in byday if 1 <= int(d) <= 7]
        if not days:
            return FlushResult.error("至少选择一天")
        return self._write(task_id, "WEEKLY", ",".join(str(d) for d in sorted(days)), revision)

    def clear(self, task_id: str, revision: int) -> FlushResult:
        return self._write(task_id, None, "", revision)

    def _write(self, task_id: str, rule, byday: str, revision: int) -> FlushResult:
        row = self.repo.get_task(task_id)
        if row is None:
            return FlushResult.error("任务不存在：%s" % task_id)
        if int(row["revision"]) != int(revision):
            return FlushResult.conflict("revision 冲突")
        ok = self.repo.update_task(task_id, {"repeat": rule, "byday": byday},
                                   expected_revision=revision)
        if not ok:
            return FlushResult.error("写库失败，草稿保留")
        self.repo.broadcast("TaskRepeatChanged", {"taskId": task_id, "rule": rule})
        return FlushResult.ok("重复规则已更新")
