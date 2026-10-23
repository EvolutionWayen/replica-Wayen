# -*- coding: utf-8 -*-
"""G2 行为蓝图门（S2 的核心，最容易被糊弄）。

判定（00-体系总纲.md §3.2 / SCHEMAS.md §4–§10）：
1. manifest.required.contract_sections（默认 16）与 SCHEMAS §8 的节数一致
2. must + in 功能 → 契约文件存在率 100%
3. 每个契约文件含 16 个二级标题（逐字），每节正文 ≥20 字或以 `N/A：` 开头
4. menus.csv 列名合法；每个非 separator/label 节点 command 与 contract_ref 非空非 `-`
5. 每个菜单节点的 显示/可用/选中 三条件非空，且不含「按原版/视情况/同前/TBD/待定」
6. linkage.csv 每行 refresh_timing 与 test_ref 非空、status 枚举合法
7. 每个 must 功能在 linkage 里 ≥2 个不同 affected_screen，或注明单屏理由
8. flows.md 每个 FL 含 正常路径 / 失败与取消 / 边界 / 恢复 四段
9. state-machines.md、data-dictionary.md 存在且不是模板占位
"""

from __future__ import annotations

import re

from . import common as C

STAGE = "G2"

#: 菜单三条件里不许出现的糊弄词（SCHEMAS §4）
BANNED_MENU_WORDS = ["按原版", "视情况", "同前", "TBD", "待定"]

MENU_SKIP_TYPES = {"separator", "label"}


def _contract_checks(g, ctx, headings):
    files = C.contract_files(ctx)
    if not files:
        g.fail("contracts-exist", "contracts/ 下有一功能一契约",
               expected="BLUEPRINT/contracts/C-F-xxx.md 至少 1 个",
               actual="BLUEPRINT/contracts/ 下没有 .md 文件",
               evidence="BLUEPRINT/contracts/",
               hint="为每个 must 功能建 contracts/C-F-<功能>.md（16 节，见 SCHEMAS §8）")
        return
    for rel in files:
        text = ctx.text(rel)
        if text is None:
            g.fail("contract-sections", "契约 %s 可读" % rel.rsplit("/", 1)[-1],
                   expected="文件存在且可读", actual="读取失败", evidence=rel,
                   hint="检查文件编码（UTF-8）与权限")
            continue
        sections = {s["title"]: s for s in C.md_sections(text, 2)}
        missing = [h for h in headings if h not in sections]
        empty = []
        for h in headings:
            sec = sections.get(h)
            if not sec:
                continue
            body = sec["body"].strip()
            if body.startswith("N/A：") or body.startswith("N/A:"):
                if len(body) >= 6:
                    continue
                empty.append("%s（N/A 但没写理由）" % h)
                continue
            if len(body) < 20:
                empty.append("%s（正文 %d 字）" % (h, len(body)))
        name = rel.rsplit("/", 1)[-1]
        if missing or empty:
            detail = []
            if missing:
                detail.append("缺节 %d 个：%s" % (len(missing), "；".join(missing[:4])))
            if empty:
                detail.append("空节 %d 个：%s" % (len(empty), "；".join(empty[:4])))
            g.fail("contract-sections", "契约 %s 的 16 节齐且非空" % name,
                   expected="%d 节标题逐字一致，每节 ≥20 字或 `N/A：理由`" % len(headings),
                   actual="；".join(detail), evidence=rel,
                   hint="按 SCHEMAS §8 的 16 个二级标题逐字补齐（含序号与空格）；"
                        "确定不适用就写 `N/A：<理由>`，不许留空")
        else:
            g.pass_("contract-sections", "契约 %s 的 16 节齐且非空" % name,
                    expected="%d 节全部有内容" % len(headings),
                    actual="%d 节齐全" % len(headings), evidence=rel)


