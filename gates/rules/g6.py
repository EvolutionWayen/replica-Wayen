# -*- coding: utf-8 -*-
"""G6 联动门（最严）—— 防「页面有、内部不联动」（R18）。

对 features.csv 中 progress=yes 的每个功能：
1. 它在 linkage.csv 作为 source_id 的所有行 status ∈ {wired, verified}
2. 这些行的 test_ref 在 TEST/results/ 最新结果里 status = pass
3. 相关屏幕（linkage.affected_screen + TRACEABILITY.screen）四态为 yes
4. progress=yes 但完全没有 linkage 行 → FAIL（有壳无芯）
另外：
5. manifest.required.contract_sections 与 G2 的 SCHEMAS 节数一致
6. 扫描 src/ 下 must 功能对应文件不应出现 TODO/FIXME
   （路径映射来自 SPEC/TRACEABILITY.csv 的路由/命令 → 文件；无映射则 NA 带理由）
"""

from __future__ import annotations

import re

from . import common as C

STAGE = "G6"

DONE_PROGRESS = "yes"
OK_LINKAGE_STATUS = {"wired", "verified"} | C.LINKAGE_NA_STATUS
CODE_EXTS = {".py", ".js", ".ts", ".tsx", ".jsx", ".swift", ".kt", ".java", ".go",
             ".rs", ".cs", ".m", ".mm", ".sql", ".vue", ".svelte", ".rb", ".php",
             ".c", ".cc", ".cpp", ".h", ".html", ".css"}
BANNED_MARKERS = ["TODO", "FIXME"]


def _linkage_index(ctx):
    out = {}
    for row in C.linkage(ctx):
        src = C.cell(row, "source_id")
        if src:
            out.setdefault(src, []).append(row)
    return out


def _latest_cases(ctx):
    path, data, err = C.latest_result(ctx)
    if data is None:
        return None, err, path
    return C.result_case_status(data), "", path


def _feature_done_checks(g, ctx):
    feature_rows = [r for r in C.features(ctx)
                    if C.cell(r, "progress").lower() == DONE_PROGRESS]
    if not feature_rows:
        g.na("progress-linkage", "progress=yes 的功能其联动全部 wired",
             reason="features.csv 里没有 progress=yes 的功能（尚未进入 S6）")
        g.na("progress-tests", "progress=yes 的功能其测试全部 pass",
             reason="没有 progress=yes 的功能")
        return

    link_idx = _linkage_index(ctx)
    cases, cases_err, cases_path = _latest_cases(ctx)
    not_wired, no_rows, test_missing, test_failed = [], [], [], []
    all_na = []

    for row in feature_rows:
        fid = C.cell(row, "feature_id")
        mine = link_idx.get(fid, [])
        if not mine:
            no_rows.append(fid)
            continue
        # 防滥用（SCHEMAS §5）：六面全 na = 等同于没做联动分析
        analysis = C.linkage_faces(mine)
        if analysis["all_na"]:
            all_na.append("%s（%d 行全部 na，已考虑面：%s）" % (
                fid, len(mine),
                "、".join(C.face_name(k) for k in analysis["considered"]) or "无法归类"))
        for lk in mine:
            lid = C.cell(lk, "link_id") or "(无 ID)"
            status = C.cell(lk, "status").lower()
            if status not in OK_LINKAGE_STATUS:
                not_wired.append("%s/%s status=%s" % (fid, lid, C.cell(lk, "status")))
            # na 行 = 确认该面不受影响，没有测试可指（SCHEMAS §5：test_ref 允许 `-`）
            if status in C.LINKAGE_NA_STATUS:
                continue
            ref = C.cell(lk, "test_ref")
            if not ref or C.is_blank(ref):
                test_missing.append("%s/%s 没有 test_ref" % (fid, lid))
                continue
            if cases is None:
                test_missing.append("%s/%s 的 %s（没有可读的结果文件）" % (fid, lid, ref))
                continue
            if ref not in cases:
                test_missing.append("%s 的 %s 不在最新结果里" % (fid, ref))
            elif cases[ref] != "pass":
                test_failed.append("%s 的 %s = %s" % (fid, ref, cases[ref]))

    if no_rows:
        g.fail("progress-linkage", "progress=yes 的功能其联动全部 wired",
               expected="每个勾选完成的功能在 linkage.csv 至少 1 行且全部 wired/verified",
               actual="%d 个功能没有任何联动行：%s" % (len(no_rows), "、".join(no_rows[:6])),
               evidence="BLUEPRINT/linkage.csv",
               hint="这就是「页面有、内部不联动」。先列六面（%s）"
                    "再写 refresh_timing 与 test_ref；找不到联动说明功能还没做完"
                    % C.face_names_text())
    elif not_wired:
        g.fail("progress-linkage", "progress=yes 的功能其联动全部 wired",
               expected="linkage.status ∈ {wired, verified}",
               actual="%d 条未接：%s" % (len(not_wired), "；".join(not_wired[:5])),
               evidence="BLUEPRINT/linkage.csv",
               hint="把 pending 改成 wired 前必须真的写代码接上；verified 需要测试证据")
    else:
        g.pass_("progress-linkage", "progress=yes 的功能其联动全部 wired",
                expected="全部 wired/verified",
                actual="%d 个功能、%d 条联动全部接上" % (
                    len(feature_rows), sum(len(link_idx.get(C.cell(r, "feature_id"), []))
                                           for r in feature_rows)),
                evidence="BLUEPRINT/linkage.csv")

    # 防滥用：六面全 na 等同于没做联动分析（SCHEMAS §5 明文，与 R20 同罪）
    if all_na:
        g.fail("linkage-all-na", "六面不允许全部标 na（等同没做联动分析）",
               expected="每个 progress=yes 的功能至少有 1 面 status=wired/verified",
               actual="%d 个功能全部 na：%s" % (len(all_na), "；".join(all_na[:4])),
               evidence="BLUEPRINT/linkage.csv",
               hint="na 只用于「想过之后确认不受影响」的那几面，不能把六面全填 na 来凑数。"
                    "要么真的接上至少一面（wired + 测试 pass），要么把这个功能降回 partial")
    else:
        g.pass_("linkage-all-na", "六面不允许全部标 na（等同没做联动分析）",
                expected="每个完成功能至少 1 面 wired/verified",
                actual="%d 个完成功能均有真接线面" % len(feature_rows),
                evidence="BLUEPRINT/linkage.csv")

    if cases is None:
        g.fail("progress-tests", "progress=yes 的功能其测试全部 pass",
               expected="TEST/results/ 有最新结果且相关用例 pass",
               actual=cases_err or "没有结果文件", evidence="TEST/results/",
               hint="跑一次 e2e 把结果写成 TEST/results/<日期>-<run>.json（格式见 SCHEMAS §14）")
    elif test_missing or test_failed:
        detail = []
        if test_missing:
            detail.append("%d 个用例缺失：%s" % (len(test_missing), "；".join(test_missing[:4])))
        if test_failed:
            detail.append("%d 个用例未通过：%s" % (len(test_failed), "；".join(test_failed[:4])))
        g.fail("progress-tests", "progress=yes 的功能其测试全部 pass",
               expected="linkage.test_ref 指向的用例在最新结果里 status=pass",
               actual="；".join(detail), evidence=ctx.rel(cases_path) if cases_path else "TEST/results/",
               hint="补跑并复现断言；不许改测试让它通过（R7），不许用 sleep 猜完成（R1）")
    else:
        g.pass_("progress-tests", "progress=yes 的功能其测试全部 pass",
                expected="相关用例全部 pass",
                actual="最新结果 %s 命中全部用例" % (ctx.rel(cases_path) if cases_path else ""),
                evidence=ctx.rel(cases_path) if cases_path else "TEST/results/")


