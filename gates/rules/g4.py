# -*- coding: utf-8 -*-
"""G4 架构门。

判定（00-体系总纲.md §3.2 / SCHEMAS.md §10、§12）：
1. SPEC/ARCHITECTURE.md 存在且含「组件边界 / 分层 / 数据流」三节
2. SPEC/schema.sql 存在且非空（有实际 DDL，不是注释占位）
3. SPEC/TRACEABILITY.csv 列齐；features.csv 里每个 must+in 功能在此表有一行，
   且 entities 与 commands 非 `-`
4. schema.sql 里出现的表名与 data-dictionary.md 的实体对应（宽松匹配：
   实体名小写化后出现在 sql 文本里即可）
5. 竖切证据文件存在（manifest.required.vertical_slice_evidence，默认 SPEC/vertical-slice.md）
"""

from __future__ import annotations

import re

from . import common as C

STAGE = "G4"

DEFAULT_VERTICAL_SLICE = "SPEC/vertical-slice.md"

ARCH_KEYWORDS = {
    "组件边界": ["组件边界", "边界", "component"],
    "分层": ["分层", "层", "layer"],
    "数据流": ["数据流", "数据流向", "data flow", "dataflow"],
}


def _architecture_checks(g, ctx):
    text = ctx.text("SPEC/ARCHITECTURE.md")
    if text is None:
        g.fail("architecture", "ARCHITECTURE.md 含组件边界/分层/数据流",
               expected="SPEC/ARCHITECTURE.md 存在且三节齐全",
               actual="文件不存在", evidence="SPEC/ARCHITECTURE.md",
               hint="按 templates/engineering/ARCHITECTURE.template.md 写：组件边界、分层、数据流")
        return
    titles = [t for lvl, t, _no in C.md_headings(text) if lvl in (2, 3)]
    missing = []
    for name, keys in ARCH_KEYWORDS.items():
        if not any(any(k.lower() in t.lower() for k in keys) for t in titles):
            missing.append(name)
    if missing:
        g.fail("architecture", "ARCHITECTURE.md 含组件边界/分层/数据流",
               expected="三个二级/三级标题：组件边界 / 分层 / 数据流",
               actual="缺：%s" % "、".join(missing), evidence="SPEC/ARCHITECTURE.md",
               hint="补标题与内容：组件边界（谁负责什么、依赖方向）、分层（层名与职责）、"
                    "数据流（写入路径与读取路径，含事务边界）")
    else:
        g.pass_("architecture", "ARCHITECTURE.md 含组件边界/分层/数据流",
                expected="三节齐全", actual="三节齐全（%d 个标题）" % len(titles),
                evidence="SPEC/ARCHITECTURE.md")


def _schema_checks(g, ctx):
    text = ctx.text("SPEC/schema.sql")
    if text is None:
        g.fail("schema-sql", "schema.sql 存在且有 DDL",
               expected="SPEC/schema.sql 含建表语句",
               actual="文件不存在", evidence="SPEC/schema.sql",
               hint="把 data-dictionary.md 的实体落成 DDL；字段名与字典一致")
        return None
    ddl = [line for line in text.splitlines()
           if re.search(r"\b(create\s+(table|index|view)|alter\s+table)\b", line, re.I)]
    if not ddl:
        g.fail("schema-sql", "schema.sql 存在且有 DDL",
               expected="至少 1 条 CREATE TABLE / CREATE INDEX",
               actual="%d 字节但没有任何 DDL" % len(text),
               evidence="SPEC/schema.sql",
               hint="写入真实建表语句；只有注释的文件不算架构产出")
        return text
    g.pass_("schema-sql", "schema.sql 存在且有 DDL",
            expected="含建表语句", actual="%d 条 DDL" % len(ddl),
            evidence="SPEC/schema.sql")
    return text


def _traceability_checks(g, ctx):
    rows = g.read_csv("SPEC/TRACEABILITY.csv", C.TRACEABILITY_COLUMNS,
                      "traceability-columns", "TRACEABILITY.csv 列名与 SCHEMAS §12 一致",
                      allow_missing=True)
    if rows is None:
        return
    by_feature = {}
    for row in rows:
        fid = C.cell(row, "feature_id")
        if fid:
            by_feature.setdefault(fid, row)
    targets = C.must_features(ctx)
    if not targets:
        g.na("traceability-rows", "must 功能在 TRACEABILITY.csv 有映射",
             reason="features.csv 里没有 must+in 功能")
        return
    missing, incomplete = [], []
    for row in targets:
        fid = C.cell(row, "feature_id")
        hit = by_feature.get(fid)
        if hit is None:
            missing.append(fid)
            continue
        for col, label in (("entities", "实体"), ("commands", "命令")):
            if C.is_blank(C.cell(hit, col)):
                incomplete.append("%s 的%s为空（entities/commands 不许填 `-`）" % (fid, label))
    if missing:
        g.fail("traceability-rows", "must 功能在 TRACEABILITY.csv 有映射",
               expected="%d 个 must+in 功能各 1 行" % len(targets),
               actual="缺 %d 个：%s" % (len(missing), "、".join(missing[:6])),
               evidence="SPEC/TRACEABILITY.csv",
               hint="每个 must 功能映射到 表/命令/路由/测试；缺映射说明架构没接住蓝图")
    else:
        g.pass_("traceability-rows", "must 功能在 TRACEABILITY.csv 有映射",
                expected="%d 个 must 功能" % len(targets),
                actual="全部有行（%d 行）" % len(rows), evidence="SPEC/TRACEABILITY.csv")
    if incomplete:
        g.fail("traceability-fields", "每个映射的 entities 与 commands 非空",
               expected="entities 与 commands 均指向具体表/命令",
               actual="；".join(incomplete[:5]), evidence="SPEC/TRACEABILITY.csv",
               hint="填真实表名与命令 ID；确实无命令（纯读功能）时写命令的读路径 ID 而不是 `-`")
    else:
        g.pass_("traceability-fields", "每个映射的 entities 与 commands 非空",
                expected="entities / commands 非 `-`",
                actual="%d 行全部填写" % len(rows), evidence="SPEC/TRACEABILITY.csv")


