#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""parity_score.py —— 一致性评分（功能分 + 界面分，双分制）

为什么双分：功能分回答「用户还能不能做完原来能做的事」，界面分回答「切换过来
顺不顺手」。两者不能互相抵消——界面再像，少一个 must 功能就是不可交付；
功能再全，布局全乱也没人愿意换（00 §3.2 G9、replica-skill/replica-diff）。

算法来源：**复用上游** `replica-skill/replica-diff/parity.py` 的加权算法
（must 3 / should 2 / could 1；yes=1、partial=0.5；skip 与你新增的功能不计分），
用 importlib 从文件路径动态加载，不写死绝对路径；加载失败则用本文件内置的等价实现，
并在输出里明确写「用的是内置实现」。

本工具在人家算法之上加了三件事：
  1. 读本项目 SCHEMAS 的列（`progress` 而不是 `clone`，`scope=out` 直接排除）
  2. 双分：功能分（加权）+ 界面分（读 imgdiff.py --json 的均值，可缺省）
  3. `--markdown` 生成 REPORT/parity.md；`--fail-under` 给门禁用退出码

用法：
    python3 tools/parity_score.py --project .
    python3 tools/parity_score.py --project . --json
    python3 tools/parity_score.py --project . --markdown --md-out REPORT/parity.md
    python3 tools/parity_score.py --project . --visual diffs/*.json --fail-under 80
    python3 tools/parity_score.py --project . --ui-dir clone-screens   # 从 screens/clone-screens 配对比

退出码：0 通过（且达到 --fail-under） / 1 未达标或 must 未全绿 / 2 输入错误
"""

from __future__ import annotations

import argparse
import glob
import importlib.util
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import replica_common as rc  # noqa: E402

TOOL = "parity_score"
FEATURES_REL = os.path.join("BLUEPRINT", "features.csv")

# 与上游一致的权重
WEIGHT = {"must": 3, "should": 2, "could": 1, "p0": 3, "p1": 2, "p2": 1}
CREDIT = {"yes": 1.0, "done": 1.0, "partial": 0.5, "no": 0.0, "skip": None, "": 0.0}
PRIORITY_NAME = {3: "must", 2: "should", 1: "could"}


# --------------------------------------------------------------------------
# 上游算法加载
# --------------------------------------------------------------------------

def _candidates_upstream(project):
    here = os.path.dirname(os.path.abspath(__file__))
    env = os.environ.get("REPLICA_PARITY_PY")
    cands = []
    if env:
        cands.append(env)
    for base in (project, os.path.dirname(here), os.getcwd()):
        if not base:
            continue
        cands.append(os.path.join(base, "replica-skill", "replica-diff", "parity.py"))
    return cands


def load_upstream(project):
    """从路径动态加载上游 parity.py。返回 (module, path) 或 (None, 原因)。"""
    for path in _candidates_upstream(project):
        if not path or not os.path.isfile(path):
            continue
        try:
            spec = importlib.util.spec_from_file_location("replica_upstream_parity", path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)  # type: ignore[union-attr]
        except Exception as exc:  # 上游文件损坏/版本不符都不该让本工具挂
            return None, "%s 加载失败：%s" % (path, exc)
        if hasattr(mod, "score") and hasattr(mod, "WEIGHT"):
            return mod, path
        return None, "%s 里没有 score()/WEIGHT，不是预期的 parity.py" % path
    return None, "找不到 replica-skill/replica-diff/parity.py"


# --------------------------------------------------------------------------
# 内置等价实现（与上游语义一致，用于上游不可用时）
# --------------------------------------------------------------------------

def builtin_score(rows):
    counted, skipped, extras, problems = [], [], [], []
    for row in rows:
        original = (row.get("original") or "yes").lower()
        prog = (row.get("progress") or "").lower()
        prio = (row.get("priority") or "").lower()
        if row.get("scope", "").lower() == "out":
            skipped.append(row)
            continue
        if original in ("no", "n", "false"):
            extras.append(row)
            continue
        if prog == "skip":
            skipped.append(row)
            continue
        if prio not in WEIGHT:
            problems.append("features.csv:%s priority='%s' 不是 must/should/could，按 could 计"
                            % (row.get("line"), row.get("priority")))
        if prog not in CREDIT:
            problems.append("features.csv:%s progress='%s' 不是 yes/partial/no/skip，按 no 计"
                            % (row.get("line"), row.get("progress")))
        w = WEIGHT.get(prio, 1)
        c = CREDIT.get(prog, 0.0)
        counted.append(dict(row, weight=w, credit=c))

    total = sum(r["weight"] for r in counted)
    got = sum(r["weight"] * r["credit"] for r in counted)
    feature = 100.0 * got / total if total else 0.0

    areas = {}
    for r in counted:
        a = r.get("area") or "(无 area)"
        t = areas.setdefault(a, [0.0, 0.0, 0])
        t[0] += r["weight"] * r["credit"]
        t[1] += r["weight"]
        t[2] += 1
    by_area = sorted(({"area": a, "score": round(100.0 * g / t, 1) if t else 0.0,
                       "features": n} for a, (g, t, n) in areas.items()),
                     key=lambda d: d["score"])

    def brief(r):
        weight = r.get("weight")
        if weight is None:
            weight = WEIGHT.get((r.get("priority") or "").lower(), 1)
        return {"feature": r.get("feature", ""), "feature_id": r.get("feature_id", ""),
                "area": r.get("area", ""),
                "priority": PRIORITY_NAME.get(weight, "could"),
                "progress": r.get("progress", "") or "no",
                "notes": r.get("notes", "")}

    missing = sorted((r for r in counted if r["credit"] < 1.0),
                     key=lambda r: (-r["weight"], r["credit"], r.get("area", ""),
                                    r.get("feature", "")))
    musts = [r for r in counted if r["weight"] == 3]
    return {
        "feature_score": round(feature, 1),
        "counted": len(counted),
        "must_have_done": sum(1 for r in musts if r["credit"] == 1.0),
        "must_have_total": len(musts),
        "by_area": by_area,
        "missing": [brief(r) for r in missing],
        "skipped": [brief(r) for r in skipped],
        "extras": [brief(r) for r in extras],
        "problems": problems,
    }


# --------------------------------------------------------------------------
# 本项目 features.csv → 上游语义的行
# --------------------------------------------------------------------------

def load_features(project):
    path = os.path.join(project, FEATURES_REL)
    if not os.path.isfile(path):
        raise rc.ToolError(
            "缺 %s" % FEATURES_REL,
            "先跑 S1 产出 features.csv（功能索引是一切评分的分母）")
    schema = rc.load_schema(project)
    rows, issues = rc.read_csv_table(path, schema.columns["features"])
    hard = [i for i in issues if i["level"] == "ERROR"]
    if hard:
        raise rc.ToolError("features.csv 表头/列有问题：%s" % "；".join(i["message"] for i in hard),
                           "列名与顺序照 templates/blueprint/SCHEMAS.md §2")
    if not rows:
        raise rc.ToolError("features.csv 里没有任何数据行",
                           "至少把核心闭环的功能列进来；空表算不出分")
    out = []
    for r in rows:
        out.append({
            "feature_id": rc.cell(r, "feature_id"),
            "feature": rc.cell(r, "feature"),
            "area": rc.cell(r, "area"),
            "priority": rc.cell(r, "priority"),
            "scope": rc.cell(r, "scope"),
            "original": rc.cell(r, "original") or "yes",
            "progress": rc.cell(r, "progress"),
            "notes": rc.cell(r, "notes"),
            "contract_ref": rc.cell(r, "contract_ref"),
            "acceptance_ref": rc.cell(r, "acceptance_ref"),
            "line": r["line"],
        })
    return out, issues


def score_features(project, rows, upstream_mod):
    """用上游算法（可用时）或内置实现打分。返回 (result, backend, note)"""
    by_name = {}
    for r in rows:
        by_name.setdefault(r.get("feature", ""), r.get("feature_id", ""))

    def enrich(result):
        """上游 brief() 不带 feature_id；补上 ID，否则报告里无法回溯到契约。"""
        for key in ("missing", "skipped", "extras"):
            for item in result.get(key, []):
                if not item.get("feature_id"):
                    item["feature_id"] = by_name.get(item.get("feature", ""), "")
        return result

    if upstream_mod is not None:
        adapted = []
        for r in rows:
            d = dict(r)
            d["clone"] = r.get("progress", "")
            if r.get("scope", "").lower() == "out":
                d["clone"] = "skip"
                if not d.get("notes"):
                    d["notes"] = "scope=out（本版不做）"
            adapted.append(d)
        try:
            result = enrich(upstream_mod.score(adapted))
            return result, "upstream", str(getattr(upstream_mod, "__file__", ""))
        except Exception as exc:
            res = builtin_score(rows)
            res["problems"] = list(res.get("problems", [])) + [
                "上游 parity.score() 执行失败（%s），已改用内置等价实现" % exc]
            return enrich(res), "builtin", "上游 score() 抛异常：%s" % exc
    res = builtin_score(rows)
    return enrich(res), "builtin", "上游不可用，使用内置等价实现"


# --------------------------------------------------------------------------
# 界面分
# --------------------------------------------------------------------------

def load_visual(paths):
    scores, errors = [], []
    for p in paths:
        for one in glob.glob(p):
            try:
                data = rc.read_json(one)
            except rc.ToolError as exc:
                errors.append(exc.message)
                continue
            if "score" not in data:
                errors.append("%s 不是 imgdiff.py --json 的输出（没有 score 字段）" % one)
                continue
            name = ""
            if isinstance(data.get("files"), dict):
                name = data["files"].get("clone") or data["files"].get("b") or ""
            scores.append({"file": name or os.path.basename(one),
                          "score": float(data["score"]),
                          "mode": data.get("mode", "layout"),
                          "source": one})
    return scores, errors


def visual_from_dir(project, screens_name, clone_name):
    """screens/<S-xx>.png 与 clone-screens/<S-xx>.png 配对，调用上游 imgdiff（若可）。"""
    up = None
    here = os.path.dirname(os.path.abspath(__file__))
    for base in (project, os.path.dirname(here), os.getcwd()):
        cand = os.path.join(base, "replica-skill", "replica-diff", "imgdiff.py")
        if os.path.isfile(cand):
            up = cand
            break
    if not up:
        return None, ["找不到 replica-skill/replica-diff/imgdiff.py，无法自动配对截图"]
    spec = importlib.util.spec_from_file_location("replica_upstream_imgdiff", up)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    try:
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
    except Exception as exc:
        return None, ["imgdiff.py 加载失败：%s" % exc]
    if not (hasattr(mod, "compare") and hasattr(mod, "read_png")):
        return None, ["imgdiff.py 没有 compare()/read_png()，版本不符；请直接用 --visual 传 json"]
    a_dir = os.path.join(project, screens_name)
    b_dir = os.path.join(project, clone_name)
    pairs, missing = [], []
    if not os.path.isdir(a_dir) or not os.path.isdir(b_dir):
        return None, ["截图目录不存在：%s 或 %s" % (screens_name, clone_name)]
    for f in sorted(os.listdir(a_dir)):
        if not f.lower().endswith((".png", ".jpg", ".jpeg")):
            continue
        b = os.path.join(b_dir, f)
        if os.path.isfile(b):
            pairs.append((os.path.join(a_dir, f), b, f))
        else:
            missing.append(f)
    scores = []
    for a, b, name in pairs:
        try:
            img_a = mod.read_png(a)
            img_b = mod.read_png(b)
            out = mod.compare(img_a, img_b, mode="layout")
            report = out[0] if isinstance(out, tuple) else out
            s = report.get("score") if isinstance(report, dict) else None
            if s is None:
                missing.append("%s（imgdiff 没返回 score）" % name)
                continue
            scores.append({"file": name, "score": float(s), "mode": "layout", "source": a})
        except Exception as exc:
            missing.append("%s（diff 失败：%s）" % (name, exc))
    return scores, missing


def combine(result, visuals):
    if visuals:
        layout = sum(v["score"] for v in visuals) / len(visuals)
        result["visual"] = visuals
        result["layout_score"] = round(layout, 1)
        result["overall"] = round(0.8 * result["feature_score"] + 0.2 * layout, 1)
    else:
        result["layout_score"] = None
        result["overall"] = result["feature_score"]
    return result


# --------------------------------------------------------------------------
# 输出
# --------------------------------------------------------------------------

def render(result, backend, backend_note, project, features_total, extra):
    out = []
    fs = result["feature_score"]
    ls = result.get("layout_score")
    ov = result["overall"]
    must_ok = result["must_have_done"] == result["must_have_total"] and result["must_have_total"] > 0

    out.append("# 一致性报告（parity）")
    out.append("")
    out.append("> 由 `tools/parity_score.py` 生成 · 项目 `%s` · %s" % (project, rc.now_iso()))
    out.append("> 算法来源：%s" % ("上游 replica-diff/parity.py（加权 must3/should2/could1，partial 计半）"
                                  if backend == "upstream"
                                  else "内置等价实现（%s）" % backend_note))
    out.append("")
    out.append("## 总分")
    out.append("")
    out.append("| 分项 | 分数 | 口径 |")
    out.append("|---|---|---|")
    out.append("| **综合** | **%.1f** | %s |"
               % (ov, "80% 功能 + 20% 界面" if ls is not None else "无界面分，等于功能分"))
    out.append("| 功能分 | %.1f | features.csv 加权：must 3 / should 2 / could 1；yes 1、partial 0.5；"
               "skip 与 scope=out 不计 |" % fs)
    if ls is not None:
        out.append("| 界面分 | %.1f | %d 张截图 imgdiff 布局分均值（忽略配色） |"
                   % (ls, len(result["visual"])))
    else:
        out.append("| 界面分 | — | 未提供截图 diff（用 --visual diffs/*.json 或 --ui-dir 补） |")
    out.append("")
    out.append("must 功能：**%d / %d 完成**。%s"
               % (result["must_have_done"], result["must_have_total"],
                  "✅ 全绿。" if must_ok else "❌ 还有 must 没做完，功能分再高也不可交付（G9）。"))
    out.append("")
    out.append("## 判定")
    out.append("")
    verdict = []
    if not must_ok:
        verdict.append("- **不可交付**：must 功能未全绿。")
    if fs < 80:
        verdict.append("- 功能分 %.1f < 80，未达 G9 门槛。" % fs)
    if ls is not None and ls < 75:
        verdict.append("- 界面分 %.1f < 75，布局结构差异明显（replica-diff 口径：75+ 为 close）。" % ls)
    if not verdict:
        verdict.append("- **可交付**（按 current 口径：must 全绿、功能分 ≥80%s）。"
                       % ("、界面分 ≥75" if ls is not None else ""))
        verdict.append("- 界面分不参与抵消功能缺失：功能分不足就算界面分 100 也判不可交付。")
    out.extend(verdict)
    out.append("")

    if result["by_area"]:
        out.append("## 按模块（弱的在前）")
        out.append("")
        out.append("| 模块 | 分数 | 功能数 |")
        out.append("|---|---|---|")
        for a in result["by_area"]:
            out.append("| %s | %.1f | %d |" % (a["area"], a["score"], a["features"]))
        out.append("")

    out.append("## 缺失清单（按建设顺序：先 must、再 should、最后 could）")
    out.append("")
    if result["missing"]:
        out.append("| 优先级 | 功能 | 现状 | 备注 |")
        out.append("|---|---|---|---|")
        for m in result["missing"]:
            out.append("| %s | `%s` %s | %s | %s |"
                       % (m["priority"], m.get("feature_id", ""), m["feature"],
                          m.get("progress", m.get("clone", "")), m.get("notes") or "-"))
    else:
        out.append("- 没有缺失：所有计分功能都已完成。")
    out.append("")

    if result["skipped"]:
        out.append("## 明确不做（不计分，但必须写理由）")
        out.append("")
        for m in result["skipped"]:
            out.append("- `%s` %s —— %s"
                       % (m.get("feature_id", ""), m["feature"],
                          m.get("notes") or "⚠ 没写理由，补上"))
        out.append("")

    if result["extras"]:
        out.append("## 你自己新增的（原版没有，不计分）")
        out.append("")
        for m in result["extras"]:
            out.append("- `%s` %s" % (m.get("feature_id", ""), m["feature"]))
        out.append("")

    if result.get("visual"):
        out.append("## 截图布局分（低者优先修）")
        out.append("")
        out.append("| 屏幕 | 布局分 | 模式 |")
        out.append("|---|---|---|")
        for v in sorted(result["visual"], key=lambda d: d["score"]):
            out.append("| %s | %.1f | %s |" % (v["file"], v["score"], v["mode"]))
        out.append("")

    if result["problems"]:
        out.append("## 评分过程中发现的数据问题")
        out.append("")
        for p in result["problems"]:
            out.append("- %s" % p)
        out.append("")

    if extra:
        out.append("## 其它提示")
        out.append("")
        for e in extra:
            out.append("- %s" % e)
        out.append("")

    out.append("## 口径声明（反驳用）")
    out.append("")
    out.append("- 分母：features.csv 中 `scope=in` 且 `original=yes` 且 `progress!=skip` 的行；"
               "共 %d 行计入。" % result["counted"])
    out.append("- 界面分只比结构（edge map 网格），不比配色；配色是你自己的品牌，不该被扣分。")
    out.append("- 哪些没上线不算失败：`scope=out` 与 `progress=skip` 都不进分母，但要写理由。")
    out.append("- 这个分不能替代真机体验：点击步数、焦点行为、错误态要看 REPORT/feedback.md。")
    out.append("")
    return "\n".join(out)


def summary_lines(result, backend):
    ls = result.get("layout_score")
    return [
        "综合 %.1f ｜ 功能 %.1f ｜ 界面 %s"
        % (result["overall"], result["feature_score"],
           "%.1f" % ls if ls is not None else "—"),
        "must %d/%d ｜ 计入 %d 行 ｜ 缺 %d 项 ｜ 算法：%s"
        % (result["must_have_done"], result["must_have_total"], result["counted"],
           len(result["missing"]), "上游" if backend == "upstream" else "内置"),
    ]


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="parity_score.py",
        description="一致性评分：功能分（加权，复用上游 parity.py 算法）+ 界面分（imgdiff 布局分均值）",
        epilog="示例：python3 tools/parity_score.py --project . --markdown --md-out REPORT/parity.md --fail-under 80",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", default=".", help="项目根目录（默认当前目录）")
    ap.add_argument("--json", action="store_true", help="输出 JSON（供 G9 门禁用）")
    ap.add_argument("--markdown", action="store_true", help="输出 Markdown 报告")
    ap.add_argument("--md-out", default="", help="写进文件，例 REPORT/parity.md")
    ap.add_argument("--visual", nargs="*", default=[], help="imgdiff.py --json 输出（可多个/通配）")
    ap.add_argument("--ui-dir", nargs=2, default=None,
                    metavar=("原版目录", "克隆目录"),
                    help="自动配对截图并跑 imgdiff 布局对比，例 --ui-dir screens clone-screens")
    ap.add_argument("--fail-under", type=float, default=None,
                    help="综合分下限，低于它退出码 1（G9 建议 80）")
    ap.add_argument("--require-must", action="store_true", default=True,
                    help="must 未全绿即退出码 1（默认开启）")
    ap.add_argument("--no-require-must", dest="require_must", action="store_false",
                    help="只报分不因 must 未全绿而失败")
    ap.add_argument("--no-upstream", action="store_true", help="强制用内置实现，不加载上游")
    args = ap.parse_args(argv)

    if not os.path.isdir(args.project):
        return rc.die(rc.ToolError("项目目录不存在：%s" % args.project, "确认路径"))

    try:
        rows, csv_issues = load_features(args.project)
    except rc.ToolError as exc:
        return rc.die(exc)

    if args.no_upstream:
        up_mod, up_path = None, "（--no-upstream 指定）"
    else:
        up_mod, up_path = load_upstream(os.path.abspath(args.project))

    result, backend, backend_note = score_features(args.project, rows, up_mod)

    extra = []
    if backend == "builtin" and up_mod is None:
        extra.append("未使用上游算法：%s" % up_path)
    if csv_issues:
        warns = [i for i in csv_issues if i["level"] == "WARN"]
        if warns:
            extra.append("features.csv 有 %d 条列结构提示（%s），跑 blueprint_lint.py 看全量"
                         % (len(warns), "；".join(i["message"] for i in warns[:3])))

    visuals = []
    if args.visual:
        visuals, errs = load_visual(args.visual)
        extra.extend(errs)
    elif args.ui_dir:
        got, missing = visual_from_dir(args.project, args.ui_dir[0], args.ui_dir[1])
        if got is None:
            extra.extend(missing or ["截图对比不可用"])
        else:
            visuals = got
            if missing:
                extra.append("有 %d 张原版截图没有对应的克隆截图：%s"
                             % (len(missing), "、".join(missing[:6])))
    else:
        auto = sorted(glob.glob(os.path.join(args.project, "diffs", "*.json")))
        if auto:
            visuals, errs = load_visual(auto)
            extra.extend(errs)
            if visuals:
                extra.append("自动发现 diffs/ 下 %d 个 imgdiff 结果，已计入界面分" % len(visuals))

    result = combine(result, visuals)
    must_ok = (result["must_have_done"] == result["must_have_total"]
               and result["must_have_total"] > 0)
    failed = []
    if args.fail_under is not None and result["overall"] < args.fail_under:
        failed.append("综合分 %.1f < %.1f" % (result["overall"], args.fail_under))
    if args.require_must and not must_ok:
        failed.append("must 功能 %d/%d，未全绿"
                      % (result["must_have_done"], result["must_have_total"]))

    payload = {
        "tool": TOOL,
        "project": os.path.abspath(args.project),
        "checked_at": rc.now_iso(),
        "backend": backend,
        "backend_path": backend_note if backend == "builtin" else str(up_path),
        "overall": result["overall"],
        "feature_score": result["feature_score"],
        "layout_score": result.get("layout_score"),
        "must_have_done": result["must_have_done"],
        "must_have_total": result["must_have_total"],
        "counted": result["counted"],
        "missing": result["missing"],
        "skipped": result["skipped"],
        "extras": result["extras"],
        "by_area": result["by_area"],
        "visual": result.get("visual", []),
        "problems": result["problems"],
        "notes": extra,
        "fail_under": args.fail_under,
        "must_all_green": must_ok,
        "passed": not failed,
        "failed_reasons": failed,
        "__RESULT__": "parity overall=%.1f feature=%.1f layout=%s must=%d/%d"
                      % (result["overall"], result["feature_score"],
                         "%.1f" % result["layout_score"] if result.get("layout_score") is not None else "NA",
                         result["must_have_done"], result["must_have_total"]),
    }

    if args.json:
        rc.print_json(payload)
    else:
        if args.markdown or args.md_out:
            md = render(result, backend, backend_note, os.path.abspath(args.project),
                        len(rows), extra)
            print(md)
        else:
            print("一致性评分（parity_score）· %s" % os.path.abspath(args.project))
            print("算法：%s" % ("上游 replica-diff/parity.py" if backend == "upstream"
                              else "内置等价实现（%s）" % backend_note))
            print("")
            for line in summary_lines(result, backend):
                print("  " + line)
            print("")
            if result["missing"]:
                print("缺失清单（按建设顺序）：")
                for m in result["missing"][:20]:
                    print("  [%s] %s %s — 现状 %s%s"
                          % (m["priority"], m.get("feature_id", ""), m["feature"],
                             m.get("progress", m.get("clone", "")),
                             ("　(%s)" % m["notes"]) if m.get("notes") else ""))
                if len(result["missing"]) > 20:
                    print("  … 还有 %d 项，用 --markdown 看全量" % (len(result["missing"]) - 20))
            else:
                print("  没有缺失。")
            if result["problems"]:
                print("")
                print("数据问题：")
                for p in result["problems"]:
                    print("  - %s" % p)
            for e in extra:
                print("  提示：%s" % e)
            print("")
            if failed:
                print("门禁结论：❌ %s" % "；".join(failed))
            elif must_ok:
                print("门禁结论：✅ 达标%s"
                      % ("（--fail-under %.1f）" % args.fail_under if args.fail_under is not None else ""))
            else:
                print("门禁结论：⚠ 分数达标，但 must 功能 %d/%d 未全绿——"
                      "G9 判定仍为「不可交付」（--no-require-must 只是不拦退出码）"
                      % (result["must_have_done"], result["must_have_total"]))

    if args.md_out:
        target = args.md_out if os.path.isabs(args.md_out) else os.path.join(args.project, args.md_out)
        os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
        with open(target, "w", encoding="utf-8") as fh:
            fh.write(render(result, backend, backend_note, os.path.abspath(args.project),
                            len(rows), extra) + "\n")
        if not args.json and not args.markdown:
            print("Markdown 已写入：%s" % target)

    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
