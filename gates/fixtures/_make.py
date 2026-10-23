#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""夹具生成器 —— 可重复生成 good-min 与 4 套 broken 夹具，并批量重算冻结哈希。

为什么要有它（而不是手写夹具）：
1. BLUEPRINT-LOCK.md 里有 11 个 64 位 SHA-256，手写必然写错；G3 是"实算比对"门，
   手写哈希的夹具永远不可能 PASS。
2. 夹具是自测基线，必须能被一键重建 → 内容确定（无随机、无当前时间）。

用法：
    python3 gates/fixtures/_make.py                 # 重建全部夹具（good + 4 个 broken）
    python3 gates/fixtures/_make.py good            # 只重建 good-min
    python3 gates/fixtures/_make.py broken          # 只重建 4 套 broken（依赖 good-min）
    python3 gates/fixtures/_make.py lock <项目目录>  # 只重算该项目的 BLUEPRINT-LOCK.md 哈希
    python3 gates/fixtures/_make.py --check         # 校验磁盘上的夹具与生成器一致（CI 用）

生成物（全部在 gates/fixtures/ 下）：
    good-min/           完整最小项目，全门 PASS（唯一 NA：G11.commercial，档位 A）
    broken-blueprint/   契约缺 2 节 + 菜单条件写「按原版」+ 缺 unknowns.csv
    broken-linkage/     progress=yes 但 linkage 仍是 pending
    broken-lock/        蓝图文件改动后未更新 BLUEPRINT-LOCK 哈希
    no-manifest/        只有目录没有 manifest → 全部 BLOCKED
"""

from __future__ import annotations

import base64
import csv
import hashlib
import io
import os
import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
GATES_DIR = HERE.parent
SYSTEM_ROOT = GATES_DIR.parent
if str(GATES_DIR) not in sys.path:
    sys.path.insert(0, str(GATES_DIR))

from rules import common as C  # noqa: E402

LOCK_VERSION = "v1.1"
LOCK_TIME = "2026-10-23T10:40+08:00"
LOCK_CONFIRMER = "Wayen"

# 1x1 透明 PNG：夹具里的「截图」用真实 PNG 字节，避免门禁把证据误判为文本占位
PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFAAH/"
    "q842iQAAAABJRU5ErkJggg=="
)


# ---------------------------------------------------------------------------
# 写盘工具
# ---------------------------------------------------------------------------

def w(root, rel, text, mode=0o644):
    p = Path(root) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    data = text.encode("utf-8") if isinstance(text, str) else text
    p.write_bytes(data)
    os.chmod(str(p), mode)
    return p


def csv_text(header, rows):
    buf = io.StringIO(newline="")
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(header)
    for row in rows:
        writer.writerow(row)
    return buf.getvalue()


def sha256(rel, root):
    return hashlib.sha256((Path(root) / rel).read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# good-min 内容
# ---------------------------------------------------------------------------

MANIFEST = """\
# 门禁清单（唯一配置来源）· 格式见 templates/blueprint/SCHEMAS.md §15
project: good-min
tier: A                          # A 本地自用 | B 半自用 | C 商业
target: "目标应用 8.x"
baseline_commit: "a1b2c3d"
created_at: "2026-10-20T09:00+08:00"

thresholds:
  parity_feature: 80             # G9 功能分下限
  consecutive_runs: 3            # G8 连跑次数

required:
  evidence_dirs: [evidence, screens]
  contract_sections: 16
  vertical_slice_evidence: SPEC/vertical-slice.md
  start_script: scripts/start.sh
  runbook: REPORT/release/local-runbook.md
  restore_drill: REPORT/release/restore-drill.md
  parity_report: REPORT/parity.md
  feedback_report: REPORT/feedback.md
  flush_result_symbol: FlushResult

# 经批准的 N/A（G3 之后不许新增；R20）
na_approved:
  - id: G11.commercial
    reason: "A 档本地自用，不做商店合规与品牌清扫"
    approved_by: Wayen
    approved_at: "2026-10-23T10:40+08:00"
"""

PROJECT_MD = """\
# good-min · 日期型任务桌面重建（夹具）

> 这是门禁自测用的最小完整项目。所有内容都是**可复算的示例**，不是真实产品。

## 一句话定位
为像我这样的个人用户，把手机上的日期型任务在桌面端本地重建，做到功能等价、数据自有、断网可用。

## 档位
档位：A（本地自用，不外发，无需品牌清扫与商店合规）

## 目标制品
| 项 | 值 |
|---|---|
| 名称 | 目标应用 |
| 版本 | 8.x |
| 平台形态 | 本地 App（单机 + 本地库） |
| 获取方式 | 本机已安装副本，只读复制 |
| SHA-256 | 3f786850e387550fdab836ed7e6dc881de23001b8fa1cd12bb0fd9dde0e6b4b1 |
| 取证日期 | 2026-10-20 |
| 档位 | A |

## 不做清单
1. 不做云端同步与账号体系（本版只单机）
2. 不做共享日历与协作邀请
3. 不做移动端 App，只做桌面端
4. 不做付费订阅与支付
5. 不做品牌视觉重设计（沿用中性灰蓝，不搬运原版素材）
6. 不做多语言，只中文

## 这一版做什么
- 任务的日期/时间修改（含全天切换）
- 重复规则设置与清除（工作日 / 每周 / 自定义）
- 主列表、详情、日历三个面的联动刷新

## 交付判定
功能分 ≥80 且 must 功能全绿；界面分单独记录，不参与抵消。
"""

DECISIONS_MD = """\
# DECISIONS —— 决策台账

> 只追加，不改行。决策被推翻时新增一行写「推翻 D-00x，原因」，旧行保留。

## 用法
- 每条必须有：编号、日期（ISO 8601）、决策内容、理由、影响面。
- 决策表是唯一被 G0 统计的地方（「实例」章节的示例行不计入）。

## 决策表

| ID | 日期 | 决策 | 理由 | 影响面 | 状态 |
|---|---|---|---|---|---|
| D-001 | 2026-10-20T09:30+08:00 | 本项目定 A 档（本地自用），只做桌面端单机，不做云端 | 只有我一个人用、不进商店、出问题自己承担、不切品牌资产 | `PROJECT.md`、manifest `tier: A` | 已定 |
| D-002 | 2026-10-20T10:10+08:00 | 复刻对象锁定 目标应用 8.x | 该版本是本机在用版本，且已取到完整制品身份（SHA-256 已入 evidence） | `PROJECT.md` 目标制品、`evidence/notes-2026-10-20.md` | 已定 |
| D-003 | 2026-10-20T10:40+08:00 | 数据层用本地 SQLite 单文件（WAL 模式） | 真文件可做重启读回测试（R4），无需服务端，且单用户无并发冲突 | `SPEC/schema.sql`、S7 数据层、G7 | 已定 |
| D-004 | 2026-10-22T19:00+08:00 | 接受 U-002 的风险：本版不支持「每月第 N 周」重复规则 | 该规则使用率低（样本内 4/42 提及），本版不做；产品官批准记 accepted-risk | `F-REPEAT-SET` 范围、`BLUEPRINT/unknowns.csv` U-002 | 已定 |

## 待决项（Open Questions）

| # | 问题 | 谁来定 | 截止 |
|---|---|---|---|
| Q1 | 提醒时区口径（U-001） | 产品官 | G3 冻结前 |
"""

REDLINES_MD = """\
# 质量红线（R 编号以 00-体系总纲.md §9 为唯一权威）

| 编号 | 红线 | 本项目怎么落地 |
|---|---|---|
| R1 | 不得用 sleep / 固定延时等待异步完成 | 等待一律用完成信号（FlushResult / await），测试里 grep 不到 sleep |
| R2 | 影响持久状态的异步写必须进串行链，并暴露可 await 的完成信号 | 写队列单线程串行，每条命令带不可变 entityId + revision |
| R3 | 关窗/退出前必须冲刷，且冲刷返回结构化结果 | flush() 返回 FlushResult{ok|unknown|error}，关窗流程消费它 |
| R4 | 持久化测试用真文件，禁内存库；断言查具体值 | tests 用 tempfile.mkdtemp() 下的真 SQLite 文件，断言 dueDate == 具体值 |
| R5 | 全量测试连跑 ≥3 次 | TEST/results 存 3 份连续结果，G8 校验 |
| R6 | 构建 0 错误 0 警告 | 构建日志进 BUILD/build-log.md |
| R7 | 不许注释掉报错来"通过" | 门禁扫 src 无 TODO/FIXME；不许改断言 |
| R8 | 不许空壳实现 | 每个命令有实现与测试；空壳函数体进评审清单 |
| R9 | 反编译/还原代码只当规格书读，不编入产品 | 只读证据在 evidence/，src 全部自己写 |
| R10 | 不破坏已通过的功能 | 改一处跑全量回归（3 次连跑） |
| R11 | 不能写成数值或步骤的体验要求 = 无效要求 | 契约 §15 写点击数、焦点、动效时长 |
| R12 | 性能必须带口径 | 契约给起点/终点/环境与 p50-p95 |
| R13 | catch 不得全吞异常 | 至少留脱敏日志与错误码 |
| R14 | 启动期做"声称 vs 实际"自检 | 启动自检建表数、索引数、PRAGMA foreign_keys 实测值 |
| R15 | 引用用可 grep 的文本锚点 | 证据写 文件:行 + baseline commit a1b2c3d |
| R16 | 只改必须改的 | 变更单 + 影响面清单 |
| R17 | 踩坑库每条标「当前是否已修」+ 时间 | 见 REPORT/feedback.md 与案例层 |
| R18 | 页面完成不等于功能完成 | 六面联动 + G6 门（linkage wired + 测试 pass） |
| R19 | 不得用 A || B 式或放行 | 断言取合取：数据落库 与 冲刷结果 都要满足 |
| R20 | BLOCKED 不得当 PASS；N/A 必须带理由 | 唯一 NA（G11.commercial）在 manifest.na_approved 登记 |
"""

AGENTS_MD = """\
# AI 执行约束（谁都不能越）

