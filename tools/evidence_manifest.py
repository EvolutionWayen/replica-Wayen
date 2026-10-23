#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""evidence_manifest.py —— 证据清单（把「我截过图」变成「可核对的证据台账」）

扫 evidence/ 与 screens/，生成/增量更新 `evidence/MANIFEST.csv`：

    相对路径 | SHA-256 前16 | 字节数 | mtime(ISO) | 采集方式 | 对应屏幕S-xx | 首次登记 | 状态

三条硬规则（这就是它存在的理由）：
  1. **只加不改**：已登记的文件永远不会被重写（"重跑只追加新文件"）。
  2. **同名文件内容变了 = WARN，不覆盖**：说明原版行为改了或截图被替换，
     旧结论需要复核——这正是 00 §10-18「蓝图冻结了还在改」的同族问题。
  3. **消失的文件标 MISSING，不删行**：证据被删了要留痕，否则无法判断
     "这条结论当初有没有证据"。

`采集方式` 与 `对应屏幕` 两列由人填（工具只留空并给提示），因为只有你知道
这张图是菜单截图、数据库导出还是接口记录。

用法：
    python3 tools/evidence_manifest.py --project .                 # 增量更新并打印汇总
    python3 tools/evidence_manifest.py --project . --json
    python3 tools/evidence_manifest.py --project . --check         # 门禁：有 WARN/MISSING 退出码 1
    python3 tools/evidence_manifest.py --project . --dirs evidence screens --init
    python3 tools/evidence_manifest.py --project . --verify        # 只校验已登记项，不扫描新文件

退出码：0 干净 / 1 有 WARN 或 MISSING（--check 时）或校验失败 / 2 输入错误
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import replica_common as rc  # noqa: E402

TOOL = "evidence_manifest"
MANIFEST_REL = os.path.join("evidence", "MANIFEST.csv")

COLUMNS = ["path", "sha256_16", "bytes", "mtime_iso", "capture_method",
           "screen_id", "first_seen", "status", "sha256_full", "notes"]

DEFAULT_DIRS = ["evidence", "screens"]

SKIP_DIR_NAMES = {".git", "__pycache__", ".DS_Store", "node_modules", "_archive"}
SKIP_FILE_NAMES = {"MANIFEST.csv", ".DS_Store", ".gitkeep", "README.md"}


def discover(project, dirs):
    """返回 [(相对路径, 绝对路径)]，跳过清单自身与噪声文件。"""
    out = []
    for d in dirs:
        base = d if os.path.isabs(d) else os.path.join(project, d)
        if not os.path.isdir(base):
            continue
        for root, subdirs, files in os.walk(base):
            subdirs[:] = sorted(s for s in subdirs if s not in SKIP_DIR_NAMES)
            for name in sorted(files):
                if name in SKIP_FILE_NAMES or name.startswith("."):
                    continue
                full = os.path.join(root, name)
                if not os.path.isfile(full):
                    continue
                rel = os.path.relpath(full, project)
                # MANIFEST 自身在任意 evidence 子目录下都跳过
                if rel.replace("\\", "/").endswith("evidence/MANIFEST.csv"):
                    continue
                out.append((rel, full))
    return out


def load_manifest(path):
    """读已有 MANIFEST。返回 (rows, issues)。列名不匹配时报错而不是静默重建。"""
    if not os.path.isfile(path):
        return [], []
    rows, issues = rc.read_csv_table(path, COLUMNS)
    if not rows and os.path.getsize(path) > 0:
        # 有内容但没解析出数据行
        issues.append(rc.csv_issue("WARN", "MANIFEST-UNPARSED", "evidence/MANIFEST.csv",
                                   "MANIFEST.csv 有内容但没解析出数据行",
                                   "检查是否被 Excel 改了编码/加了标题行"))
    return rows, issues


def mtime_iso(full):
    ts = os.path.getmtime(full)
    return datetime.fromtimestamp(ts, tz=timezone.utc).astimezone().isoformat(timespec="seconds")


def ensure_manifest_header(path):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    if not os.path.isfile(path) or os.path.getsize(path) == 0:
        with open(path, "w", newline="", encoding="utf-8") as fh:
            csv.writer(fh).writerow(COLUMNS)


