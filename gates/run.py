#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""统一门禁引擎（Replica OS v2）—— 唯一入口。

用法：
    python3 gates/run.py --project <dir>                 # 全部 12 道门
    python3 gates/run.py --project <dir> --stage G2       # 单门
    python3 gates/run.py --project <dir> --stage all --json
    python3 gates/run.py --project <dir> --verbose        # 附期望/实际/证据全文

退出码：
    0 = 全 PASS（NA 允许）
    1 = 有 FAIL
    2 = 无 FAIL 但有 BLOCKED

末行固定：__RESULT__ pass=N fail=M blocked=K na=J

设计纪律（00-体系总纲.md §10-16 / §3）：
- 不写死任何项目路径或数字：阈值、可选路径全部来自 <项目>/.replica/gate.manifest.yml。
- 缺 manifest 不崩溃：所有门 BLOCKED，退出码 2，并提示怎么补。
- 规则里抛异常 → 转成 FAIL（附 hint），绝不把栈抛给用户。
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from rules import common as C  # noqa: E402

STAGE_ORDER = ["G%d" % i for i in range(12)]
STAGE_NAMES = {
    "G0": "立项与边界",
    "G1": "取证 recon",
    "G2": "行为蓝图",
    "G3": "审查与冻结",
    "G4": "架构",
    "G5": "设计系统",
    "G6": "联动门",
    "G7": "后端与本地能力",
    "G8": "测试",
    "G9": "一致性评分",
    "G10": "痛点与差异化",
    "G11": "发布",
}

COLORS = {
    C.PASS: "\033[32m", C.FAIL: "\033[31m", C.BLOCKED: "\033[33m", C.NA: "\033[36m",
}
RESET = "\033[0m"


# ---------------------------------------------------------------------------
# 加载规则
# ---------------------------------------------------------------------------

def load_rules():
    """动态导入 rules/g0..g11，返回 {stage: check_fn}。缺模块时不崩，记错误。"""
    mods, errors = {}, {}
    for stage in STAGE_ORDER:
        name = "rules.g%s" % stage[1:]
        try:
            module = importlib.import_module(name)
            check = getattr(module, "check", None)
            if not callable(check):
                errors[stage] = "%s 没有暴露 check(ctx)" % name
                continue
            mods[stage] = check
        except Exception as exc:  # 导入失败：门级 FAIL，不影响其它门
            errors[stage] = "导入 %s 失败：%s" % (name, exc)
    return mods, errors


# ---------------------------------------------------------------------------
# 运行
# ---------------------------------------------------------------------------

def run_stage(stage, check, ctx):
    """跑一道门，兜住一切异常。"""
    try:
        results = check(ctx) or []
        cleaned = []
        for item in results:
            if not isinstance(item, C.Result):
                cleaned.append(C.Result.fail(
                    stage, "%s.shape" % stage, "规则返回值类型合法", expected="Result 实例",
                    actual=type(item).__name__,
                    hint="规则模块必须返回 list[Result]"))
                continue
            if not item.stage:
                item.stage = stage
            cleaned.append(item)
        return cleaned
    except Exception as exc:
        detail = "".join(traceback.format_exception_only(type(exc), exc)).strip()
        return [C.Result.fail(
            stage, "%s.crash" % stage, "规则执行不中断",
            expected="规则正常返回判定结果",
            actual="%s" % detail,
            hint=("这是门禁自身的 bug，不是项目的问题。请把这条报给门禁维护者；"
                  "常见原因是项目文件格式异常（%s: %s）"
                  % (os.path.basename(HERE), exc)),
        )]


def build_context(project):
    root = os.path.abspath(project)
    manifest, err = C.load_manifest(root)
    return C.Context(root, manifest=manifest, manifest_error=err)


def summarize(results):
    counts = {C.PASS: 0, C.FAIL: 0, C.BLOCKED: 0, C.NA: 0}
    for item in results:
        counts[item.status] = counts.get(item.status, 0) + 1
    return counts


def fmt_result_line(item, verbose, use_color):
    status = item.status
    label = "[%s]" % status
    if use_color and sys.stdout.isatty():
        label = "%s%s%s" % (COLORS.get(status, ""), label, RESET)
    parts = [label, item.code]
    if item.title:
        parts.append(item.title)
    if verbose or status in (C.FAIL, C.BLOCKED):
        if item.expected:
            parts.append("期望: %s" % item.expected)
        if item.actual:
            parts.append("实际: %s" % item.actual)
        if item.evidence:
            parts.append("证据: %s" % item.evidence)
    if item.blocked_reason and status == C.BLOCKED and not verbose:
        parts.append("原因: %s" % item.blocked_reason)
    if verbose and item.blocked_reason and status == C.BLOCKED:
        parts.append("阻塞: %s" % item.blocked_reason)
    hint = item.hint
    if hint and (verbose or status in (C.FAIL, C.BLOCKED, C.NA)):
        parts.append("修复: %s" % hint)
    return "  ".join(parts)


