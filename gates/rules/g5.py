# -*- coding: utf-8 -*-
"""G5 设计门。

判定（00-体系总纲.md §3.2 / SCHEMAS.md §13）：
1. SPEC/DESIGN/tokens.json 存在、可 JSON 解析，且含 color / font / space / radius / pairs
2. 调用 replica-skill/replica-design/contrast.py 做 WCAG 对比度检查：
   有失败即 FAIL；脚本不存在/不可导入 → NA（带理由，R20）
3. components.md 存在，每个组件块都列出 default/hover/focus/disabled/loading/error 六态
4. 替换表（开源图标/字体）存在且无空项
"""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys

from . import common as C

STAGE = "G5"

DEFAULT_TOKENS = "SPEC/DESIGN/tokens.json"
DEFAULT_COMPONENTS = "SPEC/DESIGN/components.md"
DEFAULT_CONTRAST = "replica-skill/replica-design/contrast.py"

REQUIRED_TOKEN_KEYS = ["color", "font", "space", "radius", "pairs"]
REQUIRED_STATES = ["default", "hover", "focus", "disabled", "loading", "error"]
STATE_ALIASES = {
    "default": ["default", "默认"],
    "hover": ["hover", "悬停"],
    "focus": ["focus", "聚焦", "焦点"],
    "disabled": ["disabled", "禁用"],
    "loading": ["loading", "加载中", "加载"],
    "error": ["error", "错误"],
}


def _rel(ctx, key, default):
    return str(ctx.required.get(key) or default).strip()


def _load_tokens(g, ctx, rel):
    text = ctx.text(rel)
    if text is None:
        g.fail("tokens-file", "tokens.json 存在且可解析",
               expected="%s 存在" % rel, actual="文件不存在", evidence=rel,
               hint="按 SCHEMAS §13 / replica-skill/replica-design/tokens.json 建 tokens.json")
        return None
    try:
        tokens = json.loads(text)
    except ValueError as exc:
        g.fail("tokens-file", "tokens.json 存在且可解析",
               expected="合法 JSON", actual="解析失败：%s" % exc, evidence=rel,
               hint="检查逗号/引号；不要留尾逗号")
        return None
    if not isinstance(tokens, dict):
        g.fail("tokens-file", "tokens.json 存在且可解析",
               expected="顶层是对象", actual="顶层是 %s" % type(tokens).__name__,
               evidence=rel, hint="tokens.json 顶层必须是 JSON 对象")
        return None
    g.pass_("tokens-file", "tokens.json 存在且可解析",
            expected="合法 JSON 对象", actual="%d 个顶层键" % len(tokens), evidence=rel)

    missing = [k for k in REQUIRED_TOKEN_KEYS if k not in tokens]
    if missing:
        g.fail("tokens-keys", "tokens.json 含 color/font/space/radius/pairs",
               expected="、".join(REQUIRED_TOKEN_KEYS),
               actual="缺：%s" % "、".join(missing), evidence=rel,
               hint="补齐键：color（角色色）、font、space、radius、pairs（前景/背景组合）")
    else:
        g.pass_("tokens-keys", "tokens.json 含 color/font/space/radius/pairs",
                expected="、".join(REQUIRED_TOKEN_KEYS),
                actual="5 个键齐全", evidence=rel)

    # 颜色角色（SCHEMAS §13 列出的角色名）
    color = tokens.get("color") or {}
    if isinstance(color, dict):
        roles = ["bg", "surface", "border", "text", "text-muted", "accent",
                 "on-accent", "danger", "success"]
        flat = set()
        for k, v in color.items():
            if isinstance(v, dict):
                for k2 in v:
                    flat.add(k)
                    flat.add("%s-%s" % (k, k2))
            else:
                flat.add(k)
        missing_roles = [r for r in roles if r not in flat]
        if missing_roles:
            g.fail("tokens-roles", "颜色角色齐（SCHEMAS §13 的 9 个角色）",
                   expected="、".join(roles),
                   actual="缺：%s" % "、".join(missing_roles), evidence=rel,
                   hint="补角色色：bg/surface/border/text/text-muted/accent/on-accent/danger/success")
        else:
            g.pass_("tokens-roles", "颜色角色齐（SCHEMAS §13 的 9 个角色）",
                    expected="9 个角色", actual="9 个角色齐全", evidence=rel)
    else:
        g.fail("tokens-roles", "颜色角色齐（SCHEMAS §13 的 9 个角色）",
               expected="color 是对象", actual="color 不是对象", evidence=rel,
               hint="color 写成 {bg: '#…', text: '#…', …}")
    return tokens