## 写作用域
- 一张任务卡写死允许改的路径；一个文件一个 owner。
- 蓝图（BLUEPRINT/）在 G3 冻结后只读；改动必须走 BLUEPRINT/CHANGES/ 变更单。

## 禁止事项
1. 不许改契约、改测试断言来让门变绿（R7）。
2. 不许把 BLOCKED 当 PASS，不许新增未登记的 N/A（R20）。
3. 不许把推测写成实测：关于原版的断言必须指到 S-xx / M-xx / 证据文件（R15）。
4. 不许自批验收：实现者与验证者必须是不同上下文（A 档串行时标「自复验（独立性未满足）」）。
5. 不许顺手优化邻近代码（R16）。

## 汇报格式（缺项视为未完成）
状态 / 产出（路径清单）/ 证据（命令 + 关键输出）/ 我跑过的验证（测试名 + 结果 + 次数）/ 存疑 / 影响面
"""

STATE_MD = """\
# 状态台账（唯一现状来源）

| ID | 类型 | 名称 | 当前态 | 证据路径 | 最后更新 | 负责人 |
|---|---|---|---|---|---|---|
| F-DATE-EDIT | feature | 修改任务的日期与时间 | VERIFIED | TEST/results/2026-10-23-run3.json | 2026-10-23T11:20+08:00 | lead |
| F-REPEAT-SET | feature | 设置与清除重复规则 | VERIFIED | TEST/results/2026-10-23-run3.json | 2026-10-23T11:20+08:00 | lead |
| F-SYNC-CLOUD | feature | 同步到云端账号 | DRAFT | - | 2026-10-23T11:20+08:00 | lead |
| C-F-DATE-EDIT | contract | 日期修改契约 | APPROVED | BLUEPRINT/contracts/C-F-DATE-EDIT.md | 2026-10-22T19:00+08:00 | 产品官 |
| C-F-REPEAT | contract | 重复规则契约 | APPROVED | BLUEPRINT/contracts/C-F-REPEAT.md | 2026-10-22T19:00+08:00 | 产品官 |
"""

RECON_MD = """\
# recon · 目标应用 8.x

## 1 目标制品与身份
| 项 | 值 |
|---|---|
| 名称 | 目标应用 |
| 版本 | 8.x |
| 平台形态 | 桌面客户端 + 本地数据库 |
| 获取方式 | 本机已安装副本只读复制到 evidence/ |
| SHA-256 | 3f786850e387550fdab836ed7e6dc881de23001b8fa1cd12bb0fd9dde0e6b4b1 |
| 取证日期 | 2026-10-20 |
| 档位 | A |

## 2 信息架构（屏幕树）
| 屏幕 | 名称 | 父子关系 |
|---|---|---|
| S-01 | 主列表 | 根 |
| S-02 | 任务详情 | S-01 展开 / 点击行 |
| S-03 | 日历视图 | 根 |
| S-04 | 设置 | 根 |

## 3 全部入口清单
- 窗口菜单栏：文件 / 编辑 / 视图 / 帮助
- 托盘图标：快速添加、今日清单
- 快捷键：⌘N 新建、⌘D 日期菜单、⌘⇧W 每周工作日
- URL 深链：`targetapp://task/<id>`

## 4 核心用户流程
| 流程 | 屏幕序列 | 点击数（happy path） |
|---|---|---|
| FL-01 修改任务日期 | S-01 → 行右键 → 日期菜单 → 选择 | 3 |
| FL-02 设置重复规则 | S-02 → 重复菜单 → 每周工作日 | 2 |

## 5 模块与依赖关系
- 任务仓储（repository） → 任务模型（TaskModel） → 视图模型（ViewModel） → 屏（Screens）
- 依赖方向单一向下；视图不直接访问数据库

## 6 数据模型概览
- TaskModel（任务）、Reminder（提醒）；字段明细见 data-dictionary.md

## 7 可见区域与不可见区域
看不到的部分：服务端同步实现、付费订阅逻辑、硬件相关提醒投递。

## 8 未知与待验项
与 unknowns.csv 一一对应：U-001（提醒时区口径）、U-002（每月第 N 周）。

## 9 证据索引
| 证据文件 | 采集方式 | 采集时间 |
|---|---|---|
| screens/S01-date-menu.png | 截图（窗口级） | 2026-10-20T09:12+08:00 |
| screens/S02-repeat-menu.png | 截图（窗口级） | 2026-10-20T09:18+08:00 |
| evidence/notes-2026-10-20.md | 手工观察记录 | 2026-10-20T09:30+08:00 |

