# -*- coding: utf-8 -*-
"""G11 发布门（A 档本地 runbook；C 档加品牌清扫与上架合规）。

A/B 档判定：
1. 启动方式存在：manifest.required.start_script（默认 scripts/start.sh）可执行，
   或 runbook 里给出可执行启动命令
2. runbook 含 备份 / 恢复 / 迁移 / 卸载 四节
3. 有恢复演练记录：REPORT/release/restore-drill.md，或 runbook 内「演练」字样 + 日期
C 档额外：
4. replica-skill/replica-brand/sweep.py 可运行且 0 命中（脚本不存在 → NA）
5. REPORT/release/listing-check.json 存在且可解析
A/B 档的 C 档项按 manifest.na_approved 记 NA（带理由，R20）。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

from . import common as C

STAGE = "G11"

DEFAULT_START = "scripts/start.sh"
DEFAULT_RUNBOOK = "REPORT/release/local-runbook.md"
DEFAULT_DRILL = "REPORT/release/restore-drill.md"
DEFAULT_LISTING = "REPORT/release/listing-check.json"
DEFAULT_SWEEP = "replica-skill/replica-brand/sweep.py"

RUNBOOK_SECTIONS = {
    "备份": ["备份", "backup"],
    "恢复": ["恢复", "还原", "restore"],
    "迁移": ["迁移", "migrate", "migration"],
    "卸载": ["卸载", "uninstall", "移除"],
}
START_HINTS = ["start.sh", "启动", "npm start", "npm run", "python3 -m", "python src/",
               "open ", "./run", "make run", "uv run", "pnpm"]


def _rel(ctx, key, default):
    return str(ctx.required.get(key) or default).strip()


def _start_checks(g, ctx):
    rel = _rel(ctx, "start_script", DEFAULT_START)
    path = ctx.path(rel)
    runbook_rel = _rel(ctx, "runbook", DEFAULT_RUNBOOK)
    runbook = ctx.text(runbook_rel) or ""

    script_ok = path.is_file()
    executable = bool(script_ok and os.access(str(path), os.X_OK))
    runbook_cmd = [line for line in runbook.splitlines()
                   if line.strip().startswith(("```", "$ ")) is False
                   and any(h in line for h in START_HINTS)
                   and not line.strip().startswith("#")]

    if script_ok and executable:
        g.pass_("start-script", "启动脚本存在且可执行",
                expected="%s 存在且 chmod +x" % rel,
                actual="存在且可执行", evidence=rel)
    elif script_ok:
        g.fail("start-script", "启动脚本存在且可执行",
               expected="%s 可执行（chmod +x）" % rel,
               actual="文件存在但没有执行权限", evidence=rel,
               hint="chmod +x %s；干净机器上第一条命令就应该能启动" % rel)
    elif runbook_cmd:
        g.pass_("start-script", "启动脚本存在且可执行",
                expected="脚本可执行，或 runbook 给出启动命令",
                actual="无 %s，但 runbook 有启动命令：%s" % (rel, runbook_cmd[0].strip()[:60]),
                evidence=runbook_rel)
    else:
        g.fail("start-script", "启动脚本存在且可执行",
               expected="%s 可执行，或 runbook 内写明启动命令" % rel,
               actual="两者都没有", evidence=rel,
               hint="A 档至少要能一条命令起来：写 scripts/start.sh 或在 runbook 的「启动」节给命令")


def _runbook_checks(g, ctx):
    rel = _rel(ctx, "runbook", DEFAULT_RUNBOOK)
    text = ctx.text(rel)
    if text is None:
        g.fail("runbook", "runbook 含 备份/恢复/迁移/卸载 四节",
               expected="%s 存在且四节齐全" % rel, actual="文件不存在",
               evidence=rel,
               hint="按 templates/engineering/runbook.template.md 写四节，每节给可复制命令与期望输出")
        return ""
    titles = [t for lvl, t, _no in C.md_headings(text)]
    blob = "\n".join(titles) + "\n" + text
    missing = [name for name, keys in RUNBOOK_SECTIONS.items()
               if not any(any(k.lower() in t.lower() for k in keys) for t in titles)
               and not any(k in blob for k in keys)]
    if missing:
        g.fail("runbook", "runbook 含 备份/恢复/迁移/卸载 四节",
               expected="四节：%s" % " / ".join(RUNBOOK_SECTIONS),
               actual="缺：%s" % "、".join(missing), evidence=rel,
               hint="每节写清：命令、数据落在哪、期望输出、失败怎么办（A 档不做品牌门但不许没有恢复路径）")
    else:
        g.pass_("runbook", "runbook 含 备份/恢复/迁移/卸载 四节",
                expected="四节齐全", actual="四节齐全（%d 个标题）" % len(titles),
                evidence=rel)
    return text


def _drill_checks(g, ctx, runbook_text):
    rel = _rel(ctx, "restore_drill", DEFAULT_DRILL)
    text = ctx.text(rel)
    if text is not None and len(text.strip()) >= 40:
        date = C.DATE_RE.search(text) or C.ISO_DATETIME_RE.search(text)
        g.pass_("restore-drill", "有恢复演练记录",
                expected="%s 含演练时间与结果" % rel,
                actual="存在，%s" % ("日期 " + date.group(0) if date else "未写日期"),
                evidence=rel)
        if date is None:
            g.fail("restore-drill-date", "恢复演练记录带日期",
                   expected="含 ISO 8601 日期/时间", actual="没有日期", evidence=rel,
                   hint="演练必须能被追溯：写清哪天演练、备份哪份、恢复后校验了什么")
        else:
            g.pass_("restore-drill-date", "恢复演练记录带日期",
                    expected="ISO 8601 日期", actual=date.group(0), evidence=rel)
        return
    if runbook_text and "演练" in runbook_text:
        date = C.DATE_RE.search(runbook_text)
        if date:
            g.pass_("restore-drill", "有恢复演练记录",
                    expected="演练记录文件或 runbook 内演练字样 + 日期",
                    actual="runbook 内含「演练」与日期 %s" % date.group(0),
                    evidence=_rel(ctx, "runbook", DEFAULT_RUNBOOK))
            return
        g.fail("restore-drill", "有恢复演练记录",
               expected="演练记录含日期", actual="runbook 提到演练但没有日期",
               evidence=_rel(ctx, "runbook", DEFAULT_RUNBOOK),
               hint="写「2026-10-22 演练：备份 → 删库 → 恢复 → 逐行比对 128 行一致」")
        return
    g.fail("restore-drill", "有恢复演练记录",
           expected="%s 存在，或 runbook 内含「演练」+ 日期" % rel,
           actual="两者都没有", evidence=rel,
           hint="备份没演练等于没有备份：真删一次、真恢复一次、记下逐条校验结果")


def _commercial_checks(g, ctx):
    tier = ctx.tier or "A"
    if tier != "C":
        approved = ctx.na_approved.get("G11.commercial") or {}
        reason = approved.get("reason") if isinstance(approved, dict) else ""
        g.na("commercial", "C 档品牌清扫 0 命中 + 上架合规检查",
             reason=("档位 %s，不做商店合规（manifest.na_approved：%s）" % (tier, reason)
                     if reason else "档位 %s，不做商业档，无需品牌清扫与上架合规" % tier),
             expected="仅 C 档必做", actual="档位 %s" % tier,
             evidence=C.Context.MANIFEST_REL)
        return

    # ---- sweep.py ----
    sweep_rel = _rel(ctx, "brand_sweep", DEFAULT_SWEEP)
    sweep = C.SYSTEM_ROOT / sweep_rel
    avoid = ctx.cfg("brand_avoid") or ""
    if not sweep.is_file():
        g.na("brand-sweep", "品牌清扫 0 命中（sweep.py）",
             reason="未找到 %s" % sweep_rel, expected="sweep.py 可运行且 0 命中",
             actual="脚本不存在", evidence=sweep_rel)
    elif not avoid:
        g.na("brand-sweep", "品牌清扫 0 命中（sweep.py）",
             reason="manifest 未配置 required.brand_avoid，无清扫词表",
             expected="sweep.py 0 命中", actual="未配置词表", evidence=C.Context.MANIFEST_REL)
    else:
        cmd = [sys.executable, str(sweep), str(ctx.root), "--avoid", str(avoid)]
        domains = ctx.cfg("brand_domains")
        if domains:
            cmd += ["--domains", str(domains)]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        except Exception as exc:
            g.fail("brand-sweep", "品牌清扫 0 命中（sweep.py）",
                   expected="sweep.py 可运行", actual="运行失败：%s" % exc, evidence=sweep_rel,
                   hint="检查 sweep.py 依赖与 --avoid 参数格式")
            return
        hits = 1 if proc.returncode != 0 else 0
        if hits:
            tail = (proc.stdout or proc.stderr or "").strip().splitlines()[:6]
            g.fail("brand-sweep", "品牌清扫 0 命中（sweep.py）",
                   expected="0 命中", actual="有残留（退出码 %d）：%s" % (
                       proc.returncode, " / ".join(tail)),
                   evidence=sweep_rel,
                   hint="清除原版名称/域名/品牌色（含标识符内的名字），再跑一次 sweep.py")
        else:
            g.pass_("brand-sweep", "品牌清扫 0 命中（sweep.py）",
                    expected="0 命中", actual="退出码 0", evidence=sweep_rel)

    # ---- listing-check.json ----
    listing_rel = _rel(ctx, "listing_check", DEFAULT_LISTING)
    text = ctx.text(listing_rel)
    if text is None:
        g.fail("listing-check", "listing-check.json 存在且可解析",
               expected="%s 存在" % listing_rel, actual="文件不存在", evidence=listing_rel,
               hint="记录商店 listing 限制检查结果（截图/文案/权限声明是否合规）")
        return
    try:
        data = json.loads(text)
    except ValueError as exc:
        g.fail("listing-check", "listing-check.json 存在且可解析",
               expected="合法 JSON", actual="解析失败：%s" % exc, evidence=listing_rel,
               hint="修 JSON 语法；含检查项、结论、证据路径、时间")
        return
    g.pass_("listing-check", "listing-check.json 存在且可解析",
            expected="合法 JSON 对象",
            actual="%d 个键" % (len(data) if isinstance(data, (dict, list)) else 1),
            evidence=listing_rel)


def check(ctx):
    g = C.Gate(ctx, STAGE)
    if g.no_manifest():
        return g.results

    _start_checks(g, ctx)
    runbook_text = _runbook_checks(g, ctx)
    _drill_checks(g, ctx, runbook_text)
    _commercial_checks(g, ctx)

    return g.results
