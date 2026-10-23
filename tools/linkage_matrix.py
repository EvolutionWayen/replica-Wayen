#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""linkage_matrix.py —— 联动矩阵：功能 × 六面，一眼看出「页面有、内部没联动」

六面（SCHEMAS §5）：**名称与关键词的唯一权威定义在 `<体系根>/shared/faces.json`**
（gates 与本工具共用同一份；改关键词只改那一处，不要在这里加内联列表）。
本文件顶部的 `_FACE_FALLBACK` 只是读不到 JSON 时的兜底副本。

它回答三个问题：
  1. 每个 must 功能，六面里哪几面已经 wire、哪几面待接、哪几面确认不适用、哪几面根本没人管？
  2. 哪些功能**完全没做过联动分析**（六面无条目，或六面全填 na）？
  3. 哪些功能「只有 1 面 wire」？——多半是没想透（00 §10-01）。

四态口径（SCHEMAS §5 的 status 枚举）：

    wired / verified   → ●  已 wire（已接/已验）
    pending            → ◐  待接（有条目但还没接）
    na                 → ×  确认不适用（**必须真想过**，理由写进 state_handling）
    （无条目）          → ·  漏了

统计拆成四个数：`wired` / `pending` / `na` / `no_entry`。
- **缺面数 = no_entry 数**（不含 na，也不含 pending：pending 是已登记待做，不算漏）
- **na 不计入 missing，但计入"已考虑面数"** —— 这样"穷举过六面"与"漏了三面"能区分开
- **六面全 na = 等同于没做联动分析**（防滥用），单独报 FAIL 级问题
- **六面无条目 = 完全没做过联动分析**，同样单独报 FAIL 级问题

归类方式：按 `affected_control` 的中文关键词归类，关键词表来自 `shared/faces.json`。
在 `affected_control` 里显式写 `#面名` 也能强制归类，例：`任务行日期徽标 #主列表`。
`--config` 用于**局部覆盖**（只写要改的面即可，未提及的面沿用 SSOT）。

用法：
    python3 tools/linkage_matrix.py --project .                # Markdown 矩阵
    python3 tools/linkage_matrix.py --project . --json         # 供 G6 门禁
    python3 tools/linkage_matrix.py --project . --md-out REPORT/linkage.md
    python3 tools/linkage_matrix.py --project . --strict       # 有 no_entry / 全 na 即退出码 1
    python3 tools/linkage_matrix.py --project . --dump-config  # 导出默认关键词表

供其它工具 import 的公共 API（gate-engineer 可直接用，不要在 main 里内联）：
    load_faces(config_path=None) -> [face]
    classify(control, faces) -> [face_key]
    load_tables(project) -> (tables, issues)
    analyse(tables, faces) -> dict          # 完整分析结果（含四态统计）
    face_counts(feature_state) -> dict      # 单个功能的四态计数
    DEFAULT_FACES                           # 六面定义（读自 shared/faces.json）
    _FACE_FALLBACK                          # 读不到 JSON 时的兜底副本（不要直接引用）

退出码：0 通过 / 1 有 no_entry 或六面全 na（或条目缺字段）/ 2 输入错误
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import replica_common as rc  # noqa: E402

TOOL = "linkage_matrix"

LINKAGE_REL = os.path.join("BLUEPRINT", "linkage.csv")
FEATURES_REL = os.path.join("BLUEPRINT", "features.csv")
SCREENS_REL = os.path.join("BLUEPRINT", "screens.csv")