def _screen_state_checks(g, ctx):
    done = [r for r in C.features(ctx) if C.cell(r, "progress").lower() == DONE_PROGRESS]
    if not done:
        g.na("screens-four-states", "已完成功能的相关屏幕四态齐",
             reason="没有 progress=yes 的功能")
        return
    idx = C.screen_index(ctx)
    trace_screen = {}
    for row in C.traceability(ctx):
        fid = C.cell(row, "feature_id")
        key = C.norm_screen(C.cell(row, "screen"))
        if fid and key:
            trace_screen.setdefault(fid, set()).add(key)
    link_screens = {}
    for row in C.linkage(ctx):
        src = C.cell(row, "source_id")
        key = C.norm_screen(C.cell(row, "affected_screen"))
        if src and key:
            link_screens.setdefault(src, set()).add(key)

    bad = []
    for row in done:
        fid = C.cell(row, "feature_id")
        related = set()
        related |= link_screens.get(fid, set())
        related |= trace_screen.get(fid, set())
        if not related:
            continue
        for sid in sorted(related):
            screen = idx.get(sid)
            if screen is None:
                bad.append("%s 相关屏幕 %s 不在 screens.csv" % (fid, sid))
                continue
            ok, detail = C.screen_four_states(screen)
            if not ok:
                bad.append("%s 的 %s 四态缺：%s" % (fid, sid, "，".join(detail)))
    if bad:
        g.fail("screens-four-states", "已完成功能的相关屏幕四态齐",
               expected="相关屏幕 state_filled/empty/loading/error 全部 yes",
               actual="%d 处问题：%s" % (len(bad), "；".join(bad[:4])),
               evidence="BLUEPRINT/screens.csv",
               hint="S6 逐屏重建时四态必须都实现并截图留存；缺态 = 只做了 happy path")
    else:
        g.pass_("screens-four-states", "已完成功能的相关屏幕四态齐",
                expected="相关屏幕四态 yes",
                actual="%d 个已完成功能的相关屏幕全部齐" % len(done),
                evidence="BLUEPRINT/screens.csv")