def _entity_checks(g, ctx, sql_text):
    dict_text = ctx.text("BLUEPRINT/data-dictionary.md")
    if dict_text is None:
        g.fail("entity-mapping", "数据字典实体与 schema.sql 表对应",
               expected="data-dictionary.md 的实体在 schema.sql 里能找到",
               actual="BLUEPRINT/data-dictionary.md 不存在",
               evidence="BLUEPRINT/data-dictionary.md",
               hint="S1/S2 起草实体，S4 落成 DDL；两处必须能对上")
        return
    if sql_text is None:
        g.na("entity-mapping", "数据字典实体与 schema.sql 表对应",
             reason="schema.sql 缺失（见 schema-sql）")
        return
    # 实体名：二级标题 `## E01 TaskModel` 或表格第一列 `E01`
    entities = []
    for sec in C.md_sections(dict_text, 2):
        m = re.match(r"^(E\d{2})\s*(.*)$", sec["title"])
        if m:
            name = m.group(2).strip()
            entities.append((m.group(1), name))
    sql_lower = sql_text.lower()
    unmatched, matched = [], []
    for eid, name in entities:
        token = re.sub(r"[^A-Za-z0-9_]", "", name).lower()
        if not token and eid.lower() not in sql_lower:
            unmatched.append(eid)
            continue
        if token and token in sql_lower:
            matched.append("%s %s" % (eid, name))
        elif eid.lower() in sql_lower:
            matched.append(eid)
        else:
            unmatched.append("%s %s" % (eid, name))
    if not entities:
        g.fail("entity-mapping", "数据字典实体与 schema.sql 表对应",
               expected="data-dictionary.md 含 `## E01 <实体名>` 形式的实体",
               actual="没有解析到实体编号",
               evidence="BLUEPRINT/data-dictionary.md",
               hint="实体标题写成 `## E01 TaskModel`，S4 的 DDL 用同名表（大小写不敏感）")
    elif unmatched:
        g.fail("entity-mapping", "数据字典实体与 schema.sql 表对应",
               expected="每个实体名（小写）出现在 schema.sql 中",
               actual="%d 个实体没落成表：%s" % (len(unmatched), "、".join(unmatched[:5])),
               evidence="SPEC/schema.sql",
               hint="补建表；若实体是纯视图/派生值，在 schema.sql 用 CREATE VIEW 落地并保同名")
    else:
        g.pass_("entity-mapping", "数据字典实体与 schema.sql 表对应",
                expected="实体名均出现在 DDL 中",
                actual="%d 个实体全部对上（%s）" % (len(matched), "、".join(matched[:3])),
                evidence="SPEC/schema.sql")


def _vertical_slice_checks(g, ctx):
    rel = str(ctx.required.get("vertical_slice_evidence") or DEFAULT_VERTICAL_SLICE).strip()
    text = ctx.text(rel)
    if text is None:
        g.fail("vertical-slice", "竖切证据文件存在",
               expected="%s（可由 manifest.required.vertical_slice_evidence 配置）" % rel,
               actual="文件不存在", evidence=rel,
               hint="竖切 = 一条最薄闭环「建→读→重启还在」。写清命令、期望输出、实测输出与时间")
        return
    if len(text.strip()) < 40:
        g.fail("vertical-slice", "竖切证据文件存在",
               expected="记录一条跑通的竖切（命令 + 实测输出）",
               actual="只有 %d 字符" % len(text.strip()), evidence=rel,
               hint="补：执行命令、实测输出、重启后复查输出、耗时")
        return
    g.pass_("vertical-slice", "竖切证据文件存在",
            expected="含可复核的竖切记录",
            actual="%d 字符" % len(text.strip()), evidence=rel)


def check(ctx):
    g = C.Gate(ctx, STAGE)
    if g.no_manifest():
        return g.results

    _architecture_checks(g, ctx)
    sql_text = _schema_checks(g, ctx)
    _traceability_checks(g, ctx)
    _entity_checks(g, ctx, sql_text)
    _vertical_slice_checks(g, ctx)

    return g.results