## 10 规模判断与建议
S 规模（2 个 must 功能、4 个屏）。最难三处：菜单三条件分离、重复规则与日历联动、退出冲刷。
"""

FEATURE_ROWS = [
    ["feature_id", "feature", "area", "priority", "scope", "original", "progress",
     "contract_ref", "acceptance_ref", "evidence", "notes"],
    ["F-DATE-EDIT", "修改任务的日期与时间", "S-01-主列表", "must", "in", "yes", "yes",
     "contracts/C-F-DATE-EDIT.md", "T-101", "screens/S01-date-menu.png", "-"],
    ["F-REPEAT-SET", "设置与清除重复规则", "S-02-任务详情", "must", "in", "yes", "yes",
     "contracts/C-F-REPEAT.md", "T-102", "screens/S02-repeat-menu.png", "-"],
    ["F-SYNC-CLOUD", "同步到云端账号", "S-04-设置", "could", "in", "yes", "no",
     "-", "-", "screens/S04-sync.png", "could 级，本版不做，见 REPORT/parity.md 缺失清单"],
]

SCREEN_ROWS = [
    ["screen_id", "name", "entry", "exits", "purpose", "key_components",
     "state_filled", "state_empty", "state_loading", "state_error", "state_permission",
     "focus_restore", "flows", "notes"],
    ["S-01", "主列表", "启动默认屏 / ⌘1", "Esc 或切换到其它屏", "浏览与勾选任务",
     "任务行,日期徽标,筛选条", "yes", "yes", "yes", "yes", "yes",
     "返回时恢复滚动位置与选中行；行被筛选移出则焦点落下一行", "FL-01;FL-02", "-"],
    ["S-02", "任务详情", "主列表点击行 / ⌘D", "返回主列表 / Esc", "查看与编辑单个任务",
     "标题,日期,重复,提醒", "yes", "yes", "yes", "yes", "-",
     "返回后焦点回到触发的输入框", "FL-01;FL-02", "无权限态不适用：单用户本地库，全部可写"],
    ["S-03", "日历视图", "⌘2 / 侧栏", "切回列表", "按日期看任务分布",
     "月网格,日期格,任务条", "yes", "yes", "yes", "yes", "-",
     "返回时保持当前月与选中日", "FL-02", "无权限态不适用：单用户本地库"],
    ["S-04", "设置", "⌘,", "关闭窗口", "调整主题与启动行为",
     "主题选择,启动行为,关于", "yes", "yes", "yes", "yes", "yes",
     "返回时恢复上次停留的分节", "-", "-"],
]

MENU_ROWS = [
    # 15 列（SCHEMAS §4）：… contract_ref, screens, default_item, notes
    ["node_id", "parent_id", "path", "order", "type", "label", "shortcut",
     "visibility_cond", "enabled_cond", "checked_cond", "command", "contract_ref",
     "screens", "default_item", "notes"],
    ["M-DATE", "ROOT", "日期", "1", "submenu", "日期", "⌘D",
     "详情面板可见时出现；只读分享视图隐藏（隐藏后布局不留空位，焦点交给标题输入框）",
     "需有可写权限；退出冲刷阶段整段菜单禁用并显示「正在保存」",
     "子菜单无自身选中态，当前值由 detail.dueDate 草稿决定",
     "Cmd.OpenDateMenu", "contracts/C-F-DATE-EDIT.md", "S-02", "M-DATE-TODAY",
     "顶层子菜单；每次打开都把焦点放在「今天」"],
    ["M-DATE-TODAY", "M-DATE", "日期 › 今天", "1", "action", "今天", "⌘T",
     "始终可见", "始终可用（有选中任务）",
     "不是选中态，选择后收起菜单并把 dueDate 置为今天",
     "Cmd.SetDateToday", "contracts/C-F-DATE-EDIT.md", "S-02", "-", "快捷项"],
    ["M-DATE-TOMORROW", "M-DATE", "日期 › 明天", "2", "action", "明天", "⌘M",
     "始终可见", "始终可用（有选中任务）",
     "不是选中态，选择后收起菜单并把 dueDate 置为次日",
     "Cmd.SetDateTomorrow", "contracts/C-F-DATE-EDIT.md", "S-02", "-", "快捷项"],
    ["M-DATE-SEP-1", "M-DATE", "日期 › 分隔线", "3", "separator", "——", "-",
     "始终可见", "-", "-", "-", "-", "S-02", "-", "纯分隔线，无行为"],
    ["M-DATE-CUSTOM", "M-DATE", "日期 › 自定义…", "4", "action", "自定义…", "⌘⇧D",
     "始终可见", "需有可写权限；同步写入中禁用并提示「保存中」",
     "草稿值由打开的日期浮层决定，浮层关闭后以提交值为准",
     "Cmd.OpenDatePicker", "contracts/C-F-DATE-EDIT.md", "S-02", "-", "打开浮层"],
    ["M-REPEAT", "ROOT", "重复", "2", "submenu", "重复", "-",
     "重复功能已开启时出现；关闭时整段隐藏，菜单高度自动减少一行",
     "需有可写权限；退出冲刷阶段禁用",
     "子菜单无自身选中态，由 repeat.enabled 决定是否显示勾",
     "Cmd.OpenRepeatMenu", "contracts/C-F-REPEAT.md", "S-02", "M-REPEAT-NONE",
     "顶层子菜单；默认高亮「不重复」"],
    ["M-REPEAT-NONE", "M-REPEAT", "重复 › 不重复", "1", "radio", "不重复", "-",
     "始终可见", "始终可用",
     "repeat.rule 为空或 'NONE' 时选中",
     "Cmd.ClearRepeat", "contracts/C-F-REPEAT.md", "S-02", "-", "清除项"],
    ["M-REPEAT-WEEKLY", "M-REPEAT", "重复 › 每周工作日", "2", "radio", "每周工作日", "⌘⇧W",
     "repeat.rule 为 WEEKLY 时高亮；其余规则下仍显示但不高亮",
     "需有可写权限；云端同步中禁用并提示「同步中」",
     "repeat.rule == 'WEEKLY' 且 repeat.byday 覆盖周一至周五",
     "Cmd.SetRepeatWeeklyWorkdays", "contracts/C-F-REPEAT.md", "S-02", "-", "常用项"],
    ["M-REPEAT-CUSTOM", "M-REPEAT", "重复 › 自定义…", "3", "action", "自定义…", "-",
     "始终可见", "需有可写权限",
     "repeat.rule 为 CUSTOM 时右侧显示勾；否则显示箭头",
     "Cmd.OpenRepeatCustom", "contracts/C-F-REPEAT.md", "S-02", "-", "打开浮层"],
    ["M-REPEAT-LABEL-1", "M-REPEAT", "重复 › 频率", "4", "label", "频率", "-",
     "-", "-", "-", "-", "-", "S-02", "-", "分组说明文字，不可点击"],
]

LINKAGE_ROWS = [
    ["link_id", "source_id", "event", "affected_screen", "affected_control", "data",
     "refresh_timing", "state_handling", "test_ref", "status"],
    ["LK-001", "F-DATE-EDIT", "TaskDateChanged{taskId}", "S-01",
     "主列表行日期徽标与「今天/明天」相对文案", "TaskModel.dueDate",
     "写入事务提交成功后同步刷新（同一事务内广播事件）",
     "保留选中行与滚动位置；行因新日期移出筛选结果时焦点落到下一行", "T-101", "wired"],
    ["LK-002", "F-DATE-EDIT", "TaskDateChanged{taskId}", "S-02",
     "详情面板日期字段与全天开关", "TaskModel.dueDate",
     "事件广播后同屏就地更新，不重新挂载面板",
     "保留输入焦点与光标位置；正在编辑的其它字段不清空", "T-101", "wired"],
    ["LK-003", "F-REPEAT-SET", "TaskRepeatChanged{taskId}", "S-01",
     "主列表重复图标与「下次发生」日期", "TaskModel.repeat",
     "写入事务提交成功后重算下次发生并刷新该行",
     "保留滚动位置；图标区域的悬停态重置", "T-102", "wired"],
    ["LK-004", "F-REPEAT-SET", "TaskRepeatChanged{taskId}", "S-03",
     "日历视图重复标记与展开实例", "TaskModel.repeat",
     "事件广播后重算当前可见月份的实例（含跨月边界）",
     "保留当前月与选中日；展开的实例列表保持展开", "T-102", "wired"],
    # 一条合法的 na 行：确认「搜索面」不受影响。用来证明 na 不是漏写，
    # 而是「想过之后确认不适用」，且 test_ref 允许为 `-`（SCHEMAS §5）。
    ["LK-005", "F-REPEAT-SET", "TaskRepeatChanged{taskId}", "S-01",
     "不适用：搜索结果只按标题与备注命中，重复规则不参与索引",
     "TaskModel.repeat",
     "不适用：搜索索引不订阅重复规则变更",
     "不适用：确认搜索结果不因重复规则变化而改变，保留当前查询与滚动位置",
     "-", "na"],
]

UNKNOWN_ROWS = [
    ["unknown_id", "area", "description", "impact", "evidence_gap",
     "verification_action", "owner", "blocking", "status"],
    ["U-001", "S-02-任务详情",
     "提醒时间的时区口径：原版按设备本地时区还是按任务创建时时区计算",
     "F-DATE-EDIT 的提醒时刻、LK-004 日历实例时间",
     "缺少跨时区切换前后的提醒投递记录",
     "把系统时区从 +08:00 改到 +09:00，新建一条 09:00 提醒并观察投递时刻，记入 evidence/notes-2026-10-21.md",
     "blueprint-smith", "no", "open"],
    ["U-002", "M-REPEAT-自定义",
     "原版「每月第 N 周」规则在自定义浮层里是否存在",
     "F-REPEAT-SET 的自定义分支",
     "自定义浮层截图只覆盖了按周维度，未见按月维度入口",
     "在自定义浮层展开「按月」分组并截图；若原版无此层，记 DECISIONS.md 的 D-003",
     "product-owner", "no", "accepted-risk"],
]

CONTRACT_SECTIONS = [
    "1 目标与入口", "2 界面与层级", "3 每个菜单选项", "4 显示条件",
    "5 可用与选择条件", "6 筛选条件", "7 业务实现逻辑", "8 具体效果",
    "9 状态变化", "10 数据读取", "11 数据写入", "12 跨页面联动",
    "13 并发与生命周期", "14 撤销与恢复", "15 体验标准", "16 测试与证据",
]


def contract_text(fid, name, menu_path, command, field, extra_screens,
                  lk_ids, test_ids, summary):
    """生成 16 节契约（每节都写实内容，自然超过 20 字）。"""
    lk = "、".join(lk_ids)
    tests = "、".join(test_ids)
    screens = "、".join(extra_screens)
    body = {
        "1 目标与入口": (
            "用户意图：%s，改完立即在其他屏看到结果，不刷新页面。\n"
            "- 主入口：%s（命令 `%s`）\n"
            "- 替代入口：行右键菜单、快捷键 `⌘D`、拖拽到日历某天\n"
            "- 前置上下文：必须已有 1 条选中任务且在可写库中；无选中时入口整条禁用并提示「先选择任务」\n"
            % (name, menu_path, command)
        ),
        "2 界面与层级": (
            "控件顺序：标题输入框 → 日期行 → 重复行 → 提醒行 → 备注。\n"
            "- 日期行点击后弹出浮层（320×380，贴住触发元素右下角，空间不足时翻转向上）\n"
            "- 浮层内可滚动区为规则列表；底部固定「清除」与「确定」两个按钮\n"
            "- 尺寸策略：浮层最小宽度 280，最大高度不超过窗口高度减 48\n"
        ),
        "3 每个菜单选项": (
            "逐叶列全（对应 menus.csv 的 M-DATE 整棵子树）：\n"
            "| 路径 | 类型 | 默认/当前项 | 打开关闭行为 |\n"
            "|---|---|---|---|\n"
            "| %s | 子菜单 | 无默认项 | 悬停 120ms 展开，点击保持打开 |\n"
            "| %s › 今天 | 动作 | 无选中态 | 点击后收起并把日期置为今天 |\n"
            "| %s › 明天 | 动作 | 无选中态 | 点击后收起并把日期置为次日 |\n"
            "| %s › 自定义… | 动作 | 无选中态 | 打开日期浮层，浮层关闭后以提交值为准 |\n"
            "- 鼠标跨层：移出子菜单 400ms 后收起，斜向移动穿透一层\n"
            "- 键盘：↑↓ 移动、→ 展开子菜单、← 收起、Enter 执行、Esc 关闭并还原草稿\n"
            % (menu_path, menu_path, menu_path, menu_path)
        ),
        "4 显示条件": (
            "出现条件：详情面板可见 且 当前任务在可写库中。\n"
            "- 只读分享视图下整段隐藏，隐藏后菜单高度自动减少一行，不留空位\n"
            "- 隐藏时焦点交给标题输入框，关闭浮层后焦点回到触发元素\n"
        ),
        "5 可用与选择条件": (
            "可用 ≠ 已选中，两者分开实现：\n"
            "- 可用条件：library.writable == true 且 flush.state != busy\n"
            "- 禁用解释：不可用时整段灰化并在 tooltip 显示「正在保存，稍后可用」\n"
            "- 互斥与组合：单选规则（今天/明天/自定义）互斥；周维度可多选 byday\n"
            "- 最大选择数：byday 最多 7 个；取消选择即退出该规则\n"
            "- 选中态来源：菜单勾选由数据库持久值决定；浮层内由草稿值决定，提交后才写库\n"
        ),
        "6 筛选条件": (
            "无 AND/OR 嵌套；筛选只影响主列表可见行，不影响统计口径。\n"
            "- 空值：dueDate 为空的任务不进入「今天/明天」筛选结果\n"
            "- 边界日期：跨月、闰日、时区变更按设备本地时区归一后比较\n"
            "- 排序：先按 dueDate 升序，同日期按创建时间降序\n"
            "- 角标统计口径：未完成且 dueDate <= 今天 24:00 的任务数\n"
        ),
        "7 业务实现逻辑": (
            "规则求值顺序：校验 → 归一化日期 → 计算重复实例 → 写库 → 广播事件 → 刷新受影响面。\n"
            "- 默认规则：未指定时间时取 09:00 本地时间\n"
            "- 参数：{taskId, dueDate|'YYYY-MM-DD', allDay:boolean, revision}\n"
            "- 校验：revision 必须等于当前库中 revision，否则拒绝并提示冲突\n"
            "- 算法边界：不调用外部服务；重复实例只在可见窗口内展开\n"
        ),
        "8 具体效果": (
            "可复算的效果描述：\n"
            "- 选中 dueDate=2026-10-24 的任务点「明天」→ 主列表该行徽标从「今天」变「明天」\n"
            "- 详情面板日期字段立即显示 2026-10-24，聚焦状态与光标位置不变\n"
            "- 日历视图该任务从 10-23 格移到 10-24 格，格内计数 +1/-1\n"
            "- 提示条「已改为明天」显示 2.5 秒后淡出，不抢焦点\n"
        ),
        "9 状态变化": (
            "原状态 → 事件 → 条件 → 目标状态 → 副作用：\n"
            "- idle → SUBMITTING（提交）→ 成功 → idle，副作用：广播 TaskDateChanged\n"
            "- SUBMITTING → 失败 → error（保留草稿），副作用：显示重试按钮\n"
            "- SUBMITTING → 冲突 → conflict（不覆盖），副作用：提示「已在别处修改」\n"
            "- 失败与冲突都不清空草稿；重试成功后回到 idle\n"
        ),
        "10 数据读取": (
            "实体与字段：%s（见 data-dictionary.md E01）。\n"
            "- 查询条件：按 taskId 主键读取，附 revision\n"
            "- 派生值：相对文案（今天/明天/逾期 N 天）由 dueDate 与设备当前日期算出\n"
            "- 数据新鲜度：读取走同一连接，写入后立即可见（WAL 模式下同连接一致性）\n"
            "- 空库行为：空库时主列表显示空态而不是错误；异常库时给出可操作的提示\n"
            % field
        ),
        "11 数据写入": (
            "命令与参数：`%s{taskId, patch, revision}`。\n"
            "- 精确字段：只写 %s、updatedAt、revision 三个字段，其余字段必须保持不变\n"
            "- 事务范围：单行更新在单个事务内完成；事务提交成功后才广播事件\n"
            "- 完成信号：返回 FlushResult{ok|unknown|error}，调用方 await 它\n"
            "- 失败保留：写失败不丢草稿，草稿留在内存并由重试按钮重新提交\n"
            % (command, field)
        ),
        "12 跨页面联动": (
            "六个面逐个交代（对应 linkage.csv 的 %s）：\n"
            "- 主列表：行徽标与相对文案，事务提交成功后同步刷新\n"
            "- 角标计数：重算未完成且到期数，事件广播后刷新\n"
            "- 详情面板：同屏就地更新，不重新挂载\n"
            "- 日历视图：重算可见窗口内的实例位置\n"
            "- 搜索结果：重跑当前查询前缀，保留高亮位置\n"
            "- 提醒调度：取消旧提醒、注册新提醒，注册失败要显式记失败而不是静默\n"
            % lk
        ),
        "13 并发与生命周期": (
            "快速连点：同一 revision 的重复提交按幂等处理，第二次直接返回已成功的 FlushResult。\n"
            "- A→B 切换：命令携带入队时捕获的 entityId，绝不读「当前选中」\n"
            "- 迟到结果：读路径带 generation，过期结果直接丢弃\n"
            "- 防抖：仅对输入框做 300ms 防抖，写命令不防抖\n"
            "- 关窗/退出：先冲刷写队列，FlushResult 为 error 时阻止关窗并提示\n"
            "- 重启/睡眠唤醒：启动时按 revision 校验，冲突行标注并在 UI 上提示\n"
        ),
        "14 撤销与恢复": (
            "恢复哪些值：dueDate、allDay 两个字段，窗口期为一次成功写入后的 5 秒。\n"
            "- 连续编辑：以最后一次成功写入为撤销点，不叠加多次\n"
            "- 保存失败重试：草稿完整保留，重试沿用同一 revision\n"
            "- 误操作保护：清除日期前二次确认；撤销按钮在提示条上\n"
        ),
        "15 体验标准": (
            "输入法：中文组合输入期间不触发表单提交，Esc 先退出候选再关浮层。\n"
            "- 焦点返回：执行后焦点回到触发元素，键盘可完成整条流程\n"
            "- Esc/Enter：Esc 关闭并还原草稿，Enter 提交当前浮层值\n"
            "- 可访问性：所有菜单项有可读标签，焦点环 2px 且对比度达 AA\n"
            "- 布局稳定：浮层出现不引起主列表跳动（预留占位）\n"
            "- 性能口径：点击到主列表可见更新的 p50 ≤ 80ms、p95 ≤ 200ms（本机 macOS，库 1 万行）\n"
        ),
        "16 测试与证据": (
            "用例与断言（正常 / 负向 / 边缘 / 跨页面 / 立即退出重启）：\n"
            "- %s：正常路径，断言落库值等于预期具体值\n"
            "- 同一用例覆盖跨页面：主列表徽标、日历格计数、角标数值三处都要断言\n"
            "- 负向：只读库写入 → 返回 FlushResult.error 且草稿仍在\n"
            "- 边缘：跨月、闰日、时区切换各一条\n"
            "- 截图不能代替落库证明：必须查询数据库断言具体值\n"
            % tests
        ),
    }
    lines = ["# %s · %s" % (fid, summary), ""]
    for heading in CONTRACT_SECTIONS:
        lines.append("## " + heading)
        lines.append("")
        lines.append(body[heading].rstrip())
        lines.append("")
    return "\n".join(lines)


FLOWS_MD = """\
# flows · 用户流程

