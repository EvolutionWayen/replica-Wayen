# -*- coding: utf-8 -*-
"""G10 痛点与差异化门。

判定（00-体系总纲.md §3.2）：
1. REPORT/feedback.md 存在
2. 每条痛点含 http(s) 链接与数字计数（点赞/回复/评分等）
3. 含样本量声明行（含「样本」或「共 N 条」）
4. 无明显编造标记（不检语义，只检结构与链接形式：占位链接、占位符、无出处的「据说」）

A 档可只做「自己骂原版什么」，但结构与链接纪律不变 —— 由 manifest.required 里
可配置 feedback_allow_self_only 显式放开「自己观察」类条目（仍须写清观察方式与日期）。
"""

from __future__ import annotations

import re

from . import common as C

STAGE = "G10"

DEFAULT_FEEDBACK = "REPORT/feedback.md"
PLACEHOLDER_HOSTS = ["example.com", "example.org", "localhost", "127.0.0.1",
                     "your-site", "xxx.com", "foo.com", "test.com"]
FAKE_MARKERS = ["TODO", "待补", "待定", "TBD", "据说", "听说", "有的用户说"]
COUNT_RE = re.compile(r"\d+\s*(条|人|次|赞|票|星|分|个|回复|comments?|likes?)", re.I)


PAIN_SECTION_WORDS = ["痛点", "问题", "抱怨", "骂", "差评", "评论", "反馈"]
ENTRY_TABLE_WORDS = ["痛点", "现象", "问题", "来源", "链接", "计数", "用户说"]
#: 这些表头说明是「我们的对策/差异化」而不是痛点本身
ACTION_TABLE_WORDS = ["做法", "我们的", "改进", "对策", "落点", "方案", "解决"]


def _pain_ranges(text):
    """痛点小节的正文行号区间 [(start, end)]（1-based，含端点）；找不到返回 []。"""
    out = []
    for sec in C.md_sections(text, 2):
        if any(w in sec["title"] for w in PAIN_SECTION_WORDS):
            start = sec["line"] + 1
            end = start + len(sec["lines"]) - 1
            out.append((start, end))
    return out


def _entries(text, ranges):
    """条目化：指定行区间内的列表项 / 表格数据行（返回真实文件行号）。

    表格只取「痛点/现象/来源/链接」类表头，排除「我们的做法/对策」这类改进表。
    """
    entries = []
    if ranges:
        allowed = set()
        for a, b in ranges:
            allowed.update(range(a, b + 1))
    else:
        allowed = set(range(1, len(text.splitlines()) + 1))

    body_lines = text.splitlines()
    for no, raw in enumerate(body_lines, 1):
        if no not in allowed:
            continue
        s = raw.strip()
        if re.match(r"^([-*+]|\d+[.、)])\s+\S", s):
            entries.append((no, s))

    for table in C.md_tables(text):
        header = " ".join(table["header"]).lower()
        if not table["header"]:
            continue
        if any(w in header for w in ACTION_TABLE_WORDS):
            continue  # 改进/差异化表，不是痛点条目
        if not any(w.lower() in header for w in ENTRY_TABLE_WORDS):
            continue
        for cells, no in zip(table["rows"], table["lines"]):
            if no not in allowed:
                continue
            joined = " ".join(c for c in cells if c).strip()
            if len(joined) >= 12:
                entries.append((no, joined))
    entries.sort(key=lambda x: x[0])
    return entries