def _contrast(g, ctx, tokens, rel):
    module_rel = _rel(ctx, "contrast_module", DEFAULT_CONTRAST)
    path = C.SYSTEM_ROOT / module_rel
    if not path.is_file():
        g.na("contrast", "对比度检查 0 失败（contrast.py）",
             reason="未找到 %s，本机没有可用的对比度检查器" % module_rel,
             expected="contrast.py 存在且 0 失败", actual="脚本不存在",
             evidence=module_rel)
        return

    pairs = tokens.get("pairs")
    rows = None
    try:
        spec = importlib.util.spec_from_file_location("replica_contrast", str(path))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)  # type: ignore[union-attr]
        cols = module.colours(tokens)          # noqa: SLF001 - 上游稳定 API
        use_pairs = pairs or module.default_pairs(cols)
        rows = module.check(cols, use_pairs)
    except Exception as exc:  # 上游 API 变了或导入失败 → 退到命令行
        try:
            proc = subprocess.run(
                [sys.executable, str(path), str(ctx.path(rel)), "--json"],
                capture_output=True, text=True, timeout=60)
            rows = json.loads(proc.stdout or "[]")
        except Exception as exc2:
            g.fail("contrast", "对比度检查 0 失败（contrast.py）",
                   expected="contrast.py 可运行", actual="导入与命令行都失败：%s / %s" % (exc, exc2),
                   evidence=module_rel,
                   hint="检查 contrast.py 是否可读、tokens.json 的 pairs 是否引用存在的角色")
            return

    if not rows:
        g.fail("contrast", "对比度检查 0 失败（contrast.py）",
               expected="至少 1 组前景/背景对",
               actual="pairs 为空，没有可检查的组合", evidence=rel,
               hint="在 tokens.json 的 pairs 里列出组合，例 [[\"text\",\"bg\"],[\"on-accent\",\"accent\"]]")
        return
    fails = [r for r in rows if "error" in r or not r.get("aa", False)]
    if fails:
        detail = []
        for r in fails[:4]:
            if "error" in r:
                detail.append("%s on %s：%s" % (r.get("fg"), r.get("bg"), r["error"]))
            else:
                detail.append("%s on %s = %.2f:1（需 %.1f）" % (
                    r.get("fg"), r.get("bg"), r.get("ratio", 0),
                    4.5 if r.get("size") == "normal" else 3.0))
        g.fail("contrast", "对比度检查 0 失败（contrast.py）",
               expected="所有 pairs 达 WCAG AA", actual="%d 组不达标：%s" % (
                   len(fails), "；".join(detail)), evidence=rel,
               hint="换前景或背景色；大字号（large）门槛 3:1，UI 元素 3:1，正文 4.5:1")
    else:
        g.pass_("contrast", "对比度检查 0 失败（contrast.py）",
                expected="所有 pairs 达 WCAG AA",
                actual="%d 组全部通过" % len(rows), evidence=rel)


def _is_component_block(section):
    """组件块判定：块内必须有一张含「状态/state」列的表，或一行 states 说明。

    排除「替换表」「索引」「说明」这类非组件小节。
    """
    title = section["title"]
    if re.search(r"替换|索引|目录|说明|表$|token|token", title, re.I):
        return False
    for table in C.md_tables(section["body"]):
        header = " ".join(table["header"]).lower()
        if "状态" in header or "state" in header:
            return True
    return "states" in section["body"].lower() or "状态" in section["body"]


