# -*- coding: utf-8 -*-
"""G7 后端与本地能力门（R3/R4 的机器判定部分）。

判定（00-体系总纲.md §3.2 / SCHEMAS.md §14）：
1. 存在故障注入类用例（test-plan 的类型列含「故障 / 注入 / lifecycle / 生命周期」）且 pass
2. 存在「重启读回」类用例且 pass（用例文本含 重启/readback/reload/again 等）
3. 测试代码里不得出现 `:memory:`（扫 tests/、e2e/ 源码，R4）
4. 退出冲刷必须返回结构化结果：src/ 出现 manifest 配置的符号（默认 FlushResult）
5. 存在真实临时文件用法：src/ 或 tests/ 出现 tempfile / mkdtemp / NamedTemporaryFile ≥1
"""

from __future__ import annotations

import re

from . import common as C

STAGE = "G7"

DEFAULT_FLUSH_SYMBOL = "FlushResult"
CODE_EXTS = {".py", ".js", ".ts", ".tsx", ".jsx", ".swift", ".kt", ".java", ".go",
             ".rs", ".cs", ".m", ".mm", ".rb", ".php", ".c", ".cc", ".cpp", ".h"}
FAULT_WORDS = ["故障", "注入", "lifecycle", "生命周期", "fault", "inject", "crash", "中断"]
RESTART_WORDS = ["重启", "读回", "restart", "readback", "reopen", "relaunch", "再次启动"]
TEMP_WORDS = ["tempfile", "mkdtemp", "NamedTemporaryFile", "TemporaryDirectory",
              "tempfile.mkstemp", "createTemporaryDirectory", "NSTemporaryDirectory"]
MEMORY_TOKENS = [":memory:", "memory://", "file::memory:"]


def _code_files(ctx, dirs, exts=CODE_EXTS):
    out = []
    for rel_dir in dirs:
        base = ctx.path(rel_dir)
        if base.is_dir():
            out.extend(C.iter_text_files(base, exts=exts))
    return out


def _scan(files, tokens):
    hits = []
    for path in files:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for no, raw in enumerate(text.splitlines(), 1):
            low = raw
            for tok in tokens:
                if tok in low:
                    hits.append((path, no, tok, raw.strip()[:140]))
                    break
    return hits


def _cases_matching(plan_rows, words):
    out = []
    for row in plan_rows:
        blob = " ".join(str(v) for v in row.get("cells", [])) + " " + str(row.get("type", ""))
        low = blob.lower()
        if any(w.lower() in low for w in words):
            out.append(row)
    return out


def _cases_all_pass(g, ctx, cases, label, code, title):
    if not cases:
        return False
    if cases is None:
        return False
    result = {}
    latest_path, data, err = C.latest_result(ctx)
    if data is not None:
        result = C.result_case_status(data)
    bad, unknown = [], []
    for row in cases:
        cid = str(row.get("id") or "").strip()
        if not cid:
            continue
        if cid not in result:
            unknown.append(cid)
        elif result[cid] != "pass":
            bad.append("%s=%s" % (cid, result[cid]))
    if bad:
        g.fail(code, title,
               expected="%s 类用例在最新结果里全部 pass" % label,
               actual="未通过：%s" % "、".join(bad[:5]),
               evidence=ctx.rel(latest_path) if latest_path else "TEST/results/",
               hint="修复实现后重跑；不许改断言让其通过（R7）")
        return True
    if unknown:
        g.fail(code, title,
               expected="%s 类用例（%s）在最新结果里有记录且 pass" % (
                   label, "、".join(str(r.get("id")) for r in cases[:5])),
               actual="最新结果里没有：%s" % "、".join(unknown[:5]),
               evidence=ctx.rel(latest_path) if latest_path else "TEST/results/",
               hint="跑测试并确保这些用例被实际执行（不是被跳过）")
        return True
    g.pass_(code, title,
            expected="%s 类用例全部 pass" % label,
            actual="%d 条用例通过：%s" % (len(cases), "、".join(str(r.get("id")) for r in cases[:6])),
            evidence=ctx.rel(latest_path) if latest_path else "TEST/results/")
    return True


