#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""blueprint_lint.py —— 蓝图自检器（产品官审查前必跑的那一个）

检查对象：一个项目根目录下的 BLUEPRINT/ 全部产物。

它回答一个问题：**这份蓝图现在能不能拿去给产品官审？**
答"不能"时，逐条告诉你是哪一节、哪一行、缺什么、怎么补。

检查项（与 00 §3.2 G1/G2 判定对齐）：

  文件     必需文件是否齐（recon/features/screens/menus/flows/linkage/unknowns/contracts）
  CSV      列名与顺序是否与 templates/blueprint/SCHEMAS.md 一致；行宽是否合法
  ID       各表主键是否唯一、格式是否合法（S-01 / F-X-Y / M-A-B / LK-001 / U-001 / T-001）
  契约     每个契约文件是否有 16 节、标题是否逐字一致、每节是否有内容（或 N/A：理由）
  引用     features.contract_ref 指向的文件存在；acceptance_ref/evidence 的 ID 有主
           linkage.source_id 在 features 里存在；linkage.test_ref 形如 T-\\d{3}
           flows.md 里的 S-xx 都能在 screens.csv 找到
           menus.contract_ref 指向的文件存在；menus.screens 里的 S-xx 存在
  菜单树   parent_id 除 ROOT 外都存在、无环、order 冲突
  禁用词   按原版 / TBD / 待定 / 视情况 / 同前 / TODO / FIXME / 待填
  覆盖     priority=must & scope=in 的功能必须有契约，且契约必须存在

用法：
    python3 tools/blueprint_lint.py                      # 检查当前目录
    python3 tools/blueprint_lint.py --project ../myproj
    python3 tools/blueprint_lint.py --project . --json
    python3 tools/blueprint_lint.py --project . --fix-hints
    python3 tools/blueprint_lint.py --project . --only 契约,引用