def _contract_coverage(g, ctx):
    feature_rows = C.features(ctx)
    if not feature_rows:
        g.fail("contract-coverage", "must 功能契约覆盖率 100%",
               expected="参考 features.csv 统计 must+in 功能",
               actual="features.csv 不存在或为空", evidence="BLUEPRINT/features.csv",
               hint="先完成 S1：features.csv 是蓝图的单一事实来源")
        return
    targets = C.must_features(ctx)
    if not targets:
        g.pass_("contract-coverage", "must 功能契约覆盖率 100%",
                expected="must+in 功能均有契约",
                actual="没有 must+in 功能（全部 out / 只有 should/could）",
                evidence="BLUEPRINT/features.csv")
        return
    missing = []
    for row in targets:
        fid = C.cell(row, "feature_id")
        ref = C.cell(row, "contract_ref")
        if C.is_blank(ref):
            missing.append("%s（contract_ref 为空）" % fid)
            continue
        path = C.contract_path(ref)
        if not ctx.exists(path):
            missing.append("%s（%s 不存在）" % (fid, path))
    if missing:
        g.fail("contract-coverage", "must 功能契约覆盖率 100%",
               expected="%d 个 must+in 功能各有契约" % len(targets),
               actual="%d 个缺契约：%s" % (len(missing), "；".join(missing[:5])),
               evidence="BLUEPRINT/features.csv",
               hint="为缺契约的功能建 contracts/C-F-<功能>.md，并在 features.csv 填 contract_ref")
    else:
        g.pass_("contract-coverage", "must 功能契约覆盖率 100%",
                expected="%d 个 must+in 功能各有契约" % len(targets),
                actual="100%%（%d/%d）" % (len(targets), len(targets)),
                evidence="BLUEPRINT/features.csv")


def _cond_requirements(ntype):
    """按节点类型返回必须非空的列（SCHEMAS §4 的分级判定）。

    - radio / checkbox：有真正的「选中态」→ 三列全要
    - submenu / action：容器或一次性动作，没有选中态 → 只要 显示 + 可用
    - separator / label：无行为 → 三列都跳过（由 MENU_SKIP_TYPES 提前 continue）
    """
    if ntype in ("radio", "checkbox"):
        return ["visibility_cond", "enabled_cond", "checked_cond"]
    return ["visibility_cond", "enabled_cond"]


COND_LABELS = {
    "visibility_cond": "显示条件",
    "enabled_cond": "可用条件",
    "checked_cond": "选中条件",
}

#: 允许在这些列里写「不适用：<理由>」——只有非选中态类型才允许
NA_PREFIX = ("不适用", "n/a", "na：", "na:", "不涉及")


def _is_na_style(value):
    low = value.strip().lower()
    if low in C.BLANK_VALUES:
        return True
    return any(low.startswith(p) for p in NA_PREFIX) and len(value.strip()) >= 6