def append_rows(path, rows):
    with open(path, "a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS, extrasaction="ignore")
        for r in rows:
            w.writerow(r)


def rewrite(path, rows):
    tmp = path + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    os.replace(tmp, path)


def update(project, dirs, verify_only=False):
    manifest = os.path.join(project, MANIFEST_REL)
    old_rows, issues = load_manifest(manifest)

    # 已登记（按 path）
    known = {}
    for r in old_rows:
        p = rc.cell(r, "path")
        if p:
            known[p] = r

    found = discover(project, dirs) if not verify_only else []
    found_paths = {rel for rel, _ in found}

    added, changed, missing_now, filled = [], [], [], []
    for rel, full in found:
        digest = rc.sha256_of(full)
        size = os.path.getsize(full)
        prev = known.get(rel)
        if prev is None:
            added.append({
                "path": rel,
                "sha256_16": digest[:16],
                "bytes": size,
                "mtime_iso": mtime_iso(full),
                "capture_method": "",
                "screen_id": "",
                "first_seen": rc.now_iso(),
                "status": "NEW",
                "sha256_full": digest,
                "notes": "",
            })
            continue
        old16 = rc.cell(prev, "sha256_16")
        if old16 and old16 != digest[:16]:
            changed.append({"path": rel, "known": old16, "now": digest[:16],
                            "line": prev.get("line")})
        elif not old16:
            # 早期手工行没哈希：补上（这是唯一允许的"改"，且只补空值）
            filled.append({"path": rel, "digest": digest[:16], "size": size,
                           "mtime": mtime_iso(full), "line": prev.get("line")})

    # 校验已登记项（--verify 或常规重跑都要做）
    if verify_only:
        for rel, full in discover(project, dirs):
            found_paths.add(rel)
    for rel, r in known.items():
        if rel in found_paths:
            continue
        full = os.path.join(project, rel)
        if not os.path.isfile(full):
            # 只要文件不在就算不一致，不论上次是不是已标 MISSING——
            # 否则第二次 --check 会静默变绿（假绿的典型入口，00 §9 R19/R20）。
            prior = rc.cell(r, "status")
            missing_now.append({"path": rel, "line": r.get("line"),
                                "last_seen": rc.cell(r, "mtime_iso"),
                                "already_marked": prior == "MISSING"})

    return {
        "manifest": manifest,
        "known": len(known),
        "known_rows": list(known.values()),
        "found": len(found),
        "added": added,
        "changed": changed,
        "missing": missing_now,
        "filled": filled,
        "issues": issues,
    }


def apply_updates(result, dry_run=False):
    manifest = result["manifest"]
    if dry_run:
        return
    ensure_manifest_header(manifest)
    if result["added"]:
        append_rows(manifest, sorted(result["added"], key=lambda x: x["path"]))
    if result["filled"] or result["missing"]:
        rows, _ = load_manifest(manifest)
        dirty = False
        by_path = {rc.cell(r, "path"): r for r in rows}
        for f in result["filled"]:
            r = by_path.get(f["path"])
            if r is None:
                continue
            r["sha256_16"] = f["digest"]
            r["sha256_full"] = f["digest"]
            r["bytes"] = str(f["size"]) if not rc.cell(r, "bytes") else r["bytes"]
            dirty = True
        for m in result["missing"]:
            r = by_path.get(m["path"])
            if r is None:
                continue
            r["status"] = "MISSING"
            dirty = True
        if dirty:
            rewrite(manifest, rows)


def print_report(project, result, strict, dry_run, out=sys.stdout):
    w = out.write
    w("证据清单（evidence_manifest）· 项目：%s\n" % project)
    w("清单：%s%s\n" % (result["manifest"], "（预演，未写盘）" if dry_run else ""))
    w("已登记 %d 条；本次扫描到 %d 个文件。\n\n" % (result["known"], result["found"]))

    def block(title, items, mark):
        if not items:
            return
        w("%s %s（%d）\n" % (mark, title, len(items)))
        for it in items[:60]:
            w("   %s\n" % it)
        if len(items) > 60:
            w("   … 还有 %d 条\n" % (len(items) - 60))

    block("新增登记",
          ["%s  %s  %s" % (a["path"], a["sha256_16"], rc.human_size(a["bytes"]))
           for a in result["added"]], "＋")
    block("内容变了（同名文件哈希不同，**未覆盖**，请人工复核）",
          ["%s  旧 %s → 新 %s（第 %s 行）" % (c["path"], c["known"], c["now"], c["line"])
           for c in result["changed"]], "⚠")
    block("补全空哈希", ["%s  %s" % (f["path"], f["digest"]) for f in result["filled"]], "✎")
    block("文件消失（保留行，标 MISSING）",
          ["%s（第 %s 行，最后采集 %s）" % (m["path"], m["line"], m["last_seen"])
           for m in result["missing"]], "✗")
    for iss in result["issues"]:
        w("  [%s] %s：%s\n" % (iss["level"], iss["where"], iss["message"]))

    w("\n── 待人工填写 ──\n")
    blank_rows = sum(1 for r in result.get("known_rows", [])
                     if not rc.cell(r, "capture_method") or not rc.cell(r, "screen_id"))
    blank_rows += sum(1 for a in result["added"]
                      if not a.get("capture_method") or not a.get("screen_id"))
    if result["added"] or blank_rows:
        if result["added"]:
            w("  本次新增 %d 行的 `capture_method`（采集方式）与 `screen_id`（对应屏幕）留空。\n"
              % len(result["added"]))
        if blank_rows:
            w("  台账里共 %d 行的这两列还没填全。\n" % blank_rows)
        w("  填法：截图/录屏 → '菜单截图'；DB 导出 → 'sqlite3 只读导出'；接口 → 'mitmproxy HAR'。\n")
        w("  screen_id 填 S-xx；不针对具体屏幕的填 '-'。\n")
    else:
        w("  无（既有行的采集方式与对应屏幕都已填）。\n")

    w("\n── 结论 ──\n")
    problems = len(result["changed"]) + len(result["missing"])
    if problems:
        w("  ⚠ %d 处需要人工判断：内容变了 %d 处、文件消失 %d 处。\n"
          % (problems, len(result["changed"]), len(result["missing"])))
        w("  变了的内容要么是原版升级、要么是截图被替换——两种都要回到 S2 复核受影响的契约。\n")
    else:
        w("  ✅ 已登记项全部与磁盘一致，本次新增 %d 个文件。\n" % len(result["added"]))
    if strict:
        if problems:
            w("  门禁结论：❌ 证据台账不一致（MISSING/CHANGED 必须先处理）。\n")
        else:
            w("  门禁结论：✅ 证据台账一致。\n")


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="evidence_manifest.py",
        description="证据清单：扫 evidence/ screens/ 生成 MANIFEST.csv（SHA-256 前16 + 大小 + mtime），重跑只追加不改",
        epilog=("示例：\n"
                "  python3 tools/evidence_manifest.py --project .\n"
                "  python3 tools/evidence_manifest.py --project . --check\n"
                "  python3 tools/evidence_manifest.py --project . --verify"),
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", default=".", help="项目根目录（默认当前目录）")
    ap.add_argument("--dirs", nargs="*", default=None,
                    help="要扫的目录（相对项目根），默认 evidence screens")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    ap.add_argument("--dry-run", action="store_true", help="只报告不写盘")
    ap.add_argument("--check", action="store_true",
                    help="门禁模式：出现 CHANGED/MISSING 或新增未填列时退出码 1")
    ap.add_argument("--verify", action="store_true",
                    help="只校验已登记项（不登记新文件）")
    ap.add_argument("--init", action="store_true", help="只建表头，不扫描")
    args = ap.parse_args(argv)

    if not os.path.isdir(args.project):
        return rc.die(rc.ToolError("项目目录不存在：%s" % args.project, "确认路径"))

    dirs = args.dirs if args.dirs is not None else DEFAULT_DIRS
    present = [d for d in dirs if os.path.isdir(d if os.path.isabs(d) else os.path.join(args.project, d))]
    if not present:
        return rc.die(rc.ToolError(
            "要扫描的目录一个都不存在：%s" % "、".join(dirs),
            "先建目录并放入证据（截图/DB 导出/接口记录）；"
            "或指定 --dirs 你的实际目录名"))

    manifest = os.path.join(os.path.abspath(args.project), MANIFEST_REL)
    if args.init:
        ensure_manifest_header(manifest)
        print("已建表头：%s" % manifest)
        print("列：%s" % "、".join(COLUMNS))
        return 0

    try:
        result = update(os.path.abspath(args.project), present, verify_only=args.verify)
    except rc.ToolError as exc:
        return rc.die(exc)

    relevant = len(result["added"]) + len(result["changed"]) + len(result["missing"])
    if args.check and relevant:
        print_report(os.path.abspath(args.project), result, args.check, args.dry_run)
        return 1

    apply_updates(result, dry_run=args.dry_run or args.verify)

    if args.json:
        rc.print_json({
            "tool": TOOL,
            "project": os.path.abspath(args.project),
            "checked_at": rc.now_iso(),
            "manifest": result["manifest"],
            "dirs": present,
            "dry_run": args.dry_run,
            "known": result["known"],
            "found": result["found"],
            "added": result["added"],
            "changed": result["changed"],
            "missing": result["missing"],
            "filled": result["filled"],
            "issues": result["issues"],
            "clean": not result["changed"] and not result["missing"],
            "__RESULT__": "manifest known=%d found=%d added=%d changed=%d missing=%d"
                          % (result["known"], result["found"], len(result["added"]),
                             len(result["changed"]), len(result["missing"])),
        })
    else:
        print_report(os.path.abspath(args.project), result, args.check, args.dry_run)

    if args.check and (result["changed"] or result["missing"]):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
