"""关窗/退出冲刷：必须返回结构化结果（R3），并在失败时阻止关窗。"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FlushResult:
    """三态：ok / unknown / error。调用方必须消费它，不许 fire-and-forget。"""

    state: str
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.state == "ok"

    @classmethod
    def ok_(cls, detail: str = "") -> "FlushResult":
        return cls("ok", detail)

    @classmethod
    def unknown(cls, detail: str = "") -> "FlushResult":
        return cls("unknown", detail)

    @classmethod
    def error(cls, detail: str = "") -> "FlushResult":
        return cls("error", detail)

    @classmethod
    def conflict(cls, detail: str = "") -> "FlushResult":
        return cls("error", "conflict: " + detail)


class Flusher:
    def __init__(self, queue, repo) -> None:
        self.queue = queue
        self.repo = repo

    def flush(self) -> FlushResult:
        pending = self.queue.drain()
        if not pending:
            return FlushResult.ok_("无待写")
        try:
            self.repo.commit_all(pending)
        except Exception as exc:  # 至少留脱敏日志（R13）
            return FlushResult.error("冲刷失败：%s" % type(exc).__name__)
        return FlushResult.ok_("已写 %d 条" % len(pending))