def print_manifest_hint(ctx):
    print()
    print("  【如何补齐】")
    print("   1) 新建项目骨架（推荐）：")
    print("      ./scripts/new-project.sh <目录> --target \"<制品名 版本>\" --tier A")
    print("   2) 或手写 .replica/gate.manifest.yml（格式见 templates/blueprint/SCHEMAS.md §15）：")
    print("      project: <名字>")
    print("      tier: A")
    print("      thresholds: {parity_feature: 80, consecutive_runs: 3}")
    print("      required: {evidence_dirs: [evidence, screens], contract_sections: 16}")
    print("      na_approved: []")
    print("   （manifest 是门禁的唯一配置来源；缺它时门禁无法判定阈值，只能 BLOCKED。）")


def print_text(ctx, stages, by_stage, counts, errors):
    total = sum(counts.values())
    print("=" * 78)
    print("门禁报告 · %s" % ctx.root)
    if ctx.manifest_found:
        tier = ctx.tier or "?"
        thr = ctx.thresholds
        print("  档位 %s · 目标 %s · 连跑门槛 %d 次 · 功能分门槛 %d"
              % (tier, ctx.manifest.get("target") or "-",
                 thr["consecutive_runs"], thr["parity_feature"]))
    else:
        print("  ⚠ manifest 不可用：%s" % (ctx.manifest_error or "未找到"))
    print("=" * 78)

    for stage in stages:
        results = by_stage.get(stage, [])
        stage_counts = summarize(results)
        if not results and stage not in errors:
            continue
        head = "── %s %s " % (stage, STAGE_NAMES.get(stage, ""))
        head = head + "─" * max(0, 70 - len(head))
        print("\n" + head)
        tail = "  (%d PASS / %d FAIL / %d BLOCKED / %d NA)" % (
            stage_counts[C.PASS], stage_counts[C.FAIL],
            stage_counts[C.BLOCKED], stage_counts[C.NA])
        print(tail.lstrip() and "  小结：" + tail.strip())
        if stage in errors:
            print("  [FAIL] %s : %s" % (stage, errors[stage]))
        for item in results:
            print("  " + fmt_result_line(item, VERBOSE, True).replace("\n", "\n  "))

    print()
    print("-" * 78)
    print("合计：%d 项判定 · PASS %d / FAIL %d / BLOCKED %d / NA %d"
          % (total, counts[C.PASS], counts[C.FAIL], counts[C.BLOCKED], counts[C.NA]))
    if counts[C.FAIL]:
        print("结论：不通过。先修 FAIL —— 每条后面都有证据路径与修复动作。")
    elif counts[C.BLOCKED]:
        print("结论：被阻塞。BLOCKED ≠ PASS（R20）：补齐 manifest / 结果文件 / 依赖后重跑。")
    elif total == 0:
        print("结论：没有任何判定。检查 --stage 参数与项目目录。")
    else:
        print("结论：全 PASS（NA 已带理由）。可以进入下一阶段。")
    if not ctx.manifest_found:
        print_manifest_hint(ctx)


def check_na_approved(ctx, results):
    """R20：NA 必须在 manifest.na_approved 里登记（缺 manifest 时跳过）。"""
    if not ctx.manifest_found or not ctx.strict_na:
        return
    approved = ctx.na_approved
    for item in results:
        if item.status != C.NA:
            continue
        if item.code in approved:
            entry = approved[item.code] or {}
            if isinstance(entry, dict):
                item.hint = (item.hint + "；" if item.hint else "") + \
                    "已批准：%s（%s）" % (entry.get("approved_by") or "?",
                                        entry.get("approved_at") or "?")
            continue
        item.ok = False
        item.blocked_reason = ""
        if "未在 na_approved 登记" not in item.hint:
            item.hint = (item.hint + "；" if item.hint else "") + (
                "N/A 必须在 .replica/gate.manifest.yml 的 na_approved 里带理由与批准人（R20）")