def _menu_checks(g, ctx):
    rows = g.read_csv("BLUEPRINT/menus.csv", C.MENUS_COLUMNS,
                      "menus-columns", "menus.csv 列名与 SCHEMAS §4 一致",
                      allow_missing=True)
    if rows is None:
        return
    bad_command, bad_cond, bad_na_reason = [], [], []
    for i, row in enumerate(rows, start=2):
        ntype = C.cell(row, "type").lower()
        if ntype in MENU_SKIP_TYPES:
            continue
        node = C.cell(row, "node_id") or "(第 %d 行)" % i
        if C.is_blank(C.cell(row, "command")):
            bad_command.append("%s 缺 command" % node)
        if C.is_blank(C.cell(row, "contract_ref")):
            bad_command.append("%s 缺 contract_ref" % node)

        required = _cond_requirements(ntype)
        for col, label in COND_LABELS.items():
            value = C.cell(row, col)
            must = col in required
            if must and C.is_blank(value):
                bad_cond.append("%s（%s）的%s为空" % (node, ntype, label))
                continue
            if not must and _is_na_style(value):
                # 允许为空/不适用，但「不适用」必须带理由，不许只写两个字
                if not C.is_blank(value) and len(value.strip()) < 6:
                    bad_na_reason.append("%s 的%s写了「%s」但没给理由"
                                         % (node, label, value.strip()))
                continue
            if C.is_blank(value):
                continue
            hits = [w for w in BANNED_MENU_WORDS if w in value]
            if hits:
                bad_cond.append("%s 的%s含禁用词 %s" % (node, label, "/".join(hits)))

    if bad_command:
        g.fail("menu-command", "每个菜单叶子有触发命令与契约引用",
               expected="type 非 separator/label 的节点 command 与 contract_ref 非空非 `-`",
               actual="%d 处问题：%s" % (len(bad_command), "；".join(bad_command[:4])),
               evidence="BLUEPRINT/menus.csv",
               hint="每个叶子写 Cmd.Xxx 与对应 contracts/C-F-xxx.md；没有命令说明这个菜单还没想清楚")
    else:
        g.pass_("menu-command", "每个菜单叶子有触发命令与契约引用",
                expected="command 与 contract_ref 非空",
                actual="%d 个可交互节点全部有命令" % max(
                    0, len([r for r in rows if C.cell(r, "type").lower() not in MENU_SKIP_TYPES])),
                evidence="BLUEPRINT/menus.csv")

    if bad_cond:
        g.fail("menu-conditions", "菜单条件按类型分级齐全且具体",
               expected="radio/checkbox：显示+可用+选中三列非空；submenu/action：显示+可用非空"
                        "（选中条件可填 `-` 或 `不适用：理由`）；均不含「按原版/视情况/同前/TBD/待定」",
               actual="%d 处问题：%s" % (len(bad_cond), "；".join(bad_cond[:4])),
               evidence="BLUEPRINT/menus.csv",
               hint="radio/checkbox 的选中条件必须写成「由哪个持久/草稿值决定」；"
                    "submenu/action 没有选中态，选中条件留 `-` 或写 `不适用：容器无选中态`")
    else:
        n_radio = len([r for r in rows if C.cell(r, "type").lower() in ("radio", "checkbox")])
        n_container = len([r for r in rows
                           if C.cell(r, "type").lower() in ("submenu", "action")])
        g.pass_("menu-conditions", "菜单条件按类型分级齐全且具体",
                expected="radio/checkbox 三列、submenu/action 显示+可用两列",
                actual="%d 个 radio/checkbox 三列齐全，%d 个 submenu/action 显示与可用齐全"
                       % (n_radio, n_container),
                evidence="BLUEPRINT/menus.csv")

    if bad_na_reason:
        g.fail("menu-na-reason", "写「不适用」必须给理由",
               expected="非选中态节点的选中条件写 `-`，或写 `不适用：<理由>`（≥6 字）",
               actual="%d 处只写占位没给理由：%s" % (
                   len(bad_na_reason), "；".join(bad_na_reason[:4])),
               evidence="BLUEPRINT/menus.csv",
               hint="要么留 `-`（表示确认不适用），要么写清为什么没有选中态；"
                    "只写「不适用」两个字的等于没说")
    else:
        g.pass_("menu-na-reason", "写「不适用」必须给理由",
                expected="不适用写法带理由",
                actual="未发现无理由的「不适用」", evidence="BLUEPRINT/menus.csv")

    _order_dup_check(g, rows)
    _default_item_advisory(g, rows)


