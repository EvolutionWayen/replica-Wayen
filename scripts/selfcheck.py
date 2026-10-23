#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""体系一致性自检：检查总纲、阶段卡、模板、门禁、工具之间是否口径一致。

这是给 Lead 用的自检脚本，不是给用户用的。检查项全部可机判。

用法：
  python3 scripts/selfcheck.py
  python3 scripts/selfcheck.py --json
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

OK, WARN, FAIL = "PASS", "WARN", "FAIL"
results = []


def rec(level, code, msg, fix=""):
    results.append({"level": level, "code": code, "message": msg, "fix": fix})


def read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8")
    except Exception:
        return ""


# ---------------------------------------------------------------- 1. 阶段与门禁
def check_stages():
    stages = sorted((ROOT / "stages").glob("S*.md"))
    if len(stages) != 12:
        rec(FAIL, "STAGE-COUNT", "阶段卡不是 12 份（实际 %d）" % len(stages),
            "应覆盖 S0–S11")
    for f in stages:
        m = re.match(r"S(\d+)-", f.name)
        if not m:
            rec(FAIL, "STAGE-NAME", "阶段卡命名不规范：%s" % f.name)
            continue
        idx = int(m.group(1))
        t = read(f)
        need = ["## 一句话", "## 输入", "## 动作序列", "## 细节级产出",
                "## 执行入口", "## 常见翻车点", "## 示例", "## 退出与交接"]
        missing = [s for s in need if s not in t]
        if missing:
            rec(FAIL, "STAGE-SECTIONS", "%s 缺小节：%s" % (f.name, "、".join(missing)))
        g = re.search(r"^## 门禁 G(\d+)", t, re.M)
        if not g:
            rec(FAIL, "STAGE-GATE", "%s 没有「## 门禁 Gn」小节" % f.name)
        elif int(g.group(1)) != idx:
            rec(FAIL, "STAGE-GATE-MISMATCH",
                "%s 的门禁号是 G%s，应为 G%d" % (f.name, g.group(1), idx))


# ---------------------------------------------------------------- 2. 契约 16 节
CONTRACT_SECTIONS = [
    "1 目标与入口", "2 界面与层级", "3 每个菜单选项", "4 显示条件",
    "5 可用与选择条件", "6 筛选条件", "7 业务实现逻辑", "8 具体效果",
    "9 状态变化", "10 数据读取", "11 数据写入", "12 跨页面联动",
    "13 并发与生命周期", "14 撤销与恢复", "15 体验标准", "16 测试与证据",
]


def check_contract_template():
    p = ROOT / "templates/blueprint/contract.template.md"
    t = read(p)
    if not t:
        rec(FAIL, "CONTRACT-TPL-MISSING", "缺 contract.template.md")
        return
    missing = [s for s in CONTRACT_SECTIONS if ("## " + s) not in t]
    if missing:
        rec(FAIL, "CONTRACT-TPL-SECTIONS",
            "contract.template.md 缺 %d 节：%s" % (len(missing), "、".join(missing)))
    else:
        rec(OK, "CONTRACT-TPL-SECTIONS", "契约模板 16 节齐全")


# ---------------------------------------------------------------- 3. SCHEMAS 与门禁/工具的列一致
def schema_columns():
    """从 SCHEMAS.md 解析各表的列名（取表格里 `col` 形式的反引号）。"""
    t = read(ROOT / "templates/blueprint/SCHEMAS.md")
    out = {}
    for m in re.finditer(r"^## \d+\. `([A-Za-z0-9/_.\\-]+\.(?:csv|md))`.*?$(.*?)(?=^## \d+\.|\Z)",
                         t, re.M | re.S):
        fname, block = m.group(1), m.group(2)
        cols = []
        for line in block.splitlines():
            lm = re.match(r"^\|\s*`([a-z_]+)`\s*\|", line)
            if lm:
                cols.append(lm.group(1))
        if cols:
            out[fname] = cols
    return out


