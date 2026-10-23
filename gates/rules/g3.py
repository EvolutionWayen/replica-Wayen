# -*- coding: utf-8 -*-
"""G3 冻结门（哈希实算逐字比对，不许手填）。

判定（00-体系总纲.md §3.2 / SCHEMAS.md §11）：
1. BLUEPRINT-LOCK.md 存在且含蓝图版本 / 冻结时间（ISO 8601 带时区）/ 确认人
2. 哈希表覆盖 SCHEMAS §11 要求的全部文件（9 份蓝图 + 全部 contracts/*.md）
3. **实算每个文件 SHA-256 与记录逐字比对**，任一不符即 FAIL（含大小写不一致）
4. unknowns.csv 中 blocking=yes & status=open 计数为 0
5. accepted-risk / out-of-scope 的未知在 DECISIONS.md 有对应 D- 记录
"""

from __future__ import annotations

import re

from . import common as C

STAGE = "G3"

VERSION_RE = re.compile(r"v?\d+\.\d+(?:\.\d+)?", re.I)


def _lock_rows(text):
    """从 BLUEPRINT-LOCK.md 的两列/多列表格里取出 {文件: 哈希}。"""
    out = {}
    for table in C.md_tables(text):
        header = [h.lower() for h in table["header"]]
        file_idx, hash_idx = None, None
        for i, name in enumerate(header):
            if file_idx is None and ("文件" in name or "file" in name):
                file_idx = i
            elif hash_idx is None and ("sha" in name or "哈希" in name or "hash" in name):
                hash_idx = i
        for cells, no in zip(table["rows"], table["lines"]):
            if file_idx is not None and hash_idx is not None:
                if hash_idx >= len(cells) or file_idx >= len(cells):
                    continue
                path, digest = cells[file_idx].strip(), cells[hash_idx].strip()
            else:
                # 退路：找行内第一个像路径的格与第一个 64 位 hex
                path, digest = "", ""
                for cell in cells:
                    if not path and ("/" in cell or cell.endswith(".md") or cell.endswith(".csv")):
                        path = cell.strip()
                    m = C.SHA256_RE.search(cell)
                    if not digest and m:
                        digest = m.group(0)
            if not path or path.lower() in ("文件", "file", "路径"):
                continue
            out[path.strip().strip("`").replace("\\", "/")] = digest
    return out


def _required_lock_files(ctx):
    files = list(C.LOCK_REQUIRED_FILES)
    for rel in C.contract_files(ctx):
        if rel not in files:
            files.append(rel)
    return files