def _order_dup_check(g, rows):
    """同级 order 必须唯一 —— 重复会让渲染顺序不确定。

    与 tools/blueprint_lint.py 的 MENU-ORDER-DUP 同口径，但这里升为 ERROR：
    lint 是体检（WARN 不阻断），门禁是放行（必须 FAIL）。Lead 在 examples 里
    踩过这个坑：M-SLOT-EMPTY 与 M-TZ-SUB 都是 order=1，渲染顺序变成不确定。
    """
    seen = {}          # (parent_id, order) -> (行号, node_id)
    dups = []
    for i, row in enumerate(rows, start=2):
        ntype = C.cell(row, "type").lower()
        if ntype in MENU_SKIP_TYPES:
            continue
        node = C.cell(row, "node_id") or "(第 %d 行)" % i
        parent = C.cell(row, "parent_id") or "ROOT"
        order = C.cell(row, "order")
        if C.is_blank(order):
            continue
        key = (parent, order)
        if key in seen:
            first_line, first_node = seen[key]
            dups.append("父节点 %s 下 order=%s 重复：%s（第 %d 行）与 %s（第 %d 行）"
                        % (parent, order, first_node, first_line, node, i))
        else:
            seen[key] = (i, node)
    if dups:
        g.fail("menu-order-dup", "同一父节点下 order 唯一",
               expected="按 parent_id 分组后，组内 order 值互不相同",
               actual="%d 处重复：%s" % (len(dups), "；".join(dups[:4])),
               evidence="BLUEPRINT/menus.csv",
               hint="同级顺序决定渲染顺序，重复 = 顺序不确定。改掉重复的 order，"
                    "并确认菜单实际显示顺序与 menus.csv 的 order 一致")
    else:
        g.pass_("menu-order-dup", "同一父节点下 order 唯一",
                expected="组内 order 互不相同",
                actual="%d 个节点、%d 组同级顺序全部唯一" % (
                    len([r for r in rows if C.cell(r, "type").lower() not in MENU_SKIP_TYPES]),
                    len(seen)),
                evidence="BLUEPRINT/menus.csv")


def _default_item_advisory(g, rows):
    """default_item（默认高亮项）的**建议**检查：只提示，不阻断。

    判定口径（SCHEMAS §4）：default_item 允许为 `-`。
    但 submenu 若含 radio 子节点，首次打开时的焦点落点应当明确，否则契约 §3
    「默认项与当前项」写不实。这里只出 PASS + 建议文本，绝不升级成 FAIL。
    """
    children_of = {}
    for row in rows:
        parent = C.cell(row, "parent_id")
        if parent:
            children_of.setdefault(parent, []).append(row)
    lacking = []
    for row in rows:
        if C.cell(row, "type").lower() != "submenu":
            continue
        node = C.cell(row, "node_id")
        kids = children_of.get(node, [])
        has_radio = any(C.cell(k, "type").lower() in ("radio", "checkbox") for k in kids)
        value = C.cell(row, "default_item")
        if has_radio and (C.is_blank(value) or value.strip().lower() in ("-", "n/a")):
            lacking.append(node)
    if lacking:
        g.pass_("menu-default-item", "菜单默认高亮项（建议项，不阻断）",
                expected="含 radio/checkbox 子节点的 submenu 建议填 default_item",
                actual="%d 个 submenu 未填（允许为 `-`，但建议写明首次打开的高亮项）：%s"
                       % (len(lacking), "、".join(lacking[:6])),
                evidence="BLUEPRINT/menus.csv",
                hint="在 menus.csv 的 default_item 列写默认高亮节点 ID（如 M-DATE-TODAY），"
                     "便于契约 §3「默认项与当前项」写实；本条只是建议，不影响 PASS/FAIL")
    else:
        g.pass_("menu-default-item", "菜单默认高亮项（建议项，不阻断）",
                expected="含 radio/checkbox 子节点的 submenu 建议填 default_item",
                actual="相关 submenu 均已明确默认项", evidence="BLUEPRINT/menus.csv")