def check_schema_sync():
    schema = schema_columns()
    common = read(ROOT / "gates/rules/common.py")
    rc = read(ROOT / "tools/replica_common.py")
    for fname, cols in schema.items():
        base = fname.split("/")[-1]
        key = base.rsplit(".", 1)[0].replace("-", "_")
        # 从 common.py 找对应的 COLUMNS 常量
        m = re.search(r"%s_COLUMNS\s*=\s*\[(.*?)\]" % key.upper(), common, re.S)
        if not m:
            continue
        gate_cols = re.findall(r'"([^"]+)"', m.group(1))
        if gate_cols and gate_cols != cols:
            rec(FAIL, "SCHEMA-GATE-DRIFT",
                "%s：SCHEMAS 定义 %d 列，门禁 common.py 定义 %d 列且不一致"
                % (base, len(cols), len(gate_cols)),
                "以 SCHEMAS.md 为准，同步 gates/rules/common.py")
        # 工具
        m2 = re.search(r'"%s"\s*:\s*\[(.*?)\]' % re.escape(key), rc, re.S)
        if m2:
            tool_cols = re.findall(r'"([^"]+)"', m2.group(1))
            if tool_cols and tool_cols != cols:
                rec(FAIL, "SCHEMA-TOOL-DRIFT",
                    "%s：SCHEMAS %d 列 vs tools/replica_common.py %d 列不一致"
                    % (base, len(cols), len(tool_cols)),
                    "以 SCHEMAS.md 为准，同步 tools/replica_common.py")


# ---------------------------------------------------------------- 4. 红线编号
def check_redlines():
    total = read(ROOT / "00-体系总纲.md")
    nums = set(int(m) for m in re.findall(r"^\| R(\d+) \|", total, re.M))
    if len(nums) != 20:
        rec(FAIL, "REDLINE-COUNT",
            "总纲红线表不是 R1–R20（实际 %d 条：%s）" % (len(nums), sorted(nums)))
    else:
        rec(OK, "REDLINE-COUNT", "总纲红线 R1–R20 齐全")
    tpl = read(ROOT / "templates/engineering/REDLINES.template.md")
    if tpl:
        miss = [f"R{n}" for n in sorted(nums) if f"R{n}" not in tpl]
        if miss:
            rec(FAIL, "REDLINE-TPL-DRIFT",
                "REDLINES.template.md 缺 %d 条：%s" % (len(miss), "、".join(miss[:6])))
        else:
            rec(OK, "REDLINE-TPL-DRIFT", "REDLINES 模板覆盖 R1–R20")


# ---------------------------------------------------------------- 5. 并行编号残留
def check_no_parallel_numbering():
    """v2 不允许 C1/AUD-01/R1 之外的并行编号体系。"""
    targets = []
    for d in ("stages", "templates/blueprint", "templates/engineering", "gates", "tools", "skills"):
        dd = ROOT / d
        if dd.is_dir():
            targets += [p for p in dd.rglob("*") if p.suffix in (".md", ".py", ".csv", ".yml")]
    bad = []
    for p in targets:
        t = read(p)
        for m in re.finditer(r"\bAUD-\d{2}\b", t):
            # 允许在"引用历史编号"的语境里出现，但要带 v1 标记
            if "v1" not in t[max(0, m.start() - 200):m.start() + 200]:
                bad.append("%s: %s" % (p.relative_to(ROOT), m.group(0)))
                break
    if bad:
        rec(WARN, "PARALLEL-NUMBERING",
            "仍出现旧编号 AUD-xx（%d 处）：%s" % (len(bad), "；".join(bad[:3])),
            "v2 只认 R1–R20 与 ID 规范；旧编号仅在 v1-archive/ 里出现")
    else:
        rec(OK, "PARALLEL-NUMBERING", "无并行编号残留")


# ---------------------------------------------------------------- 6. 门禁自测
def check_gate_tests():
    tdir = ROOT / "gates/tests"
    if not tdir.is_dir() or not list(tdir.glob("test_*.py")):
        rec(FAIL, "GATE-TESTS", "gates/tests 缺自测")
        return
    r = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "gates/tests"],
                       cwd=str(ROOT), capture_output=True, text=True)
    tail = r.stderr.strip().splitlines()[-3:]
    if r.returncode == 0:
        rec(OK, "GATE-TESTS", "门禁自测全绿（%s）" % " / ".join(tail))
    else:
        rec(FAIL, "GATE-TESTS", "门禁自测未通过：%s" % " / ".join(tail),
            "python3 -m unittest discover -s gates/tests")


