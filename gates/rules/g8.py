# -*- coding: utf-8 -*-
"""G8 测试门（R5/R7）。

判定（00-体系总纲.md §3.2 / SCHEMAS.md §14）：
1. TEST/test-plan.md 存在，每行含 T-xxx ID
2. TEST/results/ 最新 JSON 必须 failed=0 且 timeout=0
3. 最近 consecutive_runs（manifest.thresholds，默认 3）份结果文件 failed=0 且 timeout=0
4. TEST/bugs.md 中不存在 status=open 且 severity ∈ {S1,S2} 的条目
5. 每个 must+in 功能在 test-plan.md 至少 1 条用例（features.acceptance_ref 非空亦可）
"""

from __future__ import annotations

import re

from . import common as C

STAGE = "G8"

DEFAULT_BUGS = "TEST/bugs.md"
SEVERE = {"s1", "s2", "critical", "blocker", "high", "严重", "高"}


def _counts(data):
    """返回 (failed, timeout, total, passed)，容忍字段缺失与字符串数字。"""
    def num(key, default=0):
        try:
            return int(str(data.get(key, default)).strip())
        except (TypeError, ValueError):
            return default
    failed = num("failed")
    timeout = num("timeout")
    total = num("total")
    passed = num("passed", -1)
    if passed < 0:
        passed = num("pass") if "pass" in data else total - failed - timeout
    return failed, timeout, total, passed


def _check_one_run(g, ctx, path, data, label):
    if data is None:
        g.fail("results-parse", "%s 可解析" % label,
               expected="合法 JSON（SCHEMAS §14）", actual="解析失败",
               evidence=ctx.rel(path), hint="结果文件必须是 json 对象，含 total/passed/failed/timeout")
        return False
    failed, timeout, total, passed = _counts(data)
    cases = data.get("cases")
    if isinstance(cases, list):
        bad_cases = [str(c.get("id") or c.get("case") or "?") for c in cases
                     if isinstance(c, dict) and str(c.get("status", "")).lower()
                     not in ("pass", "passed", "ok", "skip", "skipped")]
        if bad_cases and failed == 0:
            failed = len(bad_cases)
    if failed or timeout:
        detail = []
        if failed:
            detail.append("failed=%d" % failed)
            if isinstance(cases, list):
                names = [str(c.get("id")) for c in cases if isinstance(c, dict)
                         and str(c.get("status", "")).lower() not in ("pass", "passed", "ok")]
                if names:
                    detail.append("未过用例：%s" % "、".join(names[:5]))
        if timeout:
            detail.append("timeout=%d" % timeout)
        g.fail("results-clean", "%s failed=0 且 timeout=0" % label,
               expected="failed=0、timeout=0",
               actual="；".join(detail), evidence=ctx.rel(path),
               hint="修好失败用例再重跑；timeout 说明用了 sleep 猜完成或用例本身不稳（R1/R5）")
        return False
    g.pass_("results-clean", "%s failed=0 且 timeout=0" % label,
            expected="failed=0、timeout=0",
            actual="total=%d passed=%d" % (total, passed if passed >= 0 else total),
            evidence=ctx.rel(path))
    return True


def _bugs_checks(g, ctx):
    rel = str(ctx.required.get("bugs_file") or DEFAULT_BUGS).strip()
    text = ctx.text(rel)
    if text is None:
        g.fail("bugs", "bugs.md 存在且无 S1/S2 未关闭缺陷",
               expected="%s 存在（可为空表）" % rel, actual="文件不存在",
               evidence=rel, hint="S8 建缺陷台账；没有缺陷也要有表头（证明扫过了）")
        return
    tables = C.md_tables(text)
    found_table = False
    severe_open = []
    for table in tables:
        header = [h.lower() for h in table["header"]]
        if not header:
            continue
        sev_idx = next((i for i, h in enumerate(header)
                        if "severity" in h or "严重" in h or "级别" in h), None)
        st_idx = next((i for i, h in enumerate(header)
                       if "status" in h or "状态" in h), None)
        if sev_idx is None or st_idx is None:
            continue
        found_table = True
        for cells, no in zip(table["rows"], table["lines"]):
            if max(sev_idx, st_idx) >= len(cells):
                continue
            sev = cells[sev_idx].strip().lower()
            st = cells[st_idx].strip().lower()
            if st in ("open", "打开", "未关闭") and sev in SEVERE:
                bid = cells[0].strip() if cells else "第 %d 行" % no
                severe_open.append("%s（%s）" % (bid, cells[sev_idx].strip()))
    if not found_table:
        g.fail("bugs", "bugs.md 存在且无 S1/S2 未关闭缺陷",
               expected="缺陷表含「严重度/severity」与「状态/status」列",
               actual="没找到带这两列的表格", evidence=rel,
               hint="表头写：| ID | 严重度 | 状态 | 现象 | 复现步骤 | 证据 | 修复提交 |")
        return
    if severe_open:
        g.fail("bugs", "bugs.md 存在且无 S1/S2 未关闭缺陷",
               expected="open 且 S1/S2 的缺陷 = 0",
               actual="%d 条未关闭：%s" % (len(severe_open), "、".join(severe_open[:5])),
               evidence=rel,
               hint="S1（崩溃/丢数据）与 S2（核心功能不可用）必须先修；修完改状态并写修复提交")
    else:
        g.pass_("bugs", "bugs.md 存在且无 S1/S2 未关闭缺陷",
                expected="0 条", actual="0 条未关闭的 S1/S2", evidence=rel)


