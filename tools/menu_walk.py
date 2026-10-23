#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""menu_walk.py —— 菜单树穷举器（把「选项不对 / 该灰的不灰」这类翻车提前暴露）

读 BLUEPRINT/menus.csv，做四件事：

  --tree     缩进树，按同级 order 排序，带类型标记（▸ 子菜单 / ● 动作 / ◉ 单选 /
             ☑ 多选 / ── 分隔符 / ¶ 纯文字）
  --cards    每个叶子打印一张「三条件卡」：显示条件 / 可用条件 / 选中条件
             + 触发命令 + 契约文件 + 出现在哪些屏幕
  --gaps     缺项表：哪些叶子缺 command / 缺契约 / 缺三条件（这是 S2 最容易糊弄的地方）
  --check    门禁用：退出码 0 干净 / 1 有缺项或结构问题
  --from-screens
             按 screens/ 里的截图数量，打印「分层截图编号」操作指引，并生成一份
             待填骨架（只写说明，不联网、不猜原版行为）

为什么要这张表：00 §10-02 的真实翻车是「显示、可用、选中三种条件混成一句『看情况』」，
做出来就是该藏的没藏、该灰的不灰。本工具把这三种条件强行摊开，缺一个就报。

用法：
    python3 tools/menu_walk.py --project .              # 默认：树 + 汇总
    python3 tools/menu_walk.py --project . --tree
    python3 tools/menu_walk.py --project . --cards
    python3 tools/menu_walk.py --project . --gaps
    python3 tools/menu_walk.py --project . --check --json
    python3 tools/menu_walk.py --project . --from-screens --screens screens/