# ---------------------------------------------------------------- 7. 工具自测
def check_tool_tests():
    tdir = ROOT / "tools/tests"
    if not tdir.is_dir() or not list(tdir.glob("test_*.py")):
        rec(WARN, "TOOL-TESTS", "tools/tests 缺自测")
        return
    r = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tools/tests"],
                       cwd=str(ROOT), capture_output=True, text=True)
    tail = r.stderr.strip().splitlines()[-3:]
    if r.returncode == 0:
        rec(OK, "TOOL-TESTS", "工具自测全绿（%s）" % " / ".join(tail))
    else:
        rec(FAIL, "TOOL-TESTS", "工具自测未通过：%s" % " / ".join(tail))


# ---------------------------------------------------------------- 8. 绝对路径
def check_no_abs_paths():
    hits = []
    for d in ("stages", "templates", "gates", "tools", "skills", "scripts",
              "examples", "case-todo"):
        dd = ROOT / d
        if not dd.is_dir():
            continue
        for p in dd.rglob("*"):
            if p.suffix not in (".md", ".py", ".csv", ".yml", ".sh") or "__pycache__" in str(p):
                continue
            for i, line in enumerate(read(p).splitlines(), 1):
                if "/Users/" not in line:
                    continue
                # 排除"检测绝对路径"的代码本身（自检/测试里会故意写这个字面量）
                if any(k in line for k in ('"/Users/"', "'/Users/'", "assertNotIn",
                                           "in line", "bad in (", "for bad in")):
                    continue
                hits.append("%s:%d" % (p.relative_to(ROOT), i))
    if hits:
        rec(WARN, "ABS-PATH", "存在绝对路径 %d 处：%s" % (len(hits), "、".join(hits[:5])),
            "改成相对路径，整个目录要能搬走")
    else:
        rec(OK, "ABS-PATH", "无绝对路径残留")


# ---------------------------------------------------------------- 9. 示例项目可解析
def check_examples():
    ex = ROOT / "examples/scheduling-clone/BLUEPRINT"
    if not ex.is_dir():
        rec(WARN, "EXAMPLES", "examples/scheduling-clone 不存在")
        return
    for name, keycols in (("features.csv", 11), ("menus.csv", 15), ("screens.csv", 14),
                          ("linkage.csv", 10), ("unknowns.csv", 9)):
        p = ex / name
        if not p.is_file():
            rec(FAIL, "EXAMPLE-FILE", "示例缺 %s" % name)
            continue
        try:
            rows = list(csv.DictReader(open(p, encoding="utf-8")))
        except Exception as e:
            rec(FAIL, "EXAMPLE-CSV", "示例 %s 解析失败：%s" % (name, e))
            continue
        if len(rows[0]) != keycols:
            rec(FAIL, "EXAMPLE-COLS", "示例 %s 是 %d 列，应为 %d" % (name, len(rows[0]), keycols))
        if any(None in r for r in rows):
            rec(FAIL, "EXAMPLE-CSV-WIDTH", "示例 %s 有列数不等的行" % name)
    # 契约
    cdir = ex / "contracts"
    if cdir.is_dir():
        for c in cdir.glob("C-*.md"):
            t = read(c)
            miss = [s for s in CONTRACT_SECTIONS if ("## " + s) not in t]
            if miss:
                rec(FAIL, "EXAMPLE-CONTRACT", "%s 缺 %d 节" % (c.name, len(miss)))
    rec(OK, "EXAMPLES", "示例项目结构可解析")


# ---------------------------------------------------------------- 10. 关键文档存在
def check_key_files():
    need = [
        "00-体系总纲.md", "README.md", "中途接入.md", "产品官审查手册.md",
        "templates/blueprint/SCHEMAS.md", "templates/blueprint/contract.template.md",
        "gates/run.py", "gates/README.md", "tools/README.md", "scripts/README.md",
        "skills/replica-os/SKILL.md", "skills/replica-blueprint/SKILL.md",
        "skills/replica-local-source/SKILL.md", "case-todo/README.md",
        "examples/README.md",
    ]
    missing = [n for n in need if not (ROOT / n).exists()]
    if missing:
        rec(FAIL, "KEY-FILES", "缺 %d 个关键文件：%s" % (len(missing), "、".join(missing)))
    else:
        rec(OK, "KEY-FILES", "%d 个关键文件齐全" % len(need))


# ---------------------------------------------------------------- 11. 技能 frontmatter
def check_skills():
    for s in (ROOT / "skills").glob("*/SKILL.md"):
        t = read(s)
        if not t.startswith("---"):
            rec(FAIL, "SKILL-FM", "%s 缺 frontmatter" % s.parent.name)
            continue
        fm = t.split("---", 2)[1]
        if "name:" not in fm or "description:" not in fm:
            rec(FAIL, "SKILL-FM", "%s 的 frontmatter 缺 name 或 description" % s.parent.name)