def check(ctx):
    g = C.Gate(ctx, STAGE)
    if g.no_manifest():
        return g.results

    plan_rows, plan_err = C.load_test_plan(ctx)
    latest_path, latest, latest_err = C.latest_result(ctx)

    if plan_err:
        g.fail("test-plan", "能读到测试用例表",
               expected="TEST/test-plan.md 有 T-xxx 用例表",
               actual=plan_err, evidence="TEST/test-plan.md",
               hint="S2 起草用例、S8 补齐；每行固定列：ID/FL/类型/步骤/期望/自动化")
        for code, title in (("fault-injection", "故障注入类用例存在且 pass"),
                            ("restart-readback", "重启读回类用例存在且 pass")):
            g.blocked(code, title, reason="test-plan.md 不可用，无法判定用例类型",
                      expected=title, actual=plan_err, evidence="TEST/test-plan.md",
                      hint="先补齐 TEST/test-plan.md")
        return g.results

    if latest is None:
        g.fail("results", "TEST/results/ 有最新结果文件",
               expected="至少 1 个 *.json 结果文件（SCHEMAS §14）",
               actual=latest_err, evidence="TEST/results/",
               hint="跑一次测试并把机读结果写进 TEST/results/<日期>-<run>.json")

    # ---- 1. 故障注入 ----
    fault_cases = _cases_matching(plan_rows, FAULT_WORDS)
    if not fault_cases:
        g.fail("fault-injection", "故障注入类用例存在且 pass",
               expected="test-plan.md 的「类型」列含 故障/注入/lifecycle 的用例 ≥1 条",
               actual="没有该类用例", evidence="TEST/test-plan.md",
               hint="加用例：写失败（磁盘满/只读）、关窗冲刷失败、进程被 kill、DB 锁竞争；"
                    "断言必须是具体值（丢了几条、草稿是否还在）")
    elif latest is None:
        g.fail("fault-injection", "故障注入类用例存在且 pass",
               expected="该类用例 pass", actual="没有结果文件",
               evidence="TEST/results/", hint="跑测试并落机读结果")
    else:
        _cases_all_pass(g, ctx, fault_cases, "故障注入",
                        "fault-injection", "故障注入类用例存在且 pass")

    # ---- 2. 重启读回 ----
    restart_cases = _cases_matching(plan_rows, RESTART_WORDS)
    if not restart_cases:
        g.fail("restart-readback", "重启读回类用例存在且 pass",
               expected="test-plan.md 含「重启后读回」类用例 ≥1 条",
               actual="没有该类用例", evidence="TEST/test-plan.md",
               hint="加用例：写入 → 关进程 → 重启 → 读回，断言具体值（R4：查具体值不查非空）")
    elif latest is None:
        g.fail("restart-readback", "重启读回类用例存在且 pass",
               expected="该类用例 pass", actual="没有结果文件",
               evidence="TEST/results/", hint="跑测试并落机读结果")
    else:
        _cases_all_pass(g, ctx, restart_cases, "重启读回",
                        "restart-readback", "重启读回类用例存在且 pass")

    # ---- 3. 禁 :memory: ----
    test_files = _code_files(ctx, ["tests", "e2e"])
    if not test_files:
        g.na("no-memory-db", "测试代码不使用内存数据库",
             reason="tests/ 与 e2e/ 下没有源码文件（尚未写测试代码）",
             expected="不出现 :memory:", actual="无文件可扫", evidence="tests/")
    else:
        hits = _scan(test_files, MEMORY_TOKENS)
        if hits:
            where = "；".join("%s:%d %s" % (ctx.rel(p), no, tok) for p, no, tok, _ in hits[:4])
            g.fail("no-memory-db", "测试代码不使用内存数据库",
                   expected="测试用真文件数据库（R4）",
                   actual="%d 处使用内存库：%s" % (len(hits), where),
                   evidence=ctx.rel(hits[0][0]),
                   hint="改用 tempfile.mkdtemp() 下的真文件；断言具体值。内存库会把持久化 bug 全掩盖")
        else:
            g.pass_("no-memory-db", "测试代码不使用内存数据库",
                    expected="不出现 :memory:",
                    actual="扫描 %d 个文件，0 命中" % len(test_files), evidence="tests/")

    # ---- 4. 退出冲刷结构化结果 ----
    symbol = str(ctx.cfg("flush_result_symbol", DEFAULT_FLUSH_SYMBOL) or DEFAULT_FLUSH_SYMBOL).strip()
    src_files = _code_files(ctx, ["src"])
    flush_hits = _scan(src_files, [symbol]) if src_files else []
    flush_checked_in_tests = _scan(test_files, [symbol]) if test_files else []
    if flush_hits:
        path, no, tok, line = flush_hits[0]
        g.pass_("flush-result", "退出冲刷返回结构化结果",
                expected="src/ 出现 %s（manifest.required.flush_result_symbol 可配）" % symbol,
                actual="%d 处命中，例 %s:%d" % (len(flush_hits), ctx.rel(path), no),
                evidence="%s:%d" % (ctx.rel(path), no))
    elif flush_checked_in_tests:
        path, no, tok, line = flush_checked_in_tests[0]
        g.fail("flush-result", "退出冲刷返回结构化结果",
               expected="实现里存在 %s 类型/符号，且冲刷返回成功/失败/未知三态" % symbol,
               actual="只在测试里出现（%s:%d），实现里没有" % (ctx.rel(path), no),
               evidence="%s:%d" % (ctx.rel(path), no),
               hint="实现 FlushResult{ok/unknown/error} 并从关窗流程返回它；测试断言具体状态（R3/R19）")
    else:
        g.fail("flush-result", "退出冲刷返回结构化结果",
               expected="src/ 出现 %s" % symbol,
               actual="src/ 下 0 命中（扫描 %d 个文件）" % len(src_files),
               evidence="src/",
               hint="关窗/退出必须冲刷并返回结构化结果，不许 fire-and-forget（R3）；"
                    "符号名可通过 manifest.required.flush_result_symbol 配置")

    # ---- 5. 真临时文件 ----
    candidates = src_files + test_files
    if not candidates:
        g.na("temp-files", "存在真实临时文件路径用法",
             reason="src/、tests/、e2e/ 下都还没有源码文件",
             expected="tempfile/mkdtemp/NamedTemporaryFile", actual="无文件可扫",
             evidence="tests/")
    else:
        hits = _scan(candidates, TEMP_WORDS)
        if hits:
            path, no, tok, _ = hits[0]
            g.pass_("temp-files", "存在真实临时文件路径用法",
                    expected="tempfile / mkdtemp / NamedTemporaryFile ≥1",
                    actual="%d 处命中，例 %s:%d（%s）" % (len(hits), ctx.rel(path), no, tok),
                    evidence="%s:%d" % (ctx.rel(path), no))
        else:
            g.fail("temp-files", "存在真实临时文件路径用法",
                   expected="出现 tempfile / mkdtemp / NamedTemporaryFile ≥1",
                   actual="%d 个文件里 0 命中" % len(candidates), evidence="tests/",
                   hint="持久化测试必须对真文件跑（临时目录 + 真 SQLite 文件）；"
                        "内存库测不出 WAL/冲刷/重启问题")

    return g.results