# 六面定义：顺序 + 显示名 + 关键词（可在 --config 里覆盖）
# 六面（跨页面联动影响面）：**唯一权威定义在 <体系根>/shared/faces.json**。
# 读不到时退回内置副本（并在 stderr 提示），保证工具不会因文件缺失而瘫痪。
_FACE_FALLBACK = [
    {"key": "list", "name": "主列表", "desc": "任务/卡片列表、行内徽标、排序位置",
     "keywords": ["列表", "主列表", "行", "徽标", "badge", "清单视图", "排序", "分组",
                  "list", "row"]},
    {"key": "badge", "name": "角标计数", "desc": "侧栏/标签/智能清单上的数字",
     "keywords": ["角标", "计数", "数字", "徽标数", "badge", "counter", "sidebar",
                  "侧栏", "标签页", "tab 角标", "未完成数", "统计"]},
    {"key": "detail", "name": "详情面板", "desc": "右侧详情、编辑态、属性区",
     "keywords": ["详情", "面板", "属性", "编辑器", "detail", "inspector", "info"]},
    {"key": "calendar", "name": "日历/时间", "desc": "月/周视图、时间轴、时间选择器",
     "keywords": ["日历", "时间视图", "月视图", "周视图", "时间轴", "时间选择", "时段",
                  "calendar", "timeline"]},
    {"key": "search", "name": "搜索", "desc": "搜索结果、筛选、索引",
     "keywords": ["搜索", "检索", "筛选", "过滤", "索引", "search", "filter", "query"]},
    {"key": "remind", "name": "提醒/通知", "desc": "本地通知、提醒调度、角标调度",
     "keywords": ["提醒", "通知", "闹钟", "调度", "remind", "notification", "alert",
                  "触发时间"]},
]


def _load_faces():
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(here, "shared", "faces.json")
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        faces = data.get("faces") or []
        if len(faces) >= 6 and all("key" in f and "keywords" in f for f in faces):
            return [dict(f) for f in faces]
        raise ValueError("faces.json 结构不完整（需要 6 个含 key/keywords 的项）")
    except Exception as exc:
        sys.stderr.write(
            "[warn] 未能读取 shared/faces.json（%s），改用内置六面定义；"
            "如两者已漂移请以 shared/faces.json 为准\n" % exc)
        return [dict(f) for f in _FACE_FALLBACK]


DEFAULT_FACES = _load_faces()


# 四态
STATUS_WIRED = ("wired", "verified")
STATUS_PENDING = ("pending",)
STATUS_NA = ("na",)
STATUS_ALL = STATUS_WIRED + STATUS_PENDING + STATUS_NA

# 矩阵图例（Markdown 与终端共用）
LEGEND = {
    "wired": "●",      # wired / verified
    "pending": "◐",    # 有条目但未接
    "na": "×",         # 确认不适用
    "none": "·",       # 无条目
}
LEGEND_TEXT = "● 已 wire（含已验）／◐ 待接（pending）／× 确认不适用（na）／· 无条目"


# --------------------------------------------------------------------------
# 可 import 的公共 API
# --------------------------------------------------------------------------

def load_faces(config_path=None):
    """返回六面定义。config_path 可覆盖/扩展关键词表（JSON 数组）。"""
    faces = [dict(f) for f in DEFAULT_FACES]
    if not config_path:
        return faces
    data = rc.read_json(config_path)
    # 两种写法都收：
    #   1) 数组           [{"key":...}, ...]                  （局部覆盖，最省事）
    #   2) {"faces":[...]} 对象（**就是 shared/faces.json 本身的形态**）
    # 早期只收数组，导致 `--config shared/faces.json` 直接报错——
    # 拿 SSOT 文件喂给工具居然不认，是自相矛盾的。
    if isinstance(data, dict):
        data = data.get("faces")
    if not isinstance(data, list):
        raise rc.ToolError(
            "配置文件读不出六面列表：%s" % config_path,
            "两种写法都可以：数组 [{\"key\":...,\"name\":...,\"keywords\":[...]}]，"
            "或 {\"faces\":[...]} 对象（shared/faces.json 就是后者）")
    by_key = {f["key"]: f for f in faces}
    for item in data:
        key = str(item.get("key", "")).strip()
        if not key:
            continue
        if key in by_key:
            by_key[key].update({k: v for k, v in item.items() if k != "key"})
        else:
            faces.append({"key": key, "name": item.get("name", key),
                          "desc": item.get("desc", ""),
                          "keywords": item.get("keywords", [])})
    return faces


def classify(control, faces=None):
    """把 affected_control 归类到六面。返回匹配到的 face key 列表。

    显式 `#面名` / `#key` 优先（用于关键词不匹配时强制归类）；
    其次按关键词子串匹配（大小写不敏感）。
    """
    faces = faces or DEFAULT_FACES
    text = (control or "").lower()
    hits = []
    for f in faces:
        if ("#" + f["name"]).lower() in text or ("#" + f["key"]) in text:
            hits.append(f["key"])
    if hits:
        return hits
    for f in faces:
        for kw in f.get("keywords", []):
            if kw.lower() in text:
                hits.append(f["key"])
                break
    return hits