# ---------------------------------------------------------------- 12. 六面定义单一事实来源
def check_faces_single_source():
    """六面关键词只许有一份权威定义（shared/faces.json），gates 与 tools 都读它。"""
    shared = ROOT / "shared/faces.json"
    if not shared.is_file():
        rec(FAIL, "FACES-SSOT", "shared/faces.json 不存在（六面定义的唯一权威）",
            "从 gates/rules/common.py 的 _FACE_FALLBACK 导出到 shared/faces.json")
        return
    try:
        data = json.loads(shared.read_text(encoding="utf-8"))
        faces = data.get("faces") or []
    except Exception as e:
        rec(FAIL, "FACES-SSOT", "shared/faces.json 解析失败：%s" % e)
        return
    if len(faces) != 6:
        rec(FAIL, "FACES-SSOT", "shared/faces.json 应是 6 面，实际 %d 面" % len(faces))
        return
    need = {"key", "name", "keywords"}
    bad = [f.get("key") for f in faces if not need <= set(f.keys())]
    if bad:
        rec(FAIL, "FACES-SSOT", "六面定义缺字段：%s" % bad)
        return
    # 两侧都必须从 JSON 读，且内容一致
    try:
        sys.path.insert(0, str(ROOT))
        sys.path.insert(0, str(ROOT / "tools"))
        from gates.rules import common as C
        import linkage_matrix as LM
        g = [(f["key"], f["name"], tuple(f["keywords"])) for f in C.SIX_FACES]
        t = [(f["key"], f["name"], tuple(f["keywords"])) for f in LM.DEFAULT_FACES]
        ref = [(f["key"], f["name"], tuple(f["keywords"])) for f in faces]
        if not (g == t == ref):
            rec(FAIL, "FACES-SSOT", "门禁/工具/JSON 三者的六面定义不一致",
                "改关键词只改 shared/faces.json；两侧会自动跟随")
        else:
            rec(OK, "FACES-SSOT", "六面定义单一事实来源（gates/tools/JSON 三者一致）")
        # 兜底必须"只有名称、没有关键词"——否则 JSON 丢失时会用过期词静默归类
        fb = getattr(C, "_FACE_FALLBACK", None)
        if fb is not None:
            with_kw = [f.get("key") for f in fb if f.get("keywords")]
            if with_kw:
                rec(FAIL, "FACES-FALLBACK",
                    "门禁侧 _FACE_FALLBACK 带了关键词（%s）：JSON 丢失时会用过期词静默归类"
                    % "、".join(str(k) for k in with_kw),
                    "兜底只保留 name/desc，keywords 置空——让归类明显失效，而不是悄悄判错")
            else:
                rec(OK, "FACES-FALLBACK", "兜底定义只有名称、无关键词（失效可见）")
    except Exception as e:
        rec(WARN, "FACES-SSOT", "无法加载两侧模块对比六面定义：%s" % e)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    for fn in (check_key_files, check_stages, check_contract_template, check_schema_sync,
               check_redlines, check_no_parallel_numbering, check_examples,
               check_skills, check_no_abs_paths, check_faces_single_source,
               check_gate_tests, check_tool_tests):
        try:
            fn()
        except Exception as e:  # 自检脚本本身不能崩
            rec(FAIL, "SELFCRASH", "%s 抛异常：%s" % (fn.__name__, e))

    n_fail = sum(1 for r in results if r["level"] == FAIL)
    n_warn = sum(1 for r in results if r["level"] == WARN)
    n_ok = sum(1 for r in results if r["level"] == OK)

    if args.json:
        print(json.dumps({"summary": {"pass": n_ok, "warn": n_warn, "fail": n_fail},
                          "results": results}, ensure_ascii=False, indent=2))
    else:
        for r in results:
            mark = {OK: "✅", WARN: "⚠️ ", FAIL: "❌"}[r["level"]]
            print("%s %-24s %s" % (mark, r["code"], r["message"]))
            if r["fix"]:
                print("      → %s" % r["fix"])
        print()
        print("合计：PASS %d / WARN %d / FAIL %d" % (n_ok, n_warn, n_fail))
        print("__RESULT__ pass=%d warn=%d fail=%d" % (n_ok, n_warn, n_fail))
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
