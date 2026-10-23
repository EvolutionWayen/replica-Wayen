"""日期修改（示例实现，门禁夹具用）。

纪律：命令携带入队时捕获的 entityId 与 revision，绝不读「当前选中」（R2/失效模式 05）。
"""
from __future__ import annotations

from .repository import Repository
from .flush import FlushResult


class DateEditCommand:
    def __init__(self, repo: Repository) -> None:
        self.repo = repo

    def set_date(self, task_id: str, due_date: str, all_day: bool, revision: int) -> FlushResult:
        if not due_date:
            return FlushResult.error("dueDate 不能为空")
        row = self.repo.get_task(task_id)
        if row is None:
            return FlushResult.error("任务不存在：%s" % task_id)
        if int(row["revision"]) != int(revision):
            return FlushResult.conflict("revision 已变化：%d -> %d"
                                        % (int(revision), int(row["revision"])))
        patch = {"dueDate": due_date, "allDay": 1 if all_day else 0}
        ok = self.repo.update_task(task_id, patch, expected_revision=revision)
        if not ok:
            return FlushResult.error("写库失败，草稿保留")
        self.repo.broadcast("TaskDateChanged", {"taskId": task_id, "dueDate": due_date})
        return FlushResult.ok("已改为 %s" % due_date)
