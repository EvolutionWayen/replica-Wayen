#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""门禁自测（unittest，标准库）。

跑法：
    cd <体系根>
    python3 -m unittest discover -s gates/tests -v

覆盖四层：
A. CLI 契约：退出码（0/1/2）、末行 `__RESULT__`、`--json` 结构、单门选择、异常输入不崩。
B. 夹具基线：good-min 全 PASS；四套 broken 各自在**该失败的门**上 FAIL。
C. 规则单元：契约缺节、菜单写「按原版」、linkage pending、哈希不符、缺 manifest 等单点判定。
D. 基础设施：CSV/Markdown/YAML/哈希解析的行���，以及夹具可由 _make.py 确定性重建。

纪律：测试只读夹具；需要改文件的用例先 copytree 到临时目录，绝不就地改。
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
GATES_DIR = HERE.parent
SYSTEM_ROOT = GATES_DIR.parent
FIXTURES = GATES_DIR / "fixtures"
RUN_PY = GATES_DIR / "run.py"

sys.path.insert(0, str(GATES_DIR))
sys.path.insert(0, str(FIXTURES))

from rules import common as C  # noqa: E402
import _make  # noqa: E402

RESULT_RE = re.compile(r"^__RESULT__ pass=(\d+) fail=(\d+) blocked=(\d+) na=(\d+)$")


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------

def run_cli(args, cwd=None):
    """跑 gates/run.py，返回 (exit_code, stdout, stderr, parsed_counts)。"""
    proc = subprocess.run(
        [sys.executable, str(RUN_PY)] + list(args),
        cwd=str(cwd or SYSTEM_ROOT),
        capture_output=True, text=True, timeout=300,
    )
    lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    last = lines[-1] if lines else ""
    m = RESULT_RE.match(last)
    counts = None
    if m:
        counts = {"pass": int(m.group(1)), "fail": int(m.group(2)),
                  "blocked": int(m.group(3)), "na": int(m.group(4))}
    return proc.returncode, proc.stdout, proc.stderr, counts


def run_json(project, stage="all", extra=None):
    args = ["--project", str(project), "--stage", stage, "--json"] + list(extra or [])
    code, out, err, _counts = run_cli(args)
    return code, json.loads(out)


def _make_csv_text(fields, rows):
    """把 dict 行按列顺序写回 CSV（测试里改完行要还原成文件）。"""
    return _make.csv_text(fields, [[r.get(f, "") for f in fields] for r in rows])


def stage_results(payload, stage):
    return [r for r in payload["results"] if r["stage"] == stage]


def failures(payload, stage=None):
    return [r["code"] for r in payload["results"]
            if r["status"] == "FAIL" and (stage is None or r["stage"] == stage)]


def statuses(payload):
    out = {}
    for r in payload["results"]:
        out.setdefault(r["status"], 0)
        out[r["status"]] += 1
    return out


class FixtureCase(unittest.TestCase):
    """基类：保证夹具存在（缺了就现场重建），并提供临时项目副本。"""

    @classmethod
    def setUpClass(cls):
        if not (FIXTURES / "good-min" / ".replica" / "gate.manifest.yml").is_file():
            _make.main(["all"])

    def setUp(self):
        self._tmpdirs = []

    def tearDown(self):
        for d in self._tmpdirs:
            shutil.rmtree(d, ignore_errors=True)

    def copy_fixture(self, name, prefix="gate-test-"):
        """复制夹具到独立临时目录。

        加重试：夹具生成器（_make.py）可能在测试运行期间被重跑，
        源目录会出现"文件正在被替换"的瞬时状态，导致 copytree 失败。
        这是环境竞态，不是被测逻辑的问题，重试即可；连续失败才报错。
        """
        last = None
        for attempt in range(5):
            tmp = tempfile.mkdtemp(prefix=prefix)
            self._tmpdirs.append(tmp)
            dest = Path(tmp) / name
            try:
                shutil.copytree(FIXTURES / name, dest)
                return dest
            except (FileNotFoundError, shutil.Error) as exc:
                last = exc
                shutil.rmtree(tmp, ignore_errors=True)
                self._tmpdirs.pop()
                time.sleep(0.15 * (attempt + 1))
        raise AssertionError(
            "复制夹具 %s 连续 5 次失败（夹具源目录可能正在被重新生成）：%s" % (name, last))

    def new_empty_project(self):
        tmp = tempfile.mkdtemp(prefix="gate-empty-")
        self._tmpdirs.append(tmp)
        return Path(tmp)


# ---------------------------------------------------------------------------
# A. CLI 契约
# ---------------------------------------------------------------------------

class TestCliContract(FixtureCase):

    def test_good_min_exit_0(self):
        code, out, err, counts = run_cli(["--project", str(FIXTURES / "good-min")])
        self.assertEqual(code, 0, "good-min 应退出码 0\nstdout:\n%s\nstderr:\n%s" % (out, err))
        self.assertIsNotNone(counts, "末行必须是 __RESULT__ pass=N fail=M blocked=K na=J")
        self.assertEqual(counts["fail"], 0)
        self.assertEqual(counts["blocked"], 0)
        self.assertGreaterEqual(counts["pass"], 60, "判定项太少，说明规则没跑起来")

    def test_last_line_is_result_even_on_fail(self):
        code, out, _err, counts = run_cli(
            ["--project", str(FIXTURES / "broken-blueprint"), "--stage", "G2"])
        self.assertEqual(code, 1)
        self.assertIsNotNone(counts, "FAIL 时末行也必须是 __RESULT__")
        self.assertGreaterEqual(counts["fail"], 1)

    def test_missing_manifest_exit_2_and_not_crash(self):
        code, out, err, counts = run_cli(["--project", str(FIXTURES / "no-manifest")])
        self.assertEqual(code, 2, "缺 manifest 必须退出码 2（只有 BLOCKED）")
        self.assertNotIn("Traceback", err, "缺 manifest 不许抛异常栈给用户")
        self.assertNotIn("Traceback", out)
        self.assertIsNotNone(counts)
        self.assertEqual(counts["fail"], 0)
        self.assertGreaterEqual(counts["blocked"], 12)
        self.assertIn("new-project.sh", out, "缺 manifest 必须提示怎么补")
        self.assertIn("gate.manifest.yml", out)

    def test_empty_dir_exit_2(self):
        empty = self.new_empty_project()
        code, out, err, counts = run_cli(["--project", str(empty)])
        self.assertEqual(code, 2)
        self.assertNotIn("Traceback", err)
        self.assertIsNotNone(counts)
        self.assertEqual(counts["fail"], 0)

    def test_nonexistent_dir_exit_2(self):
        code, out, _err, counts = run_cli(["--project", "/tmp/definitely-not-here-xyz"])
        self.assertEqual(code, 2)
        self.assertIsNotNone(counts, "目录不存在也要打印 __RESULT__")
        self.assertEqual(counts["blocked"], 1)

    def test_json_shape(self):
        code, payload = run_json(FIXTURES / "good-min")
        self.assertEqual(code, 0)
        for key in ("stages", "summary", "results"):
            self.assertIn(key, payload)
        self.assertEqual(payload["summary"]["fail"], 0)
        self.assertEqual(payload["summary"]["exit_code"], 0)
        self.assertEqual(set(payload["stages"]), {"G%d" % i for i in range(12)})
        for stage, info in payload["stages"].items():
            self.assertIn("summary", info)
            for k in ("pass", "fail", "blocked", "na"):
                self.assertIn(k, info["summary"])
        self.assertIsInstance(payload["results"], list)
        first = payload["results"][0]
        for key in ("stage", "code", "status", "expected", "actual", "evidence", "hint"):
            self.assertIn(key, first)
        self.assertIn(first["status"], ("PASS", "FAIL", "BLOCKED", "NA"))

    def test_json_on_missing_manifest(self):
        code, payload = run_json(FIXTURES / "no-manifest")
        self.assertEqual(code, 2)
        self.assertIn("error", payload)
        self.assertIn("gate.manifest.yml", payload["error"])
        self.assertTrue(payload["results"])
        self.assertTrue(all(r["status"] == "BLOCKED" for r in payload["results"]),
                        "缺 manifest 时每条都必须是 BLOCKED（不许 FAIL 也不许 PASS）")

    def test_single_stage_only_runs_that_stage(self):
        code, payload = run_json(FIXTURES / "good-min", stage="G3")
        self.assertEqual(code, 0)
        self.assertEqual(list(payload["stages"].keys()), ["G3"])
        self.assertTrue(all(r["stage"] == "G3" for r in payload["results"]))

    def test_lowercase_stage_accepted(self):
        code, payload = run_json(FIXTURES / "good-min", stage="g6")
        self.assertEqual(code, 0)
        self.assertEqual(list(payload["stages"].keys()), ["G6"])

    def test_unknown_stage_is_handled(self):
        code, out, _err, counts = run_cli(
            ["--project", str(FIXTURES / "good-min"), "--stage", "G99"])
        self.assertEqual(code, 2)
        self.assertIn("未知阶段", out)
        self.assertIsNotNone(counts)

    def test_human_output_has_all_five_fields(self):
        """人类可读模式每条 FAIL 必须带 期望/实际/证据/修复。"""
        _code, out, _err, _counts = run_cli(
            ["--project", str(FIXTURES / "broken-blueprint"), "--stage", "G2"])
        fail_lines = [ln for ln in out.splitlines() if "[FAIL]" in ln]
        self.assertTrue(fail_lines, "G2 应该有 FAIL 行")
        joined = "\n".join(fail_lines)
        for field in ("期望:", "实际:", "证据:", "修复:"):
            self.assertIn(field, joined, "FAIL 行缺少 %s" % field)

    def test_verbose_expands_pass_lines(self):
        _code, quiet, _e, _c = run_cli(
            ["--project", str(FIXTURES / "good-min"), "--stage", "G0"])
        _code2, loud, _e2, _c2 = run_cli(
            ["--project", str(FIXTURES / "good-min"), "--stage", "G0", "--verbose"])
        self.assertGreater(len(loud), len(quiet), "--verbose 必须输出更多信息")
        self.assertIn("期望:", loud)

    def test_list_flag(self):
        code, out, _err, _counts = run_cli(["--list"])
        self.assertEqual(code, 0)
        for i in range(12):
            self.assertIn("G%d" % i, out)