def _linkage_checks(g, ctx):
    rows = g.read_csv("BLUEPRINT/linkage.csv", C.LINKAGE_COLUMNS,
                      "linkage-columns", "linkage.csv 列名与 SCHEMAS §5 一致",
                      allow_missing=True)
    if rows is None:
        return
    bad, bad_na = [], []
    for i, row in enumerate(rows, start=2):
        lid = C.cell(row, "link_id") or "(第 %d 行)" % i
        status = C.cell(row, "status").lower()
        if status not in C.LINKAGE_STATUS:
            bad.append("%s status=%r 非法（只允许 pending/wired/verified/na）"
                       % (lid, C.cell(row, "status")))
        if C.is_blank(C.cell(row, "refresh_timing")):
            bad.append("%s 缺 refresh_timing" % lid)
        if status in C.LINKAGE_NA_STATUS:
            # na 行：test_ref 允许 `-`，但必须写清「不适用在哪」与理由
            if C.is_blank(C.cell(row, "affected_control")):
                bad.append("%s 是 na 但缺 affected_control（要写「不适用：<哪一面不发生活动>」）" % lid)
            reason = C.cell(row, "state_handling")
            if C.is_blank(reason) or len(reason.strip()) < 6:
                bad_na.append("%s 是 na 但 state_handling 没写理由" % lid)
        else:
            if C.is_blank(C.cell(row, "test_ref")):
                bad.append("%s 缺 test_ref（只有 na 行可以填 `-`）" % lid)
    if bad:
        g.fail("linkage-rows", "每条联动有刷新时点、测试号与合法状态",
               expected="refresh_timing 非空；wired/verified/pending 的 test_ref 非空；"
                        "na 行允许 test_ref=`-` 但必须有 affected_control；"
                        "status ∈ pending/wired/verified/na",
               actual="%d 处问题：%s" % (len(bad), "；".join(bad[:5])),
               evidence="BLUEPRINT/linkage.csv",
               hint="每条联动写清「什么时候刷新」与「哪条测试证明它真的联动了」；"
                    "确认不受影响的那一面写 status=na + 理由，不要省略")
    else:
        na_count = len([r for r in rows if C.cell(r, "status").lower() in C.LINKAGE_NA_STATUS])
        g.pass_("linkage-rows", "每条联动有刷新时点、测试号与合法状态",
                expected="refresh_timing/test_ref 齐、status 合法（na 可有条件豁免 test_ref）",
                actual="%d 条联动齐全（其中 %d 条 na）" % (len(rows), na_count),
                evidence="BLUEPRINT/linkage.csv")

    if bad_na:
        g.fail("linkage-na-reason", "na 行必须写清不适用的理由",
               expected="status=na 的行在 state_handling 写「不适用：<理由>」（≥6 字）",
               actual="%d 处问题：%s" % (len(bad_na), "；".join(bad_na[:4])),
               evidence="BLUEPRINT/linkage.csv",
               hint="na 是「想过之后确认不受影响」，必须在 state_handling 写清为什么；"
                    "直接省略那一面才是错的")
    else:
        g.pass_("linkage-na-reason", "na 行必须写清不适用的理由",
                expected="na 行带理由",
                actual="na 行理由齐全", evidence="BLUEPRINT/linkage.csv")

    # 六面覆盖：must 功能 ≥1 行；wired/verified 的面 ≥1（na 计入「已考虑」）
    targets = C.must_features(ctx)
    for row in targets:
        fid = C.cell(row, "feature_id")
        mine = [r for r in rows if C.cell(r, "source_id") == fid]
        if not mine:
            g.fail("linkage-six-face", "%s 有跨页面联动条目" % fid,
                   expected="每个 must 功能在 linkage.csv 至少 1 行",
                   actual="0 行", evidence="BLUEPRINT/linkage.csv",
                   hint="列出这个功能影响到的六个面（%s）；"
                        "确认不受影响的面写 status=na + 理由，而不是一行都不写"
                        % C.face_names_text())
            continue
        analysis = C.linkage_faces(mine)
        covered = [C.face_name(k) for k in analysis["covered"]]
        considered = [C.face_name(k) for k in analysis["considered"]]
        na_faces = [C.face_name(k) for k in analysis["considered"]
                    if k not in analysis["covered"]]
        if analysis["all_na"]:
            g.fail("linkage-six-face", "%s 六面覆盖（至少一面真接线）" % fid,
                   expected="至少 1 面 status=wired/verified",
                   actual="%d 行全部为 na，没有任何一面真正接线（已考虑：%s）"
                          % (len(mine), "、".join(considered) or "无法归类"),
                   evidence="BLUEPRINT/linkage.csv",
                   hint="六面全 na 等同于没做联动分析（R18/SCHEMAS §5 明文禁止）。"
                        "要么真的接上至少一面，要么把这个功能降回 partial")
        else:
            g.pass_("linkage-six-face", "%s 六面覆盖（%d 面接线 / %d 面已考虑）"
                    % (fid, len(covered), len(considered)),
                    expected="至少 1 面 wired/verified；na 需给理由",
                    actual="接线：%s；不适用：%s" % (
                        "、".join(covered) or "-", "、".join(na_faces) or "-"),
                    evidence="BLUEPRINT/linkage.csv")