def _plan_checks(g, ctx, plan_rows, plan_err):
    if plan_err:
        g.fail("test-plan", "test-plan.md 每行含 T-xxx ID",
               expected="TEST/test-plan.md 有用例表",
               actual=plan_err, evidence="TEST/test-plan.md",
               hint="按 SCHEMAS §14 建表：| T-xxx | FL-xx | 类型 | 步骤 | 期望（具体值） | 自动化 |")
        return
    bad = [str(row.get("id")) for row in plan_rows
           if not C.TEST_ID_RE.match(str(row.get("id") or "").strip())]
    if bad:
        g.fail("test-plan", "test-plan.md 每行含 T-xxx ID",
               expected="首列形如 T-101",
               actual="%d 行不合规：%s" % (len(bad), "、".join(bad[:5])),
               evidence="TEST/test-plan.md",
               hint="用例号沿用蓝图里 acceptance_ref 的编号，只许加不许弱化")
    else:
        g.pass_("test-plan", "test-plan.md 每行含 T-xxx ID",
                expected="T-xxx", actual="%d 条用例" % len(plan_rows),
                evidence="TEST/test-plan.md")

    targets = C.must_features(ctx)
    if not targets:
        g.na("must-coverage", "每个 must 功能 ≥1 条用例",
             reason="features.csv 里没有 must+in 功能")
        return
    plan_ids = {str(row.get("id")).strip() for row in plan_rows}
    plan_blob = "\n".join(" ".join(str(c) for c in row.get("cells", [])) for row in plan_rows)
    missing = []
    for row in targets:
        fid = C.cell(row, "feature_id")
        refs = C.split_refs(C.cell(row, "acceptance_ref"))
        if refs and all(r in plan_ids for r in refs):
            continue
        if refs and any(r in plan_ids for r in refs):
            continue
        if refs:
            missing.append("%s（acceptance_ref=%s 不在用例表里）" % (fid, C.cell(row, "acceptance_ref")))
        elif fid in plan_blob:
            continue
        else:
            missing.append("%s（acceptance_ref 为空且用例表未提及）" % fid)
    if missing:
        g.fail("must-coverage", "每个 must 功能 ≥1 条用例",
               expected="%d 个 must 功能各有测试号" % len(targets),
               actual="%d 个缺：%s" % (len(missing), "；".join(missing[:5])),
               evidence="BLUEPRINT/features.csv",
               hint="在 features.csv 填 acceptance_ref，并在 test-plan.md 建对应用例（覆盖正/负/边缘）")
    else:
        g.pass_("must-coverage", "每个 must 功能 ≥1 条用例",
                expected="must 功能全部有测试号",
                actual="%d 个 must 功能全部覆盖" % len(targets),
                evidence="TEST/test-plan.md")


def check(ctx):
    g = C.Gate(ctx, STAGE)
    if g.no_manifest():
        return g.results

    plan_rows, plan_err = C.load_test_plan(ctx)
    _plan_checks(g, ctx, plan_rows, plan_err)

    files = C.load_result_files(ctx)
    if not files:
        g.fail("results", "TEST/results/ 有结果文件",
               expected="至少 1 个 *.json", actual="目录为空或不存在",
               evidence="TEST/results/",
               hint="每次跑测试都落一份机读结果（SCHEMAS §14）")
        g.na("consecutive", "连续 %d 次结果全绿" % ctx.thresholds["consecutive_runs"],
             reason="没有结果文件可供比较")
        _bugs_checks(g, ctx)
        return g.results

    ok_all = True
    latest_path, latest_data, latest_err = files[-1]
    ok_all &= _check_one_run(g, ctx, latest_path, latest_data, "最新结果")

    need = ctx.thresholds["consecutive_runs"]
    window = files[-need:] if len(files) >= need else files
    if len(files) < need:
        g.fail("consecutive", "最近 %d 份结果连续全绿" % need,
               expected="%d 份结果文件（R5：连跑 ≥3 次）" % need,
               actual="只有 %d 份：%s" % (len(files), "、".join(ctx.rel(p) for p, _d, _e in files)),
               evidence="TEST/results/",
               hint="把全量测试连跑 %d 次，每次落一份结果；单次绿不可信" % need)
    else:
        bad = []
        for path, data, err in window:
            if data is None:
                bad.append(ctx.rel(path))
                continue
            failed, timeout, _total, _passed = _counts(data)
            if failed or timeout:
                bad.append("%s（failed=%d timeout=%d）" % (ctx.rel(path), failed, timeout))
        if bad:
            g.fail("consecutive", "最近 %d 份结果连续全绿" % need,
                   expected="全部 failed=0 timeout=0",
                   actual="%d 份不达标：%s" % (len(bad), "；".join(bad[:4])),
                   evidence="TEST/results/",
                   hint="不稳定用例（flaky）等于红灯：查竞态、去掉 sleep、补完成信号（R1/R2）")
        else:
            g.pass_("consecutive", "最近 %d 份结果连续全绿" % need,
                    expected="%d 份全部 failed=0" % need,
                    actual="%s 全部通过（共 %d 份）" % (
                        "、".join(ctx.rel(p) for p, _d, _e in window), len(files)),
                    evidence=ctx.rel(window[-1][0]))

    _bugs_checks(g, ctx)
    return g.results
