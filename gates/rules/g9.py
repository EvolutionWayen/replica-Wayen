# -*- coding: utf-8 -*-
"""G9 一致性门（功能分必须由 features.csv 实算，不许手填）。

判定（00-体系总纲.md §3.2）：
1. REPORT/parity.md 存在，含功能分与界面分两个数字
2. 功能分由 features.csv 实算：
   weight: must=3 / should=2 / could=1；progress: yes=1 / partial=0.5 / no=0
   剔除 progress=skip 与 original=no 的行
   实算与报告数字误差 ≤ 1
3. 实算功能分 ≥ manifest.thresholds.parity_feature（默认 80）才算 PASS，
   低于则 FAIL 并列出缺失 must 清单
4. 缺失清单非空（必须能反驳：具体到功能 ID）
"""

from __future__ import annotations

import re

from . import common as C

STAGE = "G9"

DEFAULT_PARITY = "REPORT/parity.md"
WEIGHTS = {"must": 3, "should": 2, "could": 1}
PROGRESS_VALUE = {"yes": 1.0, "partial": 0.5, "no": 0.0}


def compute_feature_score(ctx):
    """返回 (score|None, detail dict)。score=None 表示 features.csv 不可用。"""
    rows, _fields, err = ctx.csv("BLUEPRINT/features.csv")
    if rows is None:
        return None, {"error": err}
    total = 0.0
    earned = 0.0
    counted, skipped = [], []
    missing_must = []      # must 但没做满的
    incomplete = []        # 任何未做满的功能（用于阈值未达时的缺失清单）
    for row in rows:
        fid = C.cell(row, "feature_id")
        priority = C.normalize_priority(C.cell(row, "priority"))
        progress = C.cell(row, "progress").lower()
        original = C.cell(row, "original").lower()
        scope = (C.cell(row, "scope") or "in").lower()
        if progress == "skip" or original == "no" or scope == "out":
            skipped.append(fid)
            continue
        weight = WEIGHTS.get(priority)
        if weight is None:
            skipped.append(fid)
            continue
        value = PROGRESS_VALUE.get(progress, 0.0)
        total += weight
        earned += weight * value
        counted.append((fid, priority, progress))
        if value < 1.0:
            incomplete.append("%s（%s，%s）" % (fid, priority, progress or "-"))
        if priority == "must" and value < 1.0:
            missing_must.append("%s（%s）" % (fid, progress or "-"))
    if total <= 0:
        return 0.0, {"total_weight": 0, "earned": 0, "counted": counted,
                     "skipped": skipped, "missing_must": missing_must,
                     "incomplete": incomplete}
    return round(earned / total * 100, 1), {
        "total_weight": total, "earned": round(earned, 2), "counted": counted,
        "skipped": skipped, "missing_must": missing_must, "incomplete": incomplete,
    }


def _reported_scores(text):
    """从 parity.md 里提取功能分与界面分。返回 (feature_value, ui_value, evidence_line)。"""
    feature, ui, line_no = None, None, 1
    lines = text.splitlines()
    for no, raw in enumerate(lines, 1):
        if feature is None and re.search(r"功能分|feature\s*score", raw, re.I):
            m = re.search(r"(\d+(?:\.\d+)?)\s*%?", raw)
            if m:
                feature, line_no = float(m.group(1)), no
        if ui is None and re.search(r"界面分|ui\s*score|视觉分", raw, re.I):
            m = re.search(r"(\d+(?:\.\d+)?)\s*%?", raw)
            if m:
                ui = float(m.group(1))
    # 表格形态退化处理：两行都写在表里（| 功能分 | 92 |）
    for table in C.md_tables(text):
        for cells in table["rows"]:
            if not cells:
                continue
            joined = " ".join(cells)
            if feature is None and re.search(r"功能分|feature", joined, re.I):
                for cell in cells:
                    m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*%?\s*", cell)
                    if m:
                        feature = float(m.group(1))
                        break
            if ui is None and re.search(r"界面分|ui|视觉", joined, re.I):
                for cell in cells:
                    m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*%?\s*", cell)
                    if m:
                        ui = float(m.group(1))
                        break
    return feature, ui, line_no


def _missing_list(text):
    """缺失清单：优先取「缺失清单」小节里的行，否则全文找 F- 引用。"""
    sec = C.section_by_keyword(C.md_sections(text, 2), ["缺失", "差距", "未实现", "缺口"])
    body = sec["body"] if sec else text
    ids = sorted(set(re.findall(r"\bF-[A-Z0-9][A-Z0-9-]*", body)))
    items = 0
    for line in body.splitlines():
        s = line.strip()
        if re.match(r"^([-*+]|\d+[.、)])\s+\S", s) or (
                s.startswith("|") and not re.match(r"^\|[\s|:-]+\|$", s)):
            items += 1
    return ids, items, (sec["line"] if sec else 1)