def load_tables(project):
    """读三张表。缺文件抛 ToolError（带下一步动作）。"""
    schema = rc.load_schema(project)
    issues = []
    tables = {}
    for name, rel in (("features", FEATURES_REL), ("linkage", LINKAGE_REL),
                      ("screens", SCREENS_REL)):
        path = os.path.join(project, rel)
        if not os.path.isfile(path):
            hint = {"features": "先跑 S1 产出 features.csv",
                    "linkage": "跑 S2，用本工具检查六面；linkage.csv 是防「页面有不联动」的核心表",
                    "screens": "先跑 S1 产出 screens.csv"}[name]
            raise rc.ToolError("缺 %s" % rel, hint)
        rows, iss = rc.read_csv_table(path, schema.columns[name])
        issues.extend(iss)
        tables[name] = rows
    hard = [i for i in issues if i["level"] == "ERROR"]
    if hard:
        raise rc.ToolError("CSV 表头/列有问题：%s" % "；".join(i["message"] for i in hard),
                           "列名与顺序照 templates/blueprint/SCHEMAS.md")
    return tables, issues


def face_counts(feature_state):
    """单个功能的四态计数。feature_state = analyse() 里 musts[i]['faces']。"""
    wired = pending = na = none = 0
    for key, st in feature_state.items():
        if not st.get("has_link"):
            none += 1
        elif st.get("status_class") == "na":
            na += 1
        elif st.get("status_class") == "wired":
            wired += 1
        else:
            pending += 1
    return {"wired": wired, "pending": pending, "na": na, "no_entry": none,
            "considered": wired + pending + na}


def _status_class(statuses):
    """一组条目（同一面可能多行）→ 归类。

    优先级：有任一 wired/verified 就算 wired（这一面确实接了）；
    否则有 pending 算 pending；否则全是 na 才算 na。
    混合（wired + na）按 wired 算，但记 note。
    """
    ss = set(statuses)
    if ss & set(STATUS_WIRED):
        return "wired"
    if ss & set(STATUS_PENDING):
        return "pending"
    if ss and ss <= set(STATUS_NA):
        return "na"
    return "pending"