## FL-01 修改任务日期

- 目标：把一条任务的日期从今天改到明天
- 起点：主列表任一行
- 路径：S-01 → 行右键 → M-DATE 子菜单 → M-DATE-TOMORROW → 结果回到 S-01
- 点击数：3

### 正常路径
1. 选中行 → 该行高亮，详情面板加载该任务 → 详情显示当前 dueDate
2. 打开日期菜单 → 子菜单展开，「今天」标记为当前值 → 菜单内高亮当前项
3. 点击「明天」→ 菜单收起 → 主列表徽标变「明天」→ 详情日期字段同步 → 提示条 2.5s 后淡出

### 失败与取消
| 情形 | 用户看到 | 系统状态 | 可恢复动作 |
|---|---|---|---|
| 写库失败（只读/磁盘满） | 提示条「保存失败，已保留修改」 | 草稿保留，库未变 | 修复磁盘后点重试 |
| revision 冲突 | 提示「已在别处修改」 | 不覆盖，重新读取 | 点「查看最新」后重选日期 |
| Esc 取消 | 浮层关闭 | 草稿丢弃，库未变 | 重新打开菜单 |

### 边界
| 边界 | 期望行为 | 依据 |
|---|---|---|
| 跨月（10-31 → 11-01） | 主列表与日历同时更新，角标重算 | S-03 截图 2026-10-20T09:20 |
| 闰日（02-28 → 02-29） | 允许，重复实例按实际月天数展开 | 观察记录 notes-2026-10-20 |
| 时区变更（+08:00 → +09:00） | 已存日期不变，相对文案重算 | U-001 待验 |
| 全天开关切换 | 时间置 00:00 或恢复 09:00，提醒同步改 | S-02 截图 |

### 恢复
误操作可在提示条上 5 秒内撤销；保存失败不清草稿；应用中途中止后重启会按 revision 校验并提示冲突行。

## FL-02 设置重复规则

- 目标：把任务设为「每周工作日」
- 起点：任务详情（S-02）
- 路径：S-02 → M-REPEAT 子菜单 → M-REPEAT-WEEKLY → 结果在 S-01/S-03 可见
- 点击数：2

### 正常路径
1. 打开重复菜单 → 子菜单展开，「不重复」为当前项 → 菜单高亮当前项
2. 点击「每周工作日」→ 菜单收起 → repeat.rule=WEEKLY、byday=[1,2,3,4,5] → 主列表出现重复图标 → 日历展开 5 个工作日实例

### 失败与取消
| 情形 | 用户看到 | 系统状态 | 可恢复动作 |
|---|---|---|---|
| 同步中禁用 | 菜单项灰化 + 「同步中」提示 | 库未变 | 等同步结束后重试 |
| 写失败 | 提示「重复规则未保存」 | 草稿保留 | 点重试 |
| 取消（Esc） | 浮层关闭 | 库未变 | 重新打开 |

### 边界
| 边界 | 期望行为 | 依据 |
|---|---|---|
| 跨月展开 | 只在可见窗口展开，跨月实例正确 | S-03 截图 |
| 清除重复 | byday 清空、下次发生清空、日历实例移除 | 契约 §9 |
| 已有提醒 | 重复变更后提醒按新规则重排 | 契约 §12 提醒调度 |
| 每月第 N 周 | 本版不支持（accepted-risk） | DECISIONS D-003 |

### 恢复
清空重复前二次确认；写失败保留草稿；重启后按 revision 校验，冲突行在 UI 上标注。
"""

STATE_MACHINES_MD = """\
# state-machines · 状态机

## SM-01 任务日期

### 状态
| 状态 | 含义 | 是否持久化 |
|---|---|---|
| idle | 无进行中的写入 | 否 |
| SUBMITTING | 已提交，等待落库完成信号 | 否 |
| conflict | revision 冲突，等待用户选择 | 否 |
| error | 写入失败，草稿保留 | 否 |

### 转换
| 从 | 事件 | 守卫条件 | 到 | 附带动作 | 异步结果处理 |
|---|---|---|---|---|---|
| idle | SubmitDateChange | revision 匹配 | SUBMITTING | 入写队列，捕获 entityId | await FlushResult |
| SUBMITTING | FlushOk | FlushResult.ok | idle | 广播 TaskDateChanged，刷新六面 | 过期 generation 丢弃 |
| SUBMITTING | FlushError | FlushResult.error | error | 保留草稿，显示重试 | 记录脱敏日志 |
| SUBMITTING | RevisionConflict | 库中 revision 更大 | conflict | 提示「已在别处修改」 | 重读最新值 |
| error | Retry | 磁盘可写 | SUBMITTING | 沿用同一 revision | await FlushResult |
| conflict | Reload | 用户点「查看最新」 | idle | 用最新值刷新界面 | - |

### 非法转换
| 尝试 | 期望拒绝方式 | 用户看到 |
|---|---|---|
| error → idle（跳过重试） | 拒绝，必须经 Retry 或 Reload | 提示条保持「保存失败，已保留修改」 |
| SUBMITTING → SUBMITTING（重复提交） | 幂等，直接返回首个 FlushResult | 无重复提示 |
| conflict → SUBMITTING（不重读） | 拒绝 | 提示「请先查看最新版本」 |

## SM-02 重复规则

### 状态
| 状态 | 含义 | 是否持久化 |
|---|---|---|
| none | 不重复 | 是（repeat.rule 为空） |
| weekly | 每周固定星期 | 是 |
| workdays | 每周工作日（周一至周五） | 是 |
| custom | 自定义 byday 集合 | 是 |