def check(ctx):
    g = C.Gate(ctx, STAGE)
    if g.no_manifest():
        return g.results

    rel = str(ctx.required.get("feedback_report") or DEFAULT_FEEDBACK).strip()
    text = ctx.text(rel)
    if text is None:
        g.fail("feedback-exists", "feedback.md 存在",
               expected="%s 存在" % rel, actual="文件不存在", evidence=rel,
               hint="S10 产出：每条痛点带原始链接与计数，并给出对应改进项")
        return g.results
    g.pass_("feedback-exists", "feedback.md 存在",
            expected="文件存在", actual="%d 字节" % ctx.size(rel), evidence=rel)

    ranges = _pain_ranges(text)
    entries = _entries(text, ranges)
    lines = text.splitlines()
    if not entries:
        g.fail("feedback-entries", "每条痛点带链接与数字计数",
               expected="痛点写成列表项或表格行（≥1 条）",
               actual="没有可识别的条目", evidence=rel,
               hint="一条痛点一行：现象 + 原话/链接 + 计数（多少赞/多少评论）")
        return g.results

    with_link = [(no, s) for no, s in entries if C.URL_RE.search(s)]
    with_count = [(no, s) for no, s in entries if COUNT_RE.search(s)]
    # 允许「条目本身没链接，但同段下一行给了链接」的写法
    lines = text.splitlines()
    rescued = []
    for no, s in entries:
        if C.URL_RE.search(s):
            continue
        window = "\n".join(lines[no - 1:no + 2])
        if C.URL_RE.search(window):
            rescued.append((no, s))
    effective_links = set(no for no, _ in with_link) | set(no for no, _ in rescued)

    if len(effective_links) >= len(entries):
        g.pass_("feedback-links", "每条痛点带 http(s) 链接",
                expected="每条有可点链接", actual="%d/%d 条有链接" % (len(effective_links), len(entries)),
                evidence=rel)
    else:
        missing = [str(no) for no, _ in entries if no not in effective_links]
        g.fail("feedback-links", "每条痛点带 http(s) 链接",
               expected="每条痛点有原始出处链接（不许写「很多用户反馈」）",
               actual="%d 条缺链接（第 %s 行）" % (len(missing), "、".join(missing[:6])),
               evidence=rel,
               hint="贴应用商店评论 / 论坛帖子 / 社交平台的原始 URL；拿不到的条目删掉或注明观察方式与日期")

    if len(with_count) >= len(entries):
        g.pass_("feedback-counts", "每条痛点带数字计数",
                expected="每条有计数", actual="%d/%d 条有计数" % (len(with_count), len(entries)),
                evidence=rel)
    elif with_count:
        missing = [str(no) for no, _ in entries if no not in {n for n, _ in with_count}]
        g.fail("feedback-counts", "每条痛点带数字计数",
               expected="每条写清样本计数（多少条/多少赞/多少分）",
               actual="%d 条缺计数（第 %s 行）" % (len(missing), "、".join(missing[:6])),
               evidence=rel,
               hint="写「3 条一星评论都提到…」「该帖 128 赞」这种可核对计数")
    else:
        g.fail("feedback-counts", "每条痛点带数字计数",
               expected="每条有计数", actual="0 条带计数", evidence=rel,
               hint="计数是判断代表性最低成本的办法；没有计数就没有样本量")

    # ---- 样本量声明 ----
    sample_re = re.compile(r"样本|共\s*\d+\s*(条|人|个)|抓取|采集了?\s*\d+", re.I)
    sample_lines = [(no, s) for no, s in enumerate(lines, 1) if sample_re.search(s)]
    if sample_lines:
        g.pass_("feedback-sample", "含样本量声明",
                expected="写明样本来源与规模", actual="第 %d 行：%s" % (
                    sample_lines[0][0], sample_lines[0][1].strip()[:60]),
                evidence="%s:%d" % (rel, sample_lines[0][0]))
    else:
        g.fail("feedback-sample", "含样本量声明",
               expected="含「样本」或「共 N 条」的声明行",
               actual="未找到样本量声明", evidence=rel,
               hint="写「样本：App Store 中国区 1 星评论 42 条 + 小红书笔记 18 篇，采集于 2026-10-20」，"
                    "否则痛点没有代表性")

    # ---- 编造标记 ----
    problems = []
    for no, s in entries:
        for url in C.URL_RE.findall(s):
            host = re.sub(r"^https?://", "", url).split("/")[0].lower()
            if any(p in host for p in PLACEHOLDER_HOSTS):
                problems.append("第 %d 行占位链接 %s" % (no, host))
        for marker in FAKE_MARKERS:
            if marker in s:
                problems.append("第 %d 行含「%s」" % (no, marker))
    if problems:
        g.fail("feedback-fabrication", "无明显编造标记",
               expected="无占位链接、无「据说/听说」、无 TODO",
               actual="%d 处：%s" % (len(problems), "；".join(problems[:4])),
               evidence=rel,
               hint="换成真实 URL 与真实指标；转述必须标明来源与日期（R15）")
    else:
        g.pass_("feedback-fabrication", "无明显编造标记",
                expected="无占位链接与编造词",
                actual="%d 条条目全部可追溯" % len(entries), evidence=rel)

    return g.results