def check(ctx):
    g = C.Gate(ctx, STAGE)
    if g.no_manifest():
        return g.results

    rel = str(ctx.required.get("parity_report") or DEFAULT_PARITY).strip()
    text = ctx.text(rel)

    score, detail = compute_feature_score(ctx)
    threshold = ctx.thresholds["parity_feature"]

    if text is None:
        g.fail("parity-exists", "parity.md 存在且含功能分与界面分",
               expected="%s 含「功能分」与「界面分」两个数字" % rel,
               actual="文件不存在", evidence=rel,
               hint="S9 产出：功能分（实算）+ 界面分（单独记录，不许互相抵消）+ 缺失清单")
        if score is not None:
            g.fail("parity-threshold", "功能分 ≥ 阈值 %d" % threshold,
                   expected="≥ %d" % threshold, actual="实算 %.1f" % score,
                   evidence="BLUEPRINT/features.csv",
                   hint="先补 must 功能；缺失清单见下")
        return g.results

    reported_feature, reported_ui, line_no = _reported_scores(text)
    if reported_feature is not None and reported_ui is not None:
        g.pass_("parity-scores", "parity.md 含功能分与界面分",
                expected="两个数字", actual="功能分 %g、界面分 %g" % (reported_feature, reported_ui),
                evidence="%s:%d" % (rel, line_no))
    else:
        lack = []
        if reported_feature is None:
            lack.append("功能分")
        if reported_ui is None:
            lack.append("界面分")
        g.fail("parity-scores", "parity.md 含功能分与界面分",
               expected="分别写出功能分与界面分（各带数字）",
               actual="缺：%s" % "、".join(lack), evidence=rel,
               hint="两分分制：功能分由 features.csv 实算，界面分单独记录；界面分不参与抵消功能分")

    # ---- 实算 vs 报告 ----
    if score is None:
        g.fail("parity-computed", "功能分由 features.csv 实算且与报告一致",
               expected="features.csv 可读", actual=detail.get("error", "不可读"),
               evidence="BLUEPRINT/features.csv",
               hint="先修好 features.csv（G1）")
    elif reported_feature is None:
        g.fail("parity-computed", "功能分由 features.csv 实算且与报告一致",
               expected="报告写出功能分，且等于实算 %.1f" % score,
               actual="报告没有功能分", evidence=rel,
               hint="把实算值写进 parity.md；数字必须能被 features.csv 复算")
    else:
        diff = abs(reported_feature - score)
        if diff > 1.0:
            g.fail("parity-computed", "功能分由 features.csv 实算且与报告一致",
                   expected="报告值与实算值误差 ≤1（实算 %.1f）" % score,
                   actual="报告 %g，实算 %.1f，差 %.1f" % (reported_feature, score, diff),
                   evidence=rel,
                   hint="功能分不许手填：weight must3/should2/could1 × progress yes1/partial0.5/no0，"
                        "剔除 skip 与 original=no")
        else:
            g.pass_("parity-computed", "功能分由 features.csv 实算且与报告一致",
                    expected="误差 ≤1", actual="报告 %g vs 实算 %.1f（差 %.1f）" % (
                        reported_feature, score, diff), evidence=rel)

    # ---- 阈值 ----
    if score is not None:
        if score >= threshold:
            g.pass_("parity-threshold", "功能分 ≥ 阈值 %d" % threshold,
                    expected="≥ %d" % threshold,
                    actual="实算 %.1f（权重 %g / 得分 %g）" % (
                        score, detail.get("total_weight", 0), detail.get("earned", 0)),
                    evidence="BLUEPRINT/features.csv")
        else:
            # 缺失清单要能反驳：优先列未完成的 must，其次列任何未做满的功能
            must_open = detail.get("missing_must") or []
            any_open = detail.get("incomplete") or []
            listed = must_open or any_open
            lead = "未完成的 must" if must_open else "未做满的功能"
            g.fail("parity-threshold", "功能分 ≥ 阈值 %d" % threshold,
                   expected="≥ %d" % threshold,
                   actual="实算 %.1f；%s：%s" % (
                       score, lead,
                       "、".join(listed[:8]) if listed else "（无未完成项 → 权重分母有问题）"),
                   evidence="BLUEPRINT/features.csv",
                   hint="先把 must 做满再谈交付；阈值在 manifest.thresholds.parity_feature 配置")

    # ---- 缺失清单 ----
    ids, items, sec_line = _missing_list(text)
    if ids or items >= 2:
        g.pass_("parity-gaps", "缺失清单非空且能反驳",
                expected="列出具体缺失（功能 ID 或可核对条目）",
                actual="%d 个 F- 引用、%d 条清单行" % (len(ids), items),
                evidence="%s:%d" % (rel, sec_line))
    else:
        g.fail("parity-gaps", "缺失清单非空且能反驳",
               expected="有「缺失清单」小节，逐条写功能 ID + 缺什么",
               actual="没有具体条目（0 个 F- 引用、%d 条清单行）" % items,
               evidence=rel,
               hint="写「F-DATE-EDIT：重复规则仅支持每周，未支持按月 nth 周」这种能被反驳的条目；"
                    "写「差不多完成」不算")

    return g.results
