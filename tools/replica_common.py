#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""replica_common.py —— 工具层共享底座（Python 3 标准库，无第三方依赖）

本模块不是命令行工具，只被 tools/*.py 引用。它提供三件东西：

1. **契约常量的唯一来源**：CSV 列名与契约 16 节标题都从
   `templates/blueprint/SCHEMAS.md` **现场解析**；解析失败才退回内置常量。
   这样 SCHEMAS 一改，所有工具跟着改，不会出现"文档改了脚本没改"。
2. **统一的载入与报错方式**：缺文件不抛栈，抛 `ToolError`，由工具层打印
   "缺什么 + 先做什么 + 命令"，退出码 2。
3. **统一输出**：人类可读表 / `--json`（UTF-8 原样中文）。

约定（所有工具一致）：
    退出码 0 = 干净/通过
    退出码 1 = 已完成检查，但发现问题（可修的具体项）
    退出码 2 = 用法或输入错误（缺文件、缺列、参数不合法），未做检查
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import sys
from datetime import datetime, timezone


# --------------------------------------------------------------------------
# 0. 通用：错误、IO、输出
# --------------------------------------------------------------------------

class ToolError(Exception):
    """可直接展示给使用者的错误。message = 出了什么事，hint = 下一步怎么做。"""

    def __init__(self, message, hint=None, code=2):
        super().__init__(message)
        self.message = message
        self.hint = hint
        self.code = code


def die(err):
    """打印可操作错误并返回退出码（不打印栈）。"""
    print("【错误】%s" % err.message, file=sys.stderr)
    if err.hint:
        print("【下一步】%s" % err.hint, file=sys.stderr)
    return err.code


def read_text(path):
    try:
        with open(path, encoding="utf-8-sig") as fh:
            return fh.read()
    except FileNotFoundError:
        raise ToolError("找不到文件：%s" % path,
                        "确认路径；新建项目请先跑 scripts/new-project.sh 生成骨架")
    except UnicodeDecodeError as exc:
        raise ToolError("文件不是 UTF-8 编码：%s" % path,
                        "转码后再跑，例：iconv -f GBK -t UTF-8 '%s'" % path) from exc


def read_json(path):
    text = read_text(path)
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ToolError("JSON 解析失败：%s (%s)" % (path, exc),
                        "检查第 %d 行附近，或重新生成该文件" % exc.lineno)


def print_json(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def now_iso():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def sha256_of(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            block = fh.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def human_size(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return ("%d%s" % (n, unit)) if unit == "B" else ("%.1f%s" % (n, unit))
        n /= 1024.0


def render_table(headers, rows, empty="（空）"):
    """极简等宽表格。中文按 2 个字符宽度计算，保证不歪。"""
    def width(s):
        return sum(2 if ord(ch) > 0x2E80 else 1 for ch in s)

    rows = [["" if c is None else str(c) for c in r] for r in rows]
    if not rows:
        return empty
    widths = [width(h) for h in headers]
    for r in rows:
        for i, c in enumerate(r):
            if i < len(widths):
                widths[i] = max(widths[i], width(c))
    def pad(s, w):
        return s + " " * (w - width(s))
    out = [("  ".join(pad(h, widths[i]) for i, h in enumerate(headers))).rstrip(),
           "  ".join("-" * widths[i] for i in range(len(headers)))]
    for r in rows:
        out.append("  ".join(pad(c, widths[i]) for i, c in enumerate(r) if i < len(headers)).rstrip())
    return "\n".join(out)


# --------------------------------------------------------------------------
# 1. 契约常量：SCHEMAS.md 解析 + 内置兜底
# --------------------------------------------------------------------------

# 内置兜底（2026-10-23 与 templates/blueprint/SCHEMAS.md v1.0 逐字对齐）
BUILTIN_COLUMNS = {
    "features": ["feature_id", "feature", "area", "priority", "scope", "original",
                 "progress", "contract_ref", "acceptance_ref", "evidence", "notes"],
    "screens": ["screen_id", "name", "entry", "exits", "purpose", "key_components",
                "state_filled", "state_empty", "state_loading", "state_error",
                "state_permission", "focus_restore", "flows", "notes"],
    "menus": ["node_id", "parent_id", "path", "order", "type", "label", "shortcut",
              "visibility_cond", "enabled_cond", "checked_cond", "command",
              "contract_ref", "screens", "default_item", "notes"],
    "linkage": ["link_id", "source_id", "event", "affected_screen", "affected_control",
                "data", "refresh_timing", "state_handling", "test_ref", "status"],
    "unknowns": ["unknown_id", "area", "description", "impact", "evidence_gap",
                 "verification_action", "owner", "blocking", "status"],
}

# 契约 16 节（序号 + 标题）与"每节最小内容"，兜底用
BUILTIN_SECTIONS = [
    ("1 目标与入口", "用户意图、全部入口（含快捷键与替代路径）、前置上下文"),
    ("2 界面与层级", "控件顺序与层级、浮层/子菜单关系、可滚动区、尺寸策略"),
    ("3 每个菜单选项", "每个菜单叶子：完整路径、顺序、类型、默认项与当前项、打开关闭行为、鼠标跨层与键盘行为"),
    ("4 显示条件", "出现条件、隐藏后的布局与焦点处理"),
    ("5 可用与选择条件", "可用 ≠ 已选中：可用条件、禁用解释、互斥与组合、最大选择数、取消选择"),
    ("6 筛选条件", "AND/OR 与嵌套优先级、包含/排除、空值、边界日期与时区、排序、分组、分页、角标统计口径"),
    ("7 业务实现逻辑", "规则求值顺序、默认规则、参数、校验、算法边界（不许只写“调用某服务”）"),
    ("8 具体效果", "每步操作后的文案、数值、位置、列表成员、计数、反馈；能被具体输入复算"),
    ("9 状态变化", "原状态 → 事件 → 条件 → 目标状态 → 副作用；含加载/保存中/失败/冲突/重试/取消/撤销"),
    ("10 数据读取", "实体与字段来源、查询条件、派生值、数据新鲜度、空库与异常库行为"),
    ("11 数据写入", "命令与参数、精确字段、事务范围、约束、写入时点、完成信号、失败保留、必须不变的字段"),
    # %FACES% 由 faces_brief() 在运行时替换（六面名单只有 shared/faces.json 一份权威）
    ("12 跨页面联动", "%FACES% 各自影响；刷新或失效机制、时序与一致性"),
    ("13 并发与生命周期", "快速连点、重复提交、A→B 切换、迟到结果、防抖、关窗、退出、重启、睡眠唤醒"),
    ("14 撤销与恢复", "恢复哪些值、窗口期、连续编辑处理、保存失败重试、误操作保护"),
    ("15 体验标准", "输入法组合、焦点返回、Esc/Enter、可访问性、布局稳定、滚动动效、性能起止点"),
    ("16 测试与证据", "正常/负向/边缘/跨页面/立即退出重启 用例号与断言值；截图不能代替落库证明"),
]

# 禁用词 / 占位词（00 §附录A.7、SCHEMAS §0.4、G2 判定）
# 「待填」不在这里：它由 looks_placeholder() 单独判成"某节是占位"，
# 这样一条占位只报一次错，不会被禁用词再淹一遍。
BANNED_WORDS = ["按原版", "TBD", "待定", "视情况", "同前", "TODO", "FIXME"]

# 占位词：契约里由"节是否只有占位"单独判定（避免同一处报两遍错）；
# 非契约文件（CSV/MD）里出现则直接算禁用词。
PLACEHOLDER_WORDS = ["待填", "待补", "请填"]

# 契约 16 节的"反例"（scaffold 注释用；lint 不检查）
SECTION_ANTI_EXAMPLES = {
    "1 目标与入口": "✗「用户点日期按钮改日期」——漏了快捷键、右键菜单、拖拽这三种真实入口",
    "2 界面与层级": "✗「一个弹层选择日期」——没写控件顺序、层级、可滚动区与尺寸策略",
    "3 每个菜单选项": "✗「日期菜单有今天/明天/自定义」——漏了顺序、默认项、分隔符与键盘跨层行为",
    "4 显示条件": "✗「按原版显示」——等于没写；必须写成可判定的表达式或明确的数据状态",
    "5 可用与选择条件": "✗「可点，选中时高亮」——可用与选中混成一句，做出来该灰的不灰",
    "6 筛选条件": "✗「按时间过滤」——没写时区、边界日期、空值与角标统计口径",
    "7 业务实现逻辑": "✗「调用日期服务」——必须写规则求值顺序、参数与算法边界",
    "8 具体效果": "✗「界面刷新」——要写：主列表行日期徽标同步更新，角标计数重算为 3",
    "9 状态变化": "✗「保存后状态更新」——没写失败、冲突、重试、取消各自去哪",
    "10 数据读取": "✗「从数据库读」——要写实体.字段、查询条件、派生值与空库行为",
    "11 数据写入": "✗「写入任务表」——要写命令参数、字段、事务范围、完成信号与必须不变的字段",
    "12 跨页面联动": "✗「相关页面刷新」——六面逐面写，每面给刷新时点与 LK 编号",
    "13 并发与生命周期": "✗「正常使用没问题」——快速连点、A→B 切换、关窗、睡眠唤醒逐条写",
    "14 撤销与恢复": "✗「支持撤销」——要写恢复哪些值、窗口期、连续编辑如何处理",
    "15 体验标准": "✗「体验流畅」——R11：不能写成数值或步骤的体验要求 = 无效要求",
    "16 测试与证据": "✗「测试通过」——要写用例号 + 断言的具体值；截图不能代替落库证明",
}


class Schema:
    """SCHEMAS.md 解析结果。source 标明是"现场解析"还是"内置兜底"，便于自检。"""

    def __init__(self, columns, sections, source, warnings=None):
        self.columns = columns
        self.sections = sections          # [{"no": int, "title": str, "desc": str}]
        self.source = source
        self.warnings = warnings or []

    @property
    def section_titles(self):
        return [s["title"] for s in self.sections]


def _section_bodies(text):
    """把 markdown 按 '## N' 切段，返回 {编号: [行]} 与顺序列表。

    必须跳过代码围栏内的内容——SCHEMAS 的 §1/§8 里用围栏列出了 "## 1 目标与入口"
    这类示例标题，若当成真标题会把整段切碎（真实踩过）。
    """
    lines = text.splitlines()
    heads = []
    in_fence = False
    for i, line in enumerate(lines):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = re.match(r"^##\s+(\d+)\.?\s", line)
        if m:
            heads.append((int(m.group(1)), i))
    bodies = {}
    for idx, (num, start) in enumerate(heads):
        end = heads[idx + 1][1] if idx + 1 < len(heads) else len(lines)
        bodies[num] = lines[start + 1:end]
    return bodies, [n for n, _ in heads]


def _cols_from_body(body):
    cols = []
    in_fence = False
    for line in body:
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = re.match(r"^\|\s*`([A-Za-z][A-Za-z0-9_]*)`\s*\|", line)
        if m:
            cols.append(m.group(1))
    return cols


def _sections_from_body(body):
    found = []
    in_fence = False
    for line in body:
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            m = re.match(r"^##\s+(\d+)\s+(\S.*?)\s*$", line)
            if m:
                found.append((int(m.group(1)), ("%s %s" % (m.group(1), m.group(2))).strip()))
    descs = {}
    for line in body:
        m = re.match(r"^\|\s*(\d+)\s*\|\s*([^|]+?)\s*\|", line)
        if m:
            descs[int(m.group(1))] = m.group(2).strip()
    sections = []
    for no, title in found:
        sections.append({"no": no, "title": title, "desc": descs.get(no, "")})
    return sections


def parse_schemas(path):
    """解析 SCHEMAS.md。解析不出合法数量时抛 ValueError，由 load_schema 兜底。"""
    text = read_text(path)
    bodies, _order = _section_bodies(text)
    mapping = {2: "features", 3: "screens", 4: "menus", 5: "linkage", 6: "unknowns"}
    expect = {"features": 11, "screens": 14, "menus": 15, "linkage": 10, "unknowns": 9}
    columns = {}
    for num, name in mapping.items():
        cols = _cols_from_body(bodies.get(num, []))
        if len(cols) < 3:
            raise ValueError("SCHEMAS §%d 解析不到列名（拿到 %d 个）" % (num, len(cols)))
        if len(cols) != expect[name]:
            # 数量不符不致命，但必须提示：可能是 SCHEMAS 改了，也可能是解析漏了
            pass
        columns[name] = cols
    sections = _sections_from_body(bodies.get(8, []))
    if len(sections) != 16:
        raise ValueError("SCHEMAS §8 解析到 %d 节，应为 16 节" % len(sections))
    return columns, sections


def _candidate_schemas_paths(project):
    here = os.path.dirname(os.path.abspath(__file__))
    env = os.environ.get("REPLICA_SCHEMAS")
    cands = []
    if env:
        cands.append(env)
    if project:
        cands.append(os.path.join(project, "templates", "blueprint", "SCHEMAS.md"))
    # tools/ 的上一级就是体系根
    cands.append(os.path.join(os.path.dirname(here), "templates", "blueprint", "SCHEMAS.md"))
    cands.append(os.path.join(os.getcwd(), "templates", "blueprint", "SCHEMAS.md"))
    return cands


def load_schema(project="."):
    """优先现场解析 SCHEMAS.md；找不到或解析失败则用内置常量并记录 warning。"""
    warnings = []
    tried = []
    for path in _candidate_schemas_paths(project):
        if not path or not os.path.isfile(path):
            continue
        real = os.path.abspath(path)
        if real in tried:          # 同一文件不重复解析（候选路径常指向同一个）
            continue
        tried.append(real)
        try:
            columns, sections = parse_schemas(real)
        except (ToolError, ValueError) as exc:
            warnings.append("SCHEMAS 解析失败（%s）：%s；已退回内置常量" % (real, exc))
            continue
        for name, cols in columns.items():
            if len(cols) != len(BUILTIN_COLUMNS[name]):
                warnings.append("SCHEMAS 里 %s 的列数是 %d，内置常量是 %d；请确认 SCHEMAS 是否刚改过"
                                % (name, len(cols), len(BUILTIN_COLUMNS[name])))
        _fill_faces(columns, sections)
        return Schema(columns, sections, real, warnings)
    warnings.append("没找到可解析的 templates/blueprint/SCHEMAS.md，已使用内置常量"
                    "（列名与 16 节可能与你的版本不同）")
    sections = [{"no": i + 1, "title": t, "desc": d} for i, (t, d) in enumerate(BUILTIN_SECTIONS)]
    builtin_cols = {k: list(v) for k, v in BUILTIN_COLUMNS.items()}
    _fill_faces(builtin_cols, sections)
    return Schema(builtin_cols, sections, None, warnings)


def _fill_faces(columns, sections):
    """把 16 节描述里的 %FACES% 换成 shared/faces.json 的当前六面名。就地修改。"""
    brief = faces_brief()
    for sec in sections:
        if "%FACES%" in (sec.get("desc") or ""):
            sec["desc"] = sec["desc"].replace("%FACES%", brief)


# --------------------------------------------------------------------------
# 2. CSV 读取：列名/顺序校验 + 行号
# --------------------------------------------------------------------------

class CsvIssue(dict):
    """{level, code, where, message, hint} —— 与 lint 的 finding 同构。"""


def csv_issue(level, code, where, message, hint=""):
    return {"level": level, "code": code, "where": where, "message": message, "hint": hint}


def read_csv_table(path, expected_columns, strict_prefix=True):
    """读 CSV，返回 (rows, issues)。

    rows: [{"line": 行号, **列名: 值}]；值已 strip，保留原始空串（空串 ≠ "-"）。
    issues: 列缺失/顺序错/重名/行宽异常的清单（ERROR/WARN）。
    """
    issues = []
    rel = os.path.basename(path)
    try:
        with open(path, newline="", encoding="utf-8-sig") as fh:
            reader = csv.reader(fh)
            try:
                header = next(reader)
            except StopIteration:
                raise ToolError("%s 是空文件" % rel,
                                "至少要有表头；用 templates/blueprint/*.template.csv 复制一份再填")
            header = [(h or "").strip() for h in header]
            # 去掉尾随空列（Excel 另存容易产生）
            while header and header[-1] == "":
                header.pop()
            if not header:
                raise ToolError("%s 表头为空" % rel, "按 SCHEMAS 的列名重建表头")
            rows = []
            for i, raw in enumerate(reader, start=2):
                if not raw or all((c or "").strip() == "" for c in raw):
                    continue
                if len(raw) > len(header):
                    issues.append(csv_issue(
                        "ERROR", "CSV-ROW-WIDTH", "%s:%d" % (rel, i),
                        "第 %d 行有 %d 个字段，表头只有 %d 列" % (i, len(raw), len(header)),
                        "字段内含逗号时要用双引号包围；或删掉多余列"))
                    raw = raw[:len(header)]
                row = {"line": i}
                for j, name in enumerate(header):
                    row[name] = (raw[j] if j < len(raw) else "").strip()
                rows.append(row)
    except FileNotFoundError:
        raise ToolError("缺 %s" % rel,
                        "先跑上一阶段生成它（例：缺 features.csv → 先跑 S1 取证 /replica-recon）")

    # 列名与顺序校验
    if not header:
        return rows, issues
    missing = [c for c in expected_columns if c not in header]
    extra = [c for c in header if c not in expected_columns]
    if missing:
        issues.append(csv_issue(
            "ERROR", "CSV-MISSING-COLUMN", rel,
            "缺列：%s" % "、".join(missing),
            "列名与顺序照 templates/blueprint/SCHEMAS.md，不许改名；新增列加在末尾"))
    if strict_prefix and not missing:
        want = [c for c in header if c in expected_columns]
        if want != [c for c in expected_columns if c in header]:
            issues.append(csv_issue(
                "ERROR", "CSV-COLUMN-ORDER", rel,
                "列顺序与 SCHEMAS 不一致：实际 %s" % "、".join(want),
                "按 SCHEMAS 的顺序重排列；顺序固定是为了脚本按列名读取不歧义"))
    if extra:
        issues.append(csv_issue(
            "WARN", "CSV-EXTRA-COLUMN", rel,
            "多出非契约列：%s" % "、".join(extra),
            "新增列只允许加在末尾，并同步写进 SCHEMAS；否则门禁与工具读不到"))
    dup = sorted({c for c in header if header.count(c) > 1})
    if dup:
        issues.append(csv_issue("ERROR", "CSV-DUP-COLUMN", rel,
                                "重复列名：%s" % "、".join(dup), "删掉重复列"))
    return rows, issues


def cell(row, name, default=""):
    v = row.get(name, default)
    return (v or "").strip() if isinstance(v, str) else v


def is_blank(value):
    """空串 = 还没做（缺失）；'-' = 经确认不适用（SCHEMAS §0.4）。"""
    return (value or "").strip() == ""


def is_not_applicable(value):
    return (value or "").strip() in ("-", "—", "N/A", "n/a")


def is_filled(value):
    """既不是空，也不是 '-'。"""
    return not is_blank(value) and not is_not_applicable(value)


# --------------------------------------------------------------------------
# 3. Markdown 切节 + 禁用词扫描
# --------------------------------------------------------------------------

def split_md_sections(text, level=2):
    """按指定级别标题切分，返回 [{"title":..., "body":..., "line":...}]。"""
    marks = "#" * level
    lines = text.splitlines()
    out = []
    cur = None
    in_fence = False
    for i, line in enumerate(lines, start=1):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
        if not in_fence and re.match(r"^%s\s+\S" % re.escape(marks) + r"(?!#)", line):
            if cur:
                out.append(cur)
            cur = {"title": line[len(marks):].strip(),
                   "body": "", "line": i}
        elif cur is not None:
            cur["body"] += line + "\n"
    if cur:
        out.append(cur)
    return out


def body_text(body):
    """去掉 HTML 注释、引用块引导（> ）、代码围栏，返回真正的内容行。"""
    out = []
    in_comment = False
    in_fence = False
    for line in body.splitlines():
        s = line.strip()
        if s.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if in_comment:
            if "-->" in s:
                in_comment = False
            continue
        if s.startswith("<!--"):
            if "-->" not in s:
                in_comment = True
            continue
        if not s:
            continue
        if s.startswith(">"):
            # 引用块：说明/模板指引，不算正文
            continue
        out.append(s)
    return out


_PLACEHOLDER_RE = re.compile(r"^(?:[-*+]\s*)?(?:待填|待补|请填|xxx|XXX|\.\.\.|…)")


def looks_placeholder(lines):
    """判断一节正文是否只是占位：全部是空 / 「待填…」/ 单字符，或内容过短。

    骨架生成的每节第一行是「- 待填：<该写什么>」——那句是提示不是内容，
    所以按前缀识别，不算已填。
    """
    if not lines:
        return True
    real = [l for l in lines if not _PLACEHOLDER_RE.match(l)]
    if not real:
        return True
    joined = "".join(real)
    return len(joined) < 8


def scan_banned(text, skip_quotes=False, include_placeholder=False):
    """返回 [(词, 行号, 行文本)]。用于禁用词/占位词扫描。

    HTML 注释（<!-- ... -->，可跨行）始终跳过——那是模板指引，不是正文。
    skip_quotes=True 时再跳过以 '>' 开头的行（引用块=模板说明）。
    include_placeholder=True 时把「待填」这类占位词也算命中（非契约文件用）。
    """
    words = BANNED_WORDS + (PLACEHOLDER_WORDS if include_placeholder else [])
    hits = []
    in_comment = False
    for i, line in enumerate(text.splitlines(), start=1):
        s = line.strip()
        if in_comment:
            if "-->" in s:
                in_comment = False
            continue
        if s.startswith("<!--"):
            if "-->" not in s:
                in_comment = True
            continue
        if skip_quotes and s.startswith(">"):
            continue
        for word in words:
            if word in line:
                hits.append((word, i, s[:120]))
    return hits


# --------------------------------------------------------------------------
# 4. ID 与引用
# --------------------------------------------------------------------------

ID_PATTERNS = {
    "screen": re.compile(r"^S-\d{2,3}$"),
    "feature": re.compile(r"^F-[A-Z0-9]+(?:-[A-Z0-9]+)*$"),
    "menu": re.compile(r"^M-[A-Z0-9]+(?:-[A-Z0-9]+)*$"),
    "flow": re.compile(r"^FL-\d{2,3}$"),
    "link": re.compile(r"^LK-\d{3}$"),
    "unknown": re.compile(r"^U-\d{3}$"),
    "test": re.compile(r"^T-\d{3}$"),
    "contract": re.compile(r"^C-F-[A-Z0-9]+(?:-[A-Z0-9]+)*\.md$"),
}

SCREEN_REF_RE = re.compile(r"\bS-\d{2,3}\b")
FLOW_REF_RE = re.compile(r"\bFL-\d{2,3}\b")
MENU_REF_RE = re.compile(r"\bM-[A-Z0-9]+(?:-[A-Z0-9]+)*\b")
FEATURE_REF_RE = re.compile(r"\bF-[A-Z0-9]+(?:-[A-Z0-9]+)*\b")
LINK_REF_RE = re.compile(r"\bLK-\d{3}\b")
TEST_REF_RE = re.compile(r"\bT-\d{3}\b")
UNKNOWN_REF_RE = re.compile(r"\bU-\d{3}\b")


def split_refs(value, pattern):
    """把 'T-101;T-102' / 'S-01, S-02' 拆成合法 ID 列表。"""
    if is_blank(value) or is_not_applicable(value):
        return []
    return [m.group(0) for m in pattern.finditer(value)]


def pct(part, total):
    if not total:
        return 0.0
    return 100.0 * part / total


def fmt_pct(x):
    return "%.1f%%" % x


# --------------------------------------------------------------------------
# 4.5 六面（跨页面联动影响面）—— 单一事实来源是 <体系根>/shared/faces.json
# --------------------------------------------------------------------------
#
# 为什么放在这里：六面的**名称**会被多处引用（工具的提示文案、契约模板的填空题提示、
# 门禁的判定消息）。任何一处手写都会随关键词表漂移。这里只保留**读取**逻辑，
# 关键词本身一个字都不抄——全部来自 shared/faces.json。

_FACES_REL = os.path.join("shared", "faces.json")

# 读不到 JSON 时的兜底（**只有名称**，用于文案；不做归类，归类必须用 faces.json）
_FACE_NAMES_FALLBACK = ["主列表", "角标计数", "详情面板", "日历/时间", "搜索", "提醒/通知"]

_faces_cache = {}


def faces_path(project=None):
    """定位 shared/faces.json：项目根优先，其次本文件上一级（体系根）。"""
    here = os.path.dirname(os.path.abspath(__file__))
    cands = []
    if project:
        cands.append(os.path.join(project, _FACES_REL))
    cands.append(os.path.join(os.path.dirname(here), _FACES_REL))
    cands.append(os.path.join(os.getcwd(), _FACES_REL))
    for p in cands:
        if os.path.isfile(p):
            return os.path.abspath(p)
    return None


def load_faces(project=None):
    """读 shared/faces.json → [{"key","name","desc","keywords"}]。

    读不到就退回**只有名称**的兜底列表（keywords 为空），并在 stderr 提示一次。
    绝不在这里内联关键词：那是 SSOT 的职责。
    """
    path = faces_path(project)
    if path and path not in _faces_cache:
        try:
            data = read_json(path)
            if isinstance(data, dict):
                data = data.get("faces")
            if isinstance(data, list) and data and all("key" in f for f in data):
                _faces_cache[path] = [dict(f) for f in data]
            else:
                raise ValueError("结构不完整（需要 {\"faces\":[{key,name,keywords}]}）")
        except (ToolError, ValueError) as exc:
            sys.stderr.write("[warn] 读不到 %s（%s），六面名称用兜底列表；"
                             "归类功能将不可用\n" % (_FACES_REL, exc))
            _faces_cache[path] = [{"key": n, "name": n, "desc": "", "keywords": []}
                                  for n in _FACE_NAMES_FALLBACK]
    if path:
        return [dict(f) for f in _faces_cache[path]]
    return [{"key": n, "name": n, "desc": "", "keywords": []}
            for n in _FACE_NAMES_FALLBACK]


def face_names(project=None):
    """六面名称列表，顺序即 SSOT 中的顺序。"""
    return [f["name"] for f in load_faces(project)]


def faces_brief(project=None):
    """一行式六面名，用于提示文案。用顿号分隔（面名本身可能含斜杠，如「日历/时间」）。"""
    return "、".join(face_names(project))


# --------------------------------------------------------------------------
# 5. 入口：本模块不是工具，但被 tools/*.py 逐个 --help 扫到时要给解释
# --------------------------------------------------------------------------

HELP = """replica_common.py —— 工具层共享底座（不是命令行工具）

它是库里的一份模块，被下列工具 import，本身不做事：
  blueprint_lint.py · menu_walk.py · linkage_matrix.py
  parity_score.py · contract_scaffold.py · evidence_manifest.py

提供：
  1. 契约常量    Schema / load_schema()   —— 现场解析 templates/blueprint/SCHEMAS.md，
                  解析失败才退回 BUILTIN_COLUMNS / BUILTIN_SECTIONS
  2. CSV 读写    read_csv_table()          —— 列名/顺序/行宽校验，返回 (rows, issues)
  3. Markdown     split_md_sections()      —— 按标题级别切节（跳过代码围栏）
  4. 契约判定     body_text() · looks_placeholder() · scan_banned()
  5. ID 与引用    ID_PATTERNS · split_refs() · SCREEN_REF_RE 等
  6. 输出         render_table() · print_json() · human_size()
  7. 错误         ToolError(message, hint)  → die() 打印「错误 + 下一步」，退出码 2

要跑什么，请用具体工具，例：
  python3 tools/blueprint_lint.py --help
"""


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] in ("-h", "--help"):
        print(HELP)
        return 0
    print(HELP, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