# ---------------------------------------------------------------------------
# B. 夹具基线
# ---------------------------------------------------------------------------

class TestFixtureBaseline(FixtureCase):

    def test_good_min_all_stages_pass(self):
        code, payload = run_json(FIXTURES / "good-min")
        self.assertEqual(code, 0)
        self.assertEqual(payload["summary"]["fail"], 0,
                         "good-min 必须全 PASS，实际失败：%s" % failures(payload))
        # 12 道门每道都要有判定项
        for i in range(12):
            stage = "G%d" % i
            self.assertTrue(stage_results(payload, stage), "%s 没有任何判定项" % stage)
        # 唯一允许的 NA 是 A 档的 C 档商业门，且必须已在 manifest 登记
        na = [r for r in payload["results"] if r["status"] == "NA"]
        self.assertTrue(na)
        for item in na:
            self.assertEqual(item["code"], "G11.commercial")
            self.assertIn("已批准", item["hint"])

    def test_good_min_has_no_blocked(self):
        _code, payload = run_json(FIXTURES / "good-min")
        self.assertEqual(payload["summary"]["blocked"], 0)

    def test_broken_blueprint_fails_g2(self):
        code, payload = run_json(FIXTURES / "broken-blueprint", stage="G2")
        self.assertEqual(code, 1)
        codes = failures(payload, "G2")
        self.assertIn("G2.contract-sections", codes, "契约缺节必须被 G2 抓到")
        self.assertIn("G2.menu-conditions", codes, "菜单写「按原版」必须被 G2 抓到")

    def test_broken_blueprint_fails_g1_on_missing_unknowns(self):
        code, payload = run_json(FIXTURES / "broken-blueprint", stage="G1")
        self.assertEqual(code, 1)
        self.assertIn("G1.unknowns-file", failures(payload, "G1"))

    def test_broken_linkage_fails_g6_only_for_linkage(self):
        code, payload = run_json(FIXTURES / "broken-linkage", stage="G6")
        self.assertEqual(code, 1)
        codes = failures(payload, "G6")
        self.assertIn("G6.progress-linkage", codes,
                      "progress=yes 但 linkage=pending 必须被 G6 抓到")
        # 同一套夹具的 G3 应当仍 PASS（确保我们验的是 G6 而不是被连带污染）
        code3, payload3 = run_json(FIXTURES / "broken-linkage", stage="G3")
        self.assertEqual(code3, 0, "broken-linkage 的 G3 应保持通过：%s"
                         % failures(payload3, "G3"))

    def test_broken_lock_fails_g3(self):
        code, payload = run_json(FIXTURES / "broken-lock", stage="G3")
        self.assertEqual(code, 1)
        self.assertIn("G3.lock-hashes", failures(payload, "G3"))
        detail = [r for r in payload["results"] if r["code"] == "G3.lock-hashes"][0]
        self.assertIn("实算", detail["actual"], "必须给出实算值而不是只说「不符」")

    def test_out_scope_without_reason_fails_g1(self):
        """把 must 改成 scope=out 且不写理由 → G1 FAIL。

        防的是这条作弊路径：G9 功能分剔除 scope=out 的行，
        所以把 must 悄悄改成 out、重算分数与哈希，就能把分数拉满。
        out 必须是显式决策（notes 写清为什么这一版不做）。
        """
        code, payload = run_json(FIXTURES / "broken-out-scope", stage="G1")
        self.assertEqual(code, 1, "缺理由的 scope=out 必须 FAIL")
        detail = [r for r in payload["results"]
                  if r["code"] == "G1.out-scope-reason" and r["status"] == "FAIL"]
        self.assertTrue(detail, "应有 G1.out-scope-reason FAIL")
        self.assertIn("F-REPEAT-SET", detail[0]["actual"])

    def test_out_scope_with_reason_passes(self):
        """写了实质理由的 scope=out 是合法范围决策，必须放行。"""
        project = self.copy_fixture("broken-out-scope")
        path = project / "BLUEPRINT/features.csv"
        rows, fields = C.read_csv_text(path.read_text(encoding="utf-8"))
        for r in rows:
            if r["feature_id"] == "F-REPEAT-SET":
                r["notes"] = "本版不做重复规则：A 档先做单次任务闭环，重复留到下一版"
        path.write_text(_make.csv_text(fields, [[r[f] for f in fields] for r in rows]),
                        encoding="utf-8")
        code, payload = run_json(project, stage="G1")
        self.assertEqual(code, 0, "有理由的 scope=out 应通过，实际：%s" % failures(payload, "G1"))

    def test_out_scope_placeholder_reason_rejected(self):
        """占位词（无 / 待定 / - / todo）不算理由。"""
        for placeholder in ("无", "待定", "-", "TBD", "todo"):
            project = self.copy_fixture("broken-out-scope")
            path = project / "BLUEPRINT/features.csv"
            rows, fields = C.read_csv_text(path.read_text(encoding="utf-8"))
            for r in rows:
                if r["feature_id"] == "F-REPEAT-SET":
                    r["notes"] = placeholder
            path.write_text(_make.csv_text(fields, [[r[f] for f in fields] for r in rows]),
                            encoding="utf-8")
            code, _payload = run_json(project, stage="G1")
            self.assertEqual(code, 1, "占位词 %r 不能算理由" % placeholder)

    def test_each_broken_fixture_is_focused(self):
        """每套 broken 夹具的意思要清楚：G2/G6/G3 各自只有 1-4 条 FAIL。"""
        expectation = {
            "broken-blueprint": {"G1", "G2", "G3"},
            "broken-linkage": {"G6"},
            # 六面全 na 同时被 G2（蓝图阶段就该拦住）与 G6（联动门）抓到
            "broken-linkage-allna": {"G2", "G6"},
            "broken-menu-order": {"G2"},
            # 清空决策表会连带删掉 U-002 的批准记录 → G3 的 waived-unknowns 也该失败
            # （这是正确因果，不是误伤：豁免的未知失去 D- 记录就不可再豁免）
            "broken-project": {"G0", "G3"},
            # 把 must 功能悄悄改成 scope=out 来拉高 G9 分数 → G1 必须拦。
            # 连带后果也是正确因果：改了 features.csv 没重算哈希 → G3 抓；
            # 少了一个 must 后 parity.md 的报告值与实算值不符 → G9 抓。
            # 三道一起响，说明这条作弊路径确实走不通。
            "broken-out-scope": {"G1", "G3", "G9"},
            "broken-lock": {"G3"},
        }
        for name, stages in expectation.items():
            _code, payload = run_json(FIXTURES / name)
            failed_stages = {r["stage"] for r in payload["results"] if r["status"] == "FAIL"}
            self.assertEqual(failed_stages, stages,
                             "%s 的失败门应是 %s，实际 %s" % (name, stages, failed_stages))


# ---------------------------------------------------------------------------
# C. 规则单元（用临时副本做单点破坏）
# ---------------------------------------------------------------------------

