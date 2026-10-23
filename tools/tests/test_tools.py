#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tools/tests/test_tools.py —— 工具层自测（unittest，标准库，临时目录夹具）

跑法（在体系根目录，即 tools/ 的上一级）：
    python3 -m unittest discover -s tools/tests -v
    python3 tools/tests/test_tools.py            # 等价

覆盖 6 个工具：
  T-LINT-*   blueprint_lint（干净夹具通过 / 破夹具逐项报错 / 缺目录不崩）
  T-MENU-*   menu_walk（树 / 三条件卡 / 缺项 / --check 退出码 / --from-screens）
  T-LINK-*   linkage_matrix（六面归类 / 只有1面 / 未归类 / --strict）
  T-PAR-*    parity_score（双分 / fail-under 退出码 / 上游不可用走内置）
  T-SCAF-*   contract_scaffold（16 节标题逐字 / --all 批量 / --force）
  T-EMAN-*   evidence_manifest（新增 / 不覆盖 / 哈希变化 WARN / 消失标 MISSING）

每个夹具都写在临时目录里，不依赖本仓库任何真实项目。
"""

from __future__ import annotations

import csv
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ROOT = os.path.dirname(TOOLS)
sys.path.insert(0, TOOLS)

import replica_common as rc  # noqa: E402

FEATURE_COLS = rc.BUILTIN_COLUMNS["features"]
SCREEN_COLS = rc.BUILTIN_COLUMNS["screens"]
MENU_COLS = rc.BUILTIN_COLUMNS["menus"]
LINK_COLS = rc.BUILTIN_COLUMNS["linkage"]
UNKNOWN_COLS = rc.BUILTIN_COLUMNS["unknowns"]
SECTION_TITLES = [t for t, _ in rc.BUILTIN_SECTIONS]


# --------------------------------------------------------------------------
# 夹具构造
# --------------------------------------------------------------------------

def write_csv(path, cols, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in cols})


def write_text(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def slurp(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def read_csv_rows(path):
    with open(path, encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def contract_text(fid="C-F-DATE-EDIT", name="修改任务的日期与时间", bad_section=None,
                  empty_section=None, placeholder_section=None, drop_section=None):
    lines = ["# %s · %s" % (fid, name), ""]
    for i, title in enumerate(SECTION_TITLES, start=1):
        if drop_section == i:
            continue
        lines.append("## %s" % title)
        lines.append("")
        if empty_section == i:
            lines.append("")
            continue
        if placeholder_section == i:
            lines.append("- 待填")
            lines.append("")
            continue
        if bad_section == i:
            lines.append("- 界面刷新")
            lines.append("")
            continue
        lines.append("- 具体内容 %d：可判定、可复算、带证据。" % i)
        lines.append("")
    return "\n".join(lines)


def make_project(tmp, clean=True):
    """造一个最小但完整的项目。clean=False 时注入多种问题。"""
    p = tmp
    os.makedirs(os.path.join(p, "BLUEPRINT", "contracts"), exist_ok=True)
    os.makedirs(os.path.join(p, "evidence"), exist_ok=True)
    os.makedirs(os.path.join(p, "screens"), exist_ok=True)

    # recon.md 的 10 段
    recon = ["# recon · 示例应用 1.0", ""]
    for i, t in enumerate(["1 目标制品与身份", "2 信息架构（屏幕树）", "3 全部入口清单",
                           "4 核心用户流程", "5 模块与依赖关系", "6 数据模型概览",
                           "7 可见区域与不可见区域", "8 未知与待验项", "9 证据索引",
                           "10 规模判断与建议"], start=1):
        recon += ["## %s" % t, "", "- 内容 %d" % i, ""]
    write_text(os.path.join(p, "BLUEPRINT", "recon.md"), "\n".join(recon))

    features = [
        {"feature_id": "F-DATE-EDIT", "feature": "修改任务的日期与时间", "area": "S-02",
         "priority": "must", "scope": "in", "original": "yes", "progress": "yes",
         "contract_ref": "contracts/C-F-DATE-EDIT.md", "acceptance_ref": "T-101;T-102",
         "evidence": "S-02", "notes": "-"},
        {"feature_id": "F-REPEAT-SET", "feature": "设置重复规则", "area": "S-02",
         "priority": "must", "scope": "in", "original": "yes", "progress": "partial",
         "contract_ref": "contracts/C-F-REPEAT-SET.md", "acceptance_ref": "T-103",
         "evidence": "S-02", "notes": "-"},
        {"feature_id": "F-TAG-COLOR", "feature": "给标签设颜色", "area": "S-05",
         "priority": "could", "scope": "in", "original": "yes", "progress": "no",
         "contract_ref": "", "acceptance_ref": "", "evidence": "S-05", "notes": "-"},
        {"feature_id": "F-AI-SUGGEST", "feature": "AI 建议下一步", "area": "S-09",
         "priority": "should", "scope": "out", "original": "no", "progress": "skip",
         "contract_ref": "", "acceptance_ref": "", "evidence": "docs",
         "notes": "差异化功能，本版不做"},
    ]
    screens = [
        {"screen_id": "S-01", "name": "主列表", "entry": "启动", "exits": "关窗",
         "purpose": "看今天要做什么", "key_components": "列表",
         "state_filled": "yes", "state_empty": "yes", "state_loading": "yes",
         "state_error": "yes", "state_permission": "-", "focus_restore": "保留选中",
         "flows": "FL-01", "notes": "无权限态不适用（单用户）"},
        {"screen_id": "S-02", "name": "任务详情", "entry": "点任务行", "exits": "Esc",
         "purpose": "改任务", "key_components": "标题,日期",
         "state_filled": "yes", "state_empty": "yes", "state_loading": "yes",
         "state_error": "yes", "state_permission": "yes", "focus_restore": "回到列表",
         "flows": "FL-01", "notes": "-"},
    ]
    menus = [
        {"node_id": "M-DATE", "parent_id": "ROOT", "path": "日期", "order": "1",
         "type": "submenu", "label": "日期", "shortcut": "-",
         "visibility_cond": "任务详情打开", "enabled_cond": "非退出冲刷阶段",
         "checked_cond": "-", "command": "Cmd.OpenDateMenu",
         "contract_ref": "contracts/C-F-DATE-EDIT.md", "screens": "S-02",
         "default_item": "M-DATE-TODAY", "notes": "-"},
        {"node_id": "M-DATE-TODAY", "parent_id": "M-DATE", "path": "日期 › 今天",
         "order": "1", "type": "action", "label": "今天", "shortcut": "⌘T",
         "visibility_cond": "任务详情打开且未完成", "enabled_cond": "任务存在且可写",
         "checked_cond": "dueDate == 今天", "command": "Cmd.SetDateToday",
         "contract_ref": "contracts/C-F-DATE-EDIT.md", "screens": "S-02",
         "default_item": "-", "notes": "-"},
        {"node_id": "M-DATE-CLEAR", "parent_id": "M-DATE", "path": "日期 › 清除日期",
         "order": "9", "type": "action", "label": "清除日期", "shortcut": "-",
         "visibility_cond": "dueDate 非空", "enabled_cond": "任务可写",
         "checked_cond": "-", "command": "Cmd.ClearDate",
         "contract_ref": "contracts/C-F-DATE-EDIT.md", "screens": "S-02",
         "default_item": "-", "notes": "-"},
        {"node_id": "M-REPEAT", "parent_id": "ROOT", "path": "重复", "order": "2",
         "type": "submenu", "label": "重复", "shortcut": "-",
         "visibility_cond": "任务详情打开", "enabled_cond": "任务可写",
         "checked_cond": "-", "command": "Cmd.OpenRepeatMenu",
         "contract_ref": "contracts/C-F-REPEAT-SET.md", "screens": "S-02",
         "default_item": "M-REPEAT-WEEKLY", "notes": "-"},
        {"node_id": "M-REPEAT-WEEKLY", "parent_id": "M-REPEAT", "path": "重复 › 每周工作日",
         "order": "3", "type": "radio", "label": "每周工作日", "shortcut": "⌘⇧W",
         "visibility_cond": "重复已开启", "enabled_cond": "任务可写",
         "checked_cond": "repeat.rule == 'WEEKLY' && byday 覆盖周一至周五",
         "command": "Cmd.SetRepeatWeeklyWorkdays",
         "contract_ref": "contracts/C-F-REPEAT-SET.md", "screens": "S-02",
         "default_item": "-", "notes": "-"},
    ]
    linkage = [
        {"link_id": "LK-001", "source_id": "F-DATE-EDIT", "event": "TaskDateChanged{id}",
         "affected_screen": "S-01", "affected_control": "主列表行日期徽标",
         "data": "TaskModel.dueDate", "refresh_timing": "写入事务提交成功 → 同步刷新",
         "state_handling": "保留选中", "test_ref": "T-103", "status": "verified"},
        {"link_id": "LK-002", "source_id": "F-DATE-EDIT", "event": "TaskDateChanged{id}",
         "affected_screen": "S-01", "affected_control": "侧栏今天角标计数",
         "data": "count(today)", "refresh_timing": "事件广播 → 下一帧重算",
         "state_handling": "保留滚动位置", "test_ref": "T-104", "status": "wired"},
        {"link_id": "LK-003", "source_id": "F-DATE-EDIT", "event": "TaskDateChanged{id}",
         "affected_screen": "S-02", "affected_control": "详情面板日期字段",
         "data": "TaskModel.dueDate", "refresh_timing": "写入成功回调 → 立即",
         "state_handling": "保留焦点", "test_ref": "T-105", "status": "wired"},
        {"link_id": "LK-004", "source_id": "F-REPEAT-SET", "event": "RepeatChanged{id}",
         "affected_screen": "S-02", "affected_control": "详情面板重复字段",
         "data": "TaskModel.repeat", "refresh_timing": "提交成功 → 立即",
         "state_handling": "保留焦点", "test_ref": "T-106", "status": "pending"},
        {"link_id": "LK-005", "source_id": "F-REPEAT-SET", "event": "RepeatChanged{id}",
         "affected_screen": "S-01", "affected_control": "不适用：单次任务不发通知，无提醒调度",
         "data": "-", "refresh_timing": "不适用",
         "state_handling": "不适用：重复规则不影响提醒调度（提醒由 remindTime 单独决定）",
         "test_ref": "-", "status": "na"},
    ]
    unknowns = [
        {"unknown_id": "U-001", "area": "S-02", "description": "清除日期是否同时清除提醒",
         "impact": "F-DATE-EDIT", "evidence_gap": "缺少清除后的截图",
         "verification_action": "在 S-02 执行清除日期，立即看提醒字段并截图",
         "owner": "蓝图工", "blocking": "no", "status": "open"},
    ]

    write_csv(os.path.join(p, "BLUEPRINT", "features.csv"), FEATURE_COLS, features)
    write_csv(os.path.join(p, "BLUEPRINT", "screens.csv"), SCREEN_COLS, screens)
    write_csv(os.path.join(p, "BLUEPRINT", "menus.csv"), MENU_COLS, menus)
    write_csv(os.path.join(p, "BLUEPRINT", "linkage.csv"), LINK_COLS, linkage)
    write_csv(os.path.join(p, "BLUEPRINT", "unknowns.csv"), UNKNOWN_COLS, unknowns)

    flows = """# flows · 示例应用