退出码：0 干净（无 ERROR）／1 有 ERROR／2 用法或输入错误（未做检查）
WARN 不影响退出码，但会打印——WARN 是"现在能过门、以后会踩的坑"。
"""

from __future__ import annotations

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import replica_common as rc  # noqa: E402

TOOL = "blueprint_lint"
BLUEPRINT = "BLUEPRINT"
CONTRACTS = os.path.join(BLUEPRINT, "contracts")

# 检查分区（--only 用）
SECTIONS = ["文件", "CSV", "ID", "契约", "引用", "菜单树", "禁用词", "覆盖"]

REQUIRED_FILES = [
    (os.path.join(BLUEPRINT, "recon.md"), "逆向地图", "跑 S1 取证（/replica-recon），至少产出 recon.md 的 10 段"),
    (os.path.join(BLUEPRINT, "features.csv"), "功能索引", "缺 features.csv → 先跑 S1；它是一切引用的主表"),
    (os.path.join(BLUEPRINT, "screens.csv"), "屏幕清单", "缺 screens.csv → 先跑 S1，逐屏记录状态"),
    (os.path.join(BLUEPRINT, "menus.csv"), "菜单树与三条件", "缺 menus.csv → 跑 S2，用 tools/menu_walk.py --from-screens 生成骨架"),
    (os.path.join(BLUEPRINT, "flows.md"), "用户流程", "缺 flows.md → 跑 S2，按 SCHEMAS §7 的 FL 结构写"),
    (os.path.join(BLUEPRINT, "linkage.csv"), "跨页面联动", "缺 linkage.csv → 跑 S2，用 tools/linkage_matrix.py 检查六面"),
    (os.path.join(BLUEPRINT, "unknowns.csv"), "未知台账", "缺 unknowns.csv → 跑 S1；没有未知项几乎不可能，先建表"),
    (CONTRACTS, "功能契约目录", "缺 contracts/ → 用 tools/contract_scaffold.py --all 批量生成骨架"),
]

OPTIONAL_FILES = [
    (os.path.join(BLUEPRINT, "state-machines.md"), "状态机",
     "SCHEMAS §9；G3 冻结哈希要求它存在"),
    (os.path.join(BLUEPRINT, "data-dictionary.md"), "数据字典",
     "SCHEMAS §10；G3 冻结哈希要求它存在，S4 定型"),
]

SCREEN_STATE_COLS = [("state_filled", "有数据态"), ("state_empty", "空态"),
                     ("state_loading", "加载态"), ("state_error", "错误态"),
                     ("state_permission", "无权限态")]

# scaffold 生成的填空题提示行（"待填：…"）。没删干净即说明这节还没写。
HINT_LEFT_RE = re.compile(r"^(?:[-*+]\s*)?(待填|待补|请填)\s*[：:]")


class Finding(dict):
    """{level, code, section, where, message, fix}"""


def finding(level, code, section, where, message, fix=""):
    return {"level": level, "code": code, "section": section,
            "where": where, "message": message, "fix": fix}


class Linter:
    def __init__(self, project):
        self.project = os.path.abspath(project)
        self.schema = rc.load_schema(self.project)
        self.findings = []
        self.counts = {}
        self.data = {}

    # ---------- 小工具 ----------
    def path(self, rel):
        return os.path.join(self.project, rel)

    def add(self, *args, **kwargs):
        self.findings.append(finding(*args, **kwargs))

    def rel(self, path):
        try:
            return os.path.relpath(path, self.project)
        except ValueError:
            return path

    # ---------- 1. 文件 ----------
    def check_files(self):
        for rel, label, fix in REQUIRED_FILES:
            p = self.path(rel)
            if os.path.isdir(p):
                if not os.listdir(p):
                    self.add("ERROR", "FILE-EMPTY-DIR", "文件", rel,
                             "%s 目录存在但是空的" % label, fix)
                continue
            if not os.path.isfile(p):
                self.add("ERROR", "FILE-MISSING", "文件", rel,
                         "缺必需文件：%s（%s）" % (label, rel), fix)
        for rel, label, note in OPTIONAL_FILES:
            if not os.path.isfile(self.path(rel)):
                self.add("WARN", "FILE-MISSING-OPT", "文件", rel,
                         "缺 %s：%s" % (label, rel),
                         "%s；S3 冻结时 G3 会要求它进哈希表" % note)

    # ---------- 2. CSV ----------
    def load_table(self, name, rel):
        p = self.path(rel)
        if not os.path.isfile(p):
            return []
        rows, issues = rc.read_csv_table(p, self.schema.columns[name])
        for iss in issues:
            self.add(iss["level"], iss["code"], "CSV", iss["where"],
                     iss["message"], iss["hint"])
        return rows

    def check_csv(self):
        self.data["features"] = self.load_table("features", os.path.join(BLUEPRINT, "features.csv"))
        self.data["screens"] = self.load_table("screens", os.path.join(BLUEPRINT, "screens.csv"))
        self.data["menus"] = self.load_table("menus", os.path.join(BLUEPRINT, "menus.csv"))
        self.data["linkage"] = self.load_table("linkage", os.path.join(BLUEPRINT, "linkage.csv"))
        self.data["unknowns"] = self.load_table("unknowns", os.path.join(BLUEPRINT, "unknowns.csv"))

        # 枚举合法性
        for r in self.data["features"]:
            prio = rc.cell(r, "priority").lower()
            if prio and prio not in ("must", "should", "could", "p0", "p1", "p2"):
                self.add("ERROR", "ENUM-PRIORITY", "CSV",
                         "%s/%s" % ("features.csv", r["line"]),
                         "priority='%s' 不是 must/should/could（或 P0/P1/P2）" % prio,
                         "改成 must/should/could 之一；枚举见 SCHEMAS §0.5")
            scope = rc.cell(r, "scope").lower()
            if scope and scope not in ("in", "out"):
                self.add("ERROR", "ENUM-SCOPE", "CSV",
                         "features.csv:%s" % r["line"],
                         "scope='%s' 不是 in/out" % scope,
                         "本版范围写 in，明确不做写 out（并在 notes 写理由）")
            prog = rc.cell(r, "progress").lower()
            if prog and prog not in ("yes", "partial", "no", "skip"):
                self.add("ERROR", "ENUM-PROGRESS", "CSV",
                         "features.csv:%s" % r["line"],
                         "progress='%s' 不是 yes/partial/no/skip" % prog,
                         "改成四值之一（SCHEMAS §0.6）")
            orig = rc.cell(r, "original").lower()
            if orig and orig not in ("yes", "no"):
                self.add("WARN", "ENUM-ORIGINAL", "CSV",
                         "features.csv:%s" % r["line"],
                         "original='%s' 不是 yes/no" % orig, "原版有写 yes，你新增的写 no")
            if prog == "skip" and not rc.is_filled(rc.cell(r, "notes")):
                self.add("ERROR", "SKIP-NO-REASON", "CSV",
                         "features.csv:%s" % r["line"],
                         "progress=skip 但 notes 没写理由（%s）" % rc.cell(r, "feature_id"),
                         "在 notes 写清为什么不做，例：授权内容，无法自建（SCHEMAS §2）")

        for r in self.data["screens"]:
            for col, label in SCREEN_STATE_COLS:
                v = rc.cell(r, col)
                if rc.is_blank(v):
                    self.add("ERROR", "SCREEN-STATE-MISSING", "CSV",
                             "screens.csv:%s" % r["line"],
                             "%s 的%s（%s）没填" % (rc.cell(r, "screen_id"), label, col),
                             "填 yes/no；确实不适用填 '-' 并在 notes 写理由")
                elif v.lower() not in ("yes", "no", "-"):
                    self.add("WARN", "SCREEN-STATE-VALUE", "CSV",
                             "screens.csv:%s" % r["line"],
                             "%s 值 '%s' 不是 yes/no/-" % (col, v), "统一为 yes/no/-")

        for r in self.data["menus"]:
            ntype = rc.cell(r, "type").lower()
            if ntype and ntype not in ("submenu", "action", "radio", "checkbox",
                                       "separator", "label"):
                self.add("ERROR", "ENUM-MENU-TYPE", "CSV",
                         "menus.csv:%s" % r["line"],
                         "type='%s' 不在 submenu/action/radio/checkbox/separator/label" % ntype,
                         "按控件真实类型填（SCHEMAS §4）")
            order = rc.cell(r, "order")
            if order and not order.isdigit():
                self.add("WARN", "MENU-ORDER", "CSV",
                         "menus.csv:%s" % r["line"],
                         "order='%s' 不是整数" % order, "同级顺序填 1、2、3…")

        for r in self.data["linkage"]:
            status = rc.cell(r, "status").lower()
            if status and status not in ("pending", "wired", "verified", "na"):
                self.add("ERROR", "ENUM-LINKAGE-STATUS", "CSV",
                         "linkage.csv:%s" % r["line"],
                         "status='%s' 不是 pending/wired/verified/na" % status,
                         "按 SCHEMAS §5 四值填；确认不受影响的写 na 并在 state_handling 写理由")
            if status == "na":
                reason = rc.cell(r, "state_handling")
                if not rc.is_filled(reason) or "不适用" not in reason:
                    self.add("ERROR", "LINK-NA-NO-REASON", "CSV",
                             "linkage.csv:%s" % r["line"],
                             "%s 标了 na 但 state_handling 没写「不适用：<理由>」"
                             % (rc.cell(r, "link_id") or "行"),
                             "na 是「想过之后确认不影响」，必须写理由；"
                             "想不出理由说明它是漏了，不是 na")

        for r in self.data["unknowns"]:
            blocking = rc.cell(r, "blocking").lower()
            status = rc.cell(r, "status").lower()
            if blocking and blocking not in ("yes", "no"):
                self.add("ERROR", "ENUM-BLOCKING", "CSV",
                         "unknowns.csv:%s" % r["line"],
                         "blocking='%s' 不是 yes/no" % blocking, "阻断开发写 yes")
            if status and status not in ("open", "resolved", "accepted-risk", "out-of-scope"):
                self.add("ERROR", "ENUM-UNKNOWN-STATUS", "CSV",
                         "unknowns.csv:%s" % r["line"],
                         "status='%s' 不在 open/resolved/accepted-risk/out-of-scope" % status,
                         "按 SCHEMAS §6 四值填")

    # ---------- 3. ID ----------
    def check_ids(self):
        # screen_id 是**被其他文件引用的主键**，必须严格 S-\\d{2}（两位数）；
        # area 是**给人看的描述字段**，允许 "S-03-预约页" 这种带后缀写法。
        # 两者分开判定：主键规范优先，描述可读性优先（lead 定案）。
        spec = [("features", "features.csv", "feature_id", "feature", "F-域-短名", "ID-FORMAT"),
                ("screens", "screens.csv", "screen_id", "screen", "S-01", "SCREEN-ID-FORMAT"),
                ("menus", "menus.csv", "node_id", "menu", "M-DATE-SUB-03", "ID-FORMAT"),
                ("linkage", "linkage.csv", "link_id", "link", "LK-001", "ID-FORMAT"),
                ("unknowns", "unknowns.csv", "unknown_id", "unknown", "U-001", "ID-FORMAT")]
        self.ids = {}
        for table, rel, col, kind, sample, fmt_code in spec:
            rows = self.data.get(table, [])
            seen = {}
            for r in rows:
                v = rc.cell(r, col)
                where = "%s:%s" % (rel, r["line"])
                if rc.is_blank(v):
                    self.add("ERROR", "ID-MISSING", "ID", where,
                             "%s 为空" % col, "每个节点必须有稳定 ID（永不复用）；示例：%s" % sample)
                    continue
                if not rc.ID_PATTERNS[kind].match(v):
                    if kind == "screen":
                        self.add("ERROR", "SCREEN-ID-FORMAT", "ID", where,
                                 "screen_id='%s' 不是严格的 S-两位数" % v,
                                 "screen_id 是被 features/menus/linkage/flows 引用的**主键**，"
                                 "必须写成 S-01 / S-02 这种两位数字；"
                                 "带后缀的描述请写进 name 列或 features.csv 的 area 列"
                                 "（area 允许 'S-03-预约页'）")
                    else:
                        self.add("ERROR", fmt_code, "ID", where,
                                 "%s='%s' 格式不对" % (col, v),
                                 "应为形如 %s（00 §4 ID 规范）" % sample)
                if v in seen:
                    self.add("ERROR", "ID-DUP", "ID", where,
                             "%s='%s' 重复（首次出现在第 %s 行）" % (col, v, seen[v]),
                             "ID 一经分配永不复用；两行真的是一件事就删掉一行，删功能用 progress=skip 不删行")
                else:
                    seen[v] = r["line"]
            self.ids[table] = set(seen)

        # flow ID 从 flows.md 抽
        flows_path = self.path(os.path.join(BLUEPRINT, "flows.md"))
        self.flow_ids = set()
        if os.path.isfile(flows_path):
            ftext = rc.read_text(flows_path)
            for line_no, line in enumerate(ftext.splitlines(), start=1):
                m = re.match(r"^##\s+(FL-\d{2,3})\b", line)
                if m:
                    self.flow_ids.add(m.group(1))
            if not self.flow_ids:
                self.add("ERROR", "FLOW-NONE", "ID", "BLUEPRINT/flows.md",
                         "flows.md 里没有任何 '## FL-xx' 标题",
                         "按 SCHEMAS §7 的结构写：'## FL-01 修改任务日期' + 四个 ### 子节")

    # ---------- 4. 契约 ----------
    def check_contracts(self):
        cdir = self.path(CONTRACTS)
        self.contracts = {}
        if not os.path.isdir(cdir):
            return
        files = sorted(f for f in os.listdir(cdir)
                       if f.endswith(".md") and not f.startswith("."))
        if not files:
            self.add("ERROR", "CONTRACT-NONE", "契约", CONTRACTS,
                     "contracts/ 里没有任何契约文件",
                     "用 tools/contract_scaffold.py --all 从 features.csv 批量生成骨架")
            return

        want_titles = self.schema.section_titles
        for fname in files:
            rel = os.path.join(CONTRACTS, fname)
            if not rc.ID_PATTERNS["contract"].match(fname):
                self.add("WARN", "CONTRACT-NAME", "契约", rel,
                         "文件名 '%s' 不符合 C-F-xxx.md 规范" % fname,
                         "重命名为 contracts/C-<feature_id>.md，并在 features.contract_ref 同步")
            text = rc.read_text(self.path(rel))
            heads = rc.split_md_sections(text, level=2)
            self.contracts[fname] = {"path": rel, "sections": {}, "text": text}

            # 一级标题里的功能 ID
            h1 = re.search(r"^#\s+(C-F-[A-Z0-9-]+)", text, re.M)
            if not h1:
                self.add("ERROR", "CONTRACT-H1", "契约", rel,
                         "一级标题不是 '# C-F-xxx · <功能名>'",
                         "改成 '# C-F-DATE-EDIT · 修改任务的日期与时间' 这种形式")
            elif h1.group(1) + ".md" != fname:
                self.add("WARN", "CONTRACT-H1-NAME", "契约", rel,
                         "一级标题的功能 ID（%s）与文件名（%s）不一致" % (h1.group(1), fname),
                         "统一：文件名 = 一级标题 ID + .md")

            got = {h["title"]: h for h in heads}
            # 16 节逐节检查
            for i, want in enumerate(want_titles, start=1):
                # 允许标题为 "1 目标与入口"，也允许带额外空格
                norm = re.sub(r"\s+", " ", want.strip())
                match = None
                for title, h in got.items():
                    if re.sub(r"\s+", " ", title.strip()) == norm:
                        match = h
                        break
                if match is None:
                    # 也许编号对但文字错
                    prefix = "%d " % i
                    near = [t for t in got if t.startswith(prefix)]
                    self.add("ERROR", "CONTRACT-SECTION-MISSING", "契约",
                             "%s#%s" % (rel, want),
                             "缺第 %d 节「%s」" % (i, want.split(" ", 1)[-1]) +
                             ("（找到编号相同但标题不同：'%s'）" % near[0] if near else ""),
                             "标题必须与 SCHEMAS §8 逐字一致（脚本按标题匹配）；照 tools/contract_scaffold.py 生成")
                    continue
                self.contracts[fname]["sections"][want] = match
                lines = rc.body_text(match["body"])
                if not lines:
                    self.add("ERROR", "CONTRACT-SECTION-EMPTY", "契约",
                             "%s:%d" % (rel, match["line"]),
                             "第 %d 节「%s」没有正文" % (i, want.split(" ", 1)[-1]),
                             "写清这一节的最小内容（SCHEMAS §8 表格）；确实不适用就写 'N/A：<理由>'")
                elif rc.looks_placeholder(lines) and not lines[0].startswith("N/A"):
                    self.add("ERROR", "CONTRACT-SECTION-PLACEHOLDER", "契约",
                             "%s:%d" % (rel, match["line"]),
                             "第 %d 节「%s」只有占位（%s）"
                             % (i, want.split(" ", 1)[-1], "、".join(lines[:3])),
                             "填真实内容；不确定就登记到 unknowns.csv，不要留'待填'")
                elif lines[0].startswith("N/A") and len("".join(lines)) < 12:
                    self.add("WARN", "CONTRACT-NA-THIN", "契约",
                             "%s:%d" % (rel, match["line"]),
                             "第 %d 节写了 N/A 但没说理由" % i, "写成 'N/A：本节不适用，因为…'")

            # 多余的同名编号节
            for title in got:
                if title not in want_titles and re.match(r"^\d+\s", title):
                    self.add("WARN", "CONTRACT-SECTION-EXTRA", "契约", rel,
                             "多出一节「%s」，不在 16 节规范内" % title,
                             "删掉或并入对应节；16 节是门禁按标题匹配的契约")

    # ---------- 5. 引用 ----------
    def check_refs(self):
        feats = self.ids.get("features", set())
        screens = self.ids.get("screens", set())
        menus = self.ids.get("menus", set())
        flow_ids = getattr(self, "flow_ids", set())
        contract_files = set(self.contracts.keys()) if hasattr(self, "contracts") else set()

        # features → contract_ref / acceptance_ref / evidence / area
        for r in self.data.get("features", []):
            fid = rc.cell(r, "feature_id")
            where = "features.csv:%s%s" % (r["line"], (" (%s)" % fid) if fid else "")
            cref = rc.cell(r, "contract_ref")
            prio = rc.cell(r, "priority").lower()
            scope = rc.cell(r, "scope").lower()
            must = prio in ("must", "p0") and scope in ("in", "")
            if rc.is_filled(cref):
                target = self.path(os.path.join(BLUEPRINT, cref.replace("./", ""))) \
                    if not cref.startswith("BLUEPRINT") else self.path(cref)
                base = os.path.basename(cref)
                if not os.path.isfile(target) and base not in contract_files:
                    self.add("ERROR", "REF-CONTRACT-MISSING", "引用", where,
                             "contract_ref 指向的文件不存在：%s" % cref,
                             "生成它：python3 tools/contract_scaffold.py --feature %s --out BLUEPRINT/contracts/"
                             % (fid or "F-XXX"))
            elif must:
                self.add("ERROR", "REF-MUST-NO-CONTRACT", "引用", where,
                         "must 功能没有 contract_ref（%s）" % (fid or "无 ID"),
                         "must 功能契约覆盖率必须 100%%（G2）；先生成骨架再逐节填")
            elif scope == "in" and rc.is_blank(cref):
                self.add("WARN", "REF-NO-CONTRACT", "引用", where,
                         "本版范围内的 %s 功能没有契约引用" % (prio or "未标优先级"),
                         "should/could 可以先没有，但要在 notes 说明何时补")

            for tid in rc.split_refs(rc.cell(r, "acceptance_ref"), rc.TEST_REF_RE):
                if not rc.ID_PATTERNS["test"].match(tid):
                    self.add("ERROR", "REF-TEST-FORMAT", "引用", where,
                             "验收引用 '%s' 不是 T-\\d{3} 形式" % tid, "统一写成 T-101 这种三位编号")
            if rc.is_blank(rc.cell(r, "acceptance_ref")) and must:
                self.add("WARN", "REF-MUST-NO-TEST", "引用", where,
                         "must 功能没有 acceptance_ref（%s）" % (fid or "无 ID"),
                         "S2 就要起草用例号（S8 才执行）；G2 要求每行有验收引用")
            ev = rc.cell(r, "evidence")
            if rc.is_blank(ev):
                self.add("WARN", "REF-NO-EVIDENCE", "引用", where,
                         "没有 evidence：断言行没有出处（SCHEMAS §0.9）",
                         "填 S-xx / M-xx / 证据文件路径")

        # linkage → source_id / test_ref / affected_screen
        for r in self.data.get("linkage", []):
            lid = rc.cell(r, "link_id")
            where = "linkage.csv:%s%s" % (r["line"], (" (%s)" % lid) if lid else "")
            src = rc.cell(r, "source_id")
            if rc.is_blank(src):
                self.add("ERROR", "REF-LINK-SOURCE-EMPTY", "引用", where,
                         "source_id 为空", "填触发源 F-xxx（或命令/事件名）")
            elif src.startswith("F-") and src not in feats:
                self.add("ERROR", "REF-LINK-SOURCE-MISSING", "引用", where,
                         "source_id='%s' 在 features.csv 里不存在" % src,
                         "先在 features.csv 建这一行；联动必须挂到真实功能上")
            tr = rc.cell(r, "test_ref")
            is_na = rc.cell(r, "status").lower() == "na"
            if rc.is_blank(tr):
                self.add("ERROR", "REF-LINK-NO-TEST", "引用", where,
                         "test_ref 为空：联动没有测试就永远无法证明 wire 上了",
                         "填 T-\\d{3} 用例号；status=na 的行可以填 '-'（不适用无需测试）")
            elif not re.search(r"T-\d+", tr) and not (is_na and rc.is_not_applicable(tr)):
                self.add("ERROR", "REF-LINK-TEST-FORMAT", "引用", where,
                         "test_ref='%s' 不是 T-\\d+ 形式" % tr,
                         "写成 T-103；只有 status=na 的行才允许填 '-'")
            rt = rc.cell(r, "refresh_timing")
            if rc.is_blank(rt):
                self.add("ERROR", "REF-LINK-NO-TIMING", "引用", where,
                         "refresh_timing 为空：没有刷新时点 = 不知道什么时候更新",
                         "写成'写入事务提交成功 → 同步刷新'这种可判定时点")
            for sid in rc.split_refs(rc.cell(r, "affected_screen"), rc.SCREEN_REF_RE):
                if sid not in screens:
                    self.add("ERROR", "REF-LINK-SCREEN-MISSING", "引用", where,
                             "affected_screen 里的 %s 不在 screens.csv" % sid,
                             "先在 screens.csv 登记该屏幕")
            ctl = rc.cell(r, "affected_control")
            if ctl.lower() in ("界面刷新", "刷新", "ui", "-"):
                self.add("ERROR", "REF-LINK-VAGUE", "引用", where,
                         "affected_control='%s' 太笼统" % ctl,
                         "要写成具体控件，例：'%s 行日期徽标' / '侧栏今天角标计数'"
                         % rc.face_names()[0])

        # menus → parent_id / contract_ref / screens / 三条件
        for r in self.data.get("menus", []):
            nid = rc.cell(r, "node_id")
            where = "menus.csv:%s%s" % (r["line"], (" (%s)" % nid) if nid else "")
            ntype = rc.cell(r, "type").lower()
            parent = rc.cell(r, "parent_id")
            if parent and parent != "ROOT" and parent not in menus:
                self.add("ERROR", "REF-MENU-PARENT-MISSING", "引用", where,
                         "parent_id='%s' 不存在" % parent,
                         "补父节点行，或把 parent_id 改成 ROOT")
            if ntype not in ("separator", "label"):
                if not rc.is_filled(rc.cell(r, "command")):
                    self.add("ERROR", "REF-MENU-NO-COMMAND", "引用", where,
                             "type=%s 但没有 command" % (ntype or "?"),
                             "填触发后的命令 ID，例 Cmd.SetRepeatWeeklyWorkdays（G2 判定）")
                cref = rc.cell(r, "contract_ref")
                if not rc.is_filled(cref):
                    self.add("ERROR", "REF-MENU-NO-CONTRACT", "引用", where,
                             "菜单叶子没有 contract_ref", "填 contracts/C-F-XXX.md")
                elif os.path.basename(cref) not in contract_files:
                    self.add("ERROR", "REF-MENU-CONTRACT-MISSING", "引用", where,
                             "contract_ref 指向的文件不存在：%s" % cref,
                             "先生成该契约；菜单叶子没有契约 = 行为没定义")
            for sid in rc.split_refs(rc.cell(r, "screens"), rc.SCREEN_REF_RE):
                if sid not in screens:
                    self.add("ERROR", "REF-MENU-SCREEN-MISSING", "引用", where,
                             "screens 里的 %s 不在 screens.csv" % sid, "登记该屏幕")

        # flows.md → S-xx
        fpath = self.path(os.path.join(BLUEPRINT, "flows.md"))
        if os.path.isfile(fpath):
            text = rc.read_text(fpath)
            for i, line in enumerate(text.splitlines(), start=1):
                for sid in rc.SCREEN_REF_RE.findall(line):
                    if sid not in screens:
                        self.add("ERROR", "REF-FLOW-SCREEN-MISSING", "引用",
                                 "flows.md:%d" % i,
                                 "flows.md 里引用了 %s，但 screens.csv 没有它" % sid,
                                 "要么在 screens.csv 登记，要么改掉笔误")

        # 未知项 → impact 里的 ID 有主
        for r in self.data.get("unknowns", []):
            where = "unknowns.csv:%s" % r["line"]
            uid = rc.cell(r, "unknown_id")
            action = rc.cell(r, "verification_action")
            if rc.is_blank(action):
                self.add("ERROR", "UNKNOWN-NO-ACTION", "引用", where,
                         "%s 没有 verification_action" % (uid or "未知项"),
                         "写可执行动作（'再研究一下'不算）：例 '在 S-02 打开重复菜单，逐项截图对比'")
            desc = rc.cell(r, "description")
            if desc.strip() in ("细节待定", "待定", "未知", "unknown"):
                self.add("ERROR", "UNKNOWN-VAGUE", "引用", where,
                         "%s 的描述太笼统（'%s'）" % (uid or "未知项", desc),
                         "写清未知的是哪个行为：'清除日期是否同时清除提醒时间'")

    # ---------- 6. 菜单树 ----------
    def check_menu_tree(self):
        rows = self.data.get("menus", [])
        if not rows:
            return
        by_id = {}
        for r in rows:
            nid = rc.cell(r, "node_id")
            if nid:
                by_id.setdefault(nid, r)
        roots = [r for r in rows if rc.cell(r, "parent_id") == "ROOT"]
        if not roots:
            self.add("ERROR", "MENU-NO-ROOT", "菜单树", "menus.csv",
                     "没有任何 parent_id=ROOT 的顶层节点",
                     "顶层菜单填 parent_id=ROOT")

        # 环检测
        state = {}

        def visit(nid, stack):
            state[nid] = 1
            parent = rc.cell(by_id[nid], "parent_id")
            if parent and parent != "ROOT" and parent in by_id:
                if state.get(parent) == 1:
                    cyc = " → ".join(stack + [parent])
                    self.add("ERROR", "MENU-CYCLE", "菜单树",
                             "menus.csv:%s" % by_id[nid]["line"],
                             "菜单树有环：%s" % cyc,
                             "把其中一条 parent_id 改对；菜单是树，不能成环")
                elif state.get(parent) is None:
                    visit(parent, stack + [nid])
            state[nid] = 2

        for nid in by_id:
            if state.get(nid) is None:
                visit(nid, [])

        # 同级 order 冲突
        groups = {}
        for r in rows:
            parent = rc.cell(r, "parent_id") or "ROOT"
            groups.setdefault(parent, []).append(r)
        for parent, items in groups.items():
            seen = {}
            for r in items:
                order = rc.cell(r, "order")
                if not order:
                    continue
                key = order
                if key in seen:
                    # 工具判 WARN（不阻断体检），门禁 G2 判 ERROR（不放行）。
                    # 严度可以不同：工具是"体检"，门禁是"放行"（lead 定案）。
                    self.add("WARN", "MENU-ORDER-DUP", "菜单树",
                             "menus.csv:%s" % r["line"],
                             "同级 %s 下 order=%s 与第 %s 行重复"
                             % (parent, order, seen[key]),
                             "同级顺序必须唯一，否则渲染顺序不确定。"
                             "本工具只报 WARN 不阻断，但**门禁 G2 会判 ERROR**（不放行）")
                else:
                    seen[key] = r["line"]

        # 三条件缺失
        for r in rows:
            ntype = rc.cell(r, "type").lower()
            if ntype in ("separator",):
                continue
            nid = rc.cell(r, "node_id")
            for col, label in (("visibility_cond", "显示条件"),
                               ("enabled_cond", "可用条件"),
                               ("checked_cond", "选中条件")):
                v = rc.cell(r, col)
                if rc.is_blank(v):
                    self.add("ERROR", "MENU-COND-MISSING", "菜单树",
                             "menus.csv:%s%s" % (r["line"], (" (%s)" % nid) if nid else ""),
                             "%s 没填%s（%s）" % (nid or "节点", label, col),
                             "三条件必须分开写（00 §10-02）；不适用写 '-' 并在 notes 说明")

    # ---------- 7. 禁用词 ----------
    def check_banned(self):
        targets = [os.path.join(BLUEPRINT, "recon.md"),
                   os.path.join(BLUEPRINT, "flows.md"),
                   os.path.join(BLUEPRINT, "state-machines.md"),
                   os.path.join(BLUEPRINT, "data-dictionary.md"),
                   os.path.join(BLUEPRINT, "unknowns.csv"),
                   os.path.join(BLUEPRINT, "features.csv"),
                   os.path.join(BLUEPRINT, "menus.csv"),
                   os.path.join(BLUEPRINT, "linkage.csv"),
                   os.path.join(BLUEPRINT, "screens.csv")]
        cdir = self.path(CONTRACTS)
        contract_files = []
        if os.path.isdir(cdir):
            contract_files = [os.path.join(CONTRACTS, f) for f in sorted(os.listdir(cdir))
                              if f.endswith(".md")]
        for rel in targets:
            p = self.path(rel)
            if not os.path.isfile(p):
                continue
            text = rc.read_text(p)
            # 契约里的「待填」由"某节只有占位"单独判，避免同一处报两遍
            for word, line_no, line in rc.scan_banned(text, include_placeholder=False):
                level = "ERROR" if word in ("按原版", "TBD", "待定", "视情况", "同前") else "WARN"
                self.add(level, "BANNED-WORD", "禁用词", "%s:%d" % (rel, line_no),
                         "出现禁用词：「%s」：%s" % (word, line),
                         "00 §附录A.7：冻结蓝图不许出现 TODO/待定/按原版/TBD；"
                         "真的没定就登记 unknowns.csv 并写补验动作")
        for rel in contract_files:
            p = self.path(rel)
            text = rc.read_text(p)
            # 契约：禁用词按普通口径扫（占位由"某节只有占位"单独判，避免一处报两遍）
            for word, line_no, line in rc.scan_banned(text, skip_quotes=True):
                self.add("ERROR", "BANNED-WORD", "禁用词", "%s:%d" % (rel, line_no),
                         "契约里出现禁用词「%s」：%s" % (word, line),
                         "换成真实内容；不确定就登记 unknowns.csv（不许留占位）")
            # 脚手架提示行没删干净：说明这一节还没真正写
            for i, line in enumerate(text.splitlines(), start=1):
                if HINT_LEFT_RE.match(line.strip()):
                    self.add("ERROR", "CONTRACT-HINT-LEFT", "契约", "%s:%d" % (rel, i),
                             "还留着脚手架提示行：%s" % line.strip()[:80],
                             "把这条提示换成你的实际内容（它是 scaffold 生成的填空题提示）")

    # ---------- 8. must 覆盖 ----------
    def _compute_must_coverage(self):
        feats = self.data.get("features", [])
        must_in = [r for r in feats
                   if rc.cell(r, "priority").lower() in ("must", "p0")
                   and rc.cell(r, "scope").lower() in ("in", "")]
        covered = [r for r in must_in if rc.is_filled(rc.cell(r, "contract_ref"))]
        self.counts["must_in"] = len(must_in)
        self.counts["must_with_contract"] = len(covered)

    def check_coverage(self):
        feats = self.data.get("features", [])
        must_in = [r for r in feats
                   if rc.cell(r, "priority").lower() in ("must", "p0")
                   and rc.cell(r, "scope").lower() in ("in", "")]
        covered = [r for r in must_in if rc.is_filled(rc.cell(r, "contract_ref"))]
        self._compute_must_coverage()

        # 契约里是否有反向引用（契约应被至少一个 feature 引用）
        if hasattr(self, "contracts") and self.contracts:
            referenced = {os.path.basename(rc.cell(r, "contract_ref"))
                          for r in feats if rc.is_filled(rc.cell(r, "contract_ref"))}
            for fname in self.contracts:
                if fname not in referenced:
                    self.add("WARN", "CONTRACT-ORPHAN", "覆盖", os.path.join(CONTRACTS, fname),
                             "契约没有任何 features.csv 行引用它",
                             "在 features.csv 建对应行，或这是已废弃契约 → 移到 _archive/")

        # must 功能必须有菜单/联动覆盖的影子检查
        if must_in and not self.data.get("linkage"):
            self.add("ERROR", "COVERAGE-NO-LINKAGE", "覆盖", "BLUEPRINT/linkage.csv",
                     "有 %d 个 must 功能，但 linkage.csv 一行都没有" % len(must_in),
                     "每个 must 功能至少问一遍六面（%s），"
                     "用 tools/linkage_matrix.py 看还差哪几面" % rc.faces_brief())

    # ---------- 汇总 ----------
    # 前置步骤：**无论 --only 选了什么都要跑**，否则下游检查拿不到数据。
    # 曾经的真实缺陷：--only ID 时 check_csv 被跳过 → self.data 全空 → 永远报 0 条，
    # 看起来"干净"，实际是没检查（典型的假绿）。
    def _prereqs(self):
        try:
            self.check_files()
        except rc.ToolError as exc:
            self.add("ERROR", "TOOL-ERROR", "文件", "文件", exc.message, exc.hint or "")
        try:
            self.check_csv()          # 载入 features/screens/menus/linkage/unknowns
        except rc.ToolError as exc:
            self.add("ERROR", "TOOL-ERROR", "CSV", "CSV", exc.message, exc.hint or "")
        # must 覆盖率是"体检第一指标"，与 --only 无关，必须在前置算好，
        # 否则 --only ID 时会显示 "must 0/0"，看起来像没有 must 功能。
        try:
            self._compute_must_coverage()
        except rc.ToolError:
            pass

    def run(self, only=None):
        self._prereqs()
        # 顺序有依赖：check_ids 产出 self.flow_ids / self.ids，check_contracts 产出
        # self.contracts，check_refs 同时用到两者 → 必须 ID 在契约前、契约在引用前。
        steps = [("ID", self.check_ids), ("契约", self.check_contracts),
                 ("引用", self.check_refs), ("菜单树", self.check_menu_tree),
                 ("禁用词", self.check_banned), ("覆盖", self.check_coverage)]
        for name, fn in steps:
            if only and name not in only:
                continue
            try:
                fn()
            except rc.ToolError as exc:
                self.add("ERROR", "TOOL-ERROR", name, name, exc.message, exc.hint or "")
        if only:
            # --only 时把前置步骤的 finding 也过滤掉（否则"只跑 ID"会混进文件/CSV 问题），
            # 但前置步骤的**数据载入**必须已经发生。
            self.findings = [f for f in self.findings
                             if f["section"] in only or f["code"] == "TOOL-ERROR"]
        return self.findings


# 问题分组的展示顺序（产品官看的那一行用；顺序 = 修的顺序）
STAT_GROUPS = [
    ("missing_contracts", "缺契约文件（去重）"),
    ("contract_sections", "契约缺节/空节/占位"),
    ("refs", "其它引用断链"),
    ("menus", "菜单三条件/命令缺项"),
    ("ids", "ID 格式或重复"),
    ("csv", "CSV 列与枚举"),
    ("banned", "禁用词"),
    ("tree", "菜单树结构"),
    ("screens", "屏幕状态列"),
    ("files", "必需文件缺失"),
]


def collect_stats(findings, linter=None):
    """把 findings 归成"产品官能一眼看懂"的计数。返回 dict。

    重点：**missing_contracts 去重**。同一份缺失契约会被 features 与 menus 各报一次
    （保持双报是为了按文件修时能看出修完消几条），但汇总要给人看"缺几份文件"。
    """
    errs = [f for f in findings if f["level"] == "ERROR"]
    warns = [f for f in findings if f["level"] == "WARN"]
    # by_code 只数 ERROR：「按修的顺序」是修 ERROR 的顺序；
    # WARN 只报总数，避免"建议项"混进"必修项"里让产品官误判严重度。
    by_code = {}
    for f in errs:
        by_code[f["code"]] = by_code.get(f["code"], 0) + 1

    # 去重的缺失契约（从 message 里抽文件名；lint 的 message 形如
    # "contract_ref 指向的文件不存在：contracts/C-F-X.md"）
    missing_contracts = set()
    missing_refs = 0
    for f in findings:
        if f["code"] in ("REF-CONTRACT-MISSING", "REF-MENU-CONTRACT-MISSING"):
            missing_refs += 1
            msg = f.get("message", "")
            if "：" in msg:
                missing_contracts.add(os.path.basename(msg.split("：")[-1].strip()))
            elif ":" in msg:
                missing_contracts.add(os.path.basename(msg.split(":")[-1].strip()))

    groups = {
        "files": sum(n for c, n in by_code.items() if c.startswith("FILE-")),
        "csv": sum(n for c, n in by_code.items()
                   if c.startswith("CSV-") or c.startswith("ENUM-")
                   or c in ("SKIP-NO-REASON",)),
        "ids": sum(n for c, n in by_code.items()
                   if c in ("ID-MISSING", "ID-FORMAT", "ID-DUP", "SCREEN-ID-FORMAT")),
        "contract_sections": sum(n for c, n in by_code.items()
                                 if c.startswith("CONTRACT-")),
        "missing_contracts": len(missing_contracts),
        # 引用断链：**不含** REF-*-CONTRACT-MISSING（那由 missing_contracts 单独按文件计数，
        # 否则同一个缺失会被算两次，产品官看到"缺 11 份 + 断链 26 条"会以为有两类问题）
        "refs": sum(n for c, n in by_code.items()
                    if (c.startswith("REF-") or c.startswith("LINK-NA"))
                    and not c.endswith("CONTRACT-MISSING")),
        "menus": sum(n for c, n in by_code.items()
                     if c.startswith("MENU-") or c in ("NODE-CYCLE", "NODE-ORPHAN",
                                                       "NODE-PARENT-MISSING", "NODE-DUP-ID")),
        "tree": sum(n for c, n in by_code.items() if c in ("MENU-ORDER-DUP", "MENU-NO-ROOT")),
        "banned": by_code.get("BANNED-WORD", 0),
        "screens": sum(n for c, n in by_code.items() if c.startswith("SCREEN-STATE")),
    }
    must_in = linter.counts.get("must_in", 0) if linter else 0
    must_cov = linter.counts.get("must_with_contract", 0) if linter else 0
    return {
        "error": len(errs),
        "warn": len(warns),
        "by_code": by_code,
        "groups": groups,
        "missing_contracts": sorted(missing_contracts),
        "missing_contract_refs": missing_refs,
        "must_in": must_in,
        "must_with_contract": must_cov,
        "contract_files": len(getattr(linter, "contracts", {})) if linter else 0,
        "clean": not errs,
    }


def render_summary(linter, findings, out=sys.stdout, only=None):
    """--summary-only：一行结论 + 各类计数。给产品官用（他不需要看明细）。"""
    stats = collect_stats(findings, linter)
    g = stats["groups"]
    w = out.write
    if only:
        w("⚠ 只跑了分区：%s（非全量检查，结论不代表蓝图可用）\n\n" % "、".join(only))

    if stats["error"]:
        head = "❌ 不可进入产品官审查"
    elif only:
        head = "⚠ 所选分区无 ERROR，但**未做全量检查**，不能据此判可审"
    elif stats["warn"]:
        head = "✅ 可进入产品官审查（有 %d 条建议同期处理）" % stats["warn"]
    else:
        head = "✅ 干净，可以开会"

    w("蓝图自检 · %s\n" % os.path.basename(os.path.abspath(linter.project)))
    w("%s\n" % head)
    w("")
    # 一行结论（lead 要的形态）
    parts = ["ERROR %d" % stats["error"]]
    if g["missing_contracts"]:
        parts.append("缺契约 %d 份（被 %d 处引用）"
                     % (g["missing_contracts"], stats["missing_contract_refs"]))
    parts.append("WARN %d" % stats["warn"])
    if stats["must_in"]:
        parts.append("must 契约覆盖 %s（%d/%d）"
                     % (rc.fmt_pct(rc.pct(stats["must_with_contract"], stats["must_in"])),
                        stats["must_with_contract"], stats["must_in"]))
    parts.append("契约文件 %d 份" % stats["contract_files"])
    w("  " + " ／ ".join(parts) + "\n")

    # 各类计数（只列非零的，按修的顺序）
    rows = []
    for key, label in STAT_GROUPS:
        n = g.get(key, 0)
        if n:
            rows.append([label, str(n)])
    if rows:
        w("")
        w("按修的顺序：\n")
        for label, n in rows:
            w("  %-18s %s\n" % (label, n))
    if stats["warn"]:
        w("")
        w("WARN %d 条（不阻断，建议同期处理）：去掉 --summary-only 或 --json 看明细\n"
          % stats["warn"])
    if stats["error"]:
        w("")
        w("下一步：python3 tools/blueprint_lint.py --project . --fix-hints   # 每条附修法\n")
    elif only:
        w("")
        w("下一步：去掉 --only 跑全量 → python3 tools/blueprint_lint.py --project .\n")
    return stats


def print_human(linter, findings, show_fix, out=sys.stdout, only=None):
    errs = [f for f in findings if f["level"] == "ERROR"]
    warns = [f for f in findings if f["level"] == "WARN"]
    w = out.write
    w("蓝图自检（blueprint_lint）· 项目：%s\n" % linter.project)
    if only:
        w("⚠ 只跑了分区：%s —— **这不是全量检查**，结论不代表蓝图可用（去掉 --only 才是）\n"
          % "、".join(only))
    w("契约来源：%s\n" % (linter.schema.source or "内置常量（未找到 SCHEMAS.md）"))
    for msg in linter.schema.warnings:
        w("  ⚠ %s\n" % msg)
    w("\n")
    for section in SECTIONS:
        items = [f for f in findings if f["section"] == section]
        if not items:
            continue
        n_err = sum(1 for f in items if f["level"] == "ERROR")
        w("── %s ── %d 条（ERROR %d）\n" % (section, len(items), n_err))
        for f in items:
            mark = "✗" if f["level"] == "ERROR" else "⚠"
            w("  %s [%s] %s\n" % (mark, f["code"], f["where"]))
            w("      %s\n" % f["message"])
            if show_fix and f["fix"]:
                w("      → 修复：%s\n" % f["fix"])
        w("\n")

    covered = linter.counts.get("must_with_contract", 0)
    total = linter.counts.get("must_in", 0)
    stats = collect_stats(findings, linter)
    w("── 汇总 ──\n")
    w("  must 功能（scope=in）：%d，已有契约引用：%d（%s）\n"
      % (total, covered, rc.fmt_pct(rc.pct(covered, total))))
    w("  契约文件：%d 份\n" % len(getattr(linter, "contracts", {})))
    if stats["missing_contracts"]:
        w("  缺契约：**%d 份**（被 %d 处引用；同一个缺失文件会被 features 与 menus 各报一次，"
          "这是故意的——按文件修时能直接看出修完这一处消几条）\n"
          % (len(stats["missing_contracts"]), stats["missing_contract_refs"]))
    w("  ERROR %d 条 / WARN %d 条\n" % (len(errs), len(warns)))
    if errs:
        w("  结论：❌ 不可进入产品官审查。先修完 ERROR（--fix-hints 看修法）。\n")
    elif only:
        w("  结论：⚠ 所选分区无 ERROR，但**未做全量检查**，不能据此判可审。\n")
    elif warns:
        w("  结论：✅ 可进入产品官审查。WARN %d 条建议同期处理。\n" % len(warns))
    else:
        w("  结论：✅ 干净。可以拿这份蓝图去开产品官审查会。\n")
    if total and covered < total:
        w("  注意：must 契约覆盖率 %s < 100%%，G2 会直接 FAIL。\n"
          % rc.fmt_pct(rc.pct(covered, total)))


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="blueprint_lint.py",
        description="蓝图自检器：契约 16 节 / CSV 列 / ID 唯一 / 跨文件引用 / 菜单树 / 禁用词 / must 覆盖",
        epilog="示例：python3 tools/blueprint_lint.py --project ../myproj --fix-hints",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", default=".", help="项目根目录（默认当前目录）")
    ap.add_argument("--json", action="store_true", help="输出 JSON（供门禁/脚本消费）")
    ap.add_argument("--fix-hints", action="store_true", help="每条问题附修复动作")
    ap.add_argument("--only", default="", help="只跑指定分区，逗号分隔：%s" % ",".join(SECTIONS))
    ap.add_argument("--max-items", type=int, default=0, help="每分区最多打印多少条（0=全部）")
    ap.add_argument("--summary-only", action="store_true",
                    help="只输出一行结论 + 各类计数，不列明细（给产品官看）")
    args = ap.parse_args(argv)

    only = [s.strip() for s in args.only.split(",") if s.strip()] if args.only else None
    if only:
        bad = [s for s in only if s not in SECTIONS]
        if bad:
            return rc.die(rc.ToolError("未知分区：%s" % "、".join(bad),
                                       "可用分区：%s" % "、".join(SECTIONS)))

    if not os.path.isdir(args.project):
        return rc.die(rc.ToolError("项目目录不存在：%s" % args.project,
                                   "确认路径；新项目先跑 scripts/new-project.sh <目录>"))
    if not os.path.isdir(os.path.join(args.project, BLUEPRINT)):
        return rc.die(rc.ToolError(
            "缺 %s/ 目录：%s" % (BLUEPRINT, args.project),
            "这不是一个复制重建项目根目录，或还没跑 S1。先用 scripts/new-project.sh 生成骨架"))

    try:
        linter = Linter(args.project)
        findings = linter.run(only)
    except rc.ToolError as exc:
        return rc.die(exc)

    errs = sum(1 for f in findings if f["level"] == "ERROR")
    warns = sum(1 for f in findings if f["level"] == "WARN")

    stats = collect_stats(findings, linter)
    if args.json:
        rc.print_json({
            "tool": TOOL,
            "project": linter.project,
            "schema_source": linter.schema.source,
            "schema_warnings": linter.schema.warnings,
            "checked_at": rc.now_iso(),
            "counts": {
                "error": errs, "warn": warns,
                "must_in": stats["must_in"],
                "must_with_contract": stats["must_with_contract"],
                "contract_files": stats["contract_files"],
                # 去重后的缺失契约（产品官看的那个数）
                "missing_contract_files": len(stats["missing_contracts"]),
                "missing_contract_refs": stats["missing_contract_refs"],
            },
            "groups": stats["groups"],
            "by_code": stats["by_code"],
            "missing_contracts": stats["missing_contracts"],
            "missing_contracts_list": stats["missing_contracts"],
            "clean": errs == 0,
            "findings": findings,
            "__RESULT__": "lint errors=%d warns=%d missing_contracts=%d"
                          % (errs, warns, len(stats["missing_contracts"])),
        })
    elif args.summary_only:
        render_summary(linter, findings, only=only)
    else:
        print_human(linter, findings, args.fix_hints, only=only)

    return 0 if errs == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