class TestRuleUnits(FixtureCase):

    # ---- linkage na 语义（SCHEMAS §5，Lead 裁决 2026-10-23） ----

    def test_legitimate_na_row_accepted(self):
        """确认不受影响的面写 status=na + 理由，是合法的，不许报 FAIL。"""
        code, payload = run_json(FIXTURES / "good-min", stage="G2")
        self.assertEqual(code, 0, "good-min 含一条合法 na 行，必须全 PASS：%s"
                         % failures(payload))
        codes = {r["code"] for r in payload["results"]}
        self.assertIn("G2.linkage-na-reason", codes)
        self.assertIn("G2.linkage-six-face", codes)

    def test_na_row_without_reason_rejected(self):
        """na 行 state_handling 不写理由 → G2 FAIL（防把 na 当省略用）。"""
        project = self.copy_fixture("good-min")
        path = project / "BLUEPRINT/linkage.csv"
        rows, fields = C.read_csv_text(path.read_text(encoding="utf-8"))
        for row in rows:
            if row["status"] == "na":
                row["state_handling"] = "-"
        path.write_text(_make_csv_text(fields, rows), encoding="utf-8")
        code, payload = run_json(project, stage="G2")
        self.assertEqual(code, 1)
        self.assertIn("G2.linkage-na-reason", failures(payload, "G2"))

    def test_na_row_without_affected_control_rejected(self):
        """na 行必须写「不适用：哪一面」，affected_control 空 → FAIL。"""
        project = self.copy_fixture("good-min")
        path = project / "BLUEPRINT/linkage.csv"
        rows, fields = C.read_csv_text(path.read_text(encoding="utf-8"))
        for row in rows:
            if row["status"] == "na":
                row["affected_control"] = ""
        path.write_text(_make_csv_text(fields, rows), encoding="utf-8")
        code, payload = run_json(project, stage="G2")
        self.assertEqual(code, 1)
        detail = [r for r in payload["results"] if r["code"] == "G2.linkage-rows"][0]
        self.assertIn("affected_control", detail["actual"])

    def test_all_na_feature_fails_g2_and_g6(self):
        """六面全 na = 等同没做联动分析 → G2 与 G6 都要 FAIL。"""
        for stage in ("G2", "G6"):
            code, payload = run_json(FIXTURES / "broken-linkage-allna", stage=stage)
            self.assertEqual(code, 1, "%s 应报六面全 na" % stage)
            codes = failures(payload, stage)
            if stage == "G2":
                self.assertIn("G2.linkage-six-face", codes)
            else:
                self.assertIn("G6.linkage-all-na", codes)
                detail = [r for r in payload["results"]
                          if r["code"] == "G6.linkage-all-na"][0]
                self.assertIn("F-REPEAT-SET", detail["actual"])
                self.assertIn("na", detail["actual"])

    def test_na_does_not_mask_pending(self):
        """na 只豁免它自己；同一功能里 pending 的行仍要被 G6 报出来。"""
        project = self.copy_fixture("good-min")
        path = project / "BLUEPRINT/linkage.csv"
        rows, fields = C.read_csv_text(path.read_text(encoding="utf-8"))
        for row in rows:
            if row["source_id"] == "F-REPEAT-SET" and row["status"] == "wired":
                row["status"] = "pending"
                break
        path.write_text(_make_csv_text(fields, rows), encoding="utf-8")
        code, payload = run_json(project, stage="G6")
        self.assertEqual(code, 1)
        self.assertIn("G6.progress-linkage", failures(payload, "G6"))

    def test_na_status_is_legal_enum(self):
        self.assertIn("na", C.LINKAGE_STATUS)
        self.assertEqual(C.LINKAGE_STATUS, {"pending", "wired", "verified", "na"})

    # ---- 六面 SSOT：唯一权威定义在 shared/faces.json ----

    def test_faces_loaded_from_shared_json(self):
        """SIX_FACES 必须与 shared/faces.json 逐项一致（门禁侧不得自成一套）。"""
        faces_path = SYSTEM_ROOT / "shared" / "faces.json"
        self.assertTrue(faces_path.is_file(), "六面的唯一权威定义应存在：shared/faces.json")
        data = json.loads(faces_path.read_text(encoding="utf-8"))
        expected = data["faces"]
        self.assertEqual(len(C.SIX_FACES), len(expected))
        for got, want in zip(C.SIX_FACES, expected):
            self.assertEqual(got["key"], want["key"])
            self.assertEqual(got["name"], want["name"])
            self.assertEqual(got["keywords"], want["keywords"],
                             "面 %s 的关键词与 shared/faces.json 漂移" % want["key"])

    def test_faces_json_is_valid_and_complete(self):
        """faces.json 结构必须完整：6 个面、key 唯一、每面有 name 与非空 keywords。"""
        faces_path = SYSTEM_ROOT / "shared" / "faces.json"
        data = json.loads(faces_path.read_text(encoding="utf-8"))
        faces = data["faces"]
        self.assertEqual(len(faces), 6)
        keys = [f["key"] for f in faces]
        self.assertEqual(len(set(keys)), 6, "面的 key 必须唯一")
        for face in faces:
            self.assertTrue(face.get("name"), "面 %s 缺 name" % face.get("key"))
            self.assertTrue(face.get("keywords"), "面 %s 缺 keywords" % face.get("key"))
            self.assertIsInstance(face["keywords"], list)

    def test_tools_linkage_matrix_reads_same_json(self):
        """tools/linkage_matrix.py 也必须从 shared/faces.json 读，不许自成一套。"""
        path = SYSTEM_ROOT / "tools" / "linkage_matrix.py"
        text = path.read_text(encoding="utf-8")
        self.assertIn("faces.json", text,
                      "tools/linkage_matrix.py 应读取 shared/faces.json（六面 SSOT）")

    def test_face_names_text_is_dynamic(self):
        """提示文案里的六面名称必须来自 SIX_FACES，不许手写。"""
        expected = "、".join(f["name"] for f in C.SIX_FACES)
        self.assertEqual(C.face_names_text(), expected)
        # 规则源码里不许再出现手写的六面全称串
        for name in ("g2.py", "g6.py"):
            src = (GATES_DIR / "rules" / name).read_text(encoding="utf-8")
            self.assertNotIn("列表/角标/详情/日历/搜索/提醒", src,
                             "%s 里仍有手写的六面名称串，应改用 C.face_names_text()" % name)

    def test_six_faces_constant(self):
        """六面定义与 SCHEMAS §5 一致（顺序与名称都要对）。"""
        names = [f["name"] for f in C.SIX_FACES]
        self.assertEqual(names, ["主列表", "角标计数", "详情面板",
                                 "日历/时间", "搜索", "提醒/通知"])

    def test_classify_faces_explicit_marker(self):
        """显式 #面名 标记优先于关键词匹配。"""
        self.assertEqual(C.classify_faces("#主列表 行徽标"), ["list"])
        self.assertEqual(C.classify_faces("#badge 未完成数"), ["badge"])

    def test_linkage_faces_all_na_detection(self):
        rows = [
            {"affected_control": "主列表行徽标", "status": "na"},
            {"affected_control": "详情面板字段", "status": "na"},
        ]
        analysis = C.linkage_faces(rows)
        self.assertTrue(analysis["all_na"])
        self.assertEqual(sorted(analysis["considered"]), ["detail", "list"])
        self.assertEqual(analysis["covered"], [])

    def test_linkage_faces_pending_is_not_all_na(self):
        """pending 是「还没接」，不该被误报成「六面全 na」。"""
        rows = [
            {"affected_control": "主列表行徽标", "status": "pending"},
            {"affected_control": "详情面板字段", "status": "na"},
        ]
        analysis = C.linkage_faces(rows)
        self.assertFalse(analysis["all_na"])

    def test_contract_missing_section_detected(self):
        project = self.copy_fixture("good-min")
        contract = project / "BLUEPRINT/contracts/C-F-DATE-EDIT.md"
        text = contract.read_text(encoding="utf-8")
        # 删掉「6 筛选条件」整段
        lines, out, skipping = text.splitlines(), [], False
        for raw in lines:
            if raw.startswith("## "):
                if raw[3:].strip() == "6 筛选条件":
                    skipping = True
                    continue
                skipping = False
            if not skipping:
                out.append(raw)
        contract.write_text("\n".join(out) + "\n", encoding="utf-8")
        code, payload = run_json(project, stage="G2")
        self.assertEqual(code, 1)
        detail = [r for r in payload["results"] if r["code"] == "G2.contract-sections"]
        self.assertTrue(any("6 筛选条件" in r["actual"] for r in detail),
                        "必须点名缺的是哪一节：%s" % [r["actual"] for r in detail])

    def test_contract_na_section_accepted(self):
        """确定不适用写 `N/A：理由` 是合法的，不许判 FAIL。"""
        project = self.copy_fixture("good-min")
        contract = project / "BLUEPRINT/contracts/C-F-REPEAT.md"
        text = contract.read_text(encoding="utf-8")
        text = re.sub(
            r"(## 6 筛选条件\n)(.*?)(?=\n## )",
            r"\1\nN/A：重复规则不引入新的筛选维度，筛选行为完全复用 C-F-DATE-EDIT §6。\n",
            text, flags=re.S)
        contract.write_text(text, encoding="utf-8")
        code, payload = run_json(project, stage="G2")
        self.assertEqual(code, 0, "N/A：+理由 必须被接受，实际：%s" % failures(payload))

    def test_contract_empty_section_detected(self):
        project = self.copy_fixture("good-min")
        contract = project / "BLUEPRINT/contracts/C-F-REPEAT.md"
        text = contract.read_text(encoding="utf-8")
        text = re.sub(r"(## 7 业务实现逻辑\n)(.*?)(?=\n## )", r"\1\n太短\n", text, flags=re.S)
        contract.write_text(text, encoding="utf-8")
        code, payload = run_json(project, stage="G2")
        self.assertEqual(code, 1)
        matches = [r for r in payload["results"] if r["code"] == "G2.contract-sections"
                   and r["status"] == "FAIL"]
        self.assertTrue(matches, "应有一条 contract-sections FAIL，实际：%s"
                        % [r["actual"] for r in payload["results"]
                           if r["code"] == "G2.contract-sections"])
        self.assertIn("空节", matches[0]["actual"])

    # ---- 同级 order 唯一（ORDER-DUP 在门禁里是 ERROR，在 lint 里只是 WARN） ----

    def test_menu_order_dup_detected(self):
        code, payload = run_json(FIXTURES / "broken-menu-order", stage="G2")
        self.assertEqual(code, 1, "同级 order 重复必须 FAIL")
        detail = [r for r in payload["results"] if r["code"] == "G2.menu-order-dup"][0]
        self.assertEqual(detail["status"], "FAIL")
        self.assertIn("M-DATE", detail["actual"])
        self.assertIn("order=1", detail["actual"])
        # 必须点名具体节点与行号，便于直接去改
        self.assertIn("M-DATE-TODAY", detail["actual"])
        self.assertIn("M-DATE-TOMORROW", detail["actual"])

    def test_menu_order_dup_ignores_separator(self):
        """separator/label 不参与排序判定（它们不占渲染顺序）。"""
        code, payload = run_json(FIXTURES / "good-min", stage="G2")
        self.assertEqual(code, 0)
        detail = [r for r in payload["results"] if r["code"] == "G2.menu-order-dup"][0]
        self.assertEqual(detail["status"], "PASS")

    # ---- G0 假绿回归（Lead 2026-10-23 发现的两个真实缺陷） ----

    def test_empty_not_do_list_fails_g0(self):
        """不做清单只剩空表格行 → 必须 FAIL（旧逻辑把空行算成条目）。"""
        code, payload = run_json(FIXTURES / "broken-project", stage="G0")
        self.assertEqual(code, 1)
        detail = [r for r in payload["results"] if r["code"] == "G0.not-do-list"][0]
        self.assertEqual(detail["status"], "FAIL")
        self.assertIn("0 条", detail["actual"])

    def test_skeleton_decisions_fails_g0(self):
        """决策表只剩 D-001..D-003 骨架行（无日期无理由）→ 必须 FAIL。

        旧逻辑按全文正则统计 D-xxx，模板「实例」章节的完整示例行会被计入，
        于是新项目一生成就「≥3 条」——假绿。
        """
        code, payload = run_json(FIXTURES / "broken-project", stage="G0")
        self.assertEqual(code, 1)
        detail = [r for r in payload["results"] if r["code"] == "G0.decisions"][0]
        self.assertEqual(detail["status"], "FAIL")

    def test_real_decisions_in_decision_table_counted(self):
        """决策表里的真决策（带 ISO 日期 + 理由）必须被计入。"""
        text = (FIXTURES / "good-min" / "DECISIONS.md").read_text(encoding="utf-8")
        ids = __import__("rules.g0", fromlist=["_real_decision_ids"])._real_decision_ids(text)
        self.assertGreaterEqual(len(ids), 3, "good-min 决策表应有 ≥3 条真决策")
        self.assertIn("D-001", ids)
        self.assertIn("D-004", ids)

    def test_example_section_decisions_excluded(self):
        """「实例」章节的示例决策必须被排除（只认「## 决策表」小节）。"""
        from rules import g0 as G0
        text = """# DECISIONS

## 决策表

| ID | 日期 | 决策 | 理由 | 影响面 | 状态 |
|---|---|---|---|---|---|
| D-001 | 2026-10-20T09:30+08:00 | 定 A 档 | 只有我用 | PROJECT.md | 已定 |

## 实例（格式参考）

| ID | 日期 | 决策 | 理由 | 影响面 | 状态 |
|---|---|---|---|---|---|
| D-002 | 2026-10-21T10:00+08:00 | 示例决策二 | 示例理由二 | 示例影响面 | 已定 |
| D-007 | 2026-10-23T14:12+08:00 | 示例决策七 | 示例理由七 | 示例影响面 | 已定 |
| D-021 | 2026-10-23T16:00+08:00 | 示例决策廿一 | 示例理由廿一 | 示例影响面 | 已定 |
"""
        ids = G0._real_decision_ids(text)
        self.assertEqual(ids, ["D-001"],
                         "实例章节的示例行不许计入，实际计入：%s" % ids)

    def test_menu_banned_word_detected(self):
        project = self.copy_fixture("good-min")
        path = project / "BLUEPRINT/menus.csv"
        text = path.read_text(encoding="utf-8")
        path.write_text(text.replace("始终可见", "视情况", 1), encoding="utf-8")
        code, payload = run_json(project, stage="G2")
        self.assertEqual(code, 1)
        detail = [r for r in payload["results"] if r["code"] == "G2.menu-conditions"][0]
        self.assertIn("视情况", detail["actual"])

    def test_menu_missing_command_detected(self):
        project = self.copy_fixture("good-min")
        path = project / "BLUEPRINT/menus.csv"
        rows, fields = C.read_csv_text(path.read_text(encoding="utf-8"))
        for row in rows:
            if row["node_id"] == "M-REPEAT-WEEKLY":
                row["command"] = "-"
        path.write_text(_make.csv_text(fields, [[r[f] for f in fields] for r in rows]),
                        encoding="utf-8")
        code, payload = run_json(project, stage="G2")
        self.assertEqual(code, 1)
        detail = [r for r in payload["results"] if r["code"] == "G2.menu-command"][0]
        self.assertIn("M-REPEAT-WEEKLY", detail["actual"])

    def test_separator_and_label_exempt_from_command(self):
        """separator / label 没有 command 是合法的（good-min 里就有），不许 FAIL。"""
        code, payload = run_json(FIXTURES / "good-min", stage="G2")
        self.assertEqual(code, 0)
        self.assertNotIn("G2.menu-command", failures(payload))

    def test_menu_default_item_advisory_never_blocks(self):
        project = self.copy_fixture("good-min")
        path = project / "BLUEPRINT/menus.csv"
        rows, fields = C.read_csv_text(path.read_text(encoding="utf-8"))
        for row in rows:
            if row["type"] == "submenu":
                row["default_item"] = "-"
        path.write_text(_make.csv_text(fields, [[r[f] for f in fields] for r in rows]),
                        encoding="utf-8")
        code, payload = run_json(project, stage="G2")
        self.assertEqual(code, 0, "default_item 为 - 必须允许，不许升级成 FAIL")
        detail = [r for r in payload["results"] if r["code"] == "G2.menu-default-item"][0]
        self.assertEqual(detail["status"], "PASS")
        self.assertIn("建议", detail["actual"])

    def test_linkage_pending_detected(self):
        project = self.copy_fixture("good-min")
        path = project / "BLUEPRINT/linkage.csv"
        path.write_text(path.read_text(encoding="utf-8").replace("T-101,wired", "T-101,pending"),
                        encoding="utf-8")
        code, payload = run_json(project, stage="G6")
        self.assertEqual(code, 1)
        detail = [r for r in payload["results"] if r["code"] == "G6.progress-linkage"][0]
        self.assertIn("pending", detail["actual"])

    def test_feature_done_without_linkage_detected(self):
        """progress=yes 但完全没有 linkage 行 = 页面有、内部不联动 → G6 FAIL。"""
        project = self.copy_fixture("good-min")
        path = project / "BLUEPRINT/linkage.csv"
        rows, fields = C.read_csv_text(path.read_text(encoding="utf-8"))
        keep = [r for r in rows if r["source_id"] != "F-REPEAT-SET"]
        path.write_text(_make.csv_text(fields, [[r[f] for f in fields] for r in keep]),
                        encoding="utf-8")
        code, payload = run_json(project, stage="G6")
        self.assertEqual(code, 1)
        detail = [r for r in payload["results"] if r["code"] == "G6.progress-linkage"][0]
        self.assertIn("F-REPEAT-SET", detail["actual"])
        self.assertIn("没有任何联动行", detail["actual"])

    def test_linkage_test_ref_not_pass_detected(self):
        project = self.copy_fixture("good-min")
        path = project / "TEST/results/2026-10-23-run3.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        for case in data["cases"]:
            if case["id"] == "T-101":
                case["status"] = "fail"
        data["failed"] = 1
        data["passed"] = 3
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        code, payload = run_json(project, stage="G6")
        self.assertEqual(code, 1)
        self.assertIn("G6.progress-tests", failures(payload, "G6"))

    def test_lock_hash_mismatch_detected(self):
        project = self.copy_fixture("good-min")
        lock = project / "BLUEPRINT/BLUEPRINT-LOCK.md"
        text = lock.read_text(encoding="utf-8")
        good_hash = C.sha256_file(project / "BLUEPRINT/features.csv")
        bad_hash = "0" * 64
        self.assertIn(good_hash, text)
        lock.write_text(text.replace(good_hash, bad_hash), encoding="utf-8")
        code, payload = run_json(project, stage="G3")
        self.assertEqual(code, 1)
        detail = [r for r in payload["results"] if r["code"] == "G3.lock-hashes"][0]
        self.assertIn("features.csv", detail["actual"])

    def test_lock_uppercase_hash_rejected(self):
        """记录必须是小写十六进制（逐字比对，不做大小写归一）。"""
        project = self.copy_fixture("good-min")
        lock = project / "BLUEPRINT/BLUEPRINT-LOCK.md"
        text = lock.read_text(encoding="utf-8")
        good_hash = C.sha256_file(project / "BLUEPRINT/screens.csv")
        lock.write_text(text.replace(good_hash, good_hash.upper()), encoding="utf-8")
        code, payload = run_json(project, stage="G3")
        self.assertEqual(code, 1)
        self.assertIn("G3.lock-hashes", failures(payload, "G3"))

    def test_lock_missing_coverage_detected(self):
        project = self.copy_fixture("good-min")
        lock = project / "BLUEPRINT/BLUEPRINT-LOCK.md"
        text = lock.read_text(encoding="utf-8")
        # 删掉一行哈希（menus.csv）
        kept = [ln for ln in text.splitlines() if "BLUEPRINT/menus.csv" not in ln]
        lock.write_text("\n".join(kept) + "\n", encoding="utf-8")
        code, payload = run_json(project, stage="G3")
        self.assertEqual(code, 1)
        detail = [r for r in payload["results"] if r["code"] == "G3.lock-coverage"][0]
        self.assertIn("menus.csv", detail["actual"])

    def test_blocking_unknown_fails_g3(self):
        project = self.copy_fixture("good-min")
        path = project / "BLUEPRINT/unknowns.csv"
        rows, fields = C.read_csv_text(path.read_text(encoding="utf-8"))
        for row in rows:
            if row["unknown_id"] == "U-001":
                row["blocking"] = "yes"
                row["status"] = "open"
        path.write_text(_make.csv_text(fields, [[r[f] for f in fields] for r in rows]),
                        encoding="utf-8")
        code, payload = run_json(project, stage="G3")
        self.assertEqual(code, 1)
        detail = [r for r in payload["results"] if r["code"] == "G3.blocking-unknowns"][0]
        self.assertIn("U-001", detail["actual"])

    def test_waived_unknown_without_decision_fails(self):
        project = self.copy_fixture("good-min")
        decisions = project / "DECISIONS.md"
        text = decisions.read_text(encoding="utf-8")
        kept = [ln for ln in text.splitlines() if "U-002" not in ln]
        decisions.write_text("\n".join(kept) + "\n", encoding="utf-8")
        code, payload = run_json(project, stage="G3")
        self.assertEqual(code, 1)
        detail = [r for r in payload["results"] if r["code"] == "G3.waived-unknowns"][0]
        self.assertIn("U-002", detail["actual"])

    def test_feature_id_format_enforced(self):
        project = self.copy_fixture("good-min")
        path = project / "BLUEPRINT/features.csv"
        text = path.read_text(encoding="utf-8").replace("F-DATE-EDIT", "f_date_edit")
        path.write_text(text, encoding="utf-8")
        code, payload = run_json(project, stage="G1")
        self.assertEqual(code, 1)
        self.assertIn("G1.features-ids", failures(payload, "G1"))

    def test_screen_id_format_enforced(self):
        """screen_id 严格 S-两位数（与 tools 的 SCREEN-ID-FORMAT 同口径）。"""
        project = self.copy_fixture("good-min")
        path = project / "BLUEPRINT/screens.csv"
        rows, fields = C.read_csv_text(path.read_text(encoding="utf-8"))
        rows[0]["screen_id"] = "S-01-主列表"        # 带后缀 = 不合规（主键不许带描述）
        path.write_text(_make_csv_text(fields, rows), encoding="utf-8")
        code, payload = run_json(project, stage="G1")
        self.assertEqual(code, 1)
        detail = [r for r in payload["results"] if r["code"] == "G1.screens-ids"][0]
        self.assertIn("S-01-主列表", detail["actual"])
        self.assertIn("S-两位数", detail["actual"])

    def test_screen_id_duplicate_detected(self):
        project = self.copy_fixture("good-min")
        path = project / "BLUEPRINT/screens.csv"
        rows, fields = C.read_csv_text(path.read_text(encoding="utf-8"))
        rows[1]["screen_id"] = rows[0]["screen_id"]
        path.write_text(_make_csv_text(fields, rows), encoding="utf-8")
        code, payload = run_json(project, stage="G1")
        self.assertEqual(code, 1)
        detail = [r for r in payload["results"] if r["code"] == "G1.screens-ids"][0]
        self.assertIn("重复", detail["actual"])

    def test_screen_states_required(self):
        project = self.copy_fixture("good-min")
        path = project / "BLUEPRINT/screens.csv"
        rows, fields = C.read_csv_text(path.read_text(encoding="utf-8"))
        rows[0]["state_loading"] = "no"
        path.write_text(_make.csv_text(fields, [[r[f] for f in fields] for r in rows]),
                        encoding="utf-8")
        code, payload = run_json(project, stage="G1")
        self.assertEqual(code, 1)
        detail = [r for r in payload["results"] if r["code"] == "G1.screens-states"][0]
        self.assertIn("state_loading", detail["actual"])

    def test_all_na_faces_rejected(self):
        """规则（R18/SCHEMAS §5）：某功能六面全部 na = 等同于没做联动分析，必须 FAIL。"""
        project = self.copy_fixture("good-min")
        path = project / "BLUEPRINT/linkage.csv"
        rows, fields = C.read_csv_text(path.read_text(encoding="utf-8"))
        for r in rows:
            if r["source_id"] == "F-DATE-EDIT":
                r["status"] = "na"
                r["test_ref"] = "-"
                r["state_handling"] = "不适用：本功能只影响一个面，其余面确认不受影响"
        path.write_text(_make.csv_text(fields, [[r[f] for f in fields] for r in rows]),
                        encoding="utf-8")
        code, payload = run_json(project, stage="G2")
        self.assertEqual(code, 1, "六面全 na 必须 FAIL")
        detail = [r for r in payload["results"]
                  if r["code"] == "G2.linkage-six-face" and r["status"] == "FAIL"]
        self.assertTrue(detail, "应有 linkage-six-face FAIL")
        self.assertIn("没有任何一面真正接线", detail[0]["actual"])

    def test_single_wired_face_is_enough(self):
        """规则：至少 1 面 wired/verified 即通过（不再要求 2 个 affected_screen）。"""
        project = self.copy_fixture("good-min")
        path = project / "BLUEPRINT/linkage.csv"
        rows, fields = C.read_csv_text(path.read_text(encoding="utf-8"))
        keep = [r for r in rows
                if not (r["source_id"] == "F-DATE-EDIT" and r["affected_screen"] == "S-02")]
        # 保留的那条改成 wired
        for r in keep:
            if r["source_id"] == "F-DATE-EDIT":
                r["status"] = "wired"
        path.write_text(_make.csv_text(fields, [[r[f] for f in fields] for r in keep]),
                        encoding="utf-8")
        code, payload = run_json(project, stage="G2")
        self.assertEqual(code, 0, "至少 1 面 wired 应通过，实际：%s" % failures(payload))

    def test_test_plan_missing_detected_in_g8(self):
        project = self.copy_fixture("good-min")
        (project / "TEST/test-plan.md").unlink()
        code, payload = run_json(project, stage="G8")
        self.assertEqual(code, 1)
        self.assertIn("G8.test-plan", failures(payload, "G8"))

    def test_consecutive_runs_short_detected(self):
        project = self.copy_fixture("good-min")
        (project / "TEST/results/2026-10-21-run1.json").unlink()
        code, payload = run_json(project, stage="G8")
        self.assertEqual(code, 1)
        detail = [r for r in payload["results"] if r["code"] == "G8.consecutive"][0]
        self.assertIn("只有 2 份", detail["actual"])

    def test_consecutive_runs_dirty_detected(self):
        project = self.copy_fixture("good-min")
        path = project / "TEST/results/2026-10-22-run2.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["failed"] = 1
        data["passed"] = 3
        data["cases"][0]["status"] = "fail"
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        code, payload = run_json(project, stage="G8")
        self.assertEqual(code, 1)
        self.assertIn("G8.consecutive", failures(payload, "G8"))

    def test_s1_s2_open_bug_detected(self):
        project = self.copy_fixture("good-min")
        path = project / "TEST/bugs.md"
        text = path.read_text(encoding="utf-8")
        path.write_text(text.replace("| BUG-002 | S3 | open |", "| BUG-002 | S1 | open |"),
                        encoding="utf-8")
        code, payload = run_json(project, stage="G8")
        self.assertEqual(code, 1)
        detail = [r for r in payload["results"] if r["code"] == "G8.bugs"][0]
        self.assertIn("BUG-002", detail["actual"])

    def test_s3_open_bug_allowed(self):
        code, payload = run_json(FIXTURES / "good-min", stage="G8")
        self.assertEqual(code, 0, "S3 缺陷 open 是允许的：%s" % failures(payload))

    def test_memory_db_in_tests_detected(self):
        project = self.copy_fixture("good-min")
        path = project / "tests/test_persist.py"
        path.write_text(path.read_text(encoding="utf-8")
                        + '\n\ndef _bad():\n    return sqlite3.connect(":memory:")\n',
                        encoding="utf-8")
        code, payload = run_json(project, stage="G7")
        self.assertEqual(code, 1)
        detail = [r for r in payload["results"] if r["code"] == "G7.no-memory-db"][0]
        self.assertIn(":memory:", detail["actual"])

    def test_no_tempfile_detected(self):
        project = self.copy_fixture("good-min")
        path = project / "tests/test_persist.py"
        text = path.read_text(encoding="utf-8")
        for tok in ("tempfile", "mkdtemp", "NamedTemporaryFile", "TemporaryDirectory"):
            text = text.replace(tok, "os_path")
        path.write_text(text, encoding="utf-8")
        code, payload = run_json(project, stage="G7")
        self.assertEqual(code, 1)
        self.assertIn("G7.temp-files", failures(payload, "G7"))

    def test_missing_flush_result_detected(self):
        project = self.copy_fixture("good-min")
        path = project / "src/flush.py"
        path.write_text(path.read_text(encoding="utf-8").replace("FlushResult", "SomeResult"),
                        encoding="utf-8")
        for extra in ("src/date_edit.py", "src/repeat_set.py"):
            p = project / extra
            p.write_text(p.read_text(encoding="utf-8").replace("FlushResult", "SomeResult"),
                         encoding="utf-8")
        code, payload = run_json(project, stage="G7")
        self.assertEqual(code, 1)
        self.assertIn("G7.flush-result", failures(payload, "G7"))

    def test_flush_symbol_configurable(self):
        project = self.copy_fixture("good-min")
        manifest = project / ".replica/gate.manifest.yml"
        manifest.write_text(
            manifest.read_text(encoding="utf-8").replace(
                "flush_result_symbol: FlushResult", "flush_result_symbol: FlushOutcome"),
            encoding="utf-8")
        code, payload = run_json(project, stage="G7")
        self.assertEqual(code, 1, "换了符号名后实现里没有 FlushOutcome，应 FAIL")
        detail = [r for r in payload["results"] if r["code"] == "G7.flush-result"][0]
        self.assertIn("FlushOutcome", detail["expected"])

    def test_no_fault_injection_detected(self):
        """抹掉「故障注入」与「生命周期」两类标记后，G7 必须报「缺少故障注入用例」。

        口径提醒：故障注入类用例的识别词包含 lifecycle / 生命周期（进程被 kill、
        关窗冲刷失败都属这一类）。因此只抹掉「故障注入」四个字不够——T-104 仍带
        「生命周期」，会被正确识别为故障用例。要构造「一个故障用例都没有」，
        必须两个标记一起抹掉。
        """
        project = self.copy_fixture("good-min")
        path = project / "TEST/test-plan.md"
        text = path.read_text(encoding="utf-8")
        text = text.replace("故障注入", "正常").replace("生命周期", "正常")
        path.write_text(text, encoding="utf-8")
        code, payload = run_json(project, stage="G7")
        self.assertEqual(code, 1)
        self.assertIn("G7.fault-injection", failures(payload, "G7"))

    def test_parity_score_mismatch_detected(self):
        project = self.copy_fixture("good-min")
        path = project / "REPORT/parity.md"
        path.write_text(path.read_text(encoding="utf-8").replace("功能分：85.7", "功能分：99"),
                        encoding="utf-8")
        code, payload = run_json(project, stage="G9")
        self.assertEqual(code, 1)
        detail = [r for r in payload["results"] if r["code"] == "G9.parity-computed"][0]
        self.assertIn("实算", detail["actual"])

    def test_parity_score_is_recomputed(self):
        """progress 从 yes 改成 partial 后，报告里的 85.7 必须被判为不符。"""
        project = self.copy_fixture("good-min")
        path = project / "BLUEPRINT/features.csv"
        rows, fields = C.read_csv_text(path.read_text(encoding="utf-8"))
        for row in rows:
            if row["feature_id"] == "F-REPEAT-SET":
                row["progress"] = "partial"
        path.write_text(_make.csv_text(fields, [[r[f] for f in fields] for r in rows]),
                        encoding="utf-8")
        code, payload = run_json(project, stage="G9")
        self.assertEqual(code, 1)
        detail = [r for r in payload["results"] if r["code"] == "G9.parity-computed"][0]
        # 3*1 + 3*0.5 + 1*0 = 4.5 / 7 = 64.3
        self.assertIn("64.3", detail["expected"])

    def test_parity_below_threshold_detected(self):
        project = self.copy_fixture("good-min")
        manifest = project / ".replica/gate.manifest.yml"
        manifest.write_text(manifest.read_text(encoding="utf-8").replace(
            "parity_feature: 80", "parity_feature: 95"), encoding="utf-8")
        code, payload = run_json(project, stage="G9")
        self.assertEqual(code, 1)
        matches = [r for r in payload["results"] if r["code"] == "G9.parity-threshold"
                   and r["status"] == "FAIL"]
        self.assertTrue(matches, "应有 parity-threshold FAIL")
        self.assertIn("F-SYNC-CLOUD", matches[0]["actual"])

    def test_parity_missing_scores_detected(self):
        project = self.copy_fixture("good-min")
        path = project / "REPORT/parity.md"
        path.write_text("# 一致性\n\n一切良好。\n", encoding="utf-8")
        code, payload = run_json(project, stage="G9")
        self.assertEqual(code, 1)
        self.assertIn("G9.parity-scores", failures(payload, "G9"))

    def test_feedback_without_links_detected(self):
        project = self.copy_fixture("good-min")
        path = project / "REPORT/feedback.md"
        text = path.read_text(encoding="utf-8")
        text = re.sub(r"https?://\S+", "（原帖）", text)
        path.write_text(text, encoding="utf-8")
        code, payload = run_json(project, stage="G10")
        self.assertEqual(code, 1)
        self.assertIn("G10.feedback-links", failures(payload, "G10"))

    def test_feedback_placeholder_link_detected(self):
        project = self.copy_fixture("good-min")
        path = project / "REPORT/feedback.md"
        text = path.read_text(encoding="utf-8").replace(
            "https://sspai.com/post/887766#comments", "https://example.com/reviews")
        path.write_text(text, encoding="utf-8")
        code, payload = run_json(project, stage="G10")
        self.assertEqual(code, 1)
        self.assertIn("G10.feedback-fabrication", failures(payload, "G10"))

    def test_feedback_without_sample_detected(self):
        project = self.copy_fixture("good-min")
        path = project / "REPORT/feedback.md"
        text = path.read_text(encoding="utf-8")
        text = re.sub(r"^样本：.*$", "来源：网上", text, flags=re.M)
        path.write_text(text, encoding="utf-8")
        code, payload = run_json(project, stage="G10")
        self.assertEqual(code, 1)
        self.assertIn("G10.feedback-sample", failures(payload, "G10"))

    def test_architecture_missing_section_detected(self):
        project = self.copy_fixture("good-min")
        path = project / "SPEC/ARCHITECTURE.md"
        text = path.read_text(encoding="utf-8")
        text = re.sub(r"## 3 数据流\n.*$", "", text, flags=re.S)
        path.write_text(text, encoding="utf-8")
        code, payload = run_json(project, stage="G4")
        self.assertEqual(code, 1)
        detail = [r for r in payload["results"] if r["code"] == "G4.architecture"][0]
        self.assertIn("数据流", detail["actual"])

    def test_schema_without_ddl_detected(self):
        project = self.copy_fixture("good-min")
        (project / "SPEC/schema.sql").write_text("-- 待定\n", encoding="utf-8")
        code, payload = run_json(project, stage="G4")
        self.assertEqual(code, 1)
        self.assertIn("G4.schema-sql", failures(payload, "G4"))

    def test_entity_not_in_schema_detected(self):
        project = self.copy_fixture("good-min")
        path = project / "BLUEPRINT/data-dictionary.md"
        text = path.read_text(encoding="utf-8")
        path.write_text(text.replace("## E02 Reminder", "## E02 GhostEntity"), encoding="utf-8")
        code, payload = run_json(project, stage="G4")
        self.assertEqual(code, 1)
        detail = [r for r in payload["results"] if r["code"] == "G4.entity-mapping"][0]
        self.assertIn("GhostEntity", detail["actual"])

    def test_vertical_slice_missing_detected(self):
        project = self.copy_fixture("good-min")
        (project / "SPEC/vertical-slice.md").unlink()
        code, payload = run_json(project, stage="G4")
        self.assertEqual(code, 1)
        self.assertIn("G4.vertical-slice", failures(payload, "G4"))

    def test_tokens_missing_key_detected(self):
        project = self.copy_fixture("good-min")
        path = project / "SPEC/DESIGN/tokens.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        del data["pairs"]
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        code, payload = run_json(project, stage="G5")
        self.assertEqual(code, 1)
        codes = failures(payload, "G5")
        self.assertIn("G5.tokens-keys", codes)

    def test_low_contrast_detected(self):
        project = self.copy_fixture("good-min")
        path = project / "SPEC/DESIGN/tokens.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["color"]["text"] = "#eeeeee"          # 接近白底
        data["color"]["text-muted"] = "#e0e0e0"
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        code, payload = run_json(project, stage="G5")
        self.assertEqual(code, 1, "对比度不达标必须 FAIL")
        self.assertIn("G5.contrast", failures(payload, "G5"))

    def test_component_missing_state_detected(self):
        project = self.copy_fixture("good-min")
        path = project / "SPEC/DESIGN/components.md"
        text = path.read_text(encoding="utf-8")
        # 去掉 Button 块里的 loading 行
        text = re.sub(r"\| loading \| 内嵌 16px 转圈[^\n]*\n", "", text, count=1)
        path.write_text(text, encoding="utf-8")
        code, payload = run_json(project, stage="G5")
        self.assertEqual(code, 1)
        detail = [r for r in payload["results"] if r["code"] == "G5.components-blocks"][0]
        self.assertIn("loading", detail["actual"])

    def test_replacement_table_empty_cell_detected(self):
        project = self.copy_fixture("good-min")
        path = project / "SPEC/DESIGN/components.md"
        text = path.read_text(encoding="utf-8")
        text = text.replace("| 原版品牌主色 | 中性蓝 #2f5bea（自选） | 本项目 tokens.json | 自有 |",
                            "| 原版品牌主色 |  | 本项目 tokens.json | 自有 |")
        path.write_text(text, encoding="utf-8")
        code, payload = run_json(project, stage="G5")
        self.assertEqual(code, 1)
        self.assertIn("G5.replacement-table", failures(payload, "G5"))

    def test_runbook_missing_section_detected(self):
        project = self.copy_fixture("good-min")
        path = project / "REPORT/release/local-runbook.md"
        text = path.read_text(encoding="utf-8")
        text = re.sub(r"## 5 卸载\n.*?(?=\n## )", "", text, flags=re.S)
        text = text.replace("卸载", "删除程序")
        path.write_text(text, encoding="utf-8")
        code, payload = run_json(project, stage="G11")
        self.assertEqual(code, 1)
        detail = [r for r in payload["results"] if r["code"] == "G11.runbook"][0]
        self.assertIn("卸载", detail["actual"])

    def test_start_script_not_executable_detected(self):
        project = self.copy_fixture("good-min")
        os.chmod(str(project / "scripts/start.sh"), 0o644)
        code, payload = run_json(project, stage="G11")
        self.assertEqual(code, 1)
        detail = [r for r in payload["results"] if r["code"] == "G11.start-script"][0]
        self.assertIn("执行权限", detail["actual"])

    def test_restore_drill_missing_detected(self):
        project = self.copy_fixture("good-min")
        (project / "REPORT/release/restore-drill.md").unlink()
        path = project / "REPORT/release/local-runbook.md"
        path.write_text(path.read_text(encoding="utf-8").replace("演练", "测试"), encoding="utf-8")
        code, payload = run_json(project, stage="G11")
        self.assertEqual(code, 1)
        self.assertIn("G11.restore-drill", failures(payload, "G11"))

    def test_project_missing_oneliner_and_not_do_list(self):
        project = self.copy_fixture("good-min")
        (project / "PROJECT.md").write_text("# 项目\n\n随便做点东西。\n", encoding="utf-8")
        code, payload = run_json(project, stage="G0")
        self.assertEqual(code, 1)
        codes = failures(payload, "G0")
        self.assertIn("G0.oneliner", codes)
        self.assertIn("G0.not-do-list", codes)
        self.assertIn("G0.tier", codes)
        self.assertIn("G0.target-artifact", codes)

    def test_placeholder_detected_in_project(self):
        project = self.copy_fixture("good-min")
        path = project / "PROJECT.md"
        path.write_text(path.read_text(encoding="utf-8") + "\n负责人：______\n", encoding="utf-8")
        code, payload = run_json(project, stage="G0")
        self.assertEqual(code, 1)
        self.assertIn("G0.placeholders", failures(payload, "G0"))

    def test_redlines_incomplete_detected(self):
        project = self.copy_fixture("good-min")
        path = project / "REDLINES.md"
        text = "\n".join(ln for ln in path.read_text(encoding="utf-8").splitlines()
                         if "| R7 |" not in ln)
        path.write_text(text + "\n", encoding="utf-8")
        code, payload = run_json(project, stage="G0")
        self.assertEqual(code, 1)
        detail = [r for r in payload["results"] if r["code"] == "G0.redlines"][0]
        self.assertIn("R7", detail["actual"])

    def test_bad_tier_fails_g0(self):
        project = self.copy_fixture("good-min")
        manifest = project / ".replica/gate.manifest.yml"
        manifest.write_text(manifest.read_text(encoding="utf-8").replace("tier: A", "tier: Z"),
                            encoding="utf-8")
        code, payload = run_json(project, stage="G0")
        self.assertEqual(code, 1)
        self.assertIn("G0.manifest-tier", failures(payload, "G0"))

    def test_tier_c_requires_commercial_checks(self):
        """C 档时 G11 必须真的做品牌清扫与 listing 检查，不许再 NA。"""
        project = self.copy_fixture("good-min")
        manifest = project / ".replica/gate.manifest.yml"
        manifest.write_text(manifest.read_text(encoding="utf-8").replace("tier: A", "tier: C"),
                            encoding="utf-8")
        code, payload = run_json(project, stage="G11")
        self.assertEqual(code, 1)
        codes = failures(payload, "G11")
        self.assertIn("G11.listing-check", codes)

    def test_na_must_be_registered(self):
        """R20：未登记的 N/A 必须升级为 FAIL。"""
        project = self.copy_fixture("good-min")
        manifest = project / ".replica/gate.manifest.yml"
        text = manifest.read_text(encoding="utf-8")
        text = re.sub(r"na_approved:\n(  - id: G11\.commercial\n(?:    .*\n)+)", "na_approved: []\n",
                      text)
        manifest.write_text(text, encoding="utf-8")
        code, payload = run_json(project, stage="G11")
        self.assertEqual(code, 1, "NA 未登记必须变 FAIL")
        detail = [r for r in payload["results"] if r["code"] == "G11.commercial"][0]
        self.assertEqual(detail["status"], "FAIL")
        self.assertIn("na_approved", detail["hint"])


