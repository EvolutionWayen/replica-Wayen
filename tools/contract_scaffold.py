#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""contract_scaffold.py —— 契约骨架生成（把「写契约」这件大事拆成 16 个填空题）

生成的文件严格遵守 templates/blueprint/SCHEMAS.md §8：
  - 一级标题 `# C-F-xxx · <功能名>`
  - 16 个二级标题，文字与 SCHEMAS 逐字一致（门禁按标题匹配）
  - 每节正文是该节的「必须写什么」（摘自 SCHEMAS §8 表格）+ 一条具体反例
  - 空位填 `待填`，方便 grep 出还差多少

每节注释里的指引来自 SCHEMAS §8，反例来自本地实践（00 §10 与 前期细节蓝图 §3）。

用法：
    # 单个
    python3 tools/contract_scaffold.py --feature F-DATE-EDIT --name "修改日期" --out BLUEPRINT/contracts/
    # 批量：为 features.csv 里所有还没有契约的行生成
    python3 tools/contract_scaffold.py --all --project .
    # 只为 must 功能生成
    python3 tools/contract_scaffold.py --all --project . --only-must
    # 预演，不写盘
    python3 tools/contract_scaffold.py --all --project . --dry-run

退出码：0 生成成功（或无需生成）／1 有意跳过（文件已存在且未 --force）／2 输入错误
"""

from __future__ import annotations

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import replica_common as rc  # noqa: E402

TOOL = "contract_scaffold"
FEATURES_REL = os.path.join("BLUEPRINT", "features.csv")
DEFAULT_OUT = os.path.join("BLUEPRINT", "contracts")

FEATURE_ID_RE = re.compile(r"^F-[A-Z0-9]+(?:-[A-Z0-9]+)*$")

PLACEHOLDER = "待填"


def contract_id(feature_id):
    """F-DATE-EDIT → C-F-DATE-EDIT"""
    return "C-" + feature_id


def contract_filename(feature_id):
    return contract_id(feature_id) + ".md"


def render_contract(feature_id, name, schema, area="", evidence="", notes=""):
    cid = contract_id(feature_id)
    lines = []
    lines.append("# %s · %s" % (cid, name or PLACEHOLDER))
    lines.append("")
    lines.append("> 骨架由 `tools/contract_scaffold.py` 生成。每节按注释里的「必须写什么」填；"
                 "不确定就登记 `BLUEPRINT/unknowns.csv`，**不要留「待填」**——"
                 "`tools/blueprint_lint.py` 会把占位词判为 ERROR。")
    lines.append(">")
    lines.append("> 功能 ID：`%s`　所属：%s　证据：%s"
                 % (feature_id, area or "-", evidence or "-"))
    lines.append(">")
    lines.append("> 填写纪律（00 §附录A）：不许出现 `按原版`/`TBD`/`待定`/`视情况`/`同前`；"
                 "不许写「界面刷新」这种没法验收的话；"
                 "确实不适用的节，正文以 `N/A：<理由>` 开头。")
    lines.append("")
    for sec in schema.sections:
        title = sec["title"]
        desc = sec["desc"] or next(
            (d for t, d in rc.BUILTIN_SECTIONS if t == title), "")
        anti = rc.SECTION_ANTI_EXAMPLES.get(title, "")
        lines.append("## %s" % title)
        lines.append("")
        lines.append("<!-- 必须写什么：%s -->" % (desc or "见 SCHEMAS §8"))
        if anti:
            lines.append("<!-- 反例：%s -->" % anti)
        lines.append("")
        lines.append("- %s" % build_prompt(title))
        lines.append("")
    if notes:
        lines.append("<!-- features.csv notes：%s -->" % notes)
        lines.append("")
    return "\n".join(lines)


def build_prompt(title):
    """每节的第一个待填项，写成一句可直接回答的问句（比裸「待填」有用得多）。"""
    prompts = {
        "1 目标与入口": "待填：用户想达成什么？全部入口（按钮/快捷键/右键/拖拽/深链）分别是哪些？",
        "2 界面与层级": "待填：控件从上到下的顺序、浮层/子菜单关系、可滚动区、宽度与高度策略",
        "3 每个菜单选项": "待填：逐项列表（完整路径 → 顺序 → 类型 → 默认项/当前项 → 打开关闭行为 → 键盘行为）",
        "4 显示条件": "待填：出现条件（写成可判定的表达式或明确数据状态）；隐藏后布局与焦点如何变化",
        "5 可用与选择条件": "待填：可用条件 + 禁用时的解释；选中条件由哪个持久值/草稿值决定；互斥与组合",
        "6 筛选条件": "待填：AND/OR 与嵌套优先级、包含/排除、空值、边界日期与时区、排序、分组、角标口径",
        "7 业务实现逻辑": "待填：规则求值顺序、默认规则、参数、校验、算法边界（不许只写“调用某服务”）",
        "8 具体效果": "待填：每步操作后的文案/数值/位置/列表成员/计数/反馈（要能被具体输入复算）",
        "9 状态变化": "待填：原状态 → 事件 → 条件 → 目标状态 → 副作用；加载/保存中/失败/冲突/重试/取消/撤销",
        "10 数据读取": "待填：实体.字段来源、查询条件、派生值、数据新鲜度、空库与异常库行为",
        "11 数据写入": "待填：命令与参数、精确字段、事务范围、约束、写入时点、完成信号、失败保留、必须不变的字段",
        # 六面名不写死：来自 shared/faces.json（见 replica_common.load_faces）
        "12 跨页面联动": "待填：六面（%s）逐面写影响 + 刷新时点 + LK 编号"
                        % rc.faces_brief(),
        "13 并发与生命周期": "待填：快速连点、重复提交、A→B 切换、迟到结果、防抖、关窗、Cmd+Q、重启、睡眠唤醒",
        "14 撤销与恢复": "待填：恢复哪些值、窗口期、连续编辑处理、保存失败重试、误操作保护",
        "15 体验标准": "待填：输入法组合、焦点返回、Esc/Enter、可访问性、布局稳定、动效、性能起止点",
        "16 测试与证据": "待填：正常/负向/边缘/跨页面/立即退出重启的用例号 + 断言的具体值（截图不算落库证据）",
    }
    return prompts.get(title, "待填")


def load_features(project):
    path = os.path.join(project, FEATURES_REL)
    if not os.path.isfile(path):
        raise rc.ToolError("缺 %s" % FEATURES_REL,
                           "先跑 S1 产出 features.csv；或单独用 --feature/--name 指定")
    schema = rc.load_schema(project)
    rows, issues = rc.read_csv_table(path, schema.columns["features"])
    hard = [i for i in issues if i["level"] == "ERROR"]
    if hard:
        raise rc.ToolError("features.csv 表头有问题：%s" % "；".join(i["message"] for i in hard),
                           "列名与顺序照 templates/blueprint/SCHEMAS.md §2")
    return rows


def resolve_out(project, out):
    target = out or DEFAULT_OUT
    return target if os.path.isabs(target) else os.path.join(project, target)


def write_contract(path, content, force):
    if os.path.exists(path) and not force:
        return False, "已存在，未覆盖（要覆盖加 --force）"
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)
    return True, "已写入 %d 行" % content.count("\n")


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="contract_scaffold.py",
        description="契约骨架生成：16 节标题齐全，每节带「必须写什么 / 反例」注释，正文填待填占位",
        epilog=("示例：\n"
                "  python3 tools/contract_scaffold.py --feature F-DATE-EDIT --name \"修改日期\" --out BLUEPRINT/contracts/\n"
                "  python3 tools/contract_scaffold.py --all --project . --only-must"),
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", default=".", help="项目根目录（默认当前目录）")
    ap.add_argument("--feature", default="", help="功能 ID，如 F-DATE-EDIT")
    ap.add_argument("--name", default="", help="功能名（中文），默认从 features.csv 取")
    ap.add_argument("--area", default="", help="所属屏幕/模块（可选）")
    ap.add_argument("--out", default="", help="输出目录或文件，默认 BLUEPRINT/contracts/")
    ap.add_argument("--all", action="store_true", help="从 features.csv 批量生成缺失契约")
    ap.add_argument("--only-must", action="store_true", help="--all 时只处理 must 功能")
    ap.add_argument("--force", action="store_true", help="覆盖已存在的契约文件")
    ap.add_argument("--dry-run", action="store_true", help="只打印会写哪些文件，不落盘")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args(argv)

    if not args.all and not args.feature:
        return rc.die(rc.ToolError("必须指定 --feature 或 --all",
                                   "例：--feature F-DATE-EDIT --name \"修改日期\""))

    if not os.path.isdir(args.project):
        return rc.die(rc.ToolError("项目目录不存在：%s" % args.project, "确认路径"))

    schema = rc.load_schema(args.project)
    if schema.warnings:
        for w in schema.warnings:
            print("  ⚠ %s" % w, file=sys.stderr)

    out_dir = resolve_out(args.project, args.out)
    results = []

    if args.all:
        try:
            rows = load_features(args.project)
        except rc.ToolError as exc:
            return rc.die(exc)
        if not rows:
            return rc.die(rc.ToolError("features.csv 没有数据行",
                                       "先把功能清单列出来，再批量生成契约"))
        made = skipped = 0
        for r in rows:
            fid = rc.cell(r, "feature_id")
            if not fid or not FEATURE_ID_RE.match(fid):
                results.append({"feature_id": fid or "(空)", "status": "skip",
                                "reason": "ID 为空或格式不对，先修 features.csv"})
                skipped += 1
                continue
            prio = rc.cell(r, "priority").lower()
            scope = rc.cell(r, "scope").lower()
            if args.only_must and not (prio in ("must", "p0") and scope in ("in", "")):
                continue
            if rc.is_filled(rc.cell(r, "contract_ref")):
                existing = rc.cell(r, "contract_ref")
                base = os.path.basename(existing)
                cand = os.path.join(args.project, existing) if not existing.startswith("BLUEPRINT") \
                    else os.path.join(args.project, existing)
                if os.path.isfile(cand) or os.path.isfile(os.path.join(out_dir, base)):
                    results.append({"feature_id": fid, "status": "skip",
                                    "reason": "contract_ref 已指向存在的文件：%s" % existing})
                    skipped += 1
                    continue
            fname = contract_filename(fid)
            path = os.path.join(out_dir, fname) if os.path.isdir(out_dir) or not out_dir.endswith(".md") \
                else out_dir
            content = render_contract(fid, rc.cell(r, "feature"), schema,
                                      area=rc.cell(r, "area"),
                                      evidence=rc.cell(r, "evidence"),
                                      notes=rc.cell(r, "notes"))
            if args.dry_run:
                results.append({"feature_id": fid, "path": path, "status": "dry-run",
                                "lines": content.count("\n")})
                made += 1
                continue
            ok, msg = write_contract(path, content, args.force)
            results.append({"feature_id": fid, "path": path,
                            "status": "created" if ok else "skip", "reason": msg,
                            "lines": content.count("\n")})
            made += 1 if ok else 0
            skipped += 0 if ok else 1
        summary = {"created": made, "skipped": skipped, "out_dir": out_dir}
    else:
        fid = args.feature.strip()
        if not FEATURE_ID_RE.match(fid):
            return rc.die(rc.ToolError("功能 ID 格式不对：%s" % fid,
                                       "应为 F-域-短名，全大写连字符，例 F-DATE-EDIT（00 §4）"))
        name = args.name.strip()
        area = args.area.strip()
        evidence = notes = ""
        if not name and os.path.isfile(os.path.join(args.project, FEATURES_REL)):
            try:
                for r in load_features(args.project):
                    if rc.cell(r, "feature_id") == fid:
                        name = rc.cell(r, "feature")
                        area = area or rc.cell(r, "area")
                        evidence = rc.cell(r, "evidence")
                        notes = rc.cell(r, "notes")
                        break
            except rc.ToolError:
                pass
        if not name:
            name = PLACEHOLDER
        fname = contract_filename(fid)
        path = out_dir if out_dir.endswith(".md") else os.path.join(out_dir, fname)
        content = render_contract(fid, name, schema, area=area,
                                  evidence=evidence, notes=notes)
        if args.dry_run:
            results.append({"feature_id": fid, "path": path, "status": "dry-run",
                            "lines": content.count("\n")})
            summary = {"created": 1, "skipped": 0, "out_dir": os.path.dirname(path)}
        else:
            ok, msg = write_contract(path, content, args.force)
            results.append({"feature_id": fid, "path": path,
                            "status": "created" if ok else "skip", "reason": msg,
                            "lines": content.count("\n")})
            summary = {"created": 1 if ok else 0, "skipped": 0 if ok else 1,
                       "out_dir": os.path.dirname(path)}

    if args.json:
        rc.print_json({
            "tool": TOOL,
            "project": os.path.abspath(args.project),
            "schema_source": schema.source,
            "sections": len(schema.sections),
            "dry_run": args.dry_run,
            "summary": summary,
            "results": results,
            "__RESULT__": "scaffold created=%d skipped=%d sections=%d"
                          % (summary["created"], summary["skipped"], len(schema.sections)),
        })
    else:
        print("契约骨架生成 · 16 节来源：%s" % (schema.source or "内置常量"))
        print("输出目录：%s%s" % (summary["out_dir"], "（预演，未写盘）" if args.dry_run else ""))
        print("")
        for r in results:
            if r["status"] == "created":
                print("  ✓ %s → %s（%d 行）" % (r["feature_id"], r["path"], r.get("lines", 0)))
            elif r["status"] == "dry-run":
                print("  · 将生成 %s → %s（%d 行）" % (r["feature_id"], r["path"], r.get("lines", 0)))
            else:
                print("  - 跳过 %s：%s" % (r["feature_id"], r.get("reason", "")))
        print("")
        print("下一步：")
        print("  1. 逐节把「待填」换成真实内容（每节注释里写了必须写什么 + 反例）")
        print("  2. 不确定的先登记 BLUEPRINT/unknowns.csv，别在契约里写「待定」")
        print("  3. 生成完跑：python3 tools/blueprint_lint.py --project . --fix-hints")
        if summary["created"] == 0 and summary["skipped"]:
            print("  （没有任何文件被创建：都跳过了。要覆盖已存在的文件加 --force）")

    return 0 if summary["created"] or args.dry_run or not results else 1


if __name__ == "__main__":
    sys.exit(main())