### 转换
| 从 | 事件 | 守卫条件 | 到 | 附带动作 | 异步结果处理 |
|---|---|---|---|---|---|
| none | SetWorkdays | 可写 | workdays | 写 byday=[1,2,3,4,5] | await FlushResult |
| workdays | ClearRepeat | 可写 | none | 清空 byday 与下次发生 | await FlushResult |
| weekly | SetWorkdays | 可写 | workdays | 覆盖 byday | await FlushResult |

### 非法转换
| 尝试 | 期望拒绝方式 | 用户看到 |
|---|---|---|
| 重复中修改日期到过去 | 允许修改，但下次发生按规则顺延 | 下次发生日期立即更新 |
| custom 且 byday 为空 | 拒绝，回退到 none | 提示「至少选择一天」 |
"""

DATA_DICT_MD = """\
# data-dictionary · 数据字典

> 字段 ID 写作 `E01.dueDate`，代码与测试按此引用。

## E01 TaskModel
| 字段 | 类型 | 默认 | 空值 | 枚举/约束 | 关系 | 来源（原版观察/推断） | 本地映射 |
|---|---|---|---|---|---|---|---|
| id | TEXT | - | 否 | 主键，UUID | 1→N Reminder | 原版观察（DB 导出） | TaskModel.id |
| title | TEXT | '' | 否 | 长度 ≤ 500 | - | 原版观察 | TaskModel.title |
| dueDate | TEXT | - | 是 | ISO 日期或空 | - | 原版观察 | TaskModel.dueDate |
| dueTime | INTEGER | 540 | 是 | 0..1439 分钟 | - | 推断（09:00 默认） | TaskModel.dueTime |
| allDay | INTEGER | 0 | 否 | 0/1 | - | 原版观察 | TaskModel.allDay |
| repeat | TEXT | - | 是 | NONE/WEEKLY/WORKDAYS/CUSTOM | 指向 E02 | 原版观察 | TaskModel.repeat |
| byday | TEXT | - | 是 | 逗号分隔的 1..7 | - | 推断 | TaskModel.byday |
| revision | INTEGER | 1 | 否 | 每次写入 +1 | - | 推断（并发控制） | TaskModel.revision |
| updatedAt | TEXT | - | 否 | ISO 8601 带时区 | - | 原版观察 | TaskModel.updatedAt |

## E02 Reminder
| 字段 | 类型 | 默认 | 空值 | 枚举/约束 | 关系 | 来源（原版观察/推断） | 本地映射 |
|---|---|---|---|---|---|---|---|
| id | TEXT | - | 否 | 主键，UUID | N→1 E01 | 原版观察 | Reminder.id |
| taskId | TEXT | - | 否 | 外键 → E01.id | - | 原版观察 | Reminder.taskId |
| fireAt | TEXT | - | 否 | ISO 8601 带时区 | - | 原版观察 | Reminder.fireAt |
| state | TEXT | pending | 否 | pending/fired/cancelled | - | 推断 | Reminder.state |
"""

ARCHITECTURE_MD = """\
# 架构 · 本地日期任务

## 1 组件边界
| 组件 | 负责 | 依赖方向 |
|---|---|---|
| UI（view/） | 渲染屏幕与浮层，只调 ViewModel | → ViewModel |
| ViewModel | 命令分发、草稿与状态机 | → Repository |
| Repository | 事务、SQL、event 广播 | → SQLite 文件 |
| Flush 层 | 关窗冲刷、返回 FlushResult | → Repository |

依赖单向向下；UI 不直接访问数据库；Repository 不 import UI。

## 2 分层
- 表现层：S-01 主列表 / S-02 详情 / S-03 日历 / S-04 设置
- 应用层：命令（Cmd.*）与查询，含 revision 校验
- 领域层：重复规则求值、相对文案计算
- 基础设施层：SQLite 单文件、WAL、真文件路径

## 3 数据流
写入路径：UI → Cmd → ViewModel 状态机（SUBMITTING）→ Repository 事务 → 提交成功 → 广播事件 → 六面刷新 → FlushResult。
读取路径：UI → 查询 → Repository（同连接）→ 派生值计算 → 渲染。
事务边界：单命令单事务；事件在提交成功后才广播，保证「界面看到的一定已落库」。
"""

SCHEMA_SQL = """\
-- 本地单文件 SQLite 结构（S4 产出）
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE TaskModel (
  id         TEXT PRIMARY KEY,
  title      TEXT NOT NULL DEFAULT '',
  dueDate    TEXT,
  dueTime    INTEGER DEFAULT 540 CHECK (dueTime BETWEEN 0 AND 1439),
  allDay     INTEGER NOT NULL DEFAULT 0 CHECK (allDay IN (0, 1)),
  repeat     TEXT CHECK (repeat IN ('NONE', 'WEEKLY', 'WORKDAYS', 'CUSTOM')),
  byday      TEXT,
  revision   INTEGER NOT NULL DEFAULT 1,
  updatedAt  TEXT NOT NULL
);

CREATE TABLE Reminder (
  id       TEXT PRIMARY KEY,
  taskId   TEXT NOT NULL REFERENCES TaskModel(id) ON DELETE CASCADE,
  fireAt   TEXT NOT NULL,
  state    TEXT NOT NULL DEFAULT 'pending' CHECK (state IN ('pending', 'fired', 'cancelled'))
);

CREATE INDEX idx_task_due ON TaskModel(dueDate);
CREATE INDEX idx_reminder_task ON Reminder(taskId);
"""

TRACEABILITY_ROWS = [
    ["feature_id", "contract_ref", "screen", "menu_nodes", "entities", "commands",
     "routes", "tests", "state"],
    ["F-DATE-EDIT", "contracts/C-F-DATE-EDIT.md", "S-01", "M-DATE;M-DATE-TODAY;M-DATE-TOMORROW;M-DATE-CUSTOM",
     "TaskModel", "Cmd.SetTaskDate;Cmd.SetDateToday", "src/date_edit.py", "T-101;T-104", "BUILT"],
    ["F-REPEAT-SET", "contracts/C-F-REPEAT.md", "S-02", "M-REPEAT;M-REPEAT-NONE;M-REPEAT-WEEKLY;M-REPEAT-CUSTOM",
     "TaskModel;Reminder", "Cmd.SetRepeatWeeklyWorkdays;Cmd.ClearRepeat", "src/repeat_set.py", "T-102;T-103", "BUILT"],
]

VERTICAL_SLICE_MD = """\
# 竖切证据：建 → 读 → 重启还在

## 1 执行命令
```bash
python3 -m app.cli create --title "写作" --due 2026-10-24 --all-day
python3 -m app.cli show --last
```

## 2 实测输出（2026-10-22T14:03+08:00）
```
created id=9f3c… dueDate=2026-10-24 allDay=1 revision=1
show      id=9f3c… dueDate=2026-10-24 allDay=1 revision=1
```

## 3 重启后复查（2026-10-22T14:05+08:00）
```bash
# 结束进程 → 重新启动 → 再次读取
python3 -m app.cli show --id 9f3c…
```
```
id=9f3c… dueDate=2026-10-24 allDay=1 revision=1
```
结论：重启后值一致，说明落的是真文件（`~/Library/Application Support/good-min/app.db`），不是内存库。
"""

TOKENS_JSON = """\
{
  "_about": "设计 token（夹具用）。角色名固定、值可换；每次改值都要跑 contrast.py。",
  "color": {
    "bg": "#ffffff",
    "surface": "#f6f7f9",
    "border": "#e3e6ea",
    "border-input": "#868e98",
    "text": "#14171c",
    "text-muted": "#5b6470",
    "accent": "#2f5bea",
    "on-accent": "#ffffff",
    "danger": "#c62f2f",
    "success": "#1f7a4d"
  },
  "pairs": [
    ["text", "bg"],
    ["text", "surface"],
    ["text-muted", "bg"],
    ["text-muted", "surface"],
    ["on-accent", "accent"],
    ["accent", "bg"],
    ["danger", "bg"],
    ["success", "bg"],
    ["border-input", "bg", "ui"]
  ],
  "font": {
    "sans": "Inter, PingFang SC, system-ui, -apple-system, sans-serif",
    "mono": "ui-monospace, SFMono-Regular, Menlo, monospace"
  },
  "type": {
    "sm": {"size": 14, "line": 20, "weight": 400},
    "base": {"size": 16, "line": 24, "weight": 400},
    "lg": {"size": 20, "line": 28, "weight": 600}
  },
  "space": [0, 4, 8, 12, 16, 24, 32, 48, 64],
  "radius": {"sm": 6, "md": 10, "lg": 16, "pill": 999},
  "shadow": {
    "card": "0 1px 2px rgba(16,24,40,.06), 0 1px 3px rgba(16,24,40,.10)",
    "pop": "0 12px 32px rgba(16,24,40,.16)"
  },
  "motion": {"fast": "120ms", "base": "200ms", "ease": "cubic-bezier(.2,.8,.2,1)"}
}
"""

COMPONENTS_MD = """\
# 组件规格（每个组件必须六态齐全）

## Button

| 状态 | 视觉 | 触发条件 |
|---|---|---|
| default | accent 填充，文字 on-accent，圆角 10 | 静止 |
| hover | accent 提亮 6%，阴影 card | 指针悬停 |
| focus | 外环 2px accent，偏移 2px | 键盘 Tab 聚焦 |
| disabled | surface 填充，文字 text-muted，指针 not-allowed | 不可写或保存中 |
| loading | 内嵌 16px 转圈，文字变「保存中…」，宽度不变 | 提交中 |
| error | 边框 danger 1px，图标 danger | 提交失败 |

## MenuItem

| 状态 | 视觉 | 触发条件 |
|---|---|---|
| default | 文字 text，行高 32，左右内边距 12 | 静止 |
| hover | 背景 surface | 指针悬停 |
| focus | 背景 surface + 左侧 2px accent 指示条 | 键盘上下移动 |
| disabled | 文字 text-muted，无悬停背景 | 条件不满足 |
| loading | 右侧 12px 转圈 | 该节点的异步动作进行中 |
| error | 右侧 danger 感叹号，tooltip 给原因 | 该节点动作失败 |