## FL-01 修改任务日期

- 目标：把任务的截止日期改到明天
- 起点：S-01 主列表
- 路径：S-01 → S-02 → 菜单 M-DATE → 结果
- 点击数：3

### 正常路径
1. 点任务行 → 打开 S-02
2. 点日期 → 展开 M-DATE
3. 点「明天」 → 列表徽标与角标同步更新

### 失败与取消
| 情形 | 用户看到 | 系统状态 | 可恢复动作 |
|---|---|---|---|
| 写入失败 | 红条「保存失败，已保留你的输入」 | 草稿保留 | 重试 |

### 边界
| 边界 | 期望行为 | 依据 |
|---|---|---|
| 跨月 | 自动进位 | S-02 |

### 恢复
保存失败重试；误操作可撤销。
"""
    write_text(os.path.join(p, "BLUEPRINT", "flows.md"), flows)
    write_text(os.path.join(p, "BLUEPRINT", "state-machines.md"),
               "# 状态机\n\n## SM-01 任务\n\n### 状态\n| 状态 | 含义 | 是否持久化 |\n|---|---|---|\n| 待办 | 未完成 | 是 |\n")
    write_text(os.path.join(p, "BLUEPRINT", "data-dictionary.md"),
               "# 数据字典\n\n## E01 TaskModel\n| 字段 | 类型 | 默认 | 空值 | 枚举/约束 | 关系 | 来源（原版观察/推断） | 本地映射 |\n|---|---|---|---|---|---|---|---|\n| dueDate | INTEGER | NULL | 允许 | - | - | 原版观察 | due_date |\n")

    write_text(os.path.join(p, "BLUEPRINT", "contracts", "C-F-DATE-EDIT.md"),
               contract_text("C-F-DATE-EDIT", "修改任务的日期与时间"))
    write_text(os.path.join(p, "BLUEPRINT", "contracts", "C-F-REPEAT-SET.md"),
               contract_text("C-F-REPEAT-SET", "设置重复规则"))

    # 证据
    write_text(os.path.join(p, "evidence", "s02-date-menu.png"), "PNG-FAKE-1")
    write_text(os.path.join(p, "evidence", "db-schema-export.txt"), "table task(dueDate)")
    write_text(os.path.join(p, "screens", "S-01.png"), "PNG-FAKE-2")

    if not clean:
        break_blueprint(rc, p)
    return p


def break_blueprint(rc_mod, p):
    """在干净夹具上注入问题（用于断言 lint 能抓到）。"""
    # 1) 契约缺第 5 节、第 8 节只有占位、第 12 节是"界面刷新"
    write_text(os.path.join(p, "BLUEPRINT", "contracts", "C-F-DATE-EDIT.md"),
               contract_text("C-F-DATE-EDIT", "修改任务的日期与时间",
                             bad_section=12, placeholder_section=8, drop_section=5))
    # 2) features: must 功能缺契约 + 重复 ID + 非法枚举
    write_csv(os.path.join(p, "BLUEPRINT", "features.csv"), FEATURE_COLS, [
        {"feature_id": "F-DATE-EDIT", "feature": "改日期", "area": "S-02",
         "priority": "must", "scope": "in", "original": "yes", "progress": "yes",
         "contract_ref": "contracts/C-F-NOT-EXIST.md", "acceptance_ref": "T-101",
         "evidence": "S-02", "notes": "-"},
        {"feature_id": "F-DATE-EDIT", "feature": "重复 ID 的功能", "area": "S-03",
         "priority": "P0", "scope": "in", "original": "yes", "progress": "done",
         "contract_ref": "", "acceptance_ref": "", "evidence": "", "notes": ""},
        {"feature_id": "F-NO-CONTRACT", "feature": "没契约的 must", "area": "S-04",
         "priority": "must", "scope": "in", "original": "yes", "progress": "no",
         "contract_ref": "", "acceptance_ref": "", "evidence": "", "notes": ""},
        {"feature_id": "F_bad_format", "feature": "ID 格式不对的", "area": "S-04",
         "priority": "could", "scope": "out", "original": "yes", "progress": "no",
         "contract_ref": "", "acceptance_ref": "", "evidence": "", "notes": "-"},
        {"feature_id": "F-SKIP", "feature": "跳过的", "area": "S-04",
         "priority": "could", "scope": "in", "original": "yes", "progress": "skip",
         "contract_ref": "", "acceptance_ref": "", "evidence": "", "notes": ""},
    ])
    # 3) linkage: source 不存在 + 缺 test_ref + 宽松 control
    write_csv(os.path.join(p, "BLUEPRINT", "linkage.csv"), LINK_COLS, [
        {"link_id": "LK-001", "source_id": "F-GHOST", "event": "E",
         "affected_screen": "S-01", "affected_control": "界面刷新",
         "data": "D", "refresh_timing": "", "state_handling": "X",
         "test_ref": "", "status": "pending"},
        {"link_id": "LK-001", "source_id": "F-DATE-EDIT", "event": "E2",
         "affected_screen": "S-99", "affected_control": "列表行",
         "data": "D", "refresh_timing": "立即", "state_handling": "X",
         "test_ref": "abc", "status": "bogus"},
    ])
    # 4) menus: 父节点不存在 + 缺 command + 三条件空 + 禁用词
    write_csv(os.path.join(p, "BLUEPRINT", "menus.csv"), MENU_COLS, [
        {"node_id": "M-DATE", "parent_id": "M-GHOST", "path": "日期", "order": "1",
         "type": "submenu", "label": "日期", "shortcut": "-",
         "visibility_cond": "视情况", "enabled_cond": "", "checked_cond": "",
         "command": "", "contract_ref": "", "screens": "S-99", "notes": "-"},
        {"node_id": "M-DATE-TODAY", "parent_id": "M-DATE", "path": "日期 › 今天",
         "order": "1", "type": "action", "label": "今天", "shortcut": "-",
         "visibility_cond": "按原版", "enabled_cond": "按原版", "checked_cond": "同前",
         "command": "", "contract_ref": "", "screens": "S-02", "notes": "-"},
    ])
    # 5) screens: 空态没填
    write_csv(os.path.join(p, "BLUEPRINT", "screens.csv"), SCREEN_COLS, [
        {"screen_id": "S-01", "name": "主列表", "entry": "启动", "exits": "关窗",
         "purpose": "看任务", "key_components": "列表",
         "state_filled": "yes", "state_empty": "", "state_loading": "yes",
         "state_error": "YES", "state_permission": "-", "focus_restore": "-",
         "flows": "FL-01", "notes": "-"},
    ])
    # 6) flows 引用不存在的屏幕
    write_text(os.path.join(p, "BLUEPRINT", "flows.md"),
               "## FL-01 流程\n\n- 路径：S-01 → S-77\n\n### 正常路径\n1. 做\n")
    # 7) unknowns: 缺验证动作 + 笼统描述
    write_csv(os.path.join(p, "BLUEPRINT", "unknowns.csv"), UNKNOWN_COLS, [
        {"unknown_id": "U-001", "area": "S-02", "description": "细节待定",
         "impact": "-", "evidence_gap": "-", "verification_action": "",
         "owner": "x", "blocking": "yes", "status": "open"},
    ])
    # 8) recon 里塞禁用词
    write_text(os.path.join(p, "BLUEPRINT", "recon.md"),
               "# recon\n\n## 1 目标制品与身份\n\n- TBD 待定\n")


# --------------------------------------------------------------------------
# 运行工具的辅助
# --------------------------------------------------------------------------

def run_tool(name, *args, expect=None):
    """以子进程跑工具，返回 (rc, stdout, stderr)。expect 用于失败时打印上下文。"""
    path = os.path.join(TOOLS, name)
    proc = subprocess.run([sys.executable, path] + list(args),
                          capture_output=True, text=True, timeout=120)
    if expect is not None and proc.returncode != expect:
        raise AssertionError("%s 退出码 %d（期望 %d）\nSTDOUT:\n%s\nSTDERR:\n%s"
                             % (name, proc.returncode, expect, proc.stdout[-3000:],
                                proc.stderr[-2000:]))
    return proc


def run_json(name, *args, expect=None):
    res = run_tool(name, *args, "--json", expect=expect)
    try:
        return json.loads(res.stdout), res
    except json.JSONDecodeError as exc:
        raise AssertionError("%s 的 --json 输出不是合法 JSON（%s）：\n%s\n%s"
                            % (name, exc, res.stdout[:2000], res.stderr[:1000]))


def load_tool(name):
    spec = importlib.util.spec_from_file_location(
        "tool_" + name.replace(".py", ""), os.path.join(TOOLS, name))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


class TmpCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="replica-test-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def project(self, clean=True):
        return make_project(self.tmp, clean=clean)


# --------------------------------------------------------------------------
# 0. 公共底座
# --------------------------------------------------------------------------

class TestCommon(TmpCase):
    def test_schema_parses_real_schemas_md(self):
        """SCHEMAS.md 能现场解析出 5 张表列名 + 16 节。"""
        schema = rc.load_schema(ROOT)
        self.assertTrue(schema.warnings == [] or "SCHEMAS" not in " ".join(schema.warnings),
                        "体系根的 SCHEMAS.md 应能解析成功：%s" % schema.warnings)
        self.assertEqual(len(schema.sections), 16)
        self.assertEqual(schema.columns["features"], rc.BUILTIN_COLUMNS["features"])
        self.assertEqual(schema.columns["linkage"], rc.BUILTIN_COLUMNS["linkage"])

    def test_schema_falls_back_without_file(self):
        """找不到可解析的 SCHEMAS 时必须退回内置常量并给出 warning，而不是静默。"""
        orig = rc._candidate_schemas_paths
        rc._candidate_schemas_paths = lambda project: [os.path.join(self.tmp, "nope", "SCHEMAS.md")]
        try:
            schema = rc.load_schema(self.tmp)
        finally:
            rc._candidate_schemas_paths = orig
        self.assertEqual(len(schema.sections), 16)
        self.assertEqual(schema.source, None)
        self.assertTrue(any("内置常量" in w for w in schema.warnings),
                        "找不到 SCHEMAS 时必须给出 warning：%s" % schema.warnings)

    def test_schema_unparsable_falls_back(self):
        """SCHEMAS 损坏时退回内置常量，不许抛栈。"""
        bad = os.path.join(self.tmp, "templates", "blueprint")
        os.makedirs(bad, exist_ok=True)
        write_text(os.path.join(bad, "SCHEMAS.md"), "# 空的\n\n没有任何表\n")
        orig = rc._candidate_schemas_paths
        rc._candidate_schemas_paths = lambda project: [os.path.join(bad, "SCHEMAS.md")]
        try:
            schema = rc.load_schema(self.tmp)
        finally:
            rc._candidate_schemas_paths = orig
        self.assertEqual(len(schema.sections), 16)
        self.assertTrue(any("解析失败" in w for w in schema.warnings), schema.warnings)

    def test_banned_scan_skips_html_comments(self):
        text = "<!-- 注释里可以说 待填 -->\n正文 按原版\n"
        hits = rc.scan_banned(text)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0][0], "按原版")

    def test_split_md_sections(self):
        secs = rc.split_md_sections("# t\n## A\nx\n## B\ny\n", level=2)
        self.assertEqual([s["title"] for s in secs], ["A", "B"])

    def test_read_csv_missing_file(self):
        with self.assertRaises(rc.ToolError) as ctx:
            rc.read_csv_table(os.path.join(self.tmp, "nope.csv"), ["a"])
        self.assertIn("nope.csv", ctx.exception.message)
        self.assertTrue(ctx.exception.hint)


# --------------------------------------------------------------------------
# 1. blueprint_lint
# --------------------------------------------------------------------------

class TestBlueprintLint(TmpCase):
    def test_help(self):
        res = run_tool("blueprint_lint.py", "--help", expect=0)
        self.assertIn("--project", res.stdout)
        self.assertIn("--json", res.stdout)

    def test_clean_project_passes(self):
        p = self.project(clean=True)
        data, res = run_json("blueprint_lint.py", "--project", p, expect=0)
        self.assertTrue(data["clean"], "干净夹具不应有 ERROR：%s"
                        % [f for f in data["findings"] if f["level"] == "ERROR"][:5])
        self.assertEqual(data["counts"]["error"], 0)
        self.assertEqual(data["counts"]["must_in"], 2)
        self.assertEqual(data["counts"]["must_with_contract"], 2)

    def test_broken_project_fails_with_specific_codes(self):
        p = self.project(clean=False)
        data, res = run_json("blueprint_lint.py", "--project", p, expect=1)
        codes = {f["code"] for f in data["findings"] if f["level"] == "ERROR"}
        expected = {
            "CONTRACT-SECTION-MISSING",       # 缺第 5 节
            "CONTRACT-SECTION-PLACEHOLDER",   # 第 8 节只有"待填"
            "ID-DUP",                         # F-DATE-EDIT 重复
            "REF-CONTRACT-MISSING",           # contract_ref 指向不存在文件
            "REF-MUST-NO-CONTRACT",           # must 没契约
            "REF-LINK-SOURCE-MISSING",        # F-GHOST 不存在
            "REF-LINK-NO-TEST",               # 缺 test_ref
            "REF-LINK-VAGUE",                 # "界面刷新"
            "REF-MENU-PARENT-MISSING",        # M-GHOST
            "REF-MENU-NO-COMMAND",            # 叶子缺 command
            "MENU-COND-MISSING",              # 三条件空
            "BANNED-WORD",                    # 按原版 / 视情况 / TBD / 待定
            "SCREEN-STATE-MISSING",           # 空态空
            "ENUM-PROGRESS",                  # progress=done
            "REF-FLOW-SCREEN-MISSING",        # S-77
            "UNKNOWN-NO-ACTION",              # 缺验证动作
            "SKIP-NO-REASON",                 # skip 没理由
            "ID-FORMAT",                      # LK 重复/格式 + test_ref abc 走别的码
        }
        missing = expected - codes
        self.assertFalse(missing, "以下问题编号没被抓到：%s；实际抓到：%s"
                         % (sorted(missing), sorted(codes)))

    def test_fix_hints_printed(self):
        p = self.project(clean=False)
        res = run_tool("blueprint_lint.py", "--project", p, "--fix-hints", expect=1)
        self.assertIn("→ 修复", res.stdout)

    def test_only_section_filter(self):
        p = self.project(clean=False)
        data, _ = run_json("blueprint_lint.py", "--project", p, "--only", "禁用词", expect=1)
        self.assertTrue(all(f["section"] == "禁用词" for f in data["findings"]))
        self.assertGreater(len(data["findings"]), 0)

    def test_missing_blueprint_dir_gives_actionable_error(self):
        res = run_tool("blueprint_lint.py", "--project", self.tmp, expect=2)
        self.assertIn("BLUEPRINT", res.stderr)
        self.assertIn("下一步", res.stderr)
        self.assertNotIn("Traceback", res.stderr)

    def test_missing_csv_does_not_crash(self):
        p = self.project(clean=True)
        os.remove(os.path.join(p, "BLUEPRINT", "menus.csv"))
        data, res = run_json("blueprint_lint.py", "--project", p, expect=1)
        codes = {f["code"] for f in data["findings"]}
        self.assertIn("FILE-MISSING", codes)

    def test_summary_only_prints_one_line_and_counts(self):
        """--summary-only：一行结论 + 各类计数，不列明细（给产品官看）。"""
        p = self.project(clean=False)
        res = run_tool("blueprint_lint.py", "--project", p, "--summary-only", expect=1)
        out = res.stdout
        self.assertIn("不可进入产品官审查", out)
        self.assertIn("ERROR", out)
        # 不应出现明细行（finding 的 where 形如 menus.csv:3）
        self.assertNotIn("menus.csv:", out, "summary-only 不该列明细")
        self.assertNotIn("[BANNED-WORD]", out, "summary-only 不该列问题码明细")
        # 但必须有汇总计数
        self.assertIn("must 契约覆盖", out)
        self.assertIn("按修的顺序", out)

    def test_summary_only_clean_project(self):
        p = self.project(clean=True)
        res = run_tool("blueprint_lint.py", "--project", p, "--summary-only", expect=0)
        self.assertIn("✅", res.stdout)
        self.assertIn("must 契约覆盖 100.0%", res.stdout)

    def test_summary_json_has_dedup_contract_count(self):
        """汇总里的缺失契约数必须去重（同一文件被 features/menus 双报只算一份）。"""
        p = self.project(clean=False)
        data, _ = run_json("blueprint_lint.py", "--project", p, expect=1)
        counts = data["counts"]
        self.assertIn("missing_contract_files", counts)
        self.assertIn("missing_contract_refs", counts)
        refs = [f for f in data["findings"]
                if f["code"] in ("REF-CONTRACT-MISSING", "REF-MENU-CONTRACT-MISSING")]
        self.assertEqual(counts["missing_contract_refs"], len(refs),
                         "refs 数应等于双报的总条数")
        self.assertEqual(counts["missing_contract_files"],
                         len(set(data["missing_contracts"])))
        self.assertLessEqual(counts["missing_contract_files"], counts["missing_contract_refs"],
                             "去重后的文件数不可能大于引用处数")
        self.assertIn("groups", data)
        self.assertIn("by_code", data)

    def test_screen_id_format_is_strict(self):
        """screen_id 是主键，必须严格 S-两位数；带后缀报专门的 SCREEN-ID-FORMAT。"""
        p = self.project(clean=True)
        path = os.path.join(p, "BLUEPRINT", "screens.csv")
        rows = read_csv_rows(path)
        rows[0]["screen_id"] = "S-01-仪表盘"      # 带后缀 → 新码
        rows[1]["screen_id"] = "S-2"              # 一位数 → 也报
        write_csv(path, SCREEN_COLS, rows)
        data, _ = run_json("blueprint_lint.py", "--project", p, expect=1)
        codes = [f["code"] for f in data["findings"]]
        self.assertIn("SCREEN-ID-FORMAT", codes)
        self.assertEqual(codes.count("SCREEN-ID-FORMAT"), 2)
        msg = [f["message"] for f in data["findings"] if f["code"] == "SCREEN-ID-FORMAT"][0]
        self.assertIn("S-两位数", msg)
        # 提示必须指明 area 允许后缀（区分主键与描述）
        fix = [f["fix"] for f in data["findings"] if f["code"] == "SCREEN-ID-FORMAT"][0]
        self.assertIn("area", fix)

    def test_area_allows_suffix(self):
        """features.area 是描述字段，允许 'S-03-预约页' 这种写法，不许报错。"""
        p = self.project(clean=True)
        path = os.path.join(p, "BLUEPRINT", "features.csv")
        rows = read_csv_rows(path)
        rows[0]["area"] = "S-02-任务详情"        # 带后缀：合法
        write_csv(path, FEATURE_COLS, rows)
        data, _ = run_json("blueprint_lint.py", "--project", p, expect=0)
        bad = [f for f in data["findings"]
               if f["level"] == "ERROR" and "area" in f["message"]]
        self.assertEqual(bad, [], "area 带后缀不该报错：%s" % bad)

    def test_only_still_loads_data(self):
        """--only 是过滤输出，不是跳过载入：--only ID 必须能真的查 ID。"""
        p = self.project(clean=False)
        data, _ = run_json("blueprint_lint.py", "--project", p, "--only", "ID", expect=1)
        self.assertTrue(all(f["section"] == "ID" for f in data["findings"]),
                        "只该有 ID 分区的问题：%s" % {f["section"] for f in data["findings"]})
        self.assertIn("ID-DUP", {f["code"] for f in data["findings"]})
        # must 覆盖率与 --only 无关，必须仍然算出来
        self.assertGreater(data["counts"]["must_in"], 0)

    def test_only_marks_incomplete_check(self):
        """--only 时结论必须标明"非全量检查"，不许说"可以开会"（防假绿）。"""
        p = self.project(clean=True)
        res = run_tool("blueprint_lint.py", "--project", p, "--only", "ID")
        self.assertIn("不是全量检查", res.stdout)
        self.assertIn("未做全量检查", res.stdout)
        self.assertNotIn("可以拿这份蓝图去开产品官审查会", res.stdout)
        res2 = run_tool("blueprint_lint.py", "--project", p, "--only", "ID", "--summary-only")
        self.assertIn("非全量检查", res2.stdout)
        self.assertNotIn("可以开会", res2.stdout)

    def test_order_dup_stays_warn_with_gate_note(self):
        """ORDER-DUP 在 lint 是 WARN，但必须注明门禁 G2 会判 ERROR。"""
        p = self.project(clean=True)
        path = os.path.join(p, "BLUEPRINT", "menus.csv")
        rows = read_csv_rows(path)
        rows[1]["order"] = "9"       # 与 M-DATE-CLEAR 的 9 冲突
        write_csv(path, MENU_COLS, rows)
        data, _ = run_json("blueprint_lint.py", "--project", p, expect=0)
        dup = [f for f in data["findings"] if f["code"] == "MENU-ORDER-DUP"]
        self.assertTrue(dup)
        self.assertEqual(dup[0]["level"], "WARN", "lint 里应保持 WARN 不阻断")
        self.assertIn("G2", dup[0]["fix"], "修复提示必须告知门禁 G2 会判 ERROR")

    def test_bad_argument_exit_code(self):
        p = self.project(clean=True)
        res = run_tool("blueprint_lint.py", "--project", p, "--only", "不存在的分区", expect=2)
        self.assertIn("未知分区", res.stderr)


# --------------------------------------------------------------------------
# 2. menu_walk
# --------------------------------------------------------------------------

class TestMenuWalk(TmpCase):
    def test_help(self):
        res = run_tool("menu_walk.py", "--help", expect=0)
        for flag in ("--tree", "--cards", "--gaps", "--check", "--from-screens"):
            self.assertIn(flag, res.stdout)

    def test_tree_structure_and_order(self):
        p = self.project(clean=True)
        res = run_tool("menu_walk.py", "--project", p, "--tree", expect=0)
        out = res.stdout
        self.assertIn("▸ 日期", out)
        self.assertIn("● 今天", out)
        self.assertIn("◉ 每周工作日", out)
        self.assertIn("M-DATE-CLEAR", out)
        # order 9 的"清除日期"应排在 order 1 的"今天"之后
        self.assertLess(out.index("今天"), out.index("清除日期"))

    def test_cards_show_three_conditions(self):
        p = self.project(clean=True)
        res = run_tool("menu_walk.py", "--project", p, "--cards", expect=0)
        out = res.stdout
        for word in ("显示条件", "可用条件", "选中条件", "命令", "契约"):
            self.assertIn(word, out)
        self.assertIn("Cmd.SetDateToday", out)
        self.assertIn("contracts/C-F-DATE-EDIT.md", out)

    def test_gaps_report_on_broken(self):
        p = self.project(clean=False)
        data, res = run_json("menu_walk.py", "--project", p, expect=0)
        self.assertGreater(data["gap_count"], 0)
        gap = data["gaps"][0]
        self.assertTrue(set(gap["missing"]) & {"command", "contract_ref",
                                               "显示条件", "可用条件", "选中条件"})
        codes = {x["code"] for x in data["problems"]}
        self.assertIn("NODE-PARENT-MISSING", codes)

    def test_check_exit_codes(self):
        clean = self.project(clean=True)
        run_tool("menu_walk.py", "--project", clean, "--check", expect=0)
        # 独立目录：不能复制到项目自身子目录下（copytree 会拒绝"复制进自己"）
        broken = tempfile.mkdtemp(prefix="replica-broken-")
        self.addCleanup(shutil.rmtree, broken, True)
        shutil.copytree(clean, broken, dirs_exist_ok=True)
        break_blueprint(rc, broken)
        res = run_tool("menu_walk.py", "--project", broken, "--check", expect=1)
        self.assertIn("门禁结论", res.stdout)

    def test_from_screens_generates_skeleton(self):
        p = self.project(clean=True)
        res = run_tool("menu_walk.py", "--project", p, "--from-screens", "--screens", "screens",
                       expect=0)
        skel = os.path.join(p, "BLUEPRINT", "menus.skeleton.csv")
        self.assertTrue(os.path.isfile(skel), res.stdout)
        with open(skel, encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            self.assertEqual(list(reader.fieldnames), MENU_COLS)
            rows = list(reader)
        self.assertEqual(len(rows), 1)  # screens/ 里只有 1 张 png
        self.assertIn("待填", rows[0]["visibility_cond"])

    def test_missing_menus_csv_error(self):
        os.makedirs(os.path.join(self.tmp, "BLUEPRINT"))
        res = run_tool("menu_walk.py", "--project", self.tmp, "--tree", expect=2)
        self.assertIn("menus.csv", res.stderr)
        self.assertNotIn("Traceback", res.stderr)


# --------------------------------------------------------------------------
# 3. linkage_matrix
# --------------------------------------------------------------------------

class TestLinkageMatrix(TmpCase):
    def test_help(self):
        res = run_tool("linkage_matrix.py", "--help", expect=0)
        self.assertIn("--strict", res.stdout)
        self.assertIn("--md-out", res.stdout)

    def test_six_faces_and_coverage(self):
        p = self.project(clean=True)
        data, _ = run_json("linkage_matrix.py", "--project", p)
        self.assertEqual(len(data["faces"]), 6)
        face_names = [f["name"] for f in data["faces"]]
        self.assertEqual(face_names, ["主列表", "角标计数", "详情面板", "日历/时间", "搜索", "提醒/通知"])
        musts = {m["feature_id"]: m for m in data["musts"]}
        self.assertIn("F-DATE-EDIT", musts)
        date = musts["F-DATE-EDIT"]
        self.assertEqual(date["counts"]["wired"], 3)       # 列表 / 角标 / 详情
        self.assertEqual(date["counts"]["no_entry"], 3)    # 日历 / 搜索 / 提醒
        self.assertEqual(date["counts"]["na"], 0)
        self.assertTrue(date["faces"]["list"]["has_link"])
        self.assertFalse(date["faces"]["search"]["has_link"])

    def test_four_state_counts(self):
        """四态：wired / pending / na / no_entry 必须分开统计。"""
        p = self.project(clean=True)
        data, _ = run_json("linkage_matrix.py", "--project", p)
        c = data["counts"]
        for key in ("wired", "pending", "na", "no_entry", "considered"):
            self.assertIn(key, c, "counts 缺少 %s" % key)
        repeat = {m["feature_id"]: m for m in data["musts"]}["F-REPEAT-SET"]
        # 详情=pending，提醒=na，其余 4 面 no_entry
        self.assertEqual(repeat["counts"]["pending"], 1)
        self.assertEqual(repeat["counts"]["na"], 1)
        self.assertEqual(repeat["counts"]["no_entry"], 4)
        self.assertEqual(repeat["faces"]["remind"]["status_class"], "na")
        self.assertEqual(repeat["faces"]["detail"]["status_class"], "pending")
        # na 必须算"已考虑"，但不计入缺面
        self.assertEqual(c["considered"], c["wired"] + c["pending"] + c["na"])
        self.assertEqual(data["missing_faces"], c["no_entry"])

    def test_na_not_counted_as_missing(self):
        """status=na 的面不计入缺面数（lead 定的口径）。"""
        p = self.project(clean=True)
        before, _ = run_json("linkage_matrix.py", "--project", p)
        missing_before = before["missing_faces"]
        # 把 F-DATE-EDIT 的「搜索」从"无条目"补成 na
        path = os.path.join(p, "BLUEPRINT", "linkage.csv")
        rows = read_csv_rows(path)
        rows.append({"link_id": "LK-006", "source_id": "F-DATE-EDIT",
                     "event": "TaskDateChanged{id}", "affected_screen": "S-01",
                     "affected_control": "不适用：搜索按标题匹配，日期不参与索引",
                     "data": "-", "refresh_timing": "不适用",
                     "state_handling": "不适用：搜索仅索引标题与备注，不索引日期",
                     "test_ref": "-", "status": "na"})
        write_csv(path, LINK_COLS, rows)
        after, _ = run_json("linkage_matrix.py", "--project", p)
        self.assertEqual(after["missing_faces"], missing_before - 1,
                         "补一个 na 应当让缺面数减 1")
        self.assertEqual(after["counts"]["na"], before["counts"]["na"] + 1)
        self.assertTrue(after["musts"][0]["faces"]["search"]["na"])

    def test_all_na_is_flagged(self):
        """六面全 na 等同没做联动分析，必须单独报。"""
        p = self.project(clean=True)
        path = os.path.join(p, "BLUEPRINT", "linkage.csv")
        rows = [r for r in read_csv_rows(path) if r["source_id"] != "F-REPEAT-SET"]
        faces = ["主列表", "角标计数", "详情面板", "日历/时间", "搜索", "提醒/通知"]
        for i, name in enumerate(faces, start=10):
            rows.append({"link_id": "LK-%03d" % i, "source_id": "F-REPEAT-SET",
                         "event": "RepeatChanged{id}", "affected_screen": "S-02",
                         "affected_control": "不适用：%s 不受重复规则影响" % name,
                         "data": "-", "refresh_timing": "不适用",
                         "state_handling": "不适用：重复规则只影响下次触发时间",
                         "test_ref": "-", "status": "na"})
        write_csv(path, LINK_COLS, rows)
        data, _ = run_json("linkage_matrix.py", "--project", p)
        self.assertIn("F-REPEAT-SET", data["counts"]["all_na_features"])
        self.assertFalse(data["clean"], "六面全 na 必须让 clean=False")
        text = run_tool("linkage_matrix.py", "--project", p).stdout
        self.assertIn("六面全 na", text)

    def test_na_without_reason_is_error(self):
        """na 不写理由 = 造假，必须报 ERROR。"""
        p = self.project(clean=True)
        path = os.path.join(p, "BLUEPRINT", "linkage.csv")
        rows = read_csv_rows(path)
        rows.append({"link_id": "LK-007", "source_id": "F-DATE-EDIT",
                     "event": "E", "affected_screen": "S-01",
                     "affected_control": "不适用：搜索", "data": "-",
                     "refresh_timing": "不适用", "state_handling": "",
                     "test_ref": "-", "status": "na"})
        write_csv(path, LINK_COLS, rows)
        data, res = run_json("linkage_matrix.py", "--project", p)
        codes = {x["code"] for x in data["problems"]}
        self.assertIn("LINK-NA-NO-REASON", codes)
        self.assertFalse(data["clean"])

    def test_pending_not_counted_as_wired(self):
        p = self.project(clean=True)
        data, _ = run_json("linkage_matrix.py", "--project", p)
        repeat = {m["feature_id"]: m for m in data["musts"]}["F-REPEAT-SET"]
        self.assertTrue(repeat["faces"]["detail"]["has_link"])
        self.assertFalse(repeat["faces"]["detail"]["wired"])
        self.assertFalse(repeat["faces"]["detail"]["na"])
        # 有登记但 0 wire → 进度问题，不是"只有1面"的可疑
        self.assertTrue(repeat["no_wired"])
        self.assertFalse(repeat["suspicious_single"])

    def test_strict_exit_code(self):
        p = self.project(clean=True)
        res = run_tool("linkage_matrix.py", "--project", p, "--strict")
        self.assertEqual(res.returncode, 1, "有 no_entry 时 --strict 应退出 1")
        res2 = run_tool("linkage_matrix.py", "--project", p)
        self.assertEqual(res2.returncode, 0, "非严格模式只报不拦")

    def test_markdown_has_warning_sections(self):
        p = self.project(clean=True)
        res = run_tool("linkage_matrix.py", "--project", p, expect=0)
        self.assertIn("# 联动矩阵", res.stdout)
        self.assertIn("待补清单", res.stdout)
        self.assertIn("● 已 wire", res.stdout)      # 图例
        self.assertIn("× 确认不适用", res.stdout)

    def test_unclassified_and_unknown_source(self):
        p = self.project(clean=True)
        # 把一条 control 改成无法归类的词
        path = os.path.join(p, "BLUEPRINT", "linkage.csv")
        with open(path, encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        rows[0]["affected_control"] = "某个地方"
        rows[1]["source_id"] = "F-GHOST"
        write_csv(path, LINK_COLS, rows)
        data, _ = run_json("linkage_matrix.py", "--project", p)
        self.assertEqual(data["counts"]["unclassified"], 1)
        self.assertIn("F-GHOST", data["unknown_sources"])

    def test_forced_face_marker(self):
        p = self.project(clean=True)
        path = os.path.join(p, "BLUEPRINT", "linkage.csv")
        with open(path, encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        rows[0]["affected_control"] = "某个地方 #搜索"
        write_csv(path, LINK_COLS, rows)
        data, _ = run_json("linkage_matrix.py", "--project", p)
        self.assertTrue(data["musts"][0]["faces"]["search"]["has_link"]
                        or any(m["faces"]["search"]["has_link"] for m in data["musts"]))

    def test_dump_config(self):
        res = run_tool("linkage_matrix.py", "--dump-config", expect=0)
        data = json.loads(res.stdout)
        self.assertEqual(len(data), 6)
        self.assertIn("keywords", data[0])


# --------------------------------------------------------------------------
# 4. parity_score
# --------------------------------------------------------------------------

class TestParityScore(TmpCase):
    def test_help(self):
        res = run_tool("parity_score.py", "--help", expect=0)
        self.assertIn("--fail-under", res.stdout)
        self.assertIn("--markdown", res.stdout)

    def test_weighted_feature_score(self):
        p = self.project(clean=True)
        data, _ = run_json("parity_score.py", "--project", p, "--no-require-must", expect=0)
        # must: F-DATE-EDIT yes=1, F-REPEAT-SET partial=0.5 → 权重 3 各一
        # could: F-TAG-COLOR no=0 → 权重 1
        # F-AI-SUGGEST scope=out → 不计
        # 得分 = (3*1 + 3*0.5 + 1*0) / (3+3+1) = 4.5/7 = 64.2857 → 64.3
        self.assertAlmostEqual(data["feature_score"], 64.3, places=1)
        self.assertEqual(data["counted"], 3)
        self.assertEqual(data["must_have_total"], 2)
        self.assertEqual(data["must_have_done"], 1)

    def test_must_not_green_fails(self):
        p = self.project(clean=True)
        res = run_tool("parity_score.py", "--project", p)
        self.assertEqual(res.returncode, 1, "must 未全绿时应退出 1")
        self.assertIn("门禁结论", res.stdout)

    def test_fail_under_threshold(self):
        p = self.project(clean=True)
        run_tool("parity_score.py", "--project", p, "--fail-under", "10",
                 "--no-require-must", expect=0)
        run_tool("parity_score.py", "--project", p, "--fail-under", "99",
                 "--no-require-must", expect=1)

    def test_markdown_report_written(self):
        p = self.project(clean=True)
        out = os.path.join(p, "REPORT", "parity.md")
        res = run_tool("parity_score.py", "--project", p, "--markdown",
                       "--md-out", "REPORT/parity.md", "--no-require-must", expect=0)
        self.assertTrue(os.path.isfile(out), res.stderr)
        text = slurp(out)
        for word in ("一致性报告", "功能分", "界面分", "缺失清单", "口径声明"):
            self.assertIn(word, text)

    def test_visual_scores_fold_in(self):
        p = self.project(clean=True)
        diff = os.path.join(p, "diffs", "S-01.json")
        write_text(os.path.join(p, "diffs", "S-01.json"),
                   json.dumps({"score": 92.0, "mode": "layout",
                               "files": {"original": "screens/S-01.png",
                                         "clone": "clone-screens/S-01.png"}}))
        data, _ = run_json("parity_score.py", "--project", p, "--visual", diff,
                           "--no-require-must")
        self.assertEqual(data["layout_score"], 92.0)
        self.assertAlmostEqual(data["overall"],
                               0.8 * data["feature_score"] + 0.2 * 92.0, places=1)

    def test_upstream_algorithm_loaded(self):
        """体系根有 replica-skill 时应走上游算法。"""
        p = self.project(clean=True)
        data, _ = run_json("parity_score.py", "--project", p, "--no-require-must")
        expected = "upstream" if os.path.isfile(
            os.path.join(ROOT, "replica-skill", "replica-diff", "parity.py")) else "builtin"
        self.assertEqual(data["backend"], expected)
        if expected == "upstream":
            self.assertIn("parity.py", data["backend_path"])

    def test_builtin_fallback_numbers_match(self):
        """内置实现与上游同权重，同一夹具必须同分。"""
        mod = load_tool("parity_score.py")
        rows = [
            {"feature_id": "A", "feature": "a", "area": "x", "priority": "must",
             "original": "yes", "progress": "yes", "scope": "in", "line": 2},
            {"feature_id": "B", "feature": "b", "area": "x", "priority": "must",
             "original": "yes", "progress": "partial", "scope": "in", "line": 3},
            {"feature_id": "C", "feature": "c", "area": "y", "priority": "could",
             "original": "yes", "progress": "no", "scope": "in", "line": 4},
            {"feature_id": "D", "feature": "d", "area": "y", "priority": "should",
             "original": "yes", "progress": "skip", "scope": "in", "line": 5},
        ]
        res = mod.builtin_score(rows)
        self.assertAlmostEqual(res["feature_score"], 64.3, places=1)
        self.assertEqual(res["must_have_total"], 2)
        self.assertEqual(len(res["skipped"]), 1)

    def test_missing_features_csv_error(self):
        os.makedirs(os.path.join(self.tmp, "BLUEPRINT"))
        res = run_tool("parity_score.py", "--project", self.tmp, expect=2)
        self.assertIn("features.csv", res.stderr)
        self.assertNotIn("Traceback", res.stderr)


# --------------------------------------------------------------------------
# 5. contract_scaffold
# --------------------------------------------------------------------------

class TestContractScaffold(TmpCase):
    def test_help(self):
        res = run_tool("contract_scaffold.py", "--help", expect=0)
        self.assertIn("--feature", res.stdout)
        self.assertIn("--all", res.stdout)

    def test_single_contract_has_16_exact_sections(self):
        p = self.project(clean=True)
        out = os.path.join(p, "BLUEPRINT", "contracts")
        run_tool("contract_scaffold.py", "--project", p, "--feature", "F-DATE-EDIT",
                 "--name", "修改日期", "--out", out, "--force", expect=0)
        path = os.path.join(out, "C-F-DATE-EDIT.md")
        self.assertTrue(os.path.isfile(path))
        text = slurp(path)
        self.assertIn("# C-F-DATE-EDIT · 修改日期", text)
        secs = rc.split_md_sections(text, level=2)
        self.assertEqual([s["title"] for s in secs], SECTION_TITLES,
                         "16 节标题必须与 SCHEMAS §8 逐字一致")
        # 每节都有"必须写什么"注释与待填提示
        self.assertEqual(text.count("<!-- 必须写什么："), 16)
        self.assertGreaterEqual(text.count("待填"), 16)

    def test_generated_skeleton_passes_section_check_but_fails_content(self):
        """骨架能过标题检查，但因为全是待填必须被 lint 判 ERROR（占位不是内容）。"""
        p = self.project(clean=True)
        out = os.path.join(p, "BLUEPRINT", "contracts")
        run_tool("contract_scaffold.py", "--project", p, "--feature", "F-BLANK",
                 "--name", "空功能", "--out", out, expect=0)
        data, _ = run_json("blueprint_lint.py", "--project", p, expect=1)
        codes = {f["code"] for f in data["findings"]}
        self.assertIn("CONTRACT-SECTION-PLACEHOLDER", codes)
        self.assertNotIn("CONTRACT-SECTION-MISSING", codes)

    def test_all_skips_existing(self):
        p = self.project(clean=True)
        out = os.path.join(p, "BLUEPRINT", "contracts")
        data, res = run_json("contract_scaffold.py", "--project", p, "--all",
                             "--out", out, expect=0)
        # 两条 already 有 contract_ref 且文件存在 → 跳过；F-TAG-COLOR/F-AI-SUGGEST 无 ref → 生成
        created = {r["feature_id"] for r in data["results"] if r["status"] == "created"}
        self.assertIn("F-TAG-COLOR", created)
        self.assertNotIn("F-DATE-EDIT", created)

    def test_force_overwrites(self):
        p = self.project(clean=True)
        out = os.path.join(p, "BLUEPRINT", "contracts")
        path = os.path.join(out, "C-F-DATE-EDIT.md")
        before = slurp(path)
        run_tool("contract_scaffold.py", "--project", p, "--feature", "F-DATE-EDIT",
                 "--name", "改名了", "--out", out, "--force", expect=0)
        after = slurp(path)
        self.assertNotEqual(before, after)
        self.assertIn("改名了", after)

    def test_dry_run_writes_nothing(self):
        p = self.project(clean=True)
        out = os.path.join(p, "BLUEPRINT", "contracts")
        run_tool("contract_scaffold.py", "--project", p, "--feature", "F-NEW-ONE",
                 "--name", "新的", "--out", out, "--dry-run", expect=0)
        self.assertFalse(os.path.isfile(os.path.join(out, "C-F-NEW-ONE.md")))

    def test_bad_feature_id(self):
        p = self.project(clean=True)
        res = run_tool("contract_scaffold.py", "--project", p, "--feature", "bad_id",
                       expect=2)
        self.assertIn("格式不对", res.stderr)

    def test_needs_feature_or_all(self):
        res = run_tool("contract_scaffold.py", "--project", self.tmp, expect=2)
        self.assertIn("--feature", res.stderr)


# --------------------------------------------------------------------------
# 6. evidence_manifest
# --------------------------------------------------------------------------

class TestEvidenceManifest(TmpCase):
    def test_help(self):
        res = run_tool("evidence_manifest.py", "--help", expect=0)
        self.assertIn("--check", res.stdout)

    def test_first_run_registers_all(self):
        p = self.project(clean=True)
        data, _ = run_json("evidence_manifest.py", "--project", p, expect=0)
        self.assertEqual(data["known"], 0)
        self.assertEqual(data["found"], 3)
        self.assertEqual(len(data["added"]), 3)
        manifest = os.path.join(p, "evidence", "MANIFEST.csv")
        self.assertTrue(os.path.isfile(manifest))
        rows = read_csv_rows(manifest)
        self.assertEqual(len(rows), 3)
        for r in rows:
            self.assertEqual(len(r["sha256_16"]), 16)
            self.assertTrue(int(r["bytes"]) > 0)
            self.assertEqual(r["capture_method"], "", "采集方式应留空待人工填")
            self.assertEqual(r["screen_id"], "", "对应屏幕应留空待人工填")

    def test_rerun_appends_only(self):
        p = self.project(clean=True)
        run_tool("evidence_manifest.py", "--project", p, expect=0)
        manifest = os.path.join(p, "evidence", "MANIFEST.csv")
        first = slurp(manifest)
        # 再加一个文件
        write_text(os.path.join(p, "evidence", "s03-repeat-menu.png"), "PNG-FAKE-3")
        data, _ = run_json("evidence_manifest.py", "--project", p, expect=0)
        self.assertEqual(len(data["added"]), 1)
        second = slurp(manifest)
        self.assertTrue(second.startswith(first.rstrip("\n")),
                        "已有行必须原样保留，只追加新行")

    def test_hash_change_is_warned_not_overwritten(self):
        p = self.project(clean=True)
        run_tool("evidence_manifest.py", "--project", p, expect=0)
        manifest = os.path.join(p, "evidence", "MANIFEST.csv")
        before = read_csv_rows(manifest)
        old_row = [r for r in before if r["path"].endswith("s02-date-menu.png")][0]
        # 替换内容
        write_text(os.path.join(p, "evidence", "s02-date-menu.png"), "DIFFERENT-CONTENT")
        data, _ = run_json("evidence_manifest.py", "--project", p)
        self.assertEqual(len(data["changed"]), 1)
        self.assertFalse(data["clean"])
        after = read_csv_rows(manifest)
        same = [r for r in after if r["path"].endswith("s02-date-menu.png")][0]
        self.assertEqual(same["sha256_16"], old_row["sha256_16"],
                         "哈希变了也不许覆盖既有行")
        res = run_tool("evidence_manifest.py", "--project", p, "--check", expect=1)
        self.assertIn("未覆盖", res.stdout)

    def test_deleted_file_marked_missing_not_dropped(self):
        p = self.project(clean=True)
        run_tool("evidence_manifest.py", "--project", p, expect=0)
        os.remove(os.path.join(p, "evidence", "db-schema-export.txt"))
        data, _ = run_json("evidence_manifest.py", "--project", p)
        self.assertEqual(len(data["missing"]), 1)
        manifest = os.path.join(p, "evidence", "MANIFEST.csv")
        rows = read_csv_rows(manifest)
        hit = [r for r in rows if r["path"].endswith("db-schema-export.txt")]
        self.assertEqual(len(hit), 1, "消失的文件不许删行")
        self.assertEqual(hit[0]["status"], "MISSING")
        run_tool("evidence_manifest.py", "--project", p, "--check", expect=1)

    def test_verify_mode_does_not_register_new(self):
        p = self.project(clean=True)
        run_tool("evidence_manifest.py", "--project", p, expect=0)
        write_text(os.path.join(p, "evidence", "new.png"), "X")
        run_tool("evidence_manifest.py", "--project", p, "--verify", expect=0)
        manifest = os.path.join(p, "evidence", "MANIFEST.csv")
        rows = read_csv_rows(manifest)
        self.assertFalse(any(r["path"].endswith("new.png") for r in rows))

    def test_no_dirs_gives_actionable_error(self):
        os.makedirs(os.path.join(self.tmp, "BLUEPRINT"))
        res = run_tool("evidence_manifest.py", "--project", self.tmp, expect=2)
        self.assertIn("evidence", res.stderr)
        self.assertIn("下一步", res.stderr)
        self.assertNotIn("Traceback", res.stderr)

    def test_init_creates_header_only(self):
        p = self.project(clean=True)
        manifest = os.path.join(p, "evidence", "MANIFEST.csv")
        if os.path.isfile(manifest):
            os.remove(manifest)
        run_tool("evidence_manifest.py", "--project", p, "--init", expect=0)
        with open(manifest, encoding="utf-8") as fh:
            header = fh.readline().strip()
        self.assertEqual(header.split(","), rc.BUILTIN_COLUMNS.get("features") and
                         ["path", "sha256_16", "bytes", "mtime_iso", "capture_method",
                          "screen_id", "first_seen", "status", "sha256_full", "notes"])


# --------------------------------------------------------------------------
# 6.5 真实样板项目冒烟（examples/scheduling-clone，由 Lead 维护）
# --------------------------------------------------------------------------

EXAMPLES = os.path.join(ROOT, "examples", "scheduling-clone")


def _missing_contracts_from_disk(project):
    """从 features.csv + menus.csv 推出「指向了但文件不存在」的契约文件名集合。"""
    cdir = os.path.join(project, "BLUEPRINT", "contracts")
    present = set(os.listdir(cdir)) if os.path.isdir(cdir) else set()
    missing = set()
    for rel, col in ((os.path.join("BLUEPRINT", "features.csv"), "contract_ref"),
                     (os.path.join("BLUEPRINT", "menus.csv"), "contract_ref")):
        path = os.path.join(project, rel)
        if not os.path.isfile(path):
            continue
        for r in read_csv_rows(path):
            ref = (r.get(col) or "").strip()
            if ref and ref not in ("-", "待填"):
                base = os.path.basename(ref)
                if base not in present:
                    missing.add(base)
    return missing


@unittest.skipUnless(os.path.isdir(EXAMPLES), "examples/scheduling-clone 不存在，跳过真实样板冒烟")
class TestExamplesSmoke(unittest.TestCase):
    """真实样板：断言工具「能识别出缺契约」而不是崩。

    样板由 Lead 实时维护（它刻意保留 12 个功能没有契约文件作为教学态），
    所以这里不写死数字 12，而是**从磁盘反算期望值**：lint 报出的缺契约文件集合
    必须与实际缺失集合一致。这样样板演进时测试不会变成噪音。
    """

    def test_lint_identifies_missing_contracts_without_crashing(self):
        data, res = run_json("blueprint_lint.py", "--project", EXAMPLES, expect=1)
        self.assertEqual(res.returncode, 1, "样板是教学态（缺契约），应退出 1 而不是 0")
        self.assertNotIn("Traceback", res.stderr)

        reported = {os.path.basename(f["message"].split("：")[-1])
                    for f in data["findings"] if f["code"] == "REF-CONTRACT-MISSING"}
        expected = _missing_contracts_from_disk(EXAMPLES)
        self.assertEqual(reported, expected,
                         "lint 报出的缺契约集合应与磁盘实际缺失一致\n"
                         "  lint: %s\n  磁盘: %s" % (sorted(reported), sorted(expected)))
        self.assertGreaterEqual(len(reported), 1, "样板至少应有一个缺契约功能")

        # must 契约覆盖率：样板 must 功能都有 contract_ref（只是文件还没写）
        self.assertEqual(data["counts"]["must_with_contract"], data["counts"]["must_in"],
                         "样板里每个 must 功能都应填了 contract_ref")

    def test_lint_reports_menu_contract_gaps(self):
        data, _ = run_json("blueprint_lint.py", "--project", EXAMPLES, expect=1)
        menu_gaps = [f for f in data["findings"] if f["code"] == "REF-MENU-CONTRACT-MISSING"]
        self.assertGreater(len(menu_gaps), 0, "菜单叶子引用的契约文件不存在时应报出来")
        for f in menu_gaps:
            self.assertIn("menus.csv:", f["where"])

    def test_menu_walk_runs_on_example(self):
        data, _ = run_json("menu_walk.py", "--project", EXAMPLES)
        self.assertGreater(data["nodes"], 0)
        self.assertGreater(data["leaves"], 0)
        self.assertIn("gap_count", data)
        # 三条件齐则 gap 少；至少不应报结构问题（无环/父节点都在）
        cyc = [p for p in data["problems"] if p["code"] in ("NODE-CYCLE", "NODE-ORPHAN")]
        self.assertEqual(cyc, [], "样板菜单树不应有环或孤立节点")

    def test_menu_walk_cards_show_default_item(self):
        res = run_tool("menu_walk.py", "--project", EXAMPLES, "--cards", expect=0)
        self.assertIn("三条件", res.stdout)
        self.assertIn("默认项", res.stdout, "卡片应提示 default_item（SCHEMAS §4 第 14 列）")

    def test_linkage_matrix_runs_on_example(self):
        data, _ = run_json("linkage_matrix.py", "--project", EXAMPLES)
        self.assertEqual(len(data["faces"]), 6)
        self.assertGreater(data["counts"]["must_features"], 0)
        for key in ("wired", "pending", "na", "no_entry"):
            self.assertIn(key, data["counts"])
        # 四者相加必须等于 功能数 × 6
        total = sum(data["counts"][k] for k in ("wired", "pending", "na", "no_entry"))
        self.assertEqual(total, data["counts"]["face_slots"],
                         "四态之和必须等于 功能数×六面，否则统计漏了")

    def test_parity_runs_on_example(self):
        data, _ = run_json("parity_score.py", "--project", EXAMPLES,
                           "--no-require-must", "--no-require-must")
        self.assertIn("feature_score", data)
        self.assertGreater(data["counted"], 0)


# --------------------------------------------------------------------------
# 6.6 skills/ 的 references 样例必须自身合法（不然是"教错的样板"）
# --------------------------------------------------------------------------

SKILLS = os.path.join(ROOT, "skills")
MENU_EXAMPLE = os.path.join(SKILLS, "replica-blueprint", "references", "menu-example.csv")
CONTRACT_EXAMPLE = os.path.join(SKILLS, "replica-blueprint", "references", "contract-example.md")
TARGET_CASE = os.path.join(SKILLS, "replica-local-source", "references", "target-case.md")


class TestSkillReferences(unittest.TestCase):
    def test_skill_frontmatter(self):
        """三个技能都必须有 name + description，且 description 够长（能命中触发词）。"""
        expected = {"replica-os", "replica-blueprint", "replica-local-source"}
        found = set()
        for name in expected:
            path = os.path.join(SKILLS, name, "SKILL.md")
            self.assertTrue(os.path.isfile(path), "缺 %s/SKILL.md" % name)
            text = slurp(path)
            self.assertTrue(text.startswith("---\n"), "%s 缺 frontmatter" % name)
            fm = text.split("---")[1]
            self.assertIn("name: %s" % name, fm)
            self.assertIn("description:", fm)
            self.assertGreater(len(fm), 150, "%s 的 description 太短，触发不稳" % name)
            self.assertGreater(len(text.splitlines()), 80, "%s 正文太短" % name)
            found.add(name)
        self.assertEqual(found, expected)

    def test_os_description_hits_clone_phrases(self):
        """主编排技能的 description 必须能命中中文"复刻/照着做/逆向"与英文 clone。"""
        fm = slurp(os.path.join(SKILLS, "replica-os", "SKILL.md")).split("---")[1]
        for phrase in ("复刻", "照着", "逆向", "clone"):
            self.assertIn(phrase, fm, "description 缺少触发词：%s" % phrase)

    @unittest.skipUnless(os.path.isfile(MENU_EXAMPLE), "menu-example.csv 不存在")
    def test_menu_example_is_valid_csv_and_walks_clean(self):
        """菜单样例必须是 15 列、能通过 menu_walk --check（否则是在教错的写法）。"""
        import tempfile
        tmp = tempfile.mkdtemp(prefix="menu-example-")
        try:
            os.makedirs(os.path.join(tmp, "BLUEPRINT"), exist_ok=True)
            shutil.copy(MENU_EXAMPLE, os.path.join(tmp, "BLUEPRINT", "menus.csv"))
            data, res = run_json("menu_walk.py", "--project", tmp)
            self.assertEqual(data["gap_count"], 0,
                             "菜单样例不应有缺项：%s" % data["gaps"][:3])
            self.assertEqual(data["problem_count"], 0,
                             "菜单样例不应有结构问题：%s" % data["problems"][:3])
            run_tool("menu_walk.py", "--project", tmp, "--check", expect=0)
            # 必须展示三条件分离与多层结构
            self.assertGreaterEqual(data["leaves"], 5)
            text = run_tool("menu_walk.py", "--project", tmp, "--tree").stdout
            self.assertIn("日期", text)
            self.assertIn("重复", text)
            self.assertIn("默认→", text, "样例应演示 default_item（与 checked_cond 区分）")
            cards = run_tool("menu_walk.py", "--project", tmp, "--cards").stdout
            self.assertIn("清除日期", cards)
            self.assertIn("可见但禁用", cards, "样例应演示「可见但禁用」这个关键区分")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    @unittest.skipUnless(os.path.isfile(CONTRACT_EXAMPLE), "contract-example.md 不存在")
    def test_contract_example_has_16_exact_sections(self):
        """契约样例必须 16 节逐字齐、且每节都有实质内容（不是占位）。"""
        text = slurp(CONTRACT_EXAMPLE)
        secs = rc.split_md_sections(text, level=2)
        self.assertEqual([s["title"] for s in secs], SECTION_TITLES)
        for sec in secs:
            lines = rc.body_text(sec["body"])
            self.assertFalse(rc.looks_placeholder(lines),
                             "样例第「%s」节只有占位" % sec["title"])

    @unittest.skipUnless(os.path.isfile(CONTRACT_EXAMPLE), "contract-example.md 不存在")
    def test_contract_example_passes_lint_alone(self):
        """把样例放进最小项目里跑 lint，不应报契约类 ERROR。"""
        import tempfile
        tmp = tempfile.mkdtemp(prefix="contract-example-")
        try:
            make_project(tmp, clean=True)
            shutil.copy(CONTRACT_EXAMPLE,
                        os.path.join(tmp, "BLUEPRINT", "contracts", "C-F-DATE-EDIT.md"))
            data, _ = run_json("blueprint_lint.py", "--project", tmp)
            bad = [f for f in data["findings"]
                   if f["level"] == "ERROR" and f["where"].startswith("BLUEPRINT/contracts/C-F-DATE-EDIT")]
            self.assertEqual(bad, [], "契约样例本身不该有 ERROR：%s"
                             % [f["code"] for f in bad])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    @unittest.skipUnless(os.path.isfile(TARGET_CASE), "target-case.md 不存在")
    def test_target_case_has_no_absolute_paths_or_fake_precision(self):
        """案例摘要不许写死本机绝对路径；引用数字必须带复算命令或出处。"""
        text = slurp(TARGET_CASE)
        self.assertNotIn("<home>", text, "案例里不许写死本机绝对路径")
        for word in ("复算", "出处"):
            self.assertIn(word, text, "案例应说明数字如何复核")
        # 48 位掩码这条是硬坑，必须写
        self.assertIn("0x0000FFFFFFFFFFFF", text)


# --------------------------------------------------------------------------
# 6.7 六面定义单一事实来源（shared/faces.json）—— 防"改一处、另一处漂移"
# --------------------------------------------------------------------------

FACES_JSON = os.path.join(ROOT, "shared", "faces.json")


@unittest.skipUnless(os.path.isfile(FACES_JSON), "shared/faces.json 不存在")
class TestFacesSingleSource(unittest.TestCase):
    """六面的关键词只能有一份：shared/faces.json。

    gates 与 tools 都从它读；任何一侧内联关键词列表都会随它漂移。
    """

    def setUp(self):
        with open(FACES_JSON, encoding="utf-8") as fh:
            self.raw = json.load(fh)
        self.ref = self.raw["faces"]

    def test_json_shape(self):
        self.assertEqual(len(self.ref), 6, "六面必须是 6 个")
        for f in self.ref:
            for key in ("key", "name", "desc", "keywords"):
                self.assertIn(key, f, "六面项缺字段 %s" % key)
            self.assertTrue(f["keywords"], "%s 的 keywords 不能为空" % f["key"])

    def test_linkage_matrix_reads_json(self):
        """linkage_matrix.DEFAULT_FACES 必须与 JSON 逐字段相等（不是近似）。"""
        mod = load_tool("linkage_matrix.py")
        got = [(f["key"], f["name"], tuple(f["keywords"])) for f in mod.DEFAULT_FACES]
        want = [(f["key"], f["name"], tuple(f["keywords"])) for f in self.ref]
        self.assertEqual(got, want, "工具读到 ≠ shared/faces.json：改关键词只改 JSON")

    def test_classify_uses_json_keywords_not_inline(self):
        """classify() 的命中必须来自 JSON：临时改 JSON 里的关键词，归类结果要跟着变。"""
        mod = load_tool("linkage_matrix.py")
        faces = [dict(f) for f in self.ref]
        target = faces[0]["key"]
        probe = "一个JSON里没有的词"
        self.assertEqual(mod.classify(probe, faces), [], "探针词不该命中任何面")
        faces[0]["keywords"] = list(faces[0]["keywords"]) + [probe]
        self.assertEqual(mod.classify(probe, faces), [target],
                         "改了 keywords 就该命中——说明 classify 用的是传入的定义而不是内联常量")

    def test_no_inline_keyword_list_in_classify_body(self):
        """classify() 函数体里不许出现关键词字面量（只许遍历 faces）。"""
        import inspect
        mod = load_tool("linkage_matrix.py")
        src = inspect.getsource(mod.classify)
        # 允许出现「#」「name」「key」「keywords」这些结构词，但不许出现具体关键词
        for kw in ("徽标", "角标", "时间轴", "检索", "闹钟"):
            self.assertNotIn(kw, src, "classify() 里出现了内联关键词「%s」" % kw)

    def test_config_accepts_ssobject_form(self):
        """--config 必须接受 shared/faces.json 本身的 {"faces":[...]} 形态。

        早期只收数组，导致"拿 SSOT 文件喂给工具居然报错"，是自相矛盾。
        """
        p = os.path.join(ROOT, "examples", "scheduling-clone")
        if not os.path.isdir(p):
            self.skipTest("examples 不存在")
        run_tool("linkage_matrix.py", "--project", p, "--config", FACES_JSON, expect=0)
        data, _ = run_json("linkage_matrix.py", "--project", p, "--config", FACES_JSON)
        self.assertEqual([f["name"] for f in data["faces"]],
                         [f["name"] for f in self.ref])

    def test_replica_common_reads_same_json(self):
        """replica_common 的六面名也必须来自 JSON（提示文案里不再手写）。"""
        self.assertEqual(rc.face_names(), [f["name"] for f in self.ref])
        brief = rc.faces_brief()
        for f in self.ref:
            self.assertIn(f["name"], brief)

    def test_changing_json_changes_tool_output(self):
        """改 JSON 一处 → 工具的 --dump-config 跟着变（真·单一来源）。"""
        tmp = tempfile.mkdtemp(prefix="faces-ssot-")
        try:
            mutated = json.loads(json.dumps(self.raw))
            mutated["faces"][0]["name"] = "主列表改名X"
            path = os.path.join(tmp, "faces.json")
            write_text(path, json.dumps(mutated, ensure_ascii=False))
            # 用 --config 局部覆盖来验证同一读取路径（需要真实项目的表）
            proj = os.path.join(ROOT, "examples", "scheduling-clone")
            if not os.path.isdir(proj):
                self.skipTest("examples 不存在")
            data, _ = run_json("linkage_matrix.py", "--project", proj,
                               "--config", path)
            self.assertEqual(data["faces"][0]["name"], "主列表改名X")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_help_does_not_hardcode_face_names(self):
        """--help 里不许写死六面名（否则改 JSON 后帮助文本会说谎）。"""
        res = run_tool("linkage_matrix.py", "--help", expect=0)
        self.assertIn("shared/faces.json", res.stdout,
                      "帮助里应指明六面定义来自 shared/faces.json")
        self.assertNotIn("主列表/角标/详情/日历/搜索/提醒", res.stdout,
                         "--help 不该内联六面名列表")

    def test_docstring_points_to_ssot(self):
        """模块 docstring 必须指向 SSOT，而不是自己列一份六面表。"""
        mod = load_tool("linkage_matrix.py")
        doc = mod.__doc__ or ""
        self.assertIn("shared/faces.json", doc)
        self.assertNotIn("主列表 / 角标计数 / 详情面板", doc,
                         "docstring 不该再手写六面表")


# --------------------------------------------------------------------------
# 7. 跨工具一致性（同一份夹具，各工具结论不矛盾）
# --------------------------------------------------------------------------

class TestCrossTool(TmpCase):
    def test_all_tools_run_on_same_project(self):
        p = self.project(clean=True)
        lint, _ = run_json("blueprint_lint.py", "--project", p, expect=0)
        menu, _ = run_json("menu_walk.py", "--project", p)
        link, _ = run_json("linkage_matrix.py", "--project", p)
        par, _ = run_json("parity_score.py", "--project", p, "--no-require-must")
        self.assertTrue(lint["clean"])
        self.assertEqual(menu["gap_count"], 0)
        self.assertEqual(link["counts"]["must_features"], 2)
        self.assertEqual(par["must_have_total"], 2)

    def test_json_contract_has_result_marker(self):
        p = self.project(clean=True)
        for name, args in (("blueprint_lint.py", ["--project", p]),
                           ("menu_walk.py", ["--project", p]),
                           ("linkage_matrix.py", ["--project", p]),
                           ("parity_score.py", ["--project", p, "--no-require-must"]),
                           ("evidence_manifest.py", ["--project", p])):
            data, _ = run_json(name, *args)
            self.assertIn("__RESULT__", data, "%s 的 --json 应带 __RESULT__ 末行" % name)
            self.assertIn("tool", data)


if __name__ == "__main__":
    unittest.main(verbosity=2)