def main(argv=None):
    global VERBOSE
    ap = argparse.ArgumentParser(
        prog="gates/run.py",
        description="Replica OS v2 统一门禁：12 道门，manifest 驱动，末行输出 __RESULT__。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="退出码：0 全 PASS（NA 允许）/ 1 有 FAIL / 2 只有 BLOCKED",
    )
    ap.add_argument("--project", default=".", help="项目目录（默认当前目录）")
    ap.add_argument("--stage", default="all",
                    help="all 或单门 G0..G11（也接受 g2）")
    ap.add_argument("--json", action="store_true", help="机读输出")
    ap.add_argument("--verbose", "-v", action="store_true", help="输出期望/实际/证据全文")
    ap.add_argument("--list", action="store_true", help="列出 12 道门与判定项标题后退出")
    args = ap.parse_args(argv)
    VERBOSE = args.verbose

    rules, load_errors = load_rules()

    if args.list:
        for stage in STAGE_ORDER:
            print("%s  %s" % (stage, STAGE_NAMES.get(stage, "")))
        return 0

    stage_arg = str(args.stage or "all").strip()
    if stage_arg.lower() == "all":
        stages = list(STAGE_ORDER)
    else:
        key = stage_arg.upper()
        if key not in STAGE_ORDER:
            msg = "未知阶段：%s（可用：all, %s）" % (stage_arg, ", ".join(STAGE_ORDER))
            if args.json:
                print(json.dumps({"error": msg, "summary": {}, "results": [], "stages": {}},
                                 ensure_ascii=False, indent=2))
            else:
                # 用户可见的错误必须进 stdout，否则管道/重定向下会丢失
                print(msg)
            print("__RESULT__ pass=0 fail=0 blocked=0 na=0")
            return 2
        stages = [key]

    if not os.path.isdir(args.project):
        msg = "项目目录不存在或不是目录：%s" % os.path.abspath(args.project)
        if args.json:
            print(json.dumps({"error": msg, "summary": {}, "results": [], "stages": {}},
                             ensure_ascii=False, indent=2))
        else:
            print(msg, file=sys.stderr)
            print("提示：用 --project <目录> 指向项目根（含 .replica/gate.manifest.yml 的那层）")
        print("__RESULT__ pass=0 fail=0 blocked=1 na=0")
        return 2

    ctx = build_context(args.project)
    by_stage, all_results = {}, []
    for stage in stages:
        if stage in load_errors:
            results = [C.Result.fail(stage, "%s.module" % stage, "规则模块可用",
                                     expected="rules/g%s.py 暴露 check(ctx)" % stage[1:],
                                     actual=load_errors[stage],
                                     hint="检查 gates/rules/ 下该模块的语法与函数名")]
        else:
            results = run_stage(stage, rules[stage], ctx)
        # manifest 缺失时：统一把所有非 BLOCKED 的判定折叠为 BLOCKED（不许假 FAIL 也不许假 PASS）
        if not ctx.manifest_found:
            for item in results:
                if item.status != C.BLOCKED:
                    item.ok = None
                    item.blocked_reason = ctx.manifest_error or "manifest 缺失"
                    item.hint = ("先补 .replica/gate.manifest.yml："
                                 "运行 scripts/new-project.sh <目录> --target \"<制品名 版本>\"")
        by_stage[stage] = results
        all_results.extend(results)

    check_na_approved(ctx, all_results)
    counts = summarize(all_results)
    exit_code = 1 if counts[C.FAIL] else (2 if counts[C.BLOCKED] else 0)

    if args.json:
        payload = {
            "project": str(ctx.root),
            "manifest_found": ctx.manifest_found,
            "manifest_path": C.Context.MANIFEST_REL,
            "tier": ctx.tier or None,
            "thresholds": ctx.thresholds,
            "stages": {
                stage: {
                    "name": STAGE_NAMES.get(stage, ""),
                    "summary": {
                        "pass": summarize(by_stage.get(stage, []))[C.PASS],
                        "fail": summarize(by_stage.get(stage, []))[C.FAIL],
                        "blocked": summarize(by_stage.get(stage, []))[C.BLOCKED],
                        "na": summarize(by_stage.get(stage, []))[C.NA],
                    },
                } for stage in stages
            },
            "summary": {
                "pass": counts[C.PASS], "fail": counts[C.FAIL],
                "blocked": counts[C.BLOCKED], "na": counts[C.NA],
                "exit_code": exit_code,
            },
            "results": [item.as_dict() for item in all_results],
        }
        if not ctx.manifest_found:
            payload["error"] = ("manifest 缺失或不可解析：%s。"
                                "运行 scripts/new-project.sh 或补 .replica/gate.manifest.yml"
                                % (ctx.manifest_error or "未找到"))
            payload["hint"] = ("python3 gates/run.py --project <dir> 只认 "
                               "<dir>/.replica/gate.manifest.yml；"
                               "格式见 templates/blueprint/SCHEMAS.md §15")
        payload["__RESULT__"] = "pass=%d fail=%d blocked=%d na=%d" % (
            counts[C.PASS], counts[C.FAIL], counts[C.BLOCKED], counts[C.NA])
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print_text(ctx, stages, by_stage, counts, load_errors)
        print("__RESULT__ pass=%d fail=%d blocked=%d na=%d"
              % (counts[C.PASS], counts[C.FAIL], counts[C.BLOCKED], counts[C.NA]))
    return exit_code


VERBOSE = False

if __name__ == "__main__":
    sys.exit(main())