def _contract_config(g, ctx):
    try:
        configured = int(str(ctx.required.get("contract_sections", 16)).strip())
    except (TypeError, ValueError):
        configured = -1
    if configured == len(C.CONTRACT_HEADINGS):
        g.pass_("contract-config", "manifest 契约节数与 G2 一致",
                expected="contract_sections = %d" % len(C.CONTRACT_HEADINGS),
                actual=str(configured), evidence=C.Context.MANIFEST_REL)
    else:
        g.fail("contract-config", "manifest 契约节数与 G2 一致",
               expected="contract_sections = %d（SCHEMAS §8）" % len(C.CONTRACT_HEADINGS),
               actual="%r" % ctx.required.get("contract_sections"),
               evidence=C.Context.MANIFEST_REL,
               hint="门禁与蓝图必须用同一份节数定义，不允许项目自己减节来过关")


def _src_marker_checks(g, ctx):
    done_must = [r for r in C.must_features(ctx)
                 if C.cell(r, "progress").lower() == DONE_PROGRESS]
    if not done_must:
        g.na("src-markers", "src/ 中 must 功能代码无 TODO/FIXME",
             reason="没有 progress=yes 的 must 功能，无可扫描对象")
        return

    # 路径映射：TRACEABILITY.routes / commands → src/ 下真实文件
    src_base = ctx.path("src")
    if not src_base.is_dir():
        g.fail("src-markers", "src/ 中 must 功能代码无 TODO/FIXME",
               expected="src/ 存在且有 must 功能的实现文件",
               actual="src/ 目录不存在", evidence="src/",
               hint="S6 逐屏重建的代码放 src/；没有 src/ 说明还没开始建")
        return

    files = list(C.iter_text_files(src_base, exts=CODE_EXTS))
    rel_files = {ctx.rel(p): p for p in files}
    lower_map = {k.lower(): k for k in rel_files}

    # 功能 → 候选文件：优先 TRACEABILITY.routes 里的路径片段，其次命令名，再次功能名片段
    mapping, unmapped = {}, []
    trace = {C.cell(r, "feature_id"): r for r in C.traceability(ctx)}
    for row in done_must:
        fid = C.cell(row, "feature_id")
        candidates = set()
        trow = trace.get(fid)
        if trow is not None:
            raw = "%s %s %s" % (C.cell(trow, "routes"), C.cell(trow, "commands"),
                                C.cell(trow, "entities"))
            for token in re.split(r"[;,、\s]+", raw):
                token = token.strip().strip("`'\"")
                if len(token) < 3:
                    continue
                stem = re.sub(r"[^A-Za-z0-9_./-]", "", token).lower()
                if not stem:
                    continue
                for rel, path in rel_files.items():
                    if stem in rel.lower() or stem in path.stem.lower():
                        candidates.add(rel)
        if not candidates:
            # 退路：功能名里的英文/数字片段
            for token in re.split(r"[^A-Za-z0-9]+", fid.lower()):
                if len(token) < 3:
                    continue
                for low, rel in lower_map.items():
                    if token in low:
                        candidates.add(rel)
        if candidates:
            mapping[fid] = sorted(candidates)
        else:
            unmapped.append(fid)

    if not mapping:
        g.na("src-markers", "src/ 中 must 功能代码无 TODO/FIXME",
             reason="TRACEABILITY.csv 没有把功能映射到 src/ 文件（%d 个功能无映射）" % len(done_must),
             expected="可映射的实现文件", actual="0 个功能映射成功",
             evidence="SPEC/TRACEABILITY.csv")
        return

    hits = []
    for fid, rels in mapping.items():
        for rel in rels:
            text = rel_files[rel].read_text(encoding="utf-8", errors="replace")
            for no, raw in enumerate(text.splitlines(), 1):
                for marker in BANNED_MARKERS:
                    if marker in raw:
                        hits.append("%s:%d %s" % (rel, no, marker))
                        break
    if hits:
        g.fail("src-markers", "src/ 中 must 功能代码无 TODO/FIXME",
               expected="已完成功能的实现文件不含 TODO/FIXME",
               actual="%d 处：%s" % (len(hits), "；".join(hits[:5])),
               evidence=hits[0].split()[0],
               hint="要么补完实现并删标记，要么把功能 progress 改回 partial（R7：不许注释掉报错）")
    else:
        g.pass_("src-markers", "src/ 中 must 功能代码无 TODO/FIXME",
                expected="无 TODO/FIXME",
                actual="扫描 %d 个功能 / %d 个文件，0 命中" % (
                    len(mapping), sum(len(v) for v in mapping.values())),
                evidence="src/")
    if unmapped:
        g.na("src-markers-unmapped", "未映射功能的源码扫描",
             reason="%d 个功能在 TRACEABILITY.csv 里没有可对应到 src/ 的路径：%s"
                    % (len(unmapped), "、".join(unmapped[:5])),
             expected="每个 must 功能映射到实现文件",
             actual="无映射（跳过扫描，记 NA）",
             evidence="SPEC/TRACEABILITY.csv")


def check(ctx):
    g = C.Gate(ctx, STAGE)
    if g.no_manifest():
        return g.results

    _feature_done_checks(g, ctx)
    _screen_state_checks(g, ctx)
    _contract_config(g, ctx)
    _src_marker_checks(g, ctx)

    return g.results