# ---------------------------------------------------------------------------
# D. 基础设施单元
# ---------------------------------------------------------------------------

class TestInfrastructure(unittest.TestCase):

    def test_mini_yaml_manifest_like_document(self):
        text = _make.MANIFEST
        data = C.parse_manifest_text(text)
        self.assertEqual(data["project"], "good-min")
        self.assertEqual(data["tier"], "A")
        self.assertEqual(data["thresholds"]["parity_feature"], 80)
        self.assertEqual(data["thresholds"]["consecutive_runs"], 3)
        self.assertEqual(data["required"]["evidence_dirs"], ["evidence", "screens"])
        self.assertEqual(data["required"]["contract_sections"], 16)
        self.assertIsInstance(data["na_approved"], list)
        self.assertEqual(data["na_approved"][0]["id"], "G11.commercial")
        self.assertIn("A 档", data["na_approved"][0]["reason"])

    def test_mini_yaml_quotes_and_comments(self):
        data = C.parse_manifest_text(
            'project: "a: b"   # 注释\n'
            "tier: A\n"
            "thresholds:\n"
            "  parity_feature: 75\n"
            "empty_list: []\n"
            "nested:\n"
            "  a:\n"
            "    b: 1\n")
        self.assertEqual(data["project"], "a: b")
        self.assertEqual(data["empty_list"], [])
        self.assertEqual(data["nested"]["a"]["b"], 1)

    def test_manifest_missing_reports_error(self):
        tmp = tempfile.mkdtemp(prefix="gate-manifest-")
        try:
            manifest, err = C.load_manifest(tmp)
            self.assertEqual(manifest, {})
            self.assertIn("gate.manifest.yml", err)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_csv_reading_with_quotes_and_cjk(self):
        rows, fields = C.read_csv_text(
            'a,b,c\n1,"两个, 逗号",三\n4,5,\n')
        self.assertEqual(fields, ["a", "b", "c"])
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["b"], "两个, 逗号")
        self.assertEqual(rows[1]["c"], "")

    def test_md_headings_ignore_fenced_code(self):
        text = "# T\n\n```\n## 不是标题\n```\n\n## 真标题\n## 2 另一节\n"
        titles = [t for _lvl, t, _no in C.md_headings(text)]
        self.assertIn("真标题", titles)
        self.assertNotIn("不是标题", titles)

    def test_md_sections_stop_at_next_peer(self):
        text = "## A\n正文A\n### A.1\n子\n## B\n正文B\n"
        sections = {s["title"]: s for s in C.md_sections(text, 2)}
        self.assertIn("A", sections)
        self.assertIn("A.1", sections["A"]["body"])
        self.assertNotIn("正文B", sections["A"]["body"])

    def test_md_tables_parsed(self):
        text = "| 文件 | SHA-256 |\n|---|---|\n| a.md | " + "a" * 64 + " |\n"
        tables = C.md_tables(text)
        self.assertEqual(len(tables), 1)
        self.assertEqual(tables[0]["header"], ["文件", "SHA-256"])
        self.assertEqual(tables[0]["rows"][0][0], "a.md")

    def test_contract_headings_are_sixteen_and_unique(self):
        self.assertEqual(len(C.CONTRACT_HEADINGS), 16)
        self.assertEqual(len(set(C.CONTRACT_HEADINGS)), 16)
        self.assertEqual(C.CONTRACT_HEADINGS[0], "1 目标与入口")
        self.assertEqual(C.CONTRACT_HEADINGS[-1], "16 测试与证据")

    def test_menus_columns_are_fifteen_with_default_item(self):
        """Lead 裁决：menus.csv 15 列，第 14 个数据列是 default_item。"""
        self.assertEqual(len(C.MENUS_COLUMNS), 15)
        self.assertEqual(C.MENUS_COLUMNS[12], "screens")
        self.assertEqual(C.MENUS_COLUMNS[13], "default_item")
        self.assertEqual(C.MENUS_COLUMNS[14], "notes")

    def test_schema_documents_match_columns(self):
        """SCHEMAS.md 的列声明必须与 common.py 的常量一致（防两处漂移）。"""
        schemas = (SYSTEM_ROOT / "templates/blueprint/SCHEMAS.md").read_text(encoding="utf-8")
        for column in C.MENUS_COLUMNS:
            self.assertIn("`%s`" % column, schemas,
                          "SCHEMAS §4 里没有列出 %s" % column)
        for column in C.FEATURES_COLUMNS:
            self.assertIn("`%s`" % column, schemas,
                          "SCHEMAS §2 里没有列出 %s" % column)
        for column in C.LINKAGE_COLUMNS:
            self.assertIn("`%s`" % column, schemas,
                          "SCHEMAS §5 里没有列出 %s" % column)

    def test_sha256_file_matches_hashlib(self):
        path = FIXTURES / "good-min" / "PROJECT.md"
        self.assertEqual(C.sha256_file(path),
                         hashlib.sha256(path.read_bytes()).hexdigest())

    def test_normalize_priority_aliases(self):
        self.assertEqual(C.normalize_priority("P0"), "must")
        self.assertEqual(C.normalize_priority("Must"), "must")
        self.assertEqual(C.normalize_priority("p2"), "could")
        self.assertEqual(C.normalize_priority("should"), "should")

    def test_norm_screen_variants(self):
        self.assertEqual(C.norm_screen("S-01 主列表"), "S-01")
        self.assertEqual(C.norm_screen("S02-任务详情"), "S-02")
        self.assertEqual(C.norm_screen("s3"), "S-03")
        self.assertIsNone(C.norm_screen("主列表"))

    def test_result_status_semantics(self):
        self.assertEqual(C.Result.pass_("G1", "a", "t").status, C.PASS)
        self.assertEqual(C.Result.fail("G1", "a", "t").status, C.FAIL)
        self.assertEqual(C.Result.blocked("G1", "a", "t").status, C.BLOCKED)
        self.assertEqual(C.Result.na("G1", "a", "t").status, C.NA)
        # BLOCKED 必须带原因
        blocked = C.Result.blocked("G1", "a", "t", reason="缺依赖")
        self.assertEqual(blocked.blocked_reason, "缺依赖")

    def test_every_rule_module_exposes_check(self):
        checks = {}
        for i in range(12):
            module = __import__("rules.g%d" % i, fromlist=["check"])
            self.assertTrue(callable(getattr(module, "check", None)),
                            "rules/g%d.py 必须暴露 check(ctx)" % i)
            checks[i] = module
        self.assertEqual(len(checks), 12)

    def test_rules_never_raise_on_empty_project(self):
        tmp = tempfile.mkdtemp(prefix="gate-empty-rules-")
        try:
            ctx = C.Context(tmp, manifest={"tier": "A"}, manifest_error="")
            for i in range(12):
                module = __import__("rules.g%d" % i, fromlist=["check"])
                results = module.check(ctx)
                self.assertIsInstance(results, list, "g%d.check 必须返回 list" % i)
                self.assertTrue(all(isinstance(r, C.Result) for r in results))
                # 空目录不许有 PASS（没东西可证明）
                self.assertFalse(any(r.status == C.PASS for r in results),
                                 "空目录上 g%d 不该有 PASS" % i)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# E. 夹具可重建性