def _flows_checks(g, ctx):
    text = ctx.text("BLUEPRINT/flows.md")
    if text is None:
        g.fail("flows", "flows.md 每个流程四段齐全",
               expected="每个 FL-xx 含 正常路径/失败与取消/边界/恢复",
               actual="flows.md 不存在", evidence="BLUEPRINT/flows.md",
               hint="按 SCHEMAS §7 的固定结构写流程")
        return
    sections = [s for s in C.md_sections(text, 2)
                if s["title"].upper().startswith("FL-")]
    if not sections:
        g.fail("flows", "flows.md 每个流程四段齐全",
               expected="至少 1 个 `## FL-xx` 流程",
               actual="没有找到 FL- 开头的二级标题",
               evidence="BLUEPRINT/flows.md",
               hint="按 SCHEMAS §7 写流程：目标/起点/路径/点击数 + 四段子结构")
        return
    keywords = ["正常路径", "失败与取消", "边界", "恢复"]
    for sec in sections:
        titles = [t for lvl, t, _no in C.md_headings(sec["body"]) if lvl >= 3]
        missing = [k for k in keywords if not any(k in t for t in titles)]
        fl = sec["title"].split()[0]
        if missing:
            g.fail("flows", "%s 的四段子结构齐全" % fl,
                   expected="子标题含：%s" % " / ".join(keywords),
                   actual="缺：%s" % "、".join(missing),
                   evidence="BLUEPRINT/flows.md:%d" % sec["line"],
                   hint="每个流程都要写清正常路径、失败与取消、边界（跨月/闰日/时区/全天）、恢复")
        else:
            g.pass_("flows", "%s 的四段子结构齐全" % fl,
                    expected="四段子标题齐全",
                    actual="%s" % " / ".join(keywords),
                    evidence="BLUEPRINT/flows.md:%d" % sec["line"])