def analyse(tables, faces=None):
    """完整分析。返回 dict（musts / others / per_face / problems / unclassified ...）。

    gate 只需看 `counts` 与 `musts[*]['faces']`；逐行明细在 `link_rows`。
    """
    faces = faces or DEFAULT_FACES
    features = {}
    for r in tables["features"]:
        fid = rc.cell(r, "feature_id")
        if not fid:
            continue
        features[fid] = {
            "feature_id": fid,
            "feature": rc.cell(r, "feature"),
            "area": rc.cell(r, "area"),
            "priority": rc.cell(r, "priority").lower(),
            "scope": rc.cell(r, "scope").lower(),
            "progress": rc.cell(r, "progress").lower(),
            "line": r["line"],
        }

    def is_must(f):
        return f["priority"] in ("must", "p0") and f["scope"] in ("in", "")

    per_face = {f["key"]: {} for f in faces}      # face -> {fid: [links]}
    per_feature = {}                              # fid -> {face: [links]}
    unclassified = []
    problems = []
    unknown_sources = {}
    link_rows = []

    for r in tables["linkage"]:
        lid = rc.cell(r, "link_id")
        src = rc.cell(r, "source_id")
        ctl = rc.cell(r, "affected_control")
        status = rc.cell(r, "status").lower()
        where = "linkage.csv:%s" % r["line"]
        rec = {
            "link_id": lid, "source_id": src, "event": rc.cell(r, "event"),
            "affected_screen": rc.cell(r, "affected_screen"),
            "affected_control": ctl, "data": rc.cell(r, "data"),
            "refresh_timing": rc.cell(r, "refresh_timing"),
            "state_handling": rc.cell(r, "state_handling"),
            "test_ref": rc.cell(r, "test_ref"), "status": status, "line": r["line"],
        }

        # ---- 条目自身完整性 ----
        if status not in STATUS_ALL:
            problems.append({
                "code": "LINK-BAD-STATUS", "level": "ERROR", "where": where,
                "message": "%s status='%s' 不是 pending/wired/verified/na"
                           % (lid or "行", status or "(空)"),
                "fix": "按 SCHEMAS §5 四值填：pending / wired / verified / na"})
        if rc.is_blank(rec["refresh_timing"]):
            problems.append({
                "code": "LINK-NO-TIMING", "level": "ERROR", "where": where,
                "message": "%s 缺刷新时点" % (lid or "行"),
                "fix": "写'写入事务提交成功 → 同步刷新'这种可判定时点；na 行写'不适用'"})
        if rc.is_blank(rec["test_ref"]):
            problems.append({
                "code": "LINK-NO-TEST", "level": "ERROR", "where": where,
                "message": "%s 缺测试号" % (lid or "行"),
                "fix": "填 T-\\d{3}；na 行可以填 '-'（不适用无需测试）"})
        elif not rc.is_not_applicable(rec["test_ref"]) and not rc.TEST_REF_RE.search(rec["test_ref"]):
            problems.append({
                "code": "LINK-TEST-FORMAT", "level": "ERROR", "where": where,
                "message": "%s test_ref='%s' 不是 T-\\d+ 形式" % (lid or "行", rec["test_ref"]),
                "fix": "写成 T-103；na 行可以填 '-'"})

        # ---- na 的纪律：必须真想过，理由写进 state_handling ----
        if status in STATUS_NA:
            reason = rec["state_handling"]
            if rc.is_blank(reason) or "不适用" not in reason:
                problems.append({
                    "code": "LINK-NA-NO-REASON", "level": "ERROR", "where": where,
                    "message": "%s 标了 na 但 state_handling 没写「不适用：<理由>」（现在：%s）"
                               % (lid or "行", reason or "(空)"),
                    "fix": "写清为什么这一面不受影响，例：'不适用：成功页无列表，无角标'。"
                           "想不出理由就说明它不是 na，是漏了"})
            if "不适用" not in (ctl or ""):
                problems.append({
                    "code": "LINK-NA-CONTROL", "level": "WARN", "where": where,
                    "message": "%s na 行的 affected_control 建议写「不适用：…」（现在：%s）"
                               % (lid or "行", ctl or "(空)"),
                    "fix": "改成 '不适用：<面名> 无此控件'，避免被当成真实控件"})

        faces_hit = classify(ctl, faces)
        rec["faces"] = faces_hit
        link_rows.append(rec)

        if not faces_hit:
            unclassified.append({"link_id": lid, "affected_control": ctl,
                                 "line": r["line"], "source_id": src,
                                 "status": status,
                                 "advice": "在 affected_control 末尾加 `#主列表` 这类标记强制归类；"
                                           "注意：未归类的行不计入任何一面，"
                                           "会让对应面被算成「无条目」"})
        if rc.is_filled(src) and src.startswith("F-") and src not in features:
            unknown_sources.setdefault(src, []).append(where)
        for fk in faces_hit:
            per_face[fk].setdefault(src, []).append(rec)
            per_feature.setdefault(src, {}).setdefault(fk, []).append(rec)

    # ---- 每个 must 功能：六面四态 ----
    musts = []
    for fid, f in sorted(features.items()):
        if not is_must(f):
            continue
        faces_state = {}
        for face in faces:
            links = per_feature.get(fid, {}).get(face["key"], [])
            cls = _status_class([l["status"] for l in links]) if links else "none"
            verified = bool(links) and all(l["status"] == "verified" for l in links)
            faces_state[face["key"]] = {
                "name": face["name"],
                "has_link": bool(links),
                "status_class": cls,                     # wired / pending / na / none
                "wired": cls == "wired",
                "pending": cls == "pending",
                "na": cls == "na",
                "verified": verified,
                "links": [l["link_id"] for l in links],
                "statuses": sorted({l["status"] or "(空)" for l in links}),
            }
        cnt = face_counts(faces_state)
        musts.append({
            "feature_id": fid, "feature": f["feature"], "area": f["area"],
            "progress": f["progress"], "line": f["line"],
            "faces": faces_state,
            "counts": cnt,
            "faces_covered": cnt["considered"],
            "faces_wired": cnt["wired"],
            "faces_pending": cnt["pending"],
            "faces_na": cnt["na"],
            "faces_no_entry": cnt["no_entry"],
            "unwired_faces": [v["name"] for k, v in faces_state.items()
                              if v["status_class"] in ("none", "pending")],
            "missing_faces": [v["name"] for k, v in faces_state.items()
                              if v["status_class"] == "none"],
            # 判定（口径见下）：
            #   zero_faces        六面无任何条目 → 完全没做过联动分析
            #   all_na            六面全 na       → 等同于没做（防滥用 na）
            #   suspicious_single 恰好 1 面 wire、其余 5 面连条目都没有 → 多半没想透
            #                     （其余面有 pending/na 说明至少看过，不算）
            #   no_wired          有登记但一面都没接上（pending/na 占满）→ 进度问题，非漏项
            "zero_faces": cnt["no_entry"] == len(faces),
            "all_na": cnt["na"] == len(faces),
            "suspicious_single": (cnt["wired"] == 1
                                  and cnt["no_entry"] == len(faces) - 1),
            "no_wired": (cnt["wired"] == 0
                         and cnt["no_entry"] != len(faces)
                         and cnt["na"] != len(faces)),
        })

    others = []
    for fid, f in sorted(features.items()):
        if is_must(f):
            continue
        hit = per_feature.get(fid, {})
        if hit:
            others.append({"feature_id": fid, "feature": f["feature"],
                           "priority": f["priority"],
                           "faces": [face_name(faces, k) for k in hit]})

    # ---- 汇总四态（feature × face 全量口径）----
    totals = {"wired": 0, "pending": 0, "na": 0, "no_entry": 0, "considered": 0}
    for m in musts:
        for k in totals:
            totals[k] += m["counts"][k]

    return {
        "musts": musts,
        "others": others,
        "per_face": {k: sorted(v.keys()) for k, v in per_face.items()},
        "unclassified": unclassified,
        "problems": problems,
        "unknown_sources": unknown_sources,
        "link_rows": link_rows,
        "totals": totals,
        "face_total_slots": len(musts) * len(faces),
    }


