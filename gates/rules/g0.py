# -*- coding: utf-8 -*-
"""G0 立项门。

判定（00-体系总纲.md §3.2 / SCHEMAS.md）：
1. PROJECT.md 存在且非空
2. 含「一句话定位」且是具体一句话（≥10 字），全文无 `______` 占位
3. 不做清单 ≥5 条（有序列表 / 无序列表 / 表格行）
4. 档位 ∈ {A, B, C}
5. 目标制品身份含名称 + 版本 + SHA-256（或写明「取证方式」）
6. DECISIONS.md 有 ≥3 条 D- 记录
7. REDLINES.md 含 R1–R20
8. AGENTS.md 存在
9. manifest 存在且 tier 合法（缺失时本门整体 BLOCKED）
"""

from __future__ import annotations

import re

from . import common as C

STAGE = "G0"


def _one_liner(text):
    """返回「一句话定位」后面的那句话；找不到返回 None，找到但为空返回 ""。"""
    lines = text.splitlines()
    for i, raw in enumerate(lines):
        if "一句话定位" not in raw:
            continue
        m = re.split(r"一句话定位[^\n:：]{0,20}[:：]", raw, maxsplit=1)
        if len(m) == 2 and m[1].strip():
            return m[1].strip().lstrip("-*> ").strip()
        for nxt in lines[i + 1:i + 4]:
            s = nxt.strip()
            if not s or s.startswith("#"):
                continue
            return s.lstrip("-*> ").strip()
        return ""
    return None


# 占位符：空行、模板下划线、示例标记都不能算"已填条目"
_PLACEHOLDER_RE = re.compile(
    r"^[_\-\s]*$"                      # 全空 / 全下划线
    r"|^\|\s*\|\s*\|\s*\|\s*\|\s*$"     # 全空表格行
    r"|^\|\s*(示例|example|待填|TBD|-+)\s*\|",  # 表格首格是占位词
    re.I,
)


def _row_is_filled(cells):
    """表格一行是否真的填了内容。"""
    values = [c.strip() for c in cells]
    # 全空
    if not any(values):
        return False
    # 只有编号列有值，其余空 → 模板骨架
    nonempty = [v for v in values if v]
    if len(nonempty) <= 1:
        return False
    # 任一格是占位符 → 不算
    for v in nonempty:
        if v in ("-", "—", "待填", "TBD", "示例", "example", "____"):
            return False
        if set(v) <= set("_ "):
            return False
    return True


def _count_list_items(body):
    """数列表项与表格数据行（不做清单的合法写法）。

    模板骨架（空行、占位符、只有编号的空行）**不算**条目——
    否则新项目刚生成就能通过"≥5 条"，这是假绿。
    """
    items = 0
    for line in body.splitlines():
        s = line.strip()
        if re.match(r"^\d+[.、)]\s+\S", s) or re.match(r"^[-*+]\s+\S", s):
            if _PLACEHOLDER_RE.match(s):
                continue
            items += 1
    for table in C.md_tables(body):
        for row in table["rows"]:
            if _row_is_filled(row):
                items += 1
    return items


def _real_decision_ids(text):
    """数真正的决策记录：**只统计「## 决策表」小节内的表格行**。

    为什么限定小节：
    - 模板里「## 实例（格式参考）」章节带 4 条格式完整的示例决策（D-001/D-002/D-007/D-021），
      按全文正则统计会让新项目一生成就「≥3 条」——这是假绿。
    - 只认决策表，才能区分「抄了模板示例」与「真的做了决策」。

    行结构要求（同时满足）：
    ① 首格是 D-xxx；② 第 2 格是 ISO 日期；③ 除编号/日期外还有 ≥2 个非空内容格
    （决策内容 + 理由），排除只填了编号的骨架行。
    """
    section = None
    for sec in C.md_sections(text, 2):
        if re.search(r"决策表|决策台账|决策记录|decisions?\s*table", sec["title"], re.I):
            section = sec
            break
    if section is None:
        return []

    ids = set()
    for table in C.md_tables(section["body"]):
        for cells in table["rows"]:
            if len(cells) < 3:
                continue
            m = re.search(r"\bD-\d+\b", cells[0])
            if not m:
                continue
            rest = cells[1:]
            # ② 第 2 格必须是 ISO 日期（不带日期 = 还没真决策）
            if not re.search(r"\d{4}-\d{2}-\d{2}", rest[0] if rest else ""):
                continue
            # ③ 除日期外还要有 ≥2 个实质内容格
            filled = [c for c in rest[1:]
                      if c and c not in ("-", "—", "待填", "TBD", "示例", "example")]
            if len(filled) < 2:
                continue
            ids.add(m.group(0))
    return sorted(ids)