退出码：0 干净（--check 语义）；1 有缺项；2 用法/输入错误
"""

from __future__ import annotations

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import replica_common as rc  # noqa: E402

TOOL = "menu_walk"
MENUS_REL = os.path.join("BLUEPRINT", "menus.csv")
CONTRACTS_REL = os.path.join("BLUEPRINT", "contracts")

TYPE_MARK = {
    "submenu": "▸",
    "action": "●",
    "radio": "◉",
    "checkbox": "☑",
    "separator": "──",
    "label": "¶",
}
TYPE_NAME = {
    "submenu": "子菜单",
    "action": "动作",
    "radio": "单选",
    "checkbox": "多选",
    "separator": "分隔符",
    "label": "纯文字",
}
IMAGE_EXT = (".png", ".jpg", ".jpeg", ".heic", ".webp", ".gif", ".tiff")

CARD_FIELDS = [
    ("visibility_cond", "显示条件", "什么上下文/模式/数据状态下出现；隐藏后布局与焦点怎么办"),
    ("enabled_cond", "可用条件", "可见 ≠ 可用：禁用原因与提示"),
    ("checked_cond", "选中条件", "当前选中态由哪个持久值或草稿值决定"),
]


class Node:
    def __init__(self, row):
        self.row = row
        self.line = row.get("line")
        self.id = rc.cell(row, "node_id")
        self.parent = rc.cell(row, "parent_id") or "ROOT"
        self.type = rc.cell(row, "type").lower()
        self.label = rc.cell(row, "label")
        self.path = rc.cell(row, "path")
        self.order = rc.cell(row, "order")
        self.shortcut = rc.cell(row, "shortcut")
        self.vis = rc.cell(row, "visibility_cond")
        self.en = rc.cell(row, "enabled_cond")
        self.ck = rc.cell(row, "checked_cond")
        self.command = rc.cell(row, "command")
        self.contract = rc.cell(row, "contract_ref")
        self.screens = rc.cell(row, "screens")
        # SCHEMAS §4（15 列）：screens 之后、notes 之前是 default_item
        # = 打开菜单时默认高亮/预选哪一项；与 checked_cond（选中条件）不同。
        self.default_item = rc.cell(row, "default_item")
        self.notes = rc.cell(row, "notes")
        self.children = []

    @property
    def order_key(self):
        try:
            return (0, int(self.order), self.line or 0)
        except (TypeError, ValueError):
            return (1, 0, self.line or 0)

    @property
    def is_leaf(self):
        return not self.children

    @property
    def needs_behaviour(self):
        return self.type not in ("separator", "label")

    def to_dict(self):
        return {
            "node_id": self.id, "parent_id": self.parent, "path": self.path,
            "order": self.order, "type": self.type, "label": self.label,
            "shortcut": self.shortcut,
            "visibility_cond": self.vis, "enabled_cond": self.en, "checked_cond": self.ck,
            "command": self.command, "contract_ref": self.contract,
            "screens": self.screens, "default_item": self.default_item,
            "line": self.line,
            "depth": getattr(self, "depth", 0), "is_leaf": self.is_leaf,
        }


def load(project):
    path = os.path.join(project, MENUS_REL)
    if not os.path.isfile(path):
        raise rc.ToolError(
            "缺 %s" % MENUS_REL,
            "先跑 S2 把菜单拆出来；还没有截图编号时先用 --from-screens 生成待填骨架")
    expected = rc.load_schema(project).columns["menus"]
    table, issues = rc.read_csv_table(path, expected)
    errors = [i for i in issues if i["level"] == "ERROR"]
    fatal_codes = {"CSV-MISSING-COLUMN", "CSV-COLUMN-ORDER", "CSV-DUP-COLUMN",
                   "CSV-ROW-WIDTH"}
    fatal = [i for i in errors
             if i["code"] in fatal_codes and _critical_column_missing(i, expected)]
    fatal += [i for i in errors if i["code"] in ("CSV-DUP-COLUMN", "CSV-ROW-WIDTH")]
    if fatal:
        raise rc.ToolError(
            "%s 表头有问题：%s" % (MENUS_REL, "；".join(i["message"] for i in fatal)),
            "列名与顺序照 templates/blueprint/SCHEMAS.md §4；"
            "快速修：python3 tools/menu_walk.py --from-screens 生成新骨架对照")
    # 非核心列缺失（如 default_item）不阻断分析：仍能出树、出卡片、报缺项，
    # 只是多一条 WARN。schema 漂移时工具必须还能救命，而不是一起罢工。
    nodes = [Node(r) for r in table]
    return nodes, issues


# 没有这些列就没法谈结构，必须硬退；其余列缺失按 WARN 降级处理
CRITICAL_MENU_COLUMNS = {"node_id", "parent_id", "type", "label"}


def _critical_column_missing(issue, expected):
    if issue.get("code") != "CSV-MISSING-COLUMN":
        return True
    msg = issue.get("message", "")
    return any(c in msg for c in CRITICAL_MENU_COLUMNS)


def build_tree(nodes):
    """返回 (roots, problems)。problems: [{code,message,where,fix}]"""
    problems = []
    by_id = {}
    for n in nodes:
        if not n.id:
            problems.append({"code": "NODE-NO-ID", "where": "menus.csv:%s" % n.line,
                             "message": "有一行 node_id 为空", "fix": "补 M-xxx ID"})
            continue
        if n.id in by_id:
            problems.append({"code": "NODE-DUP-ID", "where": "menus.csv:%s" % n.line,
                             "message": "node_id '%s' 重复" % n.id,
                             "fix": "ID 永不复用；删掉重复行或改 ID"})
            continue
        by_id[n.id] = n

    for n in nodes:
        if not n.id or n.id not in by_id:
            continue
        if n.parent == "ROOT":
            continue
        if n.parent not in by_id:
            problems.append({"code": "NODE-PARENT-MISSING", "where": "menus.csv:%s" % n.line,
                             "message": "%s 的 parent_id='%s' 不存在，已按顶层处理"
                                        % (n.id, n.parent),
                             "fix": "补父节点行，或把 parent_id 改成 ROOT"})
            continue
        by_id[n.parent].children.append(n)

    roots = [n for n in nodes if n.id in by_id and (n.parent == "ROOT" or n.parent not in by_id)]

    # 环检测 + 深度
    seen = set()

    def walk(n, depth, stack):
        n.depth = depth
        if n.id in stack:
            problems.append({"code": "NODE-CYCLE", "where": "menus.csv:%s" % n.line,
                             "message": "菜单树成环：%s" % " → ".join(stack + [n.id]),
                             "fix": "菜单是树不是图；改掉其中一条 parent_id"})
            n.children = []
            return
        seen.add(n.id)
        for c in sorted(n.children, key=lambda x: x.order_key):
            walk(c, depth + 1, stack + [n.id])

    for r in sorted(roots, key=lambda x: x.order_key):
        walk(r, 0, [])

    orphans = [n for n in nodes if n.id in by_id and n.id not in seen]
    for n in orphans:
        problems.append({"code": "NODE-ORPHAN", "where": "menus.csv:%s" % n.line,
                         "message": "%s 没被任何树根连到（成环或父节点被孤立）" % n.id,
                         "fix": "从 ROOT 出发应该能走到每一个节点"})

    # 同级 order 冲突
    def check_order(items):
        seen_order = {}
        for n in items:
            if not n.order:
                continue
            if n.order in seen_order:
                problems.append({
                    "code": "ORDER-DUP", "where": "menus.csv:%s" % n.line,
                    "message": "%s 与 %s 同级 order 都是 %s" % (n.id, seen_order[n.order], n.order),
                    "fix": "同级顺序唯一，否则渲染顺序不确定"})
            else:
                seen_order[n.order] = n.id
        for n in items:
            check_order(sorted(n.children, key=lambda x: x.order_key))

    check_order(sorted(roots, key=lambda x: x.order_key))
    return roots, problems


def walk_nodes(roots):
    out = []

    def rec(n):
        out.append(n)
        for c in sorted(n.children, key=lambda x: x.order_key):
            rec(c)

    for r in roots:
        rec(r)
    return out


def render_tree(roots):
    lines = []
    for n in sorted(roots, key=lambda x: x.order_key):
        lines.extend(_tree_line(n))
    return "\n".join(lines)


def _tree_line(n):
    indent = "    " * getattr(n, "depth", 0)
    mark = TYPE_MARK.get(n.type, "?")
    bits = ["%s%s %s" % (indent, mark, n.label or "(无标签)")]
    bits.append("  [%s]" % n.id)
    if n.order:
        bits.append("(order %s)" % n.order)
    if n.shortcut and n.shortcut != "-":
        bits.append("快捷键 %s" % n.shortcut)
    if n.default_item and not rc.is_not_applicable(n.default_item):
        bits.append("默认→%s" % n.default_item)
    missing = []
    if n.needs_behaviour:
        if not rc.is_filled(n.command):
            missing.append("command")
        if not rc.is_filled(n.contract):
            missing.append("契约")
    for col, label, _ in CARD_FIELDS:
        if rc.is_blank(rc.cell(n.row, col)):
            missing.append(label)
    if missing:
        bits.append("⚠ 缺 %s" % "、".join(missing))
    out = [" ".join(bits)]
    for c in sorted(n.children, key=lambda x: x.order_key):
        out.extend(_tree_line(c))
    return out


def gaps_of(nodes):
    """返回缺项清单：每行 {level, node_id, path, missing[], line}"""
    out = []
    for n in nodes:
        missing = []
        if n.needs_behaviour:
            if not rc.is_filled(n.command):
                missing.append("command")
            if not rc.is_filled(n.contract):
                missing.append("contract_ref")
        for col, label, _ in CARD_FIELDS:
            if rc.is_blank(rc.cell(n.row, col)):
                missing.append(label)
        if n.type in ("radio", "checkbox"):
            if rc.is_blank(rc.cell(n.row, "checked_cond")):
                if "选中条件" not in missing:
                    missing.append("选中条件")
        if missing:
            out.append({"node_id": n.id, "path": n.path or n.label, "type": n.type,
                        "line": n.line, "missing": missing})
    return out


def contract_exists(project, ref):
    if not rc.is_filled(ref):
        return False
    base = os.path.basename(ref)
    return os.path.isfile(os.path.join(project, CONTRACTS_REL, base))


def print_card(n, project, out):
    w = out.write
    bar = "─" * 68
    w("%s\n" % bar)
    w("菜单叶子卡  %s  %s\n" % (n.label or "(无标签)", n.id))
    w("  路径        %s\n" % (n.path or "(未填 path)"))
    w("  类型        %s（%s）    同级 order：%s\n"
      % (n.type or "?", TYPE_NAME.get(n.type, "未识别"), n.order or "-"))
    if n.shortcut and n.shortcut != "-":
        w("  快捷键      %s\n" % n.shortcut)
    w("  出现在屏幕  %s\n" % (n.screens or "（未填）"))
    w("  ── 三条件（必须分开写，不许写“看情况”）──\n")
    for col, label, why in CARD_FIELDS:
        v = rc.cell(n.row, col)
        if rc.is_blank(v):
            w("  ✗ %s    —— 缺。要写：%s\n" % (label, why))
        else:
            w("  ✓ %s    %s\n" % (label, v))
    # default_item（SCHEMAS §4 第 14 列）：契约 §3 要求写清"默认项与当前项"，所以每张卡都列
    if n.default_item and not rc.is_not_applicable(n.default_item):
        w("  ✓ 默认项      %s（打开时高亮这一项；与「选中条件」不同：那是当前值是否匹配）\n"
          % n.default_item)
    else:
        w("  · 默认项      -（打开菜单时默认高亮哪一项？无默认保持 '-'；子菜单里有 radio "
          "时建议填）\n")
    w("  ── 触发 ──\n")
    if rc.is_filled(n.command):
        w("  ✓ 命令      %s\n" % n.command)
    else:
        w("  ✗ 命令      缺 command：这个选项点了之后发生什么，没有任何定义\n")
    if rc.is_filled(n.contract):
        exists = contract_exists(project, n.contract)
        w("  %s 契约      %s%s\n" % ("✓" if exists else "✗", n.contract,
                                    "" if exists else "   ← 文件不存在"))
    else:
        w("  ✗ 契约      缺 contract_ref：行为没有契约，等于没想清楚\n")
    if n.notes:
        w("  备注        %s\n" % n.notes)


def cmd_from_screens(project, screens_dir, out_path, out):
    """按截图数量生成「分层编号」指引 + 待填骨架（不猜原版行为，只搭结构）。"""
    sdir = screens_dir if os.path.isabs(screens_dir) else os.path.join(project, screens_dir)
    w = out.write
    w("菜单分层截图法 · 生成待填骨架\n")
    w("=" * 60 + "\n")
    if not os.path.isdir(sdir):
        w("找不到截图目录：%s\n" % sdir)
        w("先建目录并把原版截图放进去（文件名建议 01-主界面.png、02-日期菜单.png…）。\n")
        files = []
    else:
        files = sorted(f for f in os.listdir(sdir) if f.lower().endswith(IMAGE_EXT))
        w("截图目录：%s  发现 %d 张图\n\n" % (sdir, len(files)))

    w("操作顺序（照做，别跳步）：\n")
    steps = [
        "① 先截「合起来的第一层」：主界面 + 每个顶层菜单打开的样子，编号 01、02…",
        "② 再逐层往下：在某一个选项上悬停/点击，截出它展开的子层，编号接着排",
        "③ 每张图只拍一层，不要一张图里塞三层——否则后面写三条件会错位",
        "④ 每个菜单节点记录：完整路径、界面原文、同级顺序、类型（子菜单/动作/单选/多选/分隔符）",
        "⑤ 三条件分开写：显示（什么时候出现）、可用（什么时候能点）、选中（什么时候打勾）",
        "⑥ 同一条路上按键盘走一遍（↑↓←→ Esc Enter），把跨层与关闭行为记进 notes",
        "⑦ 截完回到这里跑：python3 tools/menu_walk.py --gaps  看还缺什么",
    ]
    for s in steps:
        w("  %s\n" % s)
    w("\n")

    rows = []
    for i, f in enumerate(files, start=1):
        rows.append({
            "node_id": "M-L%02d-01" % i,
            "parent_id": "ROOT",
            "path": "待填 › 待填",
            "order": "1",
            "type": "submenu",
            "label": "待填（截图 %s 里的选项原文）" % f,
            "shortcut": "-",
            "visibility_cond": "待填：什么上下文/数据状态下出现",
            "enabled_cond": "待填：什么时候可点；禁用时给什么提示",
            "checked_cond": "待填：选中态由哪个持久值/草稿值决定",
            "command": "待填",
            "contract_ref": "待填",
            "screens": "S-01",
            "notes": "来自截图 %s（第 %d 层，请确认层数后改 node_id）" % (f, i),
        })

    if not rows:
        rows.append({
            "node_id": "M-XXX-01", "parent_id": "ROOT", "path": "待填 › 待填",
            "order": "1", "type": "action", "label": "待填", "shortcut": "-",
            "visibility_cond": "待填", "enabled_cond": "待填", "checked_cond": "待填",
            "command": "待填", "contract_ref": "待填", "screens": "S-01",
            "notes": "无截图时的手填起点；每行一个菜单节点",
        })

    cols = rc.load_schema(project).columns["menus"]
    target = out_path if out_path else os.path.join("BLUEPRINT", "menus.skeleton.csv")
    full = target if os.path.isabs(target) else os.path.join(project, target)
    os.makedirs(os.path.dirname(full) or ".", exist_ok=True)
    with open(full, "w", newline="", encoding="utf-8") as fh:
        import csv as _csv
        writer = _csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        writer.writeheader()
        for r in rows:
            writer.writerow(r)
    w("已生成待填骨架：%s（%d 行）\n" % (full, len(rows)))
    w("注意：骨架里全是「待填」，它是脚手架不是蓝图。填完请另存为 %s，"
      "再跑 blueprint_lint.py 确认没有禁用词。\n" % MENUS_REL)
    return {"skeleton": full, "rows": len(rows), "screens_found": len(files)}


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="menu_walk.py",
        description="菜单树穷举器：树 / 三条件卡 / 缺项表 / 门禁检查 / 分层截图骨架",
        epilog="示例：python3 tools/menu_walk.py --project . --check",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", default=".", help="项目根目录（默认当前目录）")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--tree", action="store_true", help="打印缩进菜单树")
    mode.add_argument("--cards", action="store_true", help="打印每个叶子的三条件卡")
    mode.add_argument("--gaps", action="store_true", help="只打印缺项表")
    mode.add_argument("--check", action="store_true", help="门禁模式：有问题退出码 1")
    mode.add_argument("--from-screens", action="store_true",
                      help="按截图生成待填骨架（不联网、不猜行为）")
    ap.add_argument("--screens", default="screens", help="--from-screens 的截图目录（相对项目根）")
    ap.add_argument("--out", default="", help="--from-screens 的输出路径（默认 BLUEPRINT/menus.skeleton.csv）")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    ap.add_argument("--max-items", type=int, default=0, help="最多打印多少条（0=全部）")
    args = ap.parse_args(argv)

    if not os.path.isdir(args.project):
        return rc.die(rc.ToolError("项目目录不存在：%s" % args.project,
                                   "确认路径；新项目先跑 scripts/new-project.sh <目录>"))

    if args.from_screens:
        try:
            info = cmd_from_screens(args.project, args.screens, args.out, sys.stdout)
        except rc.ToolError as exc:
            return rc.die(exc)
        if args.json:
            rc.print_json(dict(info, tool=TOOL, mode="from-screens"))
        return 0

    try:
        nodes, csv_issues = load(args.project)
    except rc.ToolError as exc:
        return rc.die(exc)

    roots, problems = build_tree(nodes)
    ordered = walk_nodes(roots)
    gaps = gaps_of(ordered)
    leaves = [n for n in ordered if n.is_leaf and n.needs_behaviour]

    result = {
        "tool": TOOL,
        "project": os.path.abspath(args.project),
        "checked_at": rc.now_iso(),
        "nodes": len(nodes),
        "roots": len(roots),
        "leaves": len(leaves),
        "gap_count": len(gaps),
        "problem_count": len(problems),
        "csv_error_count": len([i for i in csv_issues if i["level"] == "ERROR"]),
        "clean": not gaps and not problems
                 and not any(i["level"] == "ERROR" for i in csv_issues),
        "problems": problems,
        "gaps": gaps,
        "csv_issues": csv_issues,
        "__RESULT__": "menu gaps=%d problems=%d nodes=%d" % (len(gaps), len(problems), len(nodes)),
    }

    if args.json:
        rc.print_json(result)
        if args.check:
            return 0 if result["clean"] else 1
        return 0

    out = sys.stdout
    w = out.write
    limit = args.max_items

    if args.tree or not (args.cards or args.gaps or args.check):
        w("菜单树（%d 个节点，%d 个树根）· 图例 ▸子菜单 ●动作 ◉单选 ☑多选 ──分隔符 ¶文字\n"
          % (len(nodes), len(roots)))
        w(render_tree(roots) if roots else "（空：menus.csv 没有 parent_id=ROOT 的节点）")
        w("\n")
        if problems:
            w("结构问题 %d 条：\n" % len(problems))
            for p in problems[:limit or None]:
                w("  ✗ [%s] %s — %s\n      → %s\n"
                  % (p["code"], p["where"], p["message"], p["fix"]))
            w("\n")
        if not (args.cards or args.gaps or args.check):
            w("叶子 %d 个，缺项 %d 条。看细节：--cards（三条件卡）/ --gaps（缺项表）\n"
              % (len(leaves), len(gaps)))

    if args.cards:
        w("三条件卡（每个叶子一张）· 共 %d 个叶子\n" % len(leaves))
        for n in leaves[:limit or None]:
            print_card(n, args.project, out)
        if not leaves:
            w("（没有叶子：可能 menus.csv 只有子菜单层，或者还需要往下拆一层）\n")
        w("\n")

    if args.gaps:
        w("缺项表（%d 条）\n" % len(gaps))
        if gaps:
            rows = [[g["node_id"], g["path"][:34], g["type"], "、".join(g["missing"]),
                     "menus.csv:%s" % g["line"]] for g in gaps[:limit or None]]
            w(rc.render_table(["节点", "路径/标签", "类型", "缺什么", "位置"], rows))
        else:
            w("（没有缺项：每个叶子都有命令、契约与三条件。这份菜单可以进产品官审查了）")
        w("\n")

    csv_errors = [i for i in csv_issues if i["level"] == "ERROR"]
    if csv_errors and (args.tree or args.check):
        w("⚠ menus.csv 与 SCHEMAS 不一致（不影响本次结构分析，但 blueprint_lint 会判 ERROR）：\n")
        for i in csv_errors:
            w("   [%s] %s — %s\n" % (i["code"], i["where"], i["message"]))
        w("   修法：%s\n\n" % (csv_errors[0].get("hint") or "按 SCHEMAS §4 补齐列"))

    if args.check:
        errs = len(gaps) + len(problems) + len(csv_errors)
        if errs:
            w("门禁结论：❌ 菜单层不可放行（缺项 %d + 结构问题 %d + 表头问题 %d）。"
              "G2 会 FAIL。\n" % (len(gaps), len(problems), len(csv_errors)))
            if csv_errors:
                w("     先修表头（缺列/列序），否则门禁读不到这些列。\n")
            w("修法：--gaps 看清单 → 补 command/contract/三条件 → 重跑 --check\n")
            return 1
        w("门禁结论：✅ 菜单层通过（%d 节点 / %d 叶子，三条件与命令齐全）。\n"
          % (len(nodes), len(leaves)))
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