def check(ctx):
    g = C.Gate(ctx, STAGE)
    if g.no_manifest():
        return g.results

    text = ctx.text("BLUEPRINT/BLUEPRINT-LOCK.md")
    if text is None:
        g.fail("lock-file", "BLUEPRINT-LOCK.md 存在且非空",
               expected="冻结记录文件存在", actual="文件不存在",
               evidence="BLUEPRINT/BLUEPRINT-LOCK.md",
               hint="按 SCHEMAS §11 建冻结记录：版本号 + 冻结时间 + 确认人 + 逐文件 SHA-256")
        return g.results  # 没有冻结记录，后续逐项判定无意义

    g.pass_("lock-file", "BLUEPRINT-LOCK.md 存在且非空",
            expected="冻结记录存在", actual="%d 字节" % ctx.size("BLUEPRINT/BLUEPRINT-LOCK.md"),
            evidence="BLUEPRINT/BLUEPRINT-LOCK.md")

    # ---- 1. 版本 / 时间 / 确认人 ----
    version = ""
    m = re.search(r"蓝图版本[^\n|]*\|?\s*(v?\d+\.\d+(?:\.\d+)?)", text, re.I)
    if m:
        version = m.group(1)
    else:
        m = VERSION_RE.search(text)
        version = m.group(0) if m else ""
    if version:
        g.pass_("lock-version", "含蓝图版本号", expected="vX.Y", actual=version,
                evidence="BLUEPRINT/BLUEPRINT-LOCK.md")
    else:
        g.fail("lock-version", "含蓝图版本号", expected="vX.Y（如 v1.0）",
               actual="未找到版本号", evidence="BLUEPRINT/BLUEPRINT-LOCK.md",
               hint="在表格里写「| 蓝图版本 | v1.0 |」")

    time_hit = C.ISO_DATETIME_RE.search(text)
    if time_hit:
        g.pass_("lock-time", "含冻结时间（ISO 8601 带时区）",
                expected="形如 2026-10-23T10:40+08:00",
                actual=time_hit.group(0), evidence="BLUEPRINT/BLUEPRINT-LOCK.md")
    else:
        bare = C.DATE_RE.search(text)
        g.fail("lock-time", "含冻结时间（ISO 8601 带时区）",
               expected="ISO 8601 带时区，如 2026-10-23T10:40+08:00",
               actual=("只有日期 %s，没有时间与时区" % bare.group(0)) if bare else "未找到时间",
               evidence="BLUEPRINT/BLUEPRINT-LOCK.md",
               hint="写完整时刻与时区（R15：时间要能判定新旧）")

    confirmer = ""
    m = re.search(r"确认人[^\n|]*\|?\s*([^\n|]+)", text)
    if m:
        confirmer = m.group(1).strip().strip("`")
    if confirmer and len(confirmer) >= 2 and confirmer not in C.BLANK_VALUES:
        g.pass_("lock-confirmer", "含确认人", expected="具体的人（产品官）",
                actual=confirmer, evidence="BLUEPRINT/BLUEPRINT-LOCK.md")
    else:
        g.fail("lock-confirmer", "含确认人", expected="具体的人名（产品官），不许写 AI / 自动",
               actual="未找到或为空", evidence="BLUEPRINT/BLUEPRINT-LOCK.md",
               hint="Agent 不得自批（§7.1）；写真实确认人")

    # ---- 2/3. 哈希覆盖 + 实算比对 ----
    recorded = _lock_rows(text)
    required = _required_lock_files(ctx)
    missing = [rel for rel in required if not any(
        rel == key or rel.endswith("/" + key) or key.endswith(rel.split("/")[-1]) and
        key.split("/")[-1] == rel.split("/")[-1] for key in recorded)]
    if missing:
        g.fail("lock-coverage", "哈希表覆盖 SCHEMAS §11 全部文件",
               expected="%d 个文件（9 份蓝图 + %d 份契约）" % (len(required), len(required) - 9),
               actual="缺 %d 个：%s" % (len(missing), "；".join(missing[:5])),
               evidence="BLUEPRINT/BLUEPRINT-LOCK.md",
               hint="冻结时必须逐文件登记 SHA-256；可用体系自带的生成器子命令 `_make.py lock <项目>` 批量重算")
    else:
        g.pass_("lock-coverage", "哈希表覆盖 SCHEMAS §11 全部文件",
                expected="%d 个文件" % len(required),
                actual="%d 个文件全部登记" % len(recorded),
                evidence="BLUEPRINT/BLUEPRINT-LOCK.md")

    mismatch, checked, missing_file = [], 0, []
    for rel in required:
        key = None
        for candidate in recorded:
            if candidate == rel or candidate.endswith("/" + rel.split("/")[-1]) \
                    and candidate.split("/")[-1] == rel.split("/")[-1]:
                key = candidate
                break
        if key is None:
            continue
        want = (recorded.get(key) or "").strip()
        if not C.SHA256_RE.fullmatch(want):
            mismatch.append("%s 记录值不是 64 位 hex（%r）" % (rel, want[:20]))
            continue
        actual = ctx.sha256(rel)
        if actual is None:
            missing_file.append(rel)
            continue
        checked += 1
        if want.lower() != actual.lower():
            mismatch.append("%s 记录 %s… 实算 %s…" % (rel, want[:12], actual[:12]))
        elif want != actual:
            mismatch.append("%s 记录与实算仅大小写不同（记录须小写十六进制）" % rel)
    if mismatch or missing_file:
        detail = []
        if mismatch:
            detail.append("%d 个哈希不符：%s" % (len(mismatch), "；".join(mismatch[:4])))
        if missing_file:
            detail.append("文件缺失：%s" % "；".join(missing_file[:4]))
        g.fail("lock-hashes", "实算 SHA-256 与记录逐字一致",
               expected="每个文件实算值 = 记录值",
               actual="；".join(detail), evidence="BLUEPRINT/BLUEPRINT-LOCK.md",
               hint="文件被改过或哈希是手填的。用体系生成器的 lock 子命令重算（`python3 _make.py lock <项目>`）；"
                    "冻结后改文件必须走变更单 + 版本 +1 + 重算哈希（§8）")
    elif checked:
        g.pass_("lock-hashes", "实算 SHA-256 与记录逐字一致",
                expected="全部一致", actual="%d 个文件逐个复算一致" % checked,
                evidence="BLUEPRINT/BLUEPRINT-LOCK.md")
    else:
        g.na("lock-hashes", "实算 SHA-256 与记录逐字一致",
             reason="记录表里没有可与实算配对的文件行（见 lock-coverage）")

    # ---- 4. 阻断级未知 = 0 ----
    unknown_rows = C.unknowns(ctx)
    blocking_open = [C.cell(r, "unknown_id") or "(无 ID)" for r in unknown_rows
                     if C.cell(r, "blocking").lower() == "yes"
                     and C.cell(r, "status").lower() == "open"]
    if blocking_open:
        g.fail("blocking-unknowns", "阻断级未知（blocking=yes & status=open）计数为 0",
               expected="0 条", actual="%d 条：%s" % (len(blocking_open),
                                                    "、".join(blocking_open[:6])),
               evidence="BLUEPRINT/unknowns.csv",
               hint="逐条补验（verification_action），或经产品官批准改为 accepted-risk / out-of-scope 并记 D-")
    else:
        g.pass_("blocking-unknowns", "阻断级未知（blocking=yes & status=open）计数为 0",
                expected="0 条", actual="0 条（共 %d 条未知）" % len(unknown_rows),
                evidence="BLUEPRINT/unknowns.csv")

    # ---- 5. accepted-risk / out-of-scope 有 D- 记录 ----
    decisions = ctx.text("DECISIONS.md") or ""
    decision_ids = sorted(set(re.findall(r"\bD-\d+\b", decisions)))
    waived = [r for r in unknown_rows
              if C.cell(r, "status").lower() in ("accepted-risk", "out-of-scope")]
    undocumented = []
    for row in waived:
        uid = C.cell(row, "unknown_id")
        desc = C.cell(row, "description")[:20]
        if re.search(re.escape(uid), decisions):
            continue
        # 没有按 U- 编号引用时，退一步看是否有 D- 记录提到这段描述的关键词
        keys = [w for w in re.split(r"[\s，。、,;；:：()（）]+", desc) if len(w) >= 3][:3]
        if keys and all(k in decisions for k in keys):
            continue
        undocumented.append("%s（%s，status=%s）" % (uid, desc, C.cell(row, "status")))
    if undocumented:
        g.fail("waived-unknowns", "被豁免的未知都有产品官批准记录",
               expected="accepted-risk / out-of-scope 的未知在 DECISIONS.md 有 D- 记录且引用其 U- 编号",
               actual="%d 条无记录：%s" % (len(undocumented), "；".join(undocumented[:4])),
               evidence="BLUEPRINT/unknowns.csv",
               hint="在 DECISIONS.md 追加一条 D-：「接受 U-00x 的风险，理由…」，由产品官批准")
    else:
        g.pass_("waived-unknowns", "被豁免的未知都有产品官批准记录",
                expected="每条豁免有 D- 记录",
                actual="%d 条豁免全部有记录" % len(waived),
                evidence="BLUEPRINT/unknowns.csv")

    return g.results