def face_name(faces, key):
    for f in faces:
        if f["key"] == key:
            return f["name"]
    return key


def summarise(result):
    """给门禁/终端用的四态摘要。"""
    musts = result["musts"]
    return {
        "must_features": len(musts),
        "face_slots": result["face_total_slots"],
        "wired": result["totals"]["wired"],
        "pending": result["totals"]["pending"],
        "na": result["totals"]["na"],
        "no_entry": result["totals"]["no_entry"],
        "considered": result["totals"]["considered"],
        # 兼容旧字段：unwired = 没接上的（pending + no_entry），na 不算缺
        "unwired_faces": result["totals"]["pending"] + result["totals"]["no_entry"],
        "zero_face_features": [m["feature_id"] for m in musts if m["zero_faces"]],
        "all_na_features": [m["feature_id"] for m in musts if m["all_na"]],
        "single_face_features": [m["feature_id"] for m in musts if m["suspicious_single"]],
        "no_wired_features": [m["feature_id"] for m in musts if m["no_wired"]],
        "unclassified": len(result["unclassified"]),
        "link_problems": len(result["problems"]),
        "unknown_sources": len(result["unknown_sources"]),
    }


# --------------------------------------------------------------------------
# 渲染
# --------------------------------------------------------------------------

def render_markdown(result, faces, project):
    out = []
    w = out.append
    s = summarise(result)
    w("# 联动矩阵（功能 × 六面）")
    w("")
    w("> 由 `tools/linkage_matrix.py` 生成 · 项目 `%s` · %s" % (project, rc.now_iso()))
    w("> 图例：%s" % LEGEND_TEXT)
    w("> 六面：%s" % " / ".join(f["name"] for f in faces))
    w("> 口径：**缺面数 = 无条目数**（不含 na，也不含 pending）；na 表示确认不适用，需在 "
      "`state_handling` 写「不适用：<理由>」")
    w("")
    w("**must 功能 %d 个 × 六面 = %d 格：已 wire %d ／ 待接 %d ／ 确认不适用 %d ／ "
      "**无条目 %d**（= 缺面数）。**"
      % (s["must_features"], s["face_slots"], s["wired"], s["pending"], s["na"],
         s["no_entry"]))
    if s["all_na_features"]:
        w("")
        w("⛔ **%d 个功能六面全 na**（等同于没做联动分析）：%s"
          % (len(s["all_na_features"]), "、".join("`%s`" % x for x in s["all_na_features"])))
    if s["zero_face_features"]:
        w("")
        w("⛔ **%d 个功能六面无任何条目**（完全没做过联动分析）：%s"
          % (len(s["zero_face_features"]),
             "、".join("`%s`" % x for x in s["zero_face_features"])))
    w("")

    # ---- 矩阵 ----
    w("## 矩阵")
    w("")
    head = ["功能 (ID)", "名称"] + [f["name"] for f in faces] + \
           ["已 wire", "待接", "不适用", "无条目"]
    w("| " + " | ".join(head) + " |")
    w("|" + "|".join(["---"] * len(head)) + "|")
    for m in result["musts"]:
        cells = []
        for f in faces:
            st = m["faces"][f["key"]]
            cls = st["status_class"]
            mark = LEGEND["wired"] if cls == "wired" else LEGEND.get(cls, LEGEND["none"])
            if cls == "wired" and st["verified"]:
                mark = "● 已验"
            cells.append(mark)
        c = m["counts"]
        w("| `%s` | %s | %s | %d | %d | %d | **%d** |"
          % (m["feature_id"], (m["feature"] or "")[:24], " | ".join(cells),
             c["wired"], c["pending"], c["na"], c["no_entry"]))
    if not result["musts"]:
        w("| （没有 must 功能） | | %s | 0 | 0 | 0 | 0 |" % " | ".join(["·"] * len(faces)))
    w("")

    # ---- 最严：完全没做过 / 六面全 na ----
    zero = [m for m in result["musts"] if m["zero_faces"]]
    if zero:
        w("## ⛔ 完全没做过联动分析（六面无任何条目）")
        w("")
        w("这些功能即使做出来也只是个壳。至少要问一遍：改完之后六面哪些会变？")
        w("")
        for m in zero:
            w("- `%s` %s —— 六面全空。下一步：在 `linkage.csv` 为它增行，"
              "确实不受影响的面上标 `status=na` 并写「不适用：<理由>」"
              % (m["feature_id"], m["feature"]))
        w("")

    allna = [m for m in result["musts"] if m["all_na"]]
    if allna:
        w("## ⛔ 六面全 na（比漏写更可疑：等于声明这个功能不影响任何地方）")
        w("")
        w("**na 是「想过之后确认不影响」，不是「懒得想」的快捷方式。** 六面全 na 的功能，"
          "请逐面复核理由；真有 5 面以上不受影响，说明这个功能可能不该是 must。")
        w("")
        for m in allna:
            w("- `%s` %s —— 六面全 na。下一步：逐面念一遍 state_handling 里的理由，"
              "站不住脚的面改回 `pending` 并补联动" % (m["feature_id"], m["feature"]))
        w("")

    # ---- 有登记但一面都没接上 ----
    nowired = [m for m in result["musts"] if m["no_wired"]]
    if nowired:
        w("## ⚠ 有登记但一面都没 wire（全部待接或 na）")
        w("")
        w("这不是漏项，是进度问题：边界问过了，但还没有一面真正接上并测过。")
        w("")
        for m in nowired:
            w("- `%s` %s —— 待接 %d ／ 不适用 %d ／ 无条目 %d"
              % (m["feature_id"], m["feature"],
                 m["faces_pending"], m["faces_na"], m["faces_no_entry"]))
        w("")

    # ---- 只有 1 面 wire ----
    single = [m for m in result["musts"] if m["suspicious_single"]]
    if single:
        w("## ⚠ 只有 1 面 wire 的可疑功能（其余五面连条目都没有，多半没想透）")
        w("")
        w("| 功能 | 只连到哪一面 | 其余五面现状 | 建议追问 |")
        w("|---|---|---|---|")
        for m in single:
            only = [f["name"] for f in faces if m["faces"][f["key"]]["status_class"] == "wired"]
            rest = []
            if m["faces_pending"]:
                rest.append("待接 %d" % m["faces_pending"])
            if m["faces_na"]:
                rest.append("na %d" % m["faces_na"])
            if m["faces_no_entry"]:
                rest.append("无条目 %d" % m["faces_no_entry"])
            w("| `%s` %s | %s | %s | 这一面改完，另外五面真的一点都不变？"
              "举例：改日期后角标与日历真的不动？ |"
              % (m["feature_id"], m["feature"], "、".join(only) or "—",
                 "、".join(rest) or "—"))
        w("")

    # ---- 待补清单 ----
    gaps = []
    for m in result["musts"]:
        for f in faces:
            st = m["faces"][f["key"]]
            if st["status_class"] == "wired":
                continue
            gaps.append((m, f, st))
    if gaps:
        w("## 待补清单（可直接派工）")
        w("")
        w("| 功能 | 面 | 现状 | 下一步 |")
        w("|---|---|---|---|")
        for m, f, st in gaps:
            if st["status_class"] == "pending":
                state = "有 LK 但状态为 %s" % "、".join(st["statuses"])
                tr = next((l["test_ref"] for l in result["link_rows"]
                           if l["link_id"] in st["links"] and rc.is_filled(l["test_ref"])), "T-xxx")
                nxt = "把 LK 推到 wired，并在 TEST/results 里有 %s 的 pass" % tr
            elif st["status_class"] == "na":
                state = "确认不适用（na）"
                nxt = "复核理由是否站得住；站得住就保持 na，站不住改回 pending"
            else:
                state = "**无联动条目**"
                nxt = ("在 linkage.csv 增行（source_id=%s，affected_control 写具体控件）；"
                       "确实不受影响就加一行 status=na + 理由" % m["feature_id"])
            w("| `%s` | %s | %s | %s |" % (m["feature_id"], f["name"], state, nxt))
        w("")

    if result["unclassified"]:
        w("## ⚠ 未能归类的联动条目（分类法够不到，建议加 `#面名` 标记）")
        w("")
        w("未归类的行**不计入任何一面**，所以它对应的面会被算成「无条目」。"
          "如果这条确实作用在某一面，请在 `affected_control` 末尾加标记，"
          "例：`底部「继续」按钮 #详情面板`。")
        w("")
        for u in result["unclassified"]:
            w("- `%s` linkage.csv:%s —— `%s`（源 %s，status %s）"
              % (u["link_id"], u["line"], u["affected_control"] or "(空)",
                 u["source_id"] or "(空)", u["status"] or "(空)"))
        w("")

    if result["problems"]:
        w("## 联动条目自身的缺项")
        w("")
        for p in result["problems"]:
            w("- [%s] %s：%s → %s"
              % (p["code"], p["where"], p["message"], p["fix"]))
        w("")

    if result["unknown_sources"]:
        w("## source_id 指向不存在的功能")
        w("")
        for src, wheres in result["unknown_sources"].items():
            w("- `%s`（%s）不在 features.csv" % (src, "、".join(wheres)))
        w("")

    w("## 六面逐面：哪些功能连到了它")
    w("")
    for f in faces:
        fids = result["per_face"].get(f["key"], [])
        w("### %s（%s）" % (f["name"], f["desc"]))
        w("")
        w("连到它的功能：%s"
          % ("、".join("`%s`" % x for x in fids) if fids else "**（一个都没有）**"))
        w("")
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="linkage_matrix.py",
        description="联动矩阵：功能 × 六面（面名与关键词由 shared/faces.json 定义），"
                    "四态统计（wired/pending/na/无条目），标出没做过联动分析与只有 1 面的可疑功能",
        epilog="示例：python3 tools/linkage_matrix.py --project . --md-out REPORT/linkage.md",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", default=".", help="项目根目录（默认当前目录）")
    ap.add_argument("--json", action="store_true", help="输出 JSON（供 G6 门禁用）")
    ap.add_argument("--markdown", action="store_true", help="输出 Markdown（默认亦为 Markdown）")
    ap.add_argument("--md-out", default="", help="把 Markdown 写进文件，如 REPORT/linkage.md")
    ap.add_argument("--config", default="",
                    help="局部覆盖六面关键词：数组或 {\"faces\":[...]} 对象均可"
                         "（默认读 shared/faces.json）")
    ap.add_argument("--strict", action="store_true",
                    help="严格模式：任何 no_entry / 六面全 na / 条目缺项 即退出码 1"
                         "（默认只报不拦）")
    ap.add_argument("--dump-config", action="store_true",
                    help="打印当前六面定义（读自 shared/faces.json）并退出")
    args = ap.parse_args(argv)

    if args.dump_config:
        rc.print_json(DEFAULT_FACES)
        return 0

    try:
        faces = load_faces(args.config)
    except rc.ToolError as exc:
        return rc.die(exc)

    if not os.path.isdir(args.project):
        return rc.die(rc.ToolError("项目目录不存在：%s" % args.project, "确认路径"))
    try:
        tables, csv_issues = load_tables(args.project)
        result = analyse(tables, faces)
    except rc.ToolError as exc:
        return rc.die(exc)

    s = summarise(result)
    hard = s["link_problems"] + s["unknown_sources"]
    payload = {
        "tool": TOOL,
        "project": os.path.abspath(args.project),
        "checked_at": rc.now_iso(),
        "faces": faces,
        "legend": LEGEND,
        "counts": s,
        "musts": result["musts"],
        "unclassified": result["unclassified"],
        "problems": result["problems"],
        "unknown_sources": result["unknown_sources"],
        "per_face": result["per_face"],
        # G6 只需看这两行：missing 口径 = no_entry；clean 不含 pending（pending 是待做不是漏）
        "missing_faces": s["no_entry"],
        # clean = 无漏面（no_entry=0）+ 无「六面全 na」+ 无条目级硬错
        # 未归类（unclassified）不计入 clean：它是分类法局限，工具会提示加 #面名，
        # 但它确实会让对应面算成「无条目」，所以终端仍会醒目提示。
        "clean": (s["no_entry"] == 0 and not s["all_na_features"]
                  and not s["zero_face_features"]
                  and s["link_problems"] == 0 and s["unknown_sources"] == 0),
        "__RESULT__": "linkage must=%d wired=%d pending=%d na=%d no_entry=%d "
                      "zero=%d allna=%d single=%d nowired=%d hard=%d"
                      % (s["must_features"], s["wired"], s["pending"], s["na"],
                         s["no_entry"], len(s["zero_face_features"]),
                         len(s["all_na_features"]), len(s["single_face_features"]),
                         len(s["no_wired_features"]), hard),
    }

    if args.json:
        rc.print_json(payload)
    else:
        print(render_markdown(result, faces, os.path.abspath(args.project)))
        print("")
        print("── 汇总 ──")
        print("  must 功能 %d 个 × 六面 = %d 格" % (s["must_features"], s["face_slots"]))
        print("    已 wire %d ｜ 待接 %d ｜ 确认不适用 %d ｜ 无条目 %d（= 缺面数）"
              % (s["wired"], s["pending"], s["na"], s["no_entry"]))
        print("    完全没做过联动分析 %d 个；六面全 na %d 个；只有 1 面 wire %d 个；"
              "有登记但未 wire %d 个"
              % (len(s["zero_face_features"]), len(s["all_na_features"]),
                 len(s["single_face_features"]), len(s["no_wired_features"])))
        if hard:
            print("  ⚠ 另有 %d 条条目级缺项（缺刷新时点/缺测试号/na 无理由/未归类/source_id 不存在）"
                  % hard)
        if payload["clean"]:
            print("  ✅ 六面都考虑过了。可以交给 G6。")
        else:
            print("  下一步：按「待补清单」逐行补 linkage.csv（不受影响的面用 status=na + 理由），"
                  "再重跑本工具。")
        if csv_issues:
            print("  （另有 %d 条 CSV 提示，跑 blueprint_lint.py 看全量）" % len(csv_issues))

    if args.md_out:
        target = args.md_out if os.path.isabs(args.md_out) else os.path.join(args.project, args.md_out)
        os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
        with open(target, "w", encoding="utf-8") as fh:
            fh.write(render_markdown(result, faces, os.path.abspath(args.project)) + "\n")
        if not args.json:
            print("  Markdown 已写入：%s" % target)

    if args.strict and (not payload["clean"] or s["unclassified"] > 0):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