# ---------------------------------------------------------------------------

class TestFixtureRebuild(unittest.TestCase):

    def test_make_py_regenerates_identically(self):
        """_make.py 必须可重复生成相同字节（否则哈希基线无法复现）。

        **不在原目录重建**：build_good_min() 先 rmtree 再写，重建期间其他
        测试的 copy_fixture 会撞上空目录（实测 10 次 1 次的 flaky）。
        改为在临时目录重建后与磁盘上的夹具逐文件比哈希 —— 验证的是
        "生成器可复现"，不需要污染源目录。
        """
        tmp = tempfile.mkdtemp(prefix="fx-regen-")
        try:
            dest = Path(tmp) / "regen"
            _make.main(["--dest", str(dest)])
            names = sorted(p.name for p in FIXTURES.iterdir()
                           if p.is_dir() and not p.name.startswith("__"))
            for name in names:
                expected = _make.snapshot(FIXTURES / name)
                actual = _make.snapshot(dest / name)
                self.assertEqual(expected, actual,
                                 "重建后的 %s 与磁盘上的不一致" % name)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_lock_hashes_match_files_on_disk(self):
        project = FIXTURES / "good-min"
        lock = (project / "BLUEPRINT/BLUEPRINT-LOCK.md").read_text(encoding="utf-8")
        pairs = re.findall(r"\| (BLUEPRINT/[\w./-]+) \| ([0-9a-f]{64}) \|", lock)
        self.assertGreaterEqual(len(pairs), 11, "冻结表至少覆盖 9 份蓝图 + 2 份契约")
        for rel, digest in pairs:
            self.assertEqual(C.sha256_file(project / rel), digest,
                             "%s 的哈希与磁盘不一致" % rel)

    def test_fixture_has_no_hardcoded_project_paths(self):
        """规则代码不许写死项目路径（manifest 驱动）。"""
        for path in sorted((GATES_DIR / "rules").glob("g*.py")):
            text = path.read_text(encoding="utf-8")
            # 去掉三引号字符串块：夹具生成器里写的是"被生成的代码"，不是它自己的依赖
            text = re.sub(r'"""[\s\S]*?"""', '""', text)
            text = re.sub(chr(39) * 3 + r"[\s\S]*?" + chr(39) * 3, chr(39) * 2, text)
            for bad in ("/Users/", "目标应用时间行事历", "gates/fixtures"):
                self.assertNotIn(bad, text,
                                 "%s 里写死了 %s，必须走 manifest/默认值" % (path.name, bad))

    def test_third_party_imports_absent(self):
        """除可选 yaml 外不许 import 真正的第三方包。

        用 ast 解析真实的 import 节点，**不用正则扫文本**：
        `_make.py` 会生成夹具源码（内含 `from flush import FlushResult` 这类字符串），
        正则会把字符串内容误判成真的 import —— 那是测试自身的缺陷，不是项目违规。

        放行：标准库、可选 yaml、本体系自有包（相对导入 / rules / flush）。
        """
        allowed = {"yaml"}
        # 本体系自有：gates/rules（run.py、_make.py 的 sys.path 根是 gates/）
        # 以及夹具 src/ 下的示例模块 flush
        local = {"rules", "common", "flush", "_make", "run"}
        targets = list((GATES_DIR / "rules").glob("*.py")) + [RUN_PY, FIXTURES / "_make.py"]
        for path in targets:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = [a.name.split(".")[0] for a in node.names]
                elif isinstance(node, ast.ImportFrom):
                    if node.level:            # 相对导入 = 本包内部
                        continue
                    names = [(node.module or "").split(".")[0]]
                else:
                    continue
                for module in names:
                    if not module:
                        continue
                    if module in sys.stdlib_module_names:
                        continue
                    if module in allowed or module in local:
                        continue
                    self.fail("%s 引入非标准库模块 %s" % (path.name, module))

if __name__ == "__main__":
    unittest.main(verbosity=2)