## 替换表（原版素材 → 开源替代）

| 原素材 | 替换为 | 来源 | 许可 |
|---|---|---|---|
| 原版图标集（不可再分发） | Lucide 线性图标集 | https://lucide.dev | ISC |
| 原版品牌字体 | Inter + 系统中文栈 PingFang SC | https://fonts.google.com/specimen/Inter | OFL-1.1 |
| 原版品牌主色 | 中性蓝 #2f5bea（自选） | 本项目 tokens.json | 自有 |
"""

TEST_PLAN_MD = """\
# 测试计划

> 类型列取值：正常 / 负向 / 边缘 / 跨页面 / 生命周期（含故障注入）。
> 期望列必须是**具体值**，不许写「正常显示」。

| ID | FL | 类型 | 步骤 | 期望（具体值） | 自动化 |
|---|---|---|---|---|---|
| T-101 | FL-01 | 正常 | 选中任务 → 日期 › 明天 → 读回库 | TaskModel.dueDate == '2026-10-24' 且主列表徽标为「明天」 | 是 |
| T-102 | FL-02 | 正常 | 选中任务 → 重复 › 每周工作日 → 读回 | repeat == 'WORKDAYS' 且 byday == '1,2,3,4,5' | 是 |
| T-103 | FL-02 | 故障注入 | 把库目录改为只读 → 设置重复规则 | 返回 FlushResult.error；detail.repeat 草稿仍在；库中 repeat 未变 | 是 |
| T-104 | FL-01 | 生命周期 | 写入 dueDate → 结束进程 → 重启 → 读回 | 重启后 dueDate == '2026-10-24'，revision == 2 | 是 |

## 覆盖说明
- 每个 must 功能至少 1 条端到端断言（T-101/T-104 覆盖 F-DATE-EDIT，T-102/T-103 覆盖 F-REPEAT-SET）
- 故障注入覆盖「写失败不丢草稿」（R3）；生命周期覆盖「重启读回」（R4）
- 全量连跑 3 次，结果落在 TEST/results/
"""

BUGS_MD = """\
# 缺陷台账（只追加 + 改状态）

| ID | 严重度 | 状态 | 现象 | 复现步骤 | 证据 | 修复提交 |
|---|---|---|---|---|---|---|
| BUG-001 | S2 | closed | 重复菜单在三态切换时闪一次空列表 | 连续切换 不重复→每周工作日 三次 | TEST/results/2026-10-21-run1.json | a1b2c3d |
| BUG-002 | S3 | open | 日历视图跨月第一格任务条右边缘被裁 1px | 切到 11 月首格 | screens/S03-calendar.png | - |
"""

PARITY_MD = """\
# 一致性报告（功能分 + 界面分双分制）

功能分：85.7（由 BLUEPRINT/features.csv 实算：weight must=3 / should=2 / could=1，progress yes=1 / partial=0.5 / no=0，剔除 skip 与 original=no）
界面分：88（视觉与操作步数分开记录，**不参与抵消功能分**）

## 算法口径
- 分子 = Σ(weight × progress 值) = 3×1 + 3×1 + 1×0 = 6
- 分母 = Σ(weight) = 3 + 3 + 1 = 7
- 功能分 = 6 / 7 × 100 = 85.7（阈值 80，manifest.thresholds.parity_feature）

## 缺失清单
- F-SYNC-CLOUD：云同步未实现（could 级，本版不做；补做需先过 S2 契约）
- F-REPEAT-SET：自定义分支只支持工作日与按周，未支持「每月第 N 周」（accepted-risk，见 D-003）

## 界面差距（供下轮）
- 浮层圆角原版 12、我方 10
- 菜单行高原版 30、我方 32
"""

FEEDBACK_MD = """\
# 痛点与差异化（每条带链接与计数）

样本：App Store 中国区 1 星评论 42 条 + 小红书笔记 18 篇 + 少数派评论 7 条，采集于 2026-10-20。

## 原版被骂最多的五点

1. 全天任务在分享卡片里显示成 00:00，用户以为时间错了 —— 一星评论 9 条提到（https://apps.apple.com/cn/app/id1234567890?see-all=reviews），该帖 128 赞
2. 重复规则选完看不到「下次发生日期」，只能靠猜 —— 小红书笔记 12 条（https://www.xiaohongshu.com/explore/6f2a1c3d），累计 246 赞
3. 退出后最后一次编辑丢失，重开会回滚 —— 少数派评论区 7 条（https://sspai.com/post/887766#comments），46 赞
4. 日历跨月时重复任务只显示一半 —— 一星评论 5 条（https://apps.apple.com/cn/app/id1234567890?see-all=reviews），该帖 31 赞
5. 菜单里「今天/明天」没有快捷键提示，键盘党来回切 —— 小红书笔记 4 条（https://www.xiaohongshu.com/explore/7a1b2c3e），88 赞

## 我们的差异化（对应改进项）
| 痛点 | 我们的做法 | 落点 |
|---|---|---|
| 全天显示成 00:00 | 分享卡片保留「全天」语义 | features.csv 新增行（走 S2 契约） |
| 看不到下次发生 | 重复菜单项右侧直接显示下次发生日期 | 契约 C-F-REPEAT §8 |
| 退出丢编辑 | 关窗冲刷返回 FlushResult，error 时阻止关窗 | R3、契约 §13 |
| 跨月只显示一半 | 日历按可见窗口展开实例 | 契约 C-F-REPEAT §12 |
| 快捷键不可见 | 菜单项右侧常显快捷键 | components.md MenuItem |
"""

RUNBOOK_MD = """\
# 本地运行手册（A 档）

## 1 启动
```bash
./scripts/start.sh            # 首次会建库并做启动自检（R14）
```
期望输出：`db tables=2 indexes=2 foreign_keys=1`，随后窗口打开。

## 2 备份
```bash
./scripts/start.sh --backup-only        # 生成的副本落在 backups/
sqlite3 backups/app-$(date +%Y%m%d-%H%M).db "PRAGMA integrity_check;"
```
先 `PRAGMA wal_checkpoint(TRUNCATE)` 再复制，否则会漏掉未合并的 WAL。

## 3 恢复
```bash
# 关闭应用后执行
cp backups/app-20261022-1403.db "$HOME/Library/Application Support/good-min/app.db"
./scripts/start.sh --verify                 # 逐表行数比对
```

## 4 迁移
```bash
# 换机器：整个数据目录打包，不迁移缓存
tar -czf good-min-data.tgz "$HOME/Library/Application Support/good-min"
# 新机解包到同一路径，启动自动迁移 schema（PRAGMA user_version 单调递增）
```

## 5 卸载
```bash
rm -rf "$HOME/Library/Application Support/good-min"   # 数据
rm -rf /Applications/good-min.app                      # 程序
# 验证无残留：
ls "$HOME/Library/Application Support" | grep -c good-min   # 期望 0
```

## 6 恢复演练记录
见 REPORT/release/restore-drill.md（2026-10-22 演练：备份 → 删库 → 恢复 → 逐行比对 128 行一致）。
"""

RESTORE_DRILL_MD = """\
# 恢复演练记录

| 项 | 值 |
|---|---|
| 演练时间 | 2026-10-22T14:30+08:00 |
| 备份文件 | backups/app-20261022-1403.db |
| 演练步骤 | 1) wal_checkpoint(TRUNCATE) 2) 备份 3) 删除主库 4) 用备份恢复 5) 启动并逐表比对 |
| 结果 | 128 行全部一致（TaskModel 96 行、Reminder 32 行），revision 无回退 |
| 失败处理 | 若行数不一致，保留备份并回滚到上一份，不允许「差不多就行」 |
| 结论 | 通过；下次演练在 2026-11-22 前完成 |
"""

EVIDENCE_NOTES = """\
# 观察记录 2026-10-20

- 09:12 窗口级截图 screens/S01-date-menu.png：日期子菜单展开时的层级与顺序
- 09:18 窗口级截图 screens/S02-repeat-menu.png：重复子菜单的当前项标记方式
- 09:26 观察：退出应用后立即重开，最后 1 秒内的编辑会回滚 → 印证 R3 的冲刷必要性
- 09:30 观察：全天任务在分享卡片显示 00:00 → 与 feedback.md 痛点 1 一致

采集方式：窗口截图 + 手工观察；未修改任何原版文件（R9）。
"""

BUILD_LOG_MD = """\
# 构建日志

| 屏幕 | 日期 | 状态 | 缺什么 | 比预想难的地方 |
|---|---|---|---|---|
| S-01 主列表 | 2026-10-21 | 四态齐 | - | 行徽标在筛选移出后的焦点落点 |
| S-02 任务详情 | 2026-10-21 | 四态齐 | - | 浮层翻转定位 |
| S-03 日历 | 2026-10-22 | 四态齐 | 跨月实例展开 | 可见窗口计算 |
| S-04 设置 | 2026-10-22 | 四态齐 | - | - |
"""

SRC_DATE_EDIT = '''\
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
'''

SRC_REPEAT_SET = '''\
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
'''

SRC_FLUSH = '''\
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
'''

SRC_REPOSITORY = '''\
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
'''

SRC_CLI = '''\
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
'''

TEST_PERSIST = '''\
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
'''

SCRIPTS_START = """\
#!/usr/bin/env bash
# 启动脚本（A 档）：建库、启动自检、可选备份模式。
set -euo pipefail
DB_HOME="$HOME/Library/Application Support/good-min"
DB="$DB_HOME/app.db"
mkdir -p "$DB_HOME"

if [ "${1:-}" = "--backup-only" ]; then
  mkdir -p backups
  sqlite3 "$DB" "PRAGMA wal_checkpoint(TRUNCATE);" >/dev/null 2>&1 || true
  cp "$DB" "backups/app-$(date +%Y%m%d-%H%M).db"
  echo "backup written to backups/"
  exit 0
fi