def _state_and_data_checks(g, ctx):
    text = ctx.text("BLUEPRINT/state-machines.md")
    if text is None:
        g.fail("state-machines", "state-machines.md 存在且非模板占位",
               expected="文件存在，含 SM-xx 状态机与转换表",
               actual="文件不存在", evidence="BLUEPRINT/state-machines.md",
               hint="按 SCHEMAS §9 写 状态 / 转换 / 非法转换 三张表")
    else:
        sm_ids = sorted(set(re.findall(r"\bSM-\d+\b", text)))
        placeholders = C.find_placeholders(text, C.TEMPLATE_PLACEHOLDERS)
        tables = C.md_tables(text)
        problems = []
        if not sm_ids:
            problems.append("没有 SM-xx 编号")
        if not tables:
            problems.append("没有状态/转换表")
        if placeholders:
            problems.append("含占位词 %s" % "、".join(sorted({t for t, _ in placeholders})))
        if problems:
            g.fail("state-machines", "state-machines.md 存在且非模板占位",
                   expected="含 SM-xx、状态表、转换表、非法转换表，无占位词",
                   actual="；".join(problems), evidence="BLUEPRINT/state-machines.md",
                   hint="按 SCHEMAS §9 补齐；模板占位不算内容")
        else:
            g.pass_("state-machines", "state-machines.md 存在且非模板占位",
                    expected="SM-xx + 表格",
                    actual="%d 个状态机、%d 张表" % (len(sm_ids), len(tables)),
                    evidence="BLUEPRINT/state-machines.md")

    text = ctx.text("BLUEPRINT/data-dictionary.md")
    if text is None:
        g.fail("data-dictionary", "data-dictionary.md 存在且非模板占位",
               expected="文件存在，含 E01 实体与字段表",
               actual="文件不存在", evidence="BLUEPRINT/data-dictionary.md",
               hint="按 SCHEMAS §10 写实体与字段表")
    else:
        entities = sorted(set(re.findall(r"\bE(\d{2})\b", text)))
        tables = C.md_tables(text)
        has_field_table = any(any("字段" in h or "field" in h.lower() for h in t["header"])
                              for t in tables)
        placeholders = C.find_placeholders(text, C.TEMPLATE_PLACEHOLDERS)
        problems = []
        if not entities:
            problems.append("没有 E01 这类实体编号")
        if not has_field_table:
            problems.append("没有含「字段」列的实体表")
        if placeholders:
            problems.append("含占位词 %s" % "、".join(sorted({t for t, _ in placeholders})))
        if problems:
            g.fail("data-dictionary", "data-dictionary.md 存在且非模板占位",
                   expected="含 E01.. 实体编号、字段表，无占位词",
                   actual="；".join(problems), evidence="BLUEPRINT/data-dictionary.md",
                   hint="按 SCHEMAS §10 补实体与字段（含来源：原版观察/推断）")
        else:
            g.pass_("data-dictionary", "data-dictionary.md 存在且非模板占位",
                    expected="实体 + 字段表",
                    actual="%d 个实体、%d 张表" % (len(entities), len(tables)),
                    evidence="BLUEPRINT/data-dictionary.md")


def check(ctx):
    g = C.Gate(ctx, STAGE)
    if g.no_manifest():
        return g.results

    # ---- 1. 契约节数配置 ----
    try:
        configured = int(str(ctx.required.get("contract_sections", 16)).strip())
    except (TypeError, ValueError):
        configured = -1
    if configured == len(C.CONTRACT_HEADINGS):
        g.pass_("contract-config", "manifest 契约节数与 SCHEMAS 一致",
                expected="contract_sections = %d" % len(C.CONTRACT_HEADINGS),
                actual=str(configured), evidence=C.Context.MANIFEST_REL)
    else:
        g.fail("contract-config", "manifest 契约节数与 SCHEMAS 一致",
               expected="contract_sections = %d（SCHEMAS §8）" % len(C.CONTRACT_HEADINGS),
               actual="required.contract_sections = %r" % ctx.required.get("contract_sections"),
               evidence=C.Context.MANIFEST_REL,
               hint="改成 16；节数由 SCHEMAS 定义，不允许项目自己减节")
    headings = (C.CONTRACT_HEADINGS[:configured]
                if 0 < configured <= len(C.CONTRACT_HEADINGS) else C.CONTRACT_HEADINGS)

    # ---- 2/3. 契约覆盖率与 16 节 ----
    _contract_coverage(g, ctx)
    _contract_checks(g, ctx, headings)

    # ---- 4/5. 菜单 ----
    _menu_checks(g, ctx)

    # ---- 6/7. 联动 ----
    _linkage_checks(g, ctx)

    # ---- 8. 流程 ----
    _flows_checks(g, ctx)

    # ---- 9. 状态机与数据字典 ----
    _state_and_data_checks(g, ctx)

    return g.results
