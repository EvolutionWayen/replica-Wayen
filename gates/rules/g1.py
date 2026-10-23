# -*- coding: utf-8 -*-
"""G1 取证门。

判定（00-体系总纲.md §3.2 / SCHEMAS.md §1–§3、§6）：
1. BLUEPRINT/ 下 recon.md / features.csv / screens.csv / unknowns.csv 存在
2. recon.md 含 10 个规定二级标题
3. features.csv 列名与顺序 = SCHEMAS §2，feature_id 唯一且形如 F-[A-Z0-9-]+
4. features.csv 枚举合法（priority/scope/original/progress）
5. screens.csv 列名 = SCHEMAS §3，四态列（filled/empty/loading/error）为 yes，
   或为 `-` 且 notes 给出理由
6. unknowns.csv 列名 = SCHEMAS §6，每行 verification_action 非空，枚举合法
7. manifest.required.evidence_dirs（默认 evidence/screens）下 ≥1 个非空受控文件
8. features.csv 每行 evidence 非空（original=no 的新增功能除外）
"""

from __future__ import annotations

import re

from . import common as C

STAGE = "G1"

DEFAULT_EVIDENCE_DIRS = ["evidence", "screens"]


def _evidence_dirs(ctx):
    value = ctx.required.get("evidence_dirs") or DEFAULT_EVIDENCE_DIRS
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list) or not value:
        value = DEFAULT_EVIDENCE_DIRS
    return [str(v).strip().strip("/") for v in value if str(v).strip()]