# R14：启动期自检「声称 vs 实际」
python3 - <<'PY'
import os, sqlite3
db = os.path.join(os.path.expanduser("~"), "Library", "Application Support", "good-min", "app.db")
os.makedirs(os.path.dirname(db), exist_ok=True)
conn = sqlite3.connect(db)
tables = conn.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchone()[0]
indexes = conn.execute("SELECT count(*) FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%'").fetchone()[0]
fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
print("db tables=%d indexes=%d foreign_keys=%d" % (tables, indexes, fk))
PY

echo "good-min 已启动（本机 macOS，本地单文件库）"
"""


def _results_json(run_iso):
    return (
        "{\n"
        '  "run": "%s",\n'
        '  "suite": "e2e",\n'
        '  "commit": "a1b2c3d",\n'
        '  "total": 4, "passed": 4, "failed": 0, "timeout": 0,\n'
        '  "cases": [\n'
        '    {"id": "T-101", "status": "pass", "duration_ms": 812},\n'
        '    {"id": "T-102", "status": "pass", "duration_ms": 640},\n'
        '    {"id": "T-103", "status": "pass", "duration_ms": 1180},\n'
        '    {"id": "T-104", "status": "pass", "duration_ms": 1530}\n'
        '  ]\n'
        '}\n' % run_iso
    )


# ---------------------------------------------------------------------------
# good-min 构建
# ---------------------------------------------------------------------------

GOOD_MIN_CONTRACTS = {
    "C-F-DATE-EDIT": dict(
        fid="C-F-DATE-EDIT",
        summary="修改任务的日期与时间",
        name="修改任务的日期与时间（含全天切换）",
        menu_path="日期 › 明天",
        command="Cmd.SetTaskDate",
        field="E01.dueDate / E01.allDay",
        extra_screens=["S-01 主列表", "S-02 任务详情"],
        lk_ids=["LK-001", "LK-002"],
        test_ids=["T-101", "T-104"],
    ),
    "C-F-REPEAT": dict(
        fid="C-F-REPEAT",
        summary="设置与清除重复规则",
        name="设置与清除重复规则（工作日 / 每周 / 自定义）",
        menu_path="重复 › 每周工作日",
        command="Cmd.SetRepeatWeeklyWorkdays",
        field="E01.repeat / E01.byday",
        extra_screens=["S-01 主列表", "S-03 日历视图"],
        lk_ids=["LK-003", "LK-004"],
        test_ids=["T-102", "T-103"],
    ),
}


def build_good_min(dest):
    dest = Path(dest)
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)

    for d in (".replica", "BLUEPRINT/contracts", "SPEC/DESIGN", "BUILD",
              "TEST/results", "REPORT/release", "evidence", "screens",
              "clone-screens", "src", "tests", "e2e", "scripts", "_archive"):
        (dest / d).mkdir(parents=True, exist_ok=True)

    w(dest, ".replica/gate.manifest.yml", MANIFEST)
    w(dest, "PROJECT.md", PROJECT_MD)
    w(dest, "DECISIONS.md", DECISIONS_MD)
    w(dest, "REDLINES.md", REDLINES_MD)
    w(dest, "AGENTS.md", AGENTS_MD)
    w(dest, "STATE.md", STATE_MD)

    w(dest, "BLUEPRINT/recon.md", RECON_MD)
    w(dest, "BLUEPRINT/features.csv", csv_text(FEATURE_ROWS[0], FEATURE_ROWS[1:]))
    w(dest, "BLUEPRINT/screens.csv", csv_text(SCREEN_ROWS[0], SCREEN_ROWS[1:]))
    w(dest, "BLUEPRINT/menus.csv", csv_text(MENU_ROWS[0], MENU_ROWS[1:]))
    w(dest, "BLUEPRINT/linkage.csv", csv_text(LINKAGE_ROWS[0], LINKAGE_ROWS[1:]))
    w(dest, "BLUEPRINT/unknowns.csv", csv_text(UNKNOWN_ROWS[0], UNKNOWN_ROWS[1:]))
    w(dest, "BLUEPRINT/flows.md", FLOWS_MD)
    w(dest, "BLUEPRINT/state-machines.md", STATE_MACHINES_MD)
    w(dest, "BLUEPRINT/data-dictionary.md", DATA_DICT_MD)
    for name, spec in GOOD_MIN_CONTRACTS.items():
        w(dest, "BLUEPRINT/contracts/%s.md" % name, contract_text(**spec))

    w(dest, "SPEC/ARCHITECTURE.md", ARCHITECTURE_MD)
    w(dest, "SPEC/schema.sql", SCHEMA_SQL)
    w(dest, "SPEC/TRACEABILITY.csv", csv_text(TRACEABILITY_ROWS[0], TRACEABILITY_ROWS[1:]))
    w(dest, "SPEC/vertical-slice.md", VERTICAL_SLICE_MD)
    w(dest, "SPEC/DESIGN/tokens.json", TOKENS_JSON)
    w(dest, "SPEC/DESIGN/components.md", COMPONENTS_MD)

    w(dest, "BUILD/build-log.md", BUILD_LOG_MD)

    w(dest, "TEST/test-plan.md", TEST_PLAN_MD)
    w(dest, "TEST/bugs.md", BUGS_MD)
    w(dest, "TEST/results/2026-10-21-run1.json", _results_json("2026-10-21T11:00+08:00"))
    w(dest, "TEST/results/2026-10-22-run2.json", _results_json("2026-10-22T11:00+08:00"))
    w(dest, "TEST/results/2026-10-23-run3.json", _results_json("2026-10-23T11:18+08:00"))

    w(dest, "REPORT/parity.md", PARITY_MD)
    w(dest, "REPORT/feedback.md", FEEDBACK_MD)
    w(dest, "REPORT/release/local-runbook.md", RUNBOOK_MD)
    w(dest, "REPORT/release/restore-drill.md", RESTORE_DRILL_MD)

    w(dest, "evidence/notes-2026-10-20.md", EVIDENCE_NOTES)
    for name in ("S01-date-menu.png", "S02-repeat-menu.png", "S04-sync.png"):
        w(dest, "screens/" + name, PNG_1PX)

    w(dest, "src/date_edit.py", SRC_DATE_EDIT)
    w(dest, "src/repeat_set.py", SRC_REPEAT_SET)
    w(dest, "src/flush.py", SRC_FLUSH)
    w(dest, "src/repository.py", SRC_REPOSITORY)
    w(dest, "src/cli.py", SRC_CLI)
    w(dest, "src/__init__.py", '"""good-min 示例实现（门禁夹具）。"""\n')

    w(dest, "tests/test_persist.py", TEST_PERSIST)
    w(dest, "e2e/test_flows.py", '''\
"""e2e 流程用例（与 TEST/test-plan.md 的 T-101..T-104 对应）。"""

# 这里只保留骨架：夹具目的是门禁判定，不追求真的起一个 UI。
# 关键是：不许出现内存库写法，且用例号与结果文件一一对应。
CASES = ["T-101", "T-102", "T-103", "T-104"]
''')

    w(dest, "scripts/start.sh", SCRIPTS_START, mode=0o755)

    compute_lock(dest)
    return dest


# ---------------------------------------------------------------------------
# 冻结哈希
# ---------------------------------------------------------------------------

def lock_files(project):
    files = list(C.LOCK_REQUIRED_FILES)
    contracts_dir = Path(project) / "BLUEPRINT/contracts"
    if contracts_dir.is_dir():
        for p in sorted(contracts_dir.glob("*.md")):
            rel = "BLUEPRINT/contracts/" + p.name
            if rel not in files:
                files.append(rel)
    return files


def compute_lock(project):
    """实算每个文件的 SHA-256，重写 BLUEPRINT-LOCK.md。"""
    project = Path(project)
    files = lock_files(project)
    rows = []
    for rel in files:
        p = project / rel
        if not p.is_file():
            raise SystemExit("lock: 缺文件 %s" % rel)
        rows.append("| %s | %s |" % (rel, hashlib.sha256(p.read_bytes()).hexdigest()))
    text = "\n".join([
        "# 蓝图冻结记录",
        "",
        "> 由 `python3 gates/fixtures/_make.py lock <项目>` 实算生成。"
        "改动蓝图必须重跑本命令并把蓝图版本 +1（00-体系总纲.md §8）。",
        "",
        "| 项 | 值 |",
        "|---|---|",
        "| 蓝图版本 | %s |" % LOCK_VERSION,
        "| 冻结时间 | %s |" % LOCK_TIME,
        "| 确认人 | %s |" % LOCK_CONFIRMER,
        "| 确认方式 | 逐条审阅 features must 行 + 2 份契约 16 节 + menus 三条件 |",
        "| 门禁结果 | G1 通过；G2 通过 |",
        "",
        "## 文件哈希（SHA-256）",
        "",
        "| 文件 | SHA-256 |",
        "|---|---|",
    ] + rows + [
        "",
        "## 确认要点",
        "- [x] 核心行为理解无误：F-DATE-EDIT、F-REPEAT-SET 逐条过审",
        "- [x] 保留与改进项已记录：DECISIONS.md D-001 到 D-004",
        "- [x] 阻断级未知为 0（U-001 为 non-blocking；U-002 已经产品方批准为 accepted-risk）",
        "",
    ])
    return w(project, "BLUEPRINT/BLUEPRINT-LOCK.md", text)


# ---------------------------------------------------------------------------
# broken 夹具
# ---------------------------------------------------------------------------

def remove_section(text, heading):
    """删掉某个二级标题开头的整段（到下一个二级标题）。"""
    lines = text.splitlines()
    out, skipping = [], False
    for raw in lines:
        if raw.startswith("## "):
            if raw[3:].strip() == heading:
                skipping = True
                continue
            if skipping:
                skipping = False
        if not skipping:
            out.append(raw)
    return "\n".join(out) + ("\n" if text.endswith("\n") else "")


def replace_in_file(path, old, new, count=1):
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit("夹具补丁失败：%s 里找不到 %r" % (path, old[:40]))
    p.write_text(text.replace(old, new, count), encoding="utf-8")


def build_broken_blueprint(good, dest):
    if Path(dest).exists():
        shutil.rmtree(dest)
    shutil.copytree(good, dest)

    # 1) 契约缺 2 节（12 跨页面联动、14 撤销与恢复）
    contract = Path(dest) / "BLUEPRINT/contracts/C-F-REPEAT.md"
    text = contract.read_text(encoding="utf-8")
    text = remove_section(text, "12 跨页面联动")
    text = remove_section(text, "14 撤销与恢复")
    contract.write_text(text, encoding="utf-8")

    # 2) 菜单条件写成「按原版」
    replace_in_file(Path(dest) / "BLUEPRINT/menus.csv",
                    "repeat.rule == 'WEEKLY' 且 repeat.byday 覆盖周一至周五",
                    "按原版")

    # 3) 缺 unknowns.csv
    (Path(dest) / "BLUEPRINT/unknowns.csv").unlink()


def build_broken_linkage(good, dest):
    if Path(dest).exists():
        shutil.rmtree(dest)
    shutil.copytree(good, dest)
    path = Path(dest) / "BLUEPRINT/linkage.csv"
    text = path.read_text(encoding="utf-8")
    text = text.replace("T-101,wired", "T-101,pending")
    path.write_text(text, encoding="utf-8")
    # 只让 G6 单独失败：改完蓝图重算冻结哈希（真实项目里必须走变更单）
    compute_lock(dest)


def build_broken_linkage_allna(good, dest):
    """某个 must 功能的 linkage 行全部标 na → G6 必须报「六面全 na」。

    构造方式：把 F-REPEAT-SET 的两行改成 na（理由写足，让 na 本身合法），
    这样失败原因就只剩「六面全 na 等于没做联动分析」这一条，
    而不是被 na 行的理由校验抢先报错。
    """
    if Path(dest).exists():
        shutil.rmtree(dest)
    shutil.copytree(good, dest)
    path = Path(dest) / "BLUEPRINT/linkage.csv"
    rows, fields = C.read_csv_text(path.read_text(encoding="utf-8"))
    for row in rows:
        if row["source_id"] != "F-REPEAT-SET":
            continue
        row["status"] = "na"
        row["test_ref"] = "-"
        row["refresh_timing"] = "不适用"
        row["affected_control"] = "不适用：%s（确认该面不随重复规则变化）" % row["affected_control"]
        row["state_handling"] = "不适用：确认该面不受重复规则影响，无需刷新"
    path.write_text(_make_csv_text(fields, rows), encoding="utf-8")
    compute_lock(dest)


def _make_csv_text(fields, rows):
    return csv_text(fields, [[r.get(f, "") for f in fields] for r in rows])


def build_broken_menu_order(good, dest):
    """同级 order 重复 → G2 必须 FAIL（ORDER-DUP 升为 ERROR）。

    Lead 在 examples 里踩过的真实坑：M-SLOT-EMPTY 与 M-TZ-SUB 都是 order=1，
    渲染顺序不确定。lint 只 WARN，门禁必须拦住。
    """
    if Path(dest).exists():
        shutil.rmtree(dest)
    shutil.copytree(good, dest)
    path = Path(dest) / "BLUEPRINT/menus.csv"
    rows, fields = C.read_csv_text(path.read_text(encoding="utf-8"))
    # 把 M-DATE-TOMORROW 的 order 改成与 M-DATE-TODAY 相同的 1
    for row in rows:
        if row["node_id"] == "M-DATE-TOMORROW":
            row["order"] = "1"
    path.write_text(_make_csv_text(fields, rows), encoding="utf-8")
    compute_lock(dest)
    return dest


def build_broken_out_scope(good, dest):
    """G1 夹具：把 must 功能悄悄改成 scope=out 且不写理由 → 必须 FAIL。

    针对的作弊路径（Lead 2026-10-23 实测）：G9 功能分剔除 scope=out 的行。
    如果把 must 功能改成 out、重算 parity.md 分数、重算 BLUEPRINT-LOCK 哈希，
    三道检查可以一起通过（实测 95/96 PASS），从而用"缩范围"把分数拉满。
    所以 out 必须是显式决策：notes 要有实质理由。
    """
    if Path(dest).exists():
        shutil.rmtree(dest)
    shutil.copytree(good, dest)

    path = Path(dest) / "BLUEPRINT/features.csv"
    rows, fields = C.read_csv_text(path.read_text(encoding="utf-8"))
    for row in rows:
        if row.get("feature_id") == "F-REPEAT-SET":
            row["scope"] = "out"
            row["notes"] = ""          # 故意不写理由
    path.write_text(csv_text(fields, [[r[f] for f in fields] for r in rows]),
                    encoding="utf-8")


def build_broken_project(good, dest):
    """G0 夹具：不做清单被清空 + 决策表只剩骨架行 → G0 必须 FAIL。

    这是针对两个真实假绿缺陷的回归夹具（Lead 2026-10-23 发现）：
    1. 不做清单只剩表头与占位行 → 旧逻辑把空行算成条目，永远 PASS
    2. 决策表只剩 D-001..D-003 的骨架行（只有编号没有日期/理由）→ 旧逻辑按全文
       正则统计，连模板「实例」章节的示例也计入，永远 PASS
    现在两者都必须报 FAIL。
    """
    if Path(dest).exists():
        shutil.rmtree(dest)
    shutil.copytree(good, dest)

    # 1) 不做清单清空（保留标题与表头，只留占位行）
    project = Path(dest) / "PROJECT.md"
    text = project.read_text(encoding="utf-8")
    text = re.sub(
        r"(## 不做清单\n)(.*?)(?=\n## )",
        r"\1\n| # | 不做的事 | 为什么不做 |\n"
        r"|---|---|---|\n"
        r"| 1 |  |  |\n"
        r"| 2 |  |  |\n"
        r"| 3 |  |  |\n"
        r"| 4 |  |  |\n"
        r"| 5 |  |  |\n",
        text, flags=re.S)
    project.write_text(text, encoding="utf-8")

    # 2) 决策表只剩骨架行
    decisions = Path(dest) / "DECISIONS.md"
    dtext = decisions.read_text(encoding="utf-8")
    dtext = re.sub(
        r"(## 决策表\n)(.*?)(?=\n## )",
        r"\1\n| ID | 日期 | 决策 | 理由 | 影响面 | 状态 |\n"
        r"|---|---|---|---|---|---|\n"
        r"| D-001 | | | | | 已定 |\n"
        r"| D-002 | | | | | 已定 |\n"
        r"| D-003 | | | | | 已定 |\n",
        dtext, flags=re.S)
    decisions.write_text(dtext, encoding="utf-8")
    return dest


def build_broken_lock(good, dest):
    if Path(dest).exists():
        shutil.rmtree(dest)
    shutil.copytree(good, dest)
    path = Path(dest) / "BLUEPRINT/recon.md"
    text = path.read_text(encoding="utf-8")
    path.write_text(text + "\n## 11 冻结后追加（未走变更单）\n这一行让哈希与 BLUEPRINT-LOCK 不符。\n",
                    encoding="utf-8")


def build_no_manifest(_good, dest):
    dest = Path(dest)
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    w(dest, "PROJECT.md", "# 只有目录，没有 manifest\n\n这个夹具用来验证：缺 manifest 时全部 BLOCKED，退出码 2。\n")
    w(dest, "BLUEPRINT/features.csv",
      "feature_id,feature,area,priority,scope,original,progress,contract_ref,acceptance_ref,evidence,notes\n")
    (dest / "SPEC").mkdir(exist_ok=True)
    (dest / "TEST/results").mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# check 模式：确认磁盘上的夹具与生成器一致
# ---------------------------------------------------------------------------

#: 快照时跳过的目录：判断"生成器可复现"只应看生成物，不看 Python 缓存
SNAPSHOT_SKIP_DIRS = {"__pycache__", ".pytest_cache", ".mypy_cache"}


def snapshot(root):
    root = Path(root)
    out = {}
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        rel_parts = p.relative_to(root).parts
        if any(part in SNAPSHOT_SKIP_DIRS for part in rel_parts):
            continue
        rel = str(p.relative_to(root)).replace(os.sep, "/")
        out[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def main(argv):
    """生成夹具。

    用法：
        python3 _make.py                      # 重建 HERE 下的全部夹具
        python3 _make.py --dest /tmp/xyz      # 在指定目录重建（不碰 HERE）
        python3 _make.py lock <项目目录>       # 只重算某个项目的冻结哈希

    --dest 是给测试用的：`test_make_py_regenerates_identically` 需要在
    不干扰其他测试的前提下验证"可重复生成"。在原目录重建会先 rmtree 再写，
    期间其他测试的 copy_fixture 可能撞上空目录（实测 10 次 1 次的 flaky）。
    """
    args = list(argv or ["all"])
    if args and args[0] == "lock":
        if len(args) < 2:
            raise SystemExit("用法：python3 gates/fixtures/_make.py lock <项目目录>")
        path = compute_lock(args[1])
        print("已重算冻结哈希：%s" % path)
        return 0

    fixtures = HERE
    if "--dest" in args:
        idx = args.index("--dest")
        if idx + 1 >= len(args):
            raise SystemExit("用法：python3 gates/fixtures/_make.py --dest <目录>")
        fixtures = Path(args[idx + 1]).resolve()
        fixtures.mkdir(parents=True, exist_ok=True)

    good = fixtures / "good-min"
    build_good_min(good)
    print("已生成 %s" % good)

    variants = {
        "broken-blueprint": build_broken_blueprint,
        "broken-linkage": build_broken_linkage,
        "broken-linkage-allna": build_broken_linkage_allna,
        "broken-menu-order": build_broken_menu_order,
        "broken-project": build_broken_project,
        "broken-out-scope": build_broken_out_scope,
        "broken-lock": build_broken_lock,
        "no-manifest": build_no_manifest,
    }
    for name, fn in variants.items():
        fn(good, fixtures / name)
        print("已生成 %s" % (fixtures / name))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