def _components(g, ctx, rel):
    text = ctx.text(rel)
    if text is None:
        g.fail("components-file", "components.md 存在",
               expected="%s 存在" % rel, actual="文件不存在", evidence=rel,
               hint="按 templates/engineering/components.template.md 逐组件写六态")
        return
    candidates = C.md_sections(text, 2)
    if len([s for s in candidates if _is_component_block(s)]) <= 1:
        deeper = C.md_sections(text, 3)
        if len([s for s in deeper if _is_component_block(s)]) > 1:
            candidates = deeper
    comps = [s for s in candidates if _is_component_block(s)]
    if not comps:
        g.fail("components-blocks", "components.md 每个组件有六态",
               expected="每个组件一个标题块，块内有「状态」列并列出六态",
               actual="没有解析到组件块", evidence=rel,
               hint="用 `## Button` 这样的标题逐个组件，块内放一张「状态 | 视觉 | 触发条件」表")
        return
    bad, good = [], []
    for sec in comps:
        body = sec["body"].lower()
        missing = [st for st in REQUIRED_STATES
                   if not any(alias.lower() in body for alias in STATE_ALIASES[st])]
        if missing:
            bad.append("%s 缺 %s" % (sec["title"], "/".join(missing)))
        else:
            good.append(sec["title"])
    if bad:
        g.fail("components-blocks", "components.md 每个组件有六态",
               expected="每块含 default/hover/focus/disabled/loading/error",
               actual="%d 个不齐：%s" % (len(bad), "；".join(bad[:4])),
               evidence=rel,
               hint="每组件补 6 态：默认、悬停、聚焦、禁用、加载中、错误；写清视觉差与触发条件")
    else:
        g.pass_("components-blocks", "components.md 每个组件有六态",
                expected="六态齐全", actual="%d 个组件全部六态齐全" % len(good),
                evidence=rel)


def _replacement_table(g, ctx, rel):
    text = ctx.text(rel)
    if text is None:
        g.na("replacement-table", "替换表（图标/字体）无空项",
             reason="components.md 不存在（见 components-file）")
        return
    sec = C.section_by_keyword(C.md_sections(text, 2), ["替换", "图标", "字体", "icon", "font"])
    body = sec["body"] if sec else text
    table = None
    for t in C.md_tables(body):
        if t["header"] and any(k in " ".join(t["header"]) for k in
                               ("原", "替换", "图标", "字体", "来源", "许可")):
            table = t
            break
    if table is None:
        g.fail("replacement-table", "替换表（图标/字体）无空项",
               expected="有「原素材 → 替换为 → 来源/许可」表格且无空项",
               actual="没找到替换表", evidence=rel,
               hint="列出原版用到的图标/字体及你的替代方案（开源库 + 许可证），不许留空")
        return
    empties = []
    for cells, no in zip(table["rows"], table["lines"]):
        for i, cell in enumerate(cells):
            if C.is_blank(cell) or cell.strip() in ("待定", "TBD", "TODO"):
                head = table["header"][i] if i < len(table["header"]) else "第%d列" % (i + 1)
                empties.append("第 %d 行「%s」为空" % (no, head))
    if empties:
        g.fail("replacement-table", "替换表（图标/字体）无空项",
               expected="每行每列都有值",
               actual="%d 处空缺：%s" % (len(empties), "；".join(empties[:4])),
               evidence=rel,
               hint="补全替代方案与许可证；确实沿用系统字体就写「系统字体栈（无版权风险）」")
    else:
        g.pass_("replacement-table", "替换表（图标/字体）无空项",
                expected="无空项", actual="%d 行全部填写" % len(table["rows"]),
                evidence=rel)


def check(ctx):
    g = C.Gate(ctx, STAGE)
    if g.no_manifest():
        return g.results

    tokens_rel = _rel(ctx, "design_tokens", DEFAULT_TOKENS)
    components_rel = _rel(ctx, "design_components", DEFAULT_COMPONENTS)

    tokens = _load_tokens(g, ctx, tokens_rel)
    if tokens is None:
        g.na("contrast", "对比度检查 0 失败（contrast.py）", reason="tokens.json 不可用")
    else:
        _contrast(g, ctx, tokens, tokens_rel)

    _components(g, ctx, components_rel)
    _replacement_table(g, ctx, components_rel)

    return g.results