def check(ctx):
    g = C.Gate(ctx, STAGE)
    if g.no_manifest():
        return g.results

    # ---- 1. 四个必需文件 ----
    g.need_file("BLUEPRINT/recon.md", "recon-file", "BLUEPRINT/recon.md 存在且非空",
                hint="按 templates/blueprint/SCHEMAS.md §1 的 10 段结构写逆向地图")
    g.need_file("BLUEPRINT/features.csv", "features-file", "BLUEPRINT/features.csv 存在且非空",
                hint="按 SCHEMAS §2 建 11 列，先列全功能再判优先级")
    g.need_file("BLUEPRINT/screens.csv", "screens-file", "BLUEPRINT/screens.csv 存在且非空",
                hint="按 SCHEMAS §3 建 14 列，屏幕四态逐列记录")
    g.need_file("BLUEPRINT/unknowns.csv", "unknowns-file", "BLUEPRINT/unknowns.csv 存在且非空",
                hint="按 SCHEMAS §6 建 9 列；一个未知都没有 = 没认真取证")

    # ---- 2. recon.md 10 段 ----
    recon = ctx.text("BLUEPRINT/recon.md")
    if recon is None:
        g.fail("recon-headings", "recon.md 含 10 个规定二级标题",
               expected="10 个标题逐字一致", actual="recon.md 不存在",
               evidence="BLUEPRINT/recon.md", hint="先完成 S1 取证")
    else:
        titles = [t for lvl, t, _no in C.md_headings(recon) if lvl == 2]
        missing = [h for h in C.RECON_HEADINGS if h not in titles]
        if missing:
            g.fail("recon-headings", "recon.md 含 10 个规定二级标题",
                   expected="10 个标题逐字一致（SCHEMAS §1）",
                   actual="缺 %d 个：%s" % (len(missing), "；".join(missing[:4])),
                   evidence="BLUEPRINT/recon.md",
                   hint="按 templates/blueprint/SCHEMAS.md §1 补齐标题（文字必须完全一致）")
        else:
            g.pass_("recon-headings", "recon.md 含 10 个规定二级标题",
                    expected="10 段", actual="10 段齐全", evidence="BLUEPRINT/recon.md")

    # ---- 3/4. features.csv ----
    feature_rows = g.read_csv("BLUEPRINT/features.csv", C.FEATURES_COLUMNS,
                              "features-columns", "features.csv 列名与 SCHEMAS §2 一致",
                              allow_missing=True)
    if feature_rows is not None:
        ids, bad_format, dup = [], [], []
        for i, row in enumerate(feature_rows, start=2):
            fid = C.cell(row, "feature_id")
            if not fid:
                bad_format.append("第 %d 行 feature_id 为空" % i)
                continue
            if not C.FEATURE_ID_RE.match(fid):
                bad_format.append("第 %d 行 %r 不合 F-[A-Z0-9-]+" % (i, fid))
            if fid in ids:
                dup.append(fid)
            ids.append(fid)
        if bad_format or dup:
            g.fail("features-ids", "feature_id 唯一且格式合法",
                   expected="每行 F-<域>-<短名>，全表唯一",
                   actual="；".join((bad_format + ["重复：%s" % ",".join(sorted(set(dup)))]
                                    if dup else bad_format))[:200],
                   evidence="BLUEPRINT/features.csv",
                   hint="ID 一经分配永不复用；删除用 progress=skip，不删行")
        else:
            g.pass_("features-ids", "feature_id 唯一且格式合法",
                    expected="F-[A-Z0-9-]+ 且唯一", actual="%d 个 ID" % len(ids),
                    evidence="BLUEPRINT/features.csv")

        enum_bad = []
        for i, row in enumerate(feature_rows, start=2):
            priority = C.normalize_priority(C.cell(row, "priority"))
            scope = C.cell(row, "scope").lower()
            original = C.cell(row, "original").lower()
            progress = C.cell(row, "progress").lower()
            if priority not in C.PRIORITY_ENUM:
                enum_bad.append("第 %d 行 priority=%r" % (i, C.cell(row, "priority")))
            if scope not in ("in", "out"):
                enum_bad.append("第 %d 行 scope=%r" % (i, C.cell(row, "scope")))
            if original not in ("yes", "no"):
                enum_bad.append("第 %d 行 original=%r" % (i, C.cell(row, "original")))
            if progress not in C.PROGRESS_ENUM:
                enum_bad.append("第 %d 行 progress=%r" % (i, C.cell(row, "progress")))
        if enum_bad:
            g.fail("features-enums", "features.csv 枚举合法",
                   expected="priority=must/should/could（或 P0/P1/P2）、scope=in/out、"
                            "original=yes/no、progress=yes/partial/no/skip",
                   actual="；".join(enum_bad[:5]), evidence="BLUEPRINT/features.csv",
                   hint="按 SCHEMAS.md §0 的枚举值改写；空值只能写 `-`（经确认不适用）")
        else:
            g.pass_("features-enums", "features.csv 枚举合法",
                    expected="枚举值全部在 SCHEMAS §0 内",
                    actual="%d 行全部合法" % len(feature_rows),
                    evidence="BLUEPRINT/features.csv")

    # ---- 5. screens.csv ----
    screen_rows = g.read_csv("BLUEPRINT/screens.csv", C.SCREENS_COLUMNS,
                             "screens-columns", "screens.csv 列名与 SCHEMAS §3 一致",
                             allow_missing=True)
    if screen_rows is not None:
        bad = []
        for i, row in enumerate(screen_rows, start=2):
            ok, detail = C.screen_four_states(row)
            if not ok:
                bad.append("第 %d 行 %s：%s" % (
                    i, C.cell(row, "screen_id") or "(无 screen_id)", "，".join(detail)))
        if bad:
            g.fail("screens-states", "每条屏幕四态已记录",
                   expected="state_filled/empty/loading/error = yes（或 '-' 且 notes 有理由）",
                   actual="；".join(bad[:4]), evidence="BLUEPRINT/screens.csv",
                   hint="逐屏补齐四态取证；不适用写 `-` 并在地 notes 说明为什么")
        else:
            g.pass_("screens-states", "每条屏幕四态已记录",
                    expected="四态全部 yes", actual="%d 条屏幕全部记录" % len(screen_rows),
                    evidence="BLUEPRINT/screens.csv")

    # ---- 5b. screen_id 格式与唯一性（与 tools/blueprint_lint.py 的 SCREEN-ID-FORMAT 同口径） ----
    if screen_rows is not None:
        bad_fmt, dup_ids, seen = [], [], {}
        for i, row in enumerate(screen_rows, start=2):
            sid = C.cell(row, "screen_id")
            if not sid:
                bad_fmt.append("第 %d 行 screen_id 为空" % i)
                continue
            # screen_id 是被 features/menus/linkage/flows 引用的主键 → 严格 S-两位数
            if not re.fullmatch(r"S-\d{2}", sid):
                bad_fmt.append("第 %d 行 %r 不是严格的 S-两位数" % (i, sid))
            if sid in seen:
                dup_ids.append("%s（第 %d 行与第 %d 行）" % (sid, seen[sid], i))
            else:
                seen[sid] = i
        if bad_fmt or dup_ids:
            detail = []
            if bad_fmt:
                detail.append("格式问题 %d 处：%s" % (len(bad_fmt), "；".join(bad_fmt[:4])))
            if dup_ids:
                detail.append("重复 %d 处：%s" % (len(dup_ids), "；".join(dup_ids[:4])))
            g.fail("screens-ids", "screen_id 严格 S-两位数且唯一",
                   expected="每个 screen_id 形如 S-01（两位数字），全表唯一",
                   actual="；".join(detail), evidence="BLUEPRINT/screens.csv",
                   hint="screen_id 是被 features/menus/linkage/flows 引用的主键，必须 S-01 这种两位数字；"
                        "带后缀的描述写进 name 列或 features.csv 的 area 列（area 允许 S-03-预约页）")
        else:
            g.pass_("screens-ids", "screen_id 严格 S-两位数且唯一",
                    expected="S-01 形式且唯一",
                    actual="%d 个 screen_id 全部合规" % len(seen),
                    evidence="BLUEPRINT/screens.csv")

    # ---- 6. unknowns.csv ----
    unknown_rows = g.read_csv("BLUEPRINT/unknowns.csv", C.UNKNOWNS_COLUMNS,
                              "unknowns-columns", "unknowns.csv 列名与 SCHEMAS §6 一致",
                              allow_missing=True)
    if unknown_rows is not None:
        bad_action = []
        for i, row in enumerate(unknown_rows, start=2):
            if C.is_blank(C.cell(row, "verification_action")):
                bad_action.append("第 %d 行 %s" % (i, C.cell(row, "unknown_id") or "(无 ID)"))
        if bad_action:
            g.fail("unknowns-actions", "每条未知都有可执行的补验动作",
                   expected="verification_action 非空且是可执行动作",
                   actual="缺：%s" % "，".join(bad_action[:5]),
                   evidence="BLUEPRINT/unknowns.csv",
                   hint="写具体动作（再点一次某菜单/抓一次接口/导出一次 DB），不写「再研究一下」")
        else:
            g.pass_("unknowns-actions", "每条未知都有可执行的补验动作",
                    expected="verification_action 非空",
                    actual="%d 条未知均有补验动作" % len(unknown_rows),
                    evidence="BLUEPRINT/unknowns.csv")

        enum_bad = []
        for i, row in enumerate(unknown_rows, start=2):
            blocking = C.cell(row, "blocking").lower()
            status = C.cell(row, "status").lower()
            if blocking not in ("yes", "no"):
                enum_bad.append("第 %d 行 blocking=%r" % (i, C.cell(row, "blocking")))
            if status not in C.UNKNOWN_STATUS:
                enum_bad.append("第 %d 行 status=%r" % (i, C.cell(row, "status")))
        if enum_bad:
            g.fail("unknowns-enums", "unknowns.csv 枚举合法",
                   expected="blocking=yes/no，status=open/resolved/accepted-risk/out-of-scope",
                   actual="；".join(enum_bad[:5]), evidence="BLUEPRINT/unknowns.csv",
                   hint="按 SCHEMAS §6 枚举改写；关闭未知必须给证据")
        else:
            g.pass_("unknowns-enums", "unknowns.csv 枚举合法",
                    expected="枚举值全部合法", actual="%d 行全部合法" % len(unknown_rows),
                    evidence="BLUEPRINT/unknowns.csv")

    # ---- 7. 证据文件 ----
    dirs = _evidence_dirs(ctx)
    found, total = [], 0
    for rel_dir in dirs:
        base = ctx.path(rel_dir)
        if not base.is_dir():
            continue
        for p in C.iter_text_files(base):
            try:
                if p.stat().st_size > 0:
                    total += 1
                    if len(found) < 3:
                        found.append(ctx.rel(p))
            except OSError:
                continue
        for p in sorted(base.rglob("*")):
            if p.is_file() and p.suffix.lower() not in (".md", ".txt", ".csv", ".json") \
                    and p.stat().st_size > 0:
                total += 1
                if len(found) < 3:
                    found.append(ctx.rel(p))
    if total >= 1:
        g.pass_("evidence-files", "受控证据文件 ≥1",
                expected="%s 下至少 1 个非空文件" % "/".join(dirs),
                actual="%d 个，示例：%s" % (total, "、".join(found)),
                evidence=found[0] if found else dirs[0])
    else:
        g.fail("evidence-files", "受控证据文件 ≥1",
               expected="%s 下至少 1 个非空文件" % "/".join(dirs),
               actual="没有找到非空文件", evidence=dirs[0],
               hint="把截图/录屏/DB 导出放进 %s（只加不改，纳入版本控制）" % "/".join(dirs))

    # ---- 8. features.csv 每行有证据 ----
    if feature_rows is not None:
        missing_evidence = []
        for i, row in enumerate(feature_rows, start=2):
            if C.cell(row, "original").lower() == "no":
                continue  # 新增的差异化功能，原版无行为可取证
            if C.is_blank(C.cell(row, "evidence")):
                missing_evidence.append("第 %d 行 %s" % (
                    i, C.cell(row, "feature_id") or "(无 ID)"))
        if missing_evidence:
            g.fail("features-evidence", "每条原版功能都指到证据",
                   expected="original=yes 的行 evidence 非空（S-xx / M-xx / 证据路径）",
                   actual="缺：%s" % "，".join(missing_evidence[:5]),
                   evidence="BLUEPRINT/features.csv",
                   hint="为每行补证据引用；没有证据的功能不进 must（改 priority 或进 unknowns.csv）")
        else:
            g.pass_("features-evidence", "每条原版功能都指到证据",
                    expected="original=yes 的行 evidence 非空",
                    actual="%d 行已指证据" % len(feature_rows),
                    evidence="BLUEPRINT/features.csv")

    # ---- scope=out 必须写明理由（防"改 out 拉分"）----
    # G9 的功能分剔除 scope=out 的行。若允许悄悄改 out，就能靠缩范围把分数拉满。
    # 所以 out 必须是显式决策：notes 里要有理由，且不能是占位词。
    MIN_REASON = 8
    PLACEHOLDER = ("-", "—", "无", "暂无", "todo", "tbd", "待定", "待补", "略")
    bad_out = []
    out_count = 0
    for row in feature_rows:
        if (C.cell(row, "scope") or "").strip().lower() != "out":
            continue
        out_count += 1
        fid = C.cell(row, "feature_id") or "(无 ID)"
        notes = (C.cell(row, "notes") or "").strip()
        low = notes.lower()
        if not notes or low in PLACEHOLDER or len(notes) < MIN_REASON:
            bad_out.append("%s（notes %s）" % (
                fid, "为空" if not notes else "仅 %d 字" % len(notes)))
    if bad_out:
        g.fail("out-scope-reason", "scope=out 的功能写明排除理由",
               expected="每行 scope=out 的 notes ≥%d 字且非占位词" % MIN_REASON,
               actual="%d/%d 行缺理由：%s" % (len(bad_out), out_count,
                                            "；".join(bad_out[:5])),
               evidence="BLUEPRINT/features.csv",
               hint="改 scope=out 会让 G9 功能分不再统计它——这是合法决策，但必须写清"
                    "「为什么这一版不做」。没有理由就说明这不是决策，而是躲分数")
    elif out_count:
        g.pass_("out-scope-reason", "scope=out 的功能写明排除理由",
                expected="每行 scope=out 的 notes ≥%d 字" % MIN_REASON,
                actual="%d 行均有理由" % out_count,
                evidence="BLUEPRINT/features.csv")
    else:
        g.pass_("out-scope-reason", "scope=out 的功能写明排除理由",
                expected="每行 scope=out 的 notes ≥%d 字" % MIN_REASON,
                actual="本版无 scope=out 行", evidence="BLUEPRINT/features.csv")

    return g.results