def _tier_of(text):
    m = re.search(r"(?:档位|tier)[^\n]{0,24}?\b([ABCabc])\b", text)
    if m:
        return m.group(1).upper()
    m = re.search(r"(?:^|\s)([ABCabc])\s*档", text)
    if m:
        return m.group(1).upper()
    for word, tier in (("本地自用", "A"), ("半自用", "B"), ("商业", "C")):
        if word in text:
            return tier
    return ""


def _block_text(text, sections, keywords, extra_lines=3):
    sec = C.section_by_keyword(sections, keywords)
    if sec:
        return sec["body"]
    lines = text.splitlines()
    for i, raw in enumerate(lines):
        if any(k in raw for k in keywords):
            return "\n".join(lines[i:i + 1 + extra_lines])
    return ""


def check(ctx):
    g = C.Gate(ctx, STAGE)
    if g.no_manifest():
        return g.results

    project = ctx.text("PROJECT.md")
    g.need_file("PROJECT.md", "project-exists", "PROJECT.md 存在且非空",
                hint="从 templates/engineering/PROJECT.template.md 复制一份，填 S0 立项内容")

    # 2. 一句话定位 + 占位符
    if project is None:
        g.fail("oneliner", "PROJECT.md 含具体的一句话定位",
               expected="「一句话定位」后跟一句 ≥10 字的话",
               actual="PROJECT.md 不存在", evidence="PROJECT.md",
               hint="写清：为谁、解决什么问题、凭什么做到")
    else:
        liner = _one_liner(project)
        if liner is None:
            g.fail("oneliner", "PROJECT.md 含具体的一句话定位",
                   expected="含「一句话定位」小节或行",
                   actual="全文没出现「一句话定位」", evidence="PROJECT.md",
                   hint="加一节「一句话定位：<一句话写清为谁解决什么>」")
        elif len(liner) < 10:
            g.fail("oneliner", "PROJECT.md 含具体的一句话定位",
                   expected="定位句 ≥10 字且可判断真假",
                   actual="定位句过短或为空：%r" % liner,
                   evidence="PROJECT.md", hint="把定位写成可验收的一句话，别写「做好用的工具」")
        else:
            g.pass_("oneliner", "PROJECT.md 含具体的一句话定位",
                    expected="定位句 ≥10 字", actual=liner[:60], evidence="PROJECT.md")

        placeholders = [no for no, raw in enumerate(project.splitlines(), 1)
                        if re.search(r"_{6,}", raw)]
        if placeholders:
            g.fail("placeholders", "PROJECT.md 无 `______` 占位",
                   expected="所有空都填上，未定的进 unknowns.csv",
                   actual="第 %s 行仍有 ______ 占位" % ", ".join(map(str, placeholders[:6])),
                   evidence="PROJECT.md:%d" % placeholders[0],
                   hint="填掉占位文本；确实未知的写进 BLUEPRINT/unknowns.csv 并给出补验动作")
        else:
            g.pass_("placeholders", "PROJECT.md 无 `______` 占位",
                    expected="无 6 个以上连续下划线", actual="未发现占位", evidence="PROJECT.md")

    # 3. 不做清单 ≥5
    sections = C.md_sections(project or "", 2)
    sec = C.section_by_keyword(sections, ["不做", "不解决", "非目标", "范围外",
                                          "排除清单", "这一版不做"])
    if sec is None:
        g.fail("not-do-list", "不做清单 ≥5 条",
               expected="有「不做清单 / 非目标 / 范围外」小节且 ≥5 条",
               actual="未找到该小节", evidence="PROJECT.md",
               hint="加一节「不做清单（≥5 条）」：明确这一版不做什么，防止采证与开发范围失控")
    else:
        count = _count_list_items(sec["body"])
        if count >= 5:
            g.pass_("not-do-list", "不做清单 ≥5 条",
                    expected="≥5 条", actual="%d 条" % count,
                    evidence="PROJECT.md:%d" % sec["line"])
        else:
            g.fail("not-do-list", "不做清单 ≥5 条",
                   expected="≥5 条（有序列表或表格行）",
                   actual="只有 %d 条" % count,
                   evidence="PROJECT.md:%d" % sec["line"],
                   hint="补到 ≥5 条：不做的功能、不做的平台、不做的档位、不接的接口、不做的自动化")

    # 4. 档位
    tier = _tier_of(project or "")
    if tier:
        g.pass_("tier", "档位 ∈ {A, B, C}",
                expected="A / B / C", actual="%s 档" % tier, evidence="PROJECT.md")
    else:
        g.fail("tier", "档位 ∈ {A, B, C}",
               expected="明确写「档位：A / B / C」及判定理由",
               actual="未找到可判定的档位",
               evidence="PROJECT.md",
               hint="A=本地自用 / B=半自用 / C=商业；档位决定 S10/S11 与品牌门是否必做")

    # 5. 目标制品身份
    block = _block_text(project or "", sections,
                        ["目标制品", "制品身份", "制品", "目标应用"])
    has_version = bool(re.search(r"\b\d+\.\d+(?:\.\d+)?\b", block)) or "版本" in block
    has_hash = bool(C.SHA256_RE.search(block))
    has_forensics = "取证方式" in block
    if block and has_version and (has_hash or has_forensics):
        g.pass_("target-artifact", "目标制品身份（名称+版本+SHA-256 或取证方式）",
                expected="名称、版本，以及 SHA-256 或取证方式",
                actual=("命中 %s" % ("SHA-256" if has_hash else "取证方式")),
                evidence="PROJECT.md")
    else:
        detail = []
        if not block:
            detail.append("没有「目标制品」内容")
        if block and not has_version:
            detail.append("缺版本号（如 8.x）")
        if block and not (has_hash or has_forensics):
            detail.append("缺 SHA-256 或「取证方式」")
        g.fail("target-artifact", "目标制品身份（名称+版本+SHA-256 或取证方式）",
               expected="名称 + 版本 + SHA-256（或写明取证方式）",
               actual="；".join(detail), evidence="PROJECT.md",
               hint="写清：应用名 + 版本号 + 安装包/网站快照的 SHA-256；拿不到包就写取证方式（截图/录屏/接口抓包）")

    # 6. DECISIONS ≥3
    decisions = ctx.text("DECISIONS.md")
    if decisions is None:
        g.fail("decisions", "DECISIONS.md 有 ≥3 条决策记录",
               expected="文件存在且 ≥3 条 D- 记录",
               actual="DECISIONS.md 不存在", evidence="DECISIONS.md",
               hint="先写 3 条：目标选择、档位、这一版范围")
    else:
        # 模板自带的示例决策不算数 —— 只认"决策表"里带日期与理由的行
        ids = _real_decision_ids(decisions)
        if len(ids) >= 3:
            g.pass_("decisions", "DECISIONS.md 有 ≥3 条决策记录",
                    expected="≥3 条", actual="%d 条：%s" % (len(ids), ",".join(ids[:6])),
                    evidence="DECISIONS.md")
        else:
            g.fail("decisions", "DECISIONS.md 有 ≥3 条决策记录",
                   expected="≥3 条 D- 编号记录", actual="只有 %d 条：%s" % (
                       len(ids), ",".join(ids) or "无"),
                   evidence="DECISIONS.md",
                   hint="至少记录：为什么做这个、档位、这一版范围（只追加，推翻写新行）")

    # 7. REDLINES R1–R20
    redlines = ctx.text("REDLINES.md")
    if redlines is None:
        g.fail("redlines", "REDLINES.md 含 R1–R20",
               expected="文件存在且 20 条红线齐全", actual="REDLINES.md 不存在",
               evidence="REDLINES.md",
               hint="从 templates/engineering/REDLINES.template.md 复制权威红线表")
    else:
        missing = [n for n in range(1, 21) if not re.search(r"\bR%d\b" % n, redlines)]
        if missing:
            g.fail("redlines", "REDLINES.md 含 R1–R20",
                   expected="R1–R20 全部出现",
                   actual="缺：%s" % ", ".join("R%d" % n for n in missing),
                   evidence="REDLINES.md",
                   hint="补齐缺失的红线；R 编号以 00-体系总纲.md §9 为唯一权威")
        else:
            g.pass_("redlines", "REDLINES.md 含 R1–R20",
                    expected="20 条", actual="20 条齐全", evidence="REDLINES.md")

    # 8. AGENTS.md
    g.need_file("AGENTS.md", "agents", "AGENTS.md 存在",
                hint="写清 AI 执行约束：禁止自批、禁止改契约绕门、写作用域隔离")

    # 9. manifest tier
    if ctx.tier:
        g.pass_("manifest-tier", "manifest 的 tier 合法",
                expected="A / B / C", actual=ctx.tier,
                evidence=C.Context.MANIFEST_REL)
    else:
        g.fail("manifest-tier", "manifest 的 tier 合法",
               expected="tier: A|B|C", actual="tier 缺失或非法",
               evidence=C.Context.MANIFEST_REL,
               hint="在 .replica/gate.manifest.yml 写 tier: A（本地自用）")

    return g.results
