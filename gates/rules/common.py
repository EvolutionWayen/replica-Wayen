# -*- coding: utf-8 -*-
"""门禁公共设施：Result、上下文、CSV / 哈希 / Markdown 标题 / manifest 读取。

设计约束（来自 00-体系总纲.md §3 与 templates/blueprint/SCHEMAS.md）：
- 只用 Python 标准库；yaml 可选，import 失败时用本文件内置的极简解析器。
- 任何输入异常都不得把异常栈抛给用户：规则 catch 后转 FAIL，run.py 再兜一层。
- 不写死任何项目路径或数字：阈值与文件位置一律来自 manifest 或本文件的 SCHEMAS 常量。

对外主要符号：
    Result / Gate / Context
    load_manifest() / parse_manifest_text()
    md_headings() / md_sections() / md_tables() / section_by_keyword()
    read_csv_text() / sha256_file()
    iter_text_files() / load_test_plan() / load_result_files() / latest_result()
    CONTRACT_HEADINGS / RECON_HEADINGS / *_COLUMNS / LOCK_REQUIRED_FILES
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# 枚举与 SCHEMAS 常量（只在这里出现一次，其它模块引用）
# ---------------------------------------------------------------------------

PASS, FAIL, BLOCKED, NA = "PASS", "FAIL", "BLOCKED", "NA"
STAGES = ["G%d" % i for i in range(12)]

PRIORITY_ENUM = {"must", "should", "could"}
PRIORITY_ALIAS = {"p0": "must", "p1": "should", "p2": "could"}
PROGRESS_ENUM = {"yes", "partial", "no", "skip"}
STATUS_ENUM = {"DRAFT", "APPROVED", "BUILT", "SELF-TESTED", "VERIFIED",
               "ACCEPTED", "RELEASED"}
TIER_ENUM = {"A", "B", "C"}
LINKAGE_STATUS = {"pending", "wired", "verified", "na"}
#: linkage 状态里「已接线」的状态；na 表示「确认不受影响」但必须登记理由
LINKAGE_WIRED_STATUS = {"wired", "verified"}
#: linkage 状态里「已考虑但确认不适用」的状态（不算 missing，计入已考虑面数）
LINKAGE_NA_STATUS = {"na"}
UNKNOWN_STATUS = {"open", "resolved", "accepted-risk", "out-of-scope"}
SCREEN_STATE_COLUMNS = ["state_filled", "state_empty", "state_loading", "state_error"]

#: SCHEMAS §5 的六面（跨页面联动的影响面）
#:
#: **唯一权威定义在 shared/faces.json**，本文件与 tools/linkage_matrix.py 都从那里读。
#: 改关键词只改 JSON 一处（此前两处各存一份，属于本体系自己明令禁止的"双写"）。
#: 读不到 JSON 时退回下面这份内置副本，并在 stderr 提示——保证门禁不会因为文件缺失而瘫痪。
#: 兜底：**只有名称，没有关键词**。
#:
#: 为什么故意不带关键词：如果兜底也存一份关键词，JSON 丢失时门禁会
#: 用一份可能已过期的词表**静默归类**——归错了看不出来，比直接失效危险得多。
#: 只有名称时，归类必然全部落到 unclassified，G2/G6 会立刻大面积 FAIL，
#: 一眼就知道"六面定义没读到"，而不是悄悄放过。
#: 名称本身不会漂移（改名的概率极低，且改了就说明该更新本文件）。
_FACE_FALLBACK = [
    {"key": "list", "name": "主列表", "desc": "任务/卡片列表、行内徽标、排序位置", "keywords": []},
    {"key": "badge", "name": "角标计数", "desc": "侧栏/标签/智能清单上的数字", "keywords": []},
    {"key": "detail", "name": "详情面板", "desc": "右侧详情、编辑态、属性区", "keywords": []},
    {"key": "calendar", "name": "日历/时间", "desc": "月/周视图、时间轴、时间选择器", "keywords": []},
    {"key": "search", "name": "搜索", "desc": "搜索结果、筛选、索引", "keywords": []},
    {"key": "remind", "name": "提醒/通知", "desc": "本地通知、提醒调度、角标调度", "keywords": []},
]


def _load_faces():
    """从 shared/faces.json 读取六面定义；失败则用内置副本并提示。"""
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))), "shared", "faces.json")
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        faces = data.get("faces") or []
        if len(faces) >= 6 and all("key" in f and "keywords" in f for f in faces):
            return faces
        raise ValueError("faces.json 结构不完整（需要 6 个含 key/keywords 的项）")
    except Exception as exc:  # 文件缺失/损坏都不该让门禁瘫痪
        sys.stderr.write(
            "[WARN] 未能读取 shared/faces.json（%s）。已退回"
            "『只有名称、没有关键词』的兜底定义：六面归类将全部落到 unclassified，"
            "G2/G6 会大面积 FAIL。这是有意为之——宁可明显失败，也不要用可能过期的"
            "关键词静默归类。\n" % exc)
        return [dict(f) for f in _FACE_FALLBACK]


SIX_FACES = _load_faces()

#: SCHEMAS §8 的 16 个二级标题（顺序即判定顺序，文字逐字比对）
CONTRACT_HEADINGS = [
    "1 目标与入口",
    "2 界面与层级",
    "3 每个菜单选项",
    "4 显示条件",
    "5 可用与选择条件",
    "6 筛选条件",
    "7 业务实现逻辑",
    "8 具体效果",
    "9 状态变化",
    "10 数据读取",
    "11 数据写入",
    "12 跨页面联动",
    "13 并发与生命周期",
    "14 撤销与恢复",
    "15 体验标准",
    "16 测试与证据",
]

#: SCHEMAS §1 的 recon.md 10 个二级标题
RECON_HEADINGS = [
    "1 目标制品与身份",
    "2 信息架构（屏幕树）",
    "3 全部入口清单",
    "4 核心用户流程",
    "5 模块与依赖关系",
    "6 数据模型概览",
    "7 可见区域与不可见区域",
    "8 未知与待验项",
    "9 证据索引",
    "10 规模判断与建议",
]

#: SCHEMAS 各 CSV 的列（顺序即契约）
FEATURES_COLUMNS = ["feature_id", "feature", "area", "priority", "scope", "original",
                    "progress", "contract_ref", "acceptance_ref", "evidence", "notes"]
SCREENS_COLUMNS = ["screen_id", "name", "entry", "exits", "purpose", "key_components",
                   "state_filled", "state_empty", "state_loading", "state_error",
                   "state_permission", "focus_restore", "flows", "notes"]
MENUS_COLUMNS = ["node_id", "parent_id", "path", "order", "type", "label", "shortcut",
                 "visibility_cond", "enabled_cond", "checked_cond", "command",
                 "contract_ref", "screens", "default_item", "notes"]
LINKAGE_COLUMNS = ["link_id", "source_id", "event", "affected_screen", "affected_control",
                   "data", "refresh_timing", "state_handling", "test_ref", "status"]
UNKNOWNS_COLUMNS = ["unknown_id", "area", "description", "impact", "evidence_gap",
                    "verification_action", "owner", "blocking", "status"]
TRACEABILITY_COLUMNS = ["feature_id", "contract_ref", "screen", "menu_nodes", "entities",
                        "commands", "routes", "tests", "state"]

#: G3 哈希表至少覆盖的蓝图文件（contracts/*.md 另行动态收集）
LOCK_REQUIRED_FILES = [
    "BLUEPRINT/recon.md",
    "BLUEPRINT/features.csv",
    "BLUEPRINT/screens.csv",
    "BLUEPRINT/menus.csv",
    "BLUEPRINT/flows.md",
    "BLUEPRINT/linkage.csv",
    "BLUEPRINT/state-machines.md",
    "BLUEPRINT/data-dictionary.md",
    "BLUEPRINT/unknowns.csv",
]

#: 冻结蓝图里不许出现的占位词（附录 A 第 7 条）
BANNED_PLACEHOLDERS = ["TODO", "FIXME", "待定", "待填", "待补", "TBD", "按原版", "视情况", "同前"]
TEMPLATE_PLACEHOLDERS = ["TODO", "FIXME", "待填", "待定", "TBD", "______", "<实体名>",
                         "<字段名>", "<screen_id>", "<FL-id>", "<功能名>"]

#: 输入文件「空值」的合法写法（SCHEMAS §0.4）
BLANK_VALUES = {"", "-", "—", "–", "n/a", "na", "无"}

DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
ISO_DATETIME_RE = re.compile(
    r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2})?(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})")
URL_RE = re.compile(r"https?://[^\s\)\]|>\"'，。；]+")
SHA256_RE = re.compile(r"\b[0-9a-fA-F]{64}\b")
FEATURE_ID_RE = re.compile(r"^F-[A-Z0-9-]+$")
TEST_ID_RE = re.compile(r"^T-[A-Za-z0-9-]+$")
SCREEN_ID_RE = re.compile(r"\bS[-\s_]?0*(\d{1,2})\b", re.I)

#: gates/ 的上一级（体系根），用于定位 replica-skill 里的可选脚本
SYSTEM_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------

class Result:
    """一条判定结果。ok=True→PASS；False→FAIL；None 且带 blocked_reason→BLOCKED；否则 NA。"""

    __slots__ = ("stage", "code", "title", "ok", "expected", "actual",
                 "evidence", "hint", "blocked_reason")

    def __init__(self, stage, code, title, ok, expected="", actual="",
                 evidence="", hint="", blocked_reason=""):
        self.stage = stage
        self.code = code
        self.title = title
        self.ok = ok
        self.expected = expected
        self.actual = actual
        self.evidence = evidence
        self.hint = hint
        self.blocked_reason = blocked_reason

    @property
    def status(self):
        if self.ok is True:
            return PASS
        if self.ok is False:
            return FAIL
        return BLOCKED if self.blocked_reason else NA

    @classmethod
    def pass_(cls, stage, code, title, **kw):
        return cls(stage, code, title, True, **kw)

    @classmethod
    def fail(cls, stage, code, title, **kw):
        return cls(stage, code, title, False, **kw)

    @classmethod
    def blocked(cls, stage, code, title, reason="", **kw):
        kw["blocked_reason"] = reason or kw.get("blocked_reason") or "环境或前置缺失"
        return cls(stage, code, title, None, **kw)

    @classmethod
    def na(cls, stage, code, title, reason="", **kw):
        # NA 不设 blocked_reason，理由放 hint/actual，便于人类阅读
        if reason and not kw.get("hint"):
            kw["hint"] = reason
        return cls(stage, code, title, None, **kw)

    def as_dict(self):
        return {
            "stage": self.stage,
            "code": self.code,
            "title": self.title,
            "status": self.status,
            "expected": self.expected,
            "actual": self.actual,
            "evidence": self.evidence,
            "hint": self.hint,
            "blocked_reason": self.blocked_reason,
        }

    def __repr__(self):  # 调试用
        return "<%s %s %s>" % (self.status, self.code, self.title)


# ---------------------------------------------------------------------------
# 极简 YAML 解析（只覆盖 gate.manifest.yml 用得到的子集）
# ---------------------------------------------------------------------------

def _strip_comment(value):
    """去掉行内注释：仅在 # 前有空白、且不在引号内时生效。"""
    out, quote, prev = [], "", ""
    for ch in value:
        if quote:
            out.append(ch)
            if ch == quote:
                quote = ""
            continue
        if ch in "\"'":
            quote = ch
            out.append(ch)
            continue
        if ch == "#" and prev in (" ", "\t"):
            break
        out.append(ch)
        prev = ch
    return "".join(out).strip()


def _scalar(text):
    s = _strip_comment(text.strip())
    if s == "":
        return ""
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
        return s[1:-1]
    low = s.lower()
    if low in ("true", "yes", "on"):
        return True
    if low in ("false", "no", "off"):
        return False
    if low in ("null", "~"):
        return None
    if s.startswith("[") and s.endswith("]"):
        inner = s[1:-1].strip()
        if not inner:
            return []
        return [_scalar(x) for x in inner.split(",")]
    if re.fullmatch(r"[+-]?\d+", s):
        return int(s)
    if re.fullmatch(r"[+-]?\d+\.\d+", s):
        return float(s)
    return s


class _MiniYAML:
    """按缩进解析 dict / list / 标量。列表项支持 `- key: value` 加续行。"""

    def __init__(self, text):
        self.lines = []
        for raw in text.splitlines():
            if not raw.strip():
                continue
            stripped = raw.lstrip(" ")
            if stripped.startswith("#"):
                continue
            if "\t" in raw[:len(raw) - len(stripped)]:
                raw = raw.replace("\t", "  ")
                stripped = raw.lstrip(" ")
            self.lines.append((len(raw) - len(stripped), stripped.rstrip()))
        self.i = 0

    def parse(self):
        if not self.lines:
            return {}
        value = self._block(self.lines[0][0])
        return value if isinstance(value, dict) else {"items": value}

    def _block(self, indent):
        if self.i >= len(self.lines):
            return {}
        ind, content = self.lines[self.i]
        if content.startswith("-"):
            return self._list(ind)
        return self._dict(ind)

    def _dict(self, indent):
        out = {}
        while self.i < len(self.lines):
            ind, content = self.lines[self.i]
            if ind < indent:
                break
            if ind > indent:            # 缩进异常，跳过，避免死循环
                self.i += 1
                continue
            if content.startswith("-"):
                break
            key, sep, rest = content.partition(":")
            if not sep:
                self.i += 1
                continue
            key = key.strip()
            rest = rest.strip()
            self.i += 1
            if rest:
                out[key] = _scalar(rest)
            elif self.i < len(self.lines):
                n_ind, n_content = self.lines[self.i]
                if n_ind > indent:
                    out[key] = self._block(n_ind)
                elif n_ind == indent and n_content.startswith("-"):
                    out[key] = self._list(n_ind)
                else:
                    out[key] = {}
            else:
                out[key] = {}
        return out

    def _list(self, indent):
        out = []
        while self.i < len(self.lines):
            ind, content = self.lines[self.i]
            if ind < indent:
                break
            if ind != indent or not content.startswith("-"):
                break
            item = content[1:].strip()
            self.i += 1
            if not item:
                if self.i < len(self.lines) and self.lines[self.i][0] > indent:
                    out.append(self._block(self.lines[self.i][0]))
                else:
                    out.append(None)
                continue
            if ":" in item and not item.startswith("["):
                key, _, rest = item.partition(":")
                entry = {key.strip(): _scalar(rest) if rest.strip() else None}
                while self.i < len(self.lines):
                    c_ind, c_content = self.lines[self.i]
                    if c_ind <= indent or c_content.startswith("-"):
                        break
                    k2, sep2, r2 = c_content.partition(":")
                    if sep2:
                        entry[k2.strip()] = _scalar(r2)
                    self.i += 1
                out.append(entry)
            else:
                out.append(_scalar(item))
        return out


def parse_manifest_text(text, where=""):
    """解析 manifest 文本，返回 dict；解析失败抛 ValueError（由调用方转 BLOCKED）。"""
    try:
        import yaml  # type: ignore  # 可选依赖
        data = yaml.safe_load(text)
        if data is None:
            return {}
        if not isinstance(data, dict):
            raise ValueError("顶层不是映射（key: value）")
        return data
    except ImportError:
        return _MiniYAML(text).parse()
    except ValueError:
        raise
    except Exception:  # yaml 语法错误等
        return _MiniYAML(text).parse()


# ---------------------------------------------------------------------------
# Context
# ---------------------------------------------------------------------------

class Context:
    """一次门禁运行的项目上下文（只读）。"""

    MANIFEST_REL = ".replica/gate.manifest.yml"

    def __init__(self, root, manifest=None, manifest_error="", manifest_path=None):
        self.root = Path(root)
        self.manifest = manifest if isinstance(manifest, dict) else {}
        self.manifest_error = manifest_error or ""
        self.manifest_path = manifest_path or (self.root / self.MANIFEST_REL)
        self._text_cache = {}
        self._csv_cache = {}

    # ---- 基础 ----
    @property
    def manifest_found(self):
        """manifest 真的可用：既解析成功了，磁盘上也确实存在这个文件。

        只检查 `self.manifest` 非空是不够的（调用方可以手工塞一个 dict 进来，
        或者会话从 snapshot 恢复），那会让「空目录」也跑出 PASS —— 假绿。
        """
        if not self.manifest or self.manifest_error:
            return False
        try:
            return Path(self.manifest_path).is_file()
        except OSError:
            return False

    def path(self, rel):
        if rel is None:
            return self.root
        return self.root / str(rel).replace("\\", "/")

    def rel(self, p):
        try:
            return str(Path(p).resolve().relative_to(self.root.resolve())).replace(os.sep, "/")
        except Exception:
            return str(p)

    def exists(self, rel):
        return self.path(rel).is_file()

    def size(self, rel):
        try:
            return self.path(rel).stat().st_size
        except OSError:
            return -1

    def read_bytes(self, rel):
        try:
            return self.path(rel).read_bytes()
        except OSError:
            return None

    def text(self, rel):
        """读文本（UTF-8，容错 BOM）；不存在/读失败返回 None。带缓存。"""
        key = str(rel)
        if key in self._text_cache:
            return self._text_cache[key]
        data = self.read_bytes(rel)
        if data is None:
            self._text_cache[key] = None
            return None
        try:
            value = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            value = data.decode("utf-8", errors="replace")
        self._text_cache[key] = value
        return value

    def lines(self, rel):
        value = self.text(rel)
        return None if value is None else value.splitlines()

    def sha256(self, rel):
        data = self.read_bytes(rel)
        if data is None:
            return None
        return hashlib.sha256(data).hexdigest()

    # ---- manifest 取值 ----
    @property
    def tier(self):
        tier = str(self.manifest.get("tier") or "").strip().upper()
        return tier if tier in TIER_ENUM else ""

    def cfg(self, key, default=None):
        """读 manifest 顶层键；也接受 required.<key>。"""
        if key in self.manifest and self.manifest[key] not in (None, ""):
            return self.manifest[key]
        req = self.manifest.get("required")
        if isinstance(req, dict) and req.get(key) not in (None, ""):
            return req[key]
        return default

    @property
    def thresholds(self):
        raw = self.manifest.get("thresholds")
        raw = raw if isinstance(raw, dict) else {}
        def _int(key, default):
            try:
                return int(str(raw.get(key, default)).strip())
            except (TypeError, ValueError):
                return default
        out = {
            "parity_feature": _int("parity_feature", 80),
            "consecutive_runs": max(1, _int("consecutive_runs", 3)),
        }
        return out

    @property
    def required(self):
        raw = self.manifest.get("required")
        return raw if isinstance(raw, dict) else {}

    @property
    def na_approved(self):
        """{code: entry}；列表项允许是 dict(id/reason/...) 或纯字符串。"""
        out = {}
        raw = self.manifest.get("na_approved")
        if isinstance(raw, dict):
            raw = [raw]
        if isinstance(raw, list):
            for item in raw:
                if isinstance(item, dict):
                    code = str(item.get("id") or item.get("code") or "").strip()
                    if code:
                        out[code] = item
                elif isinstance(item, str) and item.strip():
                    out[item.strip()] = {"id": item.strip(), "reason": ""}
        return out

    @property
    def strict_na(self):
        value = self.manifest.get("strict_na")
        if isinstance(value, bool):
            return value
        return True  # R20：N/A 必须带理由并登记，默认严格

    # ---- CSV ----
    def csv(self, rel):
        """返回 (rows, fieldnames, error)。rows 为 list[dict]；失败时 rows=None。"""
        key = str(rel)
        if key in self._csv_cache:
            return self._csv_cache[key]
        text = self.text(rel)
        if text is None:
            result = (None, [], "文件不存在或不可读：%s" % rel)
            self._csv_cache[key] = result
            return result
        try:
            rows, fields = read_csv_text(text)
            result = (rows, fields, "")
        except Exception as exc:  # csv 格式异常
            result = (None, [], "CSV 解析失败：%s" % exc)
        self._csv_cache[key] = result
        return result


class Gate:
    """一道门的收集器：带 stage 前缀的 Result 工厂 + 两个高频判定原语。"""

    def __init__(self, ctx, stage):
        self.ctx = ctx
        self.stage = stage
        self.results = []

    # ---- 结果工厂 ----
    def _code(self, code):
        code = str(code)
        return code if code.startswith(self.stage + ".") else "%s.%s" % (self.stage, code)

    def add(self, result):
        self.results.append(result)
        return result

    def pass_(self, code, title, **kw):
        return self.add(Result.pass_(self.stage, self._code(code), title, **kw))

    def fail(self, code, title, **kw):
        return self.add(Result.fail(self.stage, self._code(code), title, **kw))

    def blocked(self, code, title, reason="", **kw):
        return self.add(Result.blocked(self.stage, self._code(code), title, reason=reason, **kw))

    def na(self, code, title, reason="", **kw):
        return self.add(Result.na(self.stage, self._code(code), title, reason=reason, **kw))

    # ---- 原语 ----
    def no_manifest(self):
        """manifest 缺失/不可解析时登记一条 BLOCKED 并返回 True，规则应立即 return。"""
        if self.ctx.manifest_found:
            return False
        reason = self.ctx.manifest_error or "未找到 .replica/gate.manifest.yml"
        self.blocked(
            "manifest",
            "门禁清单存在且可解析",
            reason=reason,
            expected=".replica/gate.manifest.yml 存在、可解析、含合法 tier",
            actual=reason,
            evidence=Context.MANIFEST_REL,
            hint=("运行 scripts/new-project.sh <目录> --target \"<制品名 版本>\" 生成骨架，"
                  "或按 templates/blueprint/SCHEMAS.md §15 手写 .replica/gate.manifest.yml"),
        )
        return True

    def need_file(self, rel, code, title, expect="文件存在且非空", hint="", allow_empty=False):
        """要求文件存在（默认还要非空）。命中登记 PASS，否则登记 FAIL 并返回 False。"""
        size = self.ctx.size(rel)
        if size >= 0 and (allow_empty or size > 0):
            self.pass_(code, title, expected=expect,
                       actual=("存在，%d 字节" % size), evidence=rel)
            return True
        if size < 0:
            actual, default_hint = "文件不存在", "创建 %s（格式见 templates/blueprint/SCHEMAS.md）" % rel
        else:
            actual, default_hint = "文件存在但为空", "填写 %s 的内容" % rel
        self.fail(code, title, expected=expect, actual=actual, evidence=rel,
                  hint=hint or default_hint)
        return False

    def read_csv(self, rel, columns, code, title, allow_missing=False):
        """读 CSV 并校验列名与 SCHEMAS 一致。成功返回 rows，失败返回 rows/None。

        校验口径（SCHEMAS §0.2）：SCHEMAS 的列必须按序出现在表头**前段**；
        新增列只允许加在末尾，所以 `fields[:len(columns)] == columns` 即通过。
        改名 / 删列 / 插在中间一律 FAIL。

        allow_missing=True 时，文件缺失不登记结果（交给 need_file 报），返回 None。
        """
        rows, fields, err = self.ctx.csv(rel)
        if rows is None:
            if allow_missing:
                return None
            self.fail(code, title, expected="CSV 可按 UTF-8 解析",
                      actual=err, evidence=rel,
                      hint="用 UTF-8 逗号分隔重写该文件，首行为表头")
            return None
        if list(fields[:len(columns)]) != list(columns):
            missing = [c for c in columns if c not in fields]
            extra = [c for c in fields if c not in columns]
            detail = []
            if missing:
                detail.append("缺列：%s" % ", ".join(missing))
            if extra:
                detail.append("不在 SCHEMAS 的列：%s" % ", ".join(extra))
            if not missing and not extra:
                detail.append("列顺序与 SCHEMAS 不一致")
            self.fail(code, title,
                      expected="列名与顺序 = %s（新增列只许加在末尾）" % ", ".join(columns),
                      actual="；".join(detail) or "列名不一致",
                      evidence=rel,
                      hint="按 templates/blueprint/SCHEMAS.md 的列名与顺序修正表头"
                           "（不改名、不删列、不插在中间）")
            return rows
        appended = len(fields) - len(columns)
        self.pass_(code, title, expected="列名与顺序正确",
                   actual="%d 行数据%s" % (len(rows),
                                          "，末尾追加 %d 列" % appended if appended > 0 else ""),
                   evidence=rel)
        return rows


def read_csv_text(text):
    """解析 CSV 文本，返回 (rows, fieldnames)。自动去 BOM、去空白。"""
    reader = csv.reader(io.StringIO(text, newline=""))
    try:
        fieldnames = next(reader)
    except StopIteration:
        return [], []
    fieldnames = [str(x).strip().lstrip("\ufeff") for x in fieldnames]
    rows = []
    for raw in reader:
        if not any(str(c).strip() for c in raw):
            continue  # 跳过纯空行
        row = {}
        for i, name in enumerate(fieldnames):
            row[name] = str(raw[i]).strip() if i < len(raw) else ""
        rows.append(row)
    return rows, fieldnames


# ---------------------------------------------------------------------------
# Markdown 解析
# ---------------------------------------------------------------------------

_FENCE_RE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")


def iter_md_lines(text):
    """逐行产出 (行号, 原文, 是否在代码围栏内)。围栏行本身标记为 fenced。"""
    in_fence = False
    fence_char = ""
    for no, raw in enumerate(text.splitlines(), 1):
        m = _FENCE_RE.match(raw)
        if m:
            marker = m.group(1)
            if not in_fence:
                in_fence, fence_char = True, marker[0]
            elif marker[0] == fence_char:
                in_fence = False
            yield no, raw, True
            continue
        yield no, raw, in_fence


def md_headings(text, max_level=6):
    """返回 [(level, title, line_no)]，跳过代码围栏内的伪标题。"""
    out = []
    for no, raw, fenced in iter_md_lines(text):
        if fenced:
            continue
        m = re.match(r"^(#{1,6})\s+(.*?)\s*$", raw)
        if m and len(m.group(1)) <= max_level:
            out.append((len(m.group(1)), m.group(2).strip(), no))
    return out


def md_sections(text, level=2, max_level=6):
    """按指定层级标题切段。返回 [{'title','level','line','body','lines'}]。

    段体到下一个「层级 <= level」的标题为止（子标题保留在 body 里）。
    """
    heads = md_headings(text, max_level=max_level)
    all_lines = text.splitlines()
    out = []
    for idx, (lvl, title, no) in enumerate(heads):
        if lvl != level:
            continue
        end = len(all_lines)
        for lvl2, _t2, no2 in heads[idx + 1:]:
            if lvl2 <= level:
                end = no2 - 1
                break
        body_lines = all_lines[no:end]
        out.append({
            "title": title,
            "level": lvl,
            "line": no,
            "body": "\n".join(body_lines).strip(),
            "lines": body_lines,
        })
    return out


def section_by_keyword(sections, keywords):
    """返回第一个标题含任一关键词的段；关键词大小写不敏感。"""
    keys = [k.lower() for k in keywords]
    for sec in sections:
        title = sec["title"].lower()
        if any(k in title for k in keys):
            return sec
    return None


def _split_table_row(line):
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|") and not s.endswith("\\|"):
        s = s[:-1]
    cells, buf, esc = [], [], False
    for ch in s:
        if esc:
            buf.append(ch)
            esc = False
        elif ch == "\\":
            esc = True
        elif ch == "|":
            cells.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    cells.append("".join(buf))
    return [c.strip() for c in cells]


def _is_table_sep(cells):
    return bool(cells) and all(re.fullmatch(r":?-{2,}:?", c.strip()) for c in cells)


def md_tables(text):
    """解析所有 Markdown 表格。

    返回 [{'header': [...], 'rows': [[cells...]], 'lines': [行号], 'line': 起始行}]。
    无表头（首行即数据）时 header 为 []。表格内单元格允许空串。
    """
    tables, cur, cur_lines, start = [], [], [], 0

    def flush():
        if not cur:
            return
        header, rows, lines = [], [], []
        start_no = cur_lines[0]
        if len(cur) >= 2 and _is_table_sep(cur[1]):
            header = cur[0]
            data = cur[2:]
            data_lines = cur_lines[2:]
        elif _is_table_sep(cur[0]):
            data = cur[1:]
            data_lines = cur_lines[1:]
        else:
            data = cur
            data_lines = cur_lines
        for cells, no in zip(data, data_lines):
            rows.append(cells)
            lines.append(no)
        tables.append({"header": header, "rows": rows, "lines": lines, "line": start_no})

    for no, raw, fenced in iter_md_lines(text):
        s = raw.strip()
        if not fenced and s.startswith("|") and s.count("|") >= 2:
            if not cur:
                start = no
            cur.append(_split_table_row(raw))
            cur_lines.append(no)
        else:
            if cur:
                flush()
            cur, cur_lines = [], []
    flush()
    return tables


# ---------------------------------------------------------------------------
# 通用小工具
# ---------------------------------------------------------------------------

def cell(row, name, default=""):
    if not isinstance(row, dict):
        return default
    value = row.get(name)
    if value is None:
        return default
    return str(value).strip()


def is_blank(value):
    if value is None:
        return True
    return str(value).strip().lower() in BLANK_VALUES


def normalize_priority(value):
    v = (value or "").strip().lower()
    return PRIORITY_ALIAS.get(v, v)


def norm_screen(value):
    """把 'S-01 主列表' / 'S02-任务详情' / 's1' 统一成 'S-01'。"""
    if not value:
        return None
    m = SCREEN_ID_RE.search(str(value))
    if not m:
        return None
    return "S-%02d" % int(m.group(1))


def split_refs(value):
    """把 'T-101;T-102' / 'T-101, T-102' / 'T-101、T-102' 拆成列表。"""
    if is_blank(value):
        return []
    return [x.strip() for x in re.split(r"[;,、\s]+", str(value)) if x.strip()]


def find_placeholders(text, tokens=None):
    """返回命中的占位词 [(token, line_no)]。"""
    tokens = tokens or BANNED_PLACEHOLDERS
    hits = []
    for no, raw, fenced in iter_md_lines(text):
        if fenced:
            continue
        for tok in tokens:
            if tok in raw:
                hits.append((tok, no))
    return hits


def line_of(text, needle):
    for no, raw in enumerate(text.splitlines(), 1):
        if needle in raw:
            return no
    return 1


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def iter_text_files(base, exts=None, skip_dirs=None, max_bytes=2_000_000):
    """遍历文本文件，产出 (Path, rel_str)。跳过隐藏目录、__pycache__ 等。"""
    base = Path(base)
    if not base.is_dir():
        return
    skip = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build",
            ".mypy_cache", ".pytest_cache", "coverage", ".next", ".turbo"}
    if skip_dirs:
        skip.update(skip_dirs)
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if d not in skip and not d.startswith(".")]
        for name in sorted(filenames):
            if name.startswith("."):
                continue
            p = Path(dirpath) / name
            if exts and p.suffix.lower() not in exts:
                continue
            try:
                if p.stat().st_size > max_bytes:
                    continue
            except OSError:
                continue
            yield p


def scan_for_tokens(paths, tokens):
    """在给定文件里找关键词，返回 [(rel_path, line_no, token, line_text)]。"""
    hits = []
    for rel in paths:
        p = Path(rel) if isinstance(rel, Path) else None
        if p is None:
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for no, raw in enumerate(text.splitlines(), 1):
            for tok in tokens:
                if tok in raw:
                    hits.append((str(p), no, tok, raw.strip()[:160]))
                    break
    return hits


# ---------------------------------------------------------------------------
# manifest / 测试结果 / 用例表
# ---------------------------------------------------------------------------

def load_manifest(root):
    """读 <root>/.replica/gate.manifest.yml。

    返回 (manifest_dict, error_str)。error 非空表示没找到或解析失败（G 门全部 BLOCKED）。
    """
    path = Path(root) / Context.MANIFEST_REL
    if not path.is_file():
        return {}, "未找到 %s" % Context.MANIFEST_REL
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        return {}, "无法读取 %s：%s" % (Context.MANIFEST_REL, exc)
    if not text.strip():
        return {}, "%s 是空文件" % Context.MANIFEST_REL
    try:
        data = parse_manifest_text(text)
    except Exception as exc:
        return {}, "manifest 解析失败：%s" % exc
    if not isinstance(data, dict) or not data:
        return {}, "manifest 内容为空或格式不对"
    return data, ""


def load_result_files(ctx):
    """返回 [(Path, data|None, error)]，按文件名排序（时间前缀约定）。"""
    directory = ctx.path("TEST/results")
    out = []
    if not directory.is_dir():
        return out
    for p in sorted(directory.glob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8-sig"))
            out.append((p, data if isinstance(data, dict) else None,
                        "" if isinstance(data, dict) else "顶层不是 JSON 对象"))
        except (OSError, ValueError) as exc:
            out.append((p, None, "解析失败：%s" % exc))
    return out


def latest_result(ctx):
    """返回 (Path, data, error) 或 (None, None, '没有结果文件')。"""
    files = load_result_files(ctx)
    if not files:
        return None, None, "TEST/results/ 下没有 *.json 结果文件"
    return files[-1]


def result_case_status(data):
    """{T-id: status}。status 统一小写。"""
    out = {}
    cases = data.get("cases") if isinstance(data, dict) else None
    if isinstance(cases, list):
        for case in cases:
            if not isinstance(case, dict):
                continue
            cid = str(case.get("id") or case.get("case") or "").strip()
            if cid:
                out[cid] = str(case.get("status") or "").strip().lower()
    return out


def load_test_plan(ctx):
    """解析 TEST/test-plan.md 的用例表。

    返回 (rows, error)。rows: [{'id','type','steps','expect','auto','line'}]。
    识别规则：表头首列含 T-/用例/ID 的表格视为用例表。
    """
    text = ctx.text("TEST/test-plan.md")
    if text is None:
        return [], "TEST/test-plan.md 不存在"
    rows = []
    for table in md_tables(text):
        header = table.get("header") or []
        if not header:
            continue
        first = header[0].lower()
        if not any(k in first for k in ("t-", "用例", "id")):
            continue
        idx = {}
        for i, name in enumerate(header):
            low = name.lower()
            if "类型" in name or low == "type":
                idx.setdefault("type", i)
            elif "步骤" in name or "step" in low:
                idx.setdefault("steps", i)
            elif "期望" in name or "expect" in low or "结果" in name:
                idx.setdefault("expect", i)
            elif "自动" in name or "auto" in low:
                idx.setdefault("auto", i)
        for cells, no in zip(table["rows"], table["lines"]):
            if not cells:
                continue
            def pick(key):
                i = idx.get(key)
                return cells[i] if i is not None and i < len(cells) else ""
            rows.append({
                "id": cells[0],
                "cells": cells,
                "type": pick("type"),
                "steps": pick("steps"),
                "expect": pick("expect"),
                "auto": pick("auto"),
                "line": no,
            })
    if not rows:
        return [], "test-plan.md 里没找到以 T-xxx 开头的用例表"
    return rows, ""


def iter_stage_modules():
    """按顺序返回 [(stage, module_name)]，供 run.py 动态导入。"""
    return [("G%d" % i, "g%d" % i) for i in range(12)]


# ---------------------------------------------------------------------------
# 蓝图 CSV 的便捷读取（规则模块共用；文件缺失返回空列表）
# ---------------------------------------------------------------------------

def csv_rows(ctx, rel):
    rows, _fields, _err = ctx.csv(rel)
    return rows or []


def features(ctx):
    return csv_rows(ctx, "BLUEPRINT/features.csv")


def screens(ctx):
    return csv_rows(ctx, "BLUEPRINT/screens.csv")


def menus(ctx):
    return csv_rows(ctx, "BLUEPRINT/menus.csv")


def linkage(ctx):
    return csv_rows(ctx, "BLUEPRINT/linkage.csv")


def unknowns(ctx):
    return csv_rows(ctx, "BLUEPRINT/unknowns.csv")


def traceability(ctx):
    return csv_rows(ctx, "SPEC/TRACEABILITY.csv")


def must_features(ctx, include_out=False):
    """priority=must（兼容 P0）且 scope != out 的功能行。"""
    out = []
    for row in features(ctx):
        if normalize_priority(cell(row, "priority")) != "must":
            continue
        if not include_out and (cell(row, "scope") or "in").lower() == "out":
            continue
        out.append(row)
    return out


def in_scope(ctx):
    return [row for row in features(ctx)
            if (cell(row, "scope") or "in").lower() != "out"]


def contract_path(value):
    """把 contract_ref 的各种写法统一成项目内相对路径。"""
    v = (value or "").strip().strip("`").replace("\\", "/")
    if not v or v in BLANK_VALUES:
        return ""
    if v.startswith("BLUEPRINT/"):
        return v
    if v.startswith("./BLUEPRINT/"):
        return v[2:]
    if v.startswith("contracts/"):
        return "BLUEPRINT/" + v
    if v.startswith("./contracts/"):
        return "BLUEPRINT/" + v[2:]
    if v.endswith(".md"):
        return "BLUEPRINT/contracts/" + v.rsplit("/", 1)[-1]
    return v


def contract_files(ctx):
    """BLUEPRINT/contracts/*.md 的项目相对路径列表（不含 .gitkeep）。"""
    directory = ctx.path("BLUEPRINT/contracts")
    out = []
    if not directory.is_dir():
        return out
    for p in sorted(directory.glob("*.md")):
        out.append("BLUEPRINT/contracts/" + p.name)
    return out


def screen_four_states(row):
    """返回 (ok, detail)：四态列是否齐（yes，或 '-' 且 notes 有理由）。"""
    notes = cell(row, "notes")
    bad = []
    for col in SCREEN_STATE_COLUMNS:
        value = cell(row, col).lower()
        if value == "yes":
            continue
        if value in BLANK_VALUES and len(notes) >= 4:
            continue
        bad.append("%s=%r" % (col, cell(row, col)))
    return (not bad), bad


def screen_index(ctx):
    """{S-01: row}（同号后出现的覆盖前面的）。"""
    out = {}
    for row in screens(ctx):
        key = norm_screen(cell(row, "screen_id"))
        if key:
            out[key] = row
    return out


# ---------------------------------------------------------------------------
# 六面归类（G2 / G6 共用；口径与 tools/linkage_matrix.py 一致）
# ---------------------------------------------------------------------------

def classify_faces(control, faces=None):
    """把 affected_control / affected_screen 文本归到六面 key 列表。

    优先识别显式标记 `#主列表` / `#list`；否则按关键词匹配（一面只记一次）。
    与 tools/linkage_matrix.py 的 classify() 同口径，便于两处结论一致。
    """
    faces = faces or SIX_FACES
    text = (control or "").lower()
    hits = []
    for face in faces:
        if ("#" + face["name"]).lower() in text or ("#" + face["key"]) in text:
            hits.append(face["key"])
    if hits:
        return hits
    for face in faces:
        for kw in face.get("keywords", []):
            if kw.lower() in text:
                hits.append(face["key"])
                break
    return hits


def face_names_text(sep="、"):
    """六面名称的展示串（给 hint/expected 文案用，避免各处手写名称漂移）。"""
    return sep.join(f["name"] for f in SIX_FACES)


def face_name(key):
    for face in SIX_FACES:
        if face["key"] == key:
            return face["name"]
    return key


def linkage_faces(rows):
    """给一组 linkage 行算出六面归类结果。

    返回 {
      'faces': {face_key: [row, ...]},      # 每面命中的行（含 na / pending）
      'wired': {face_key: [row, ...]},      # 每面里 wired/verified 的行
      'na':    {face_key: [row, ...]},      # 每面里 na 的行
      'unclassified': [row, ...],           # 无法归到任何面的行
      'covered': [face_key, ...],           # 有 wired/verified 的面
      'considered': [face_key, ...],        # 有行（wired/verified/na/pending）的面
      'all_na': bool,                       # 有行，且**每一行**都是 na
    }

    说明：`all_na` 只看 na，不看 pending。pending 表示「还没接上」，
    该由 G6 的接线检查报，不该在蓝图阶段被误报成「没做六面分析」。
    """
    faces = {f["key"]: [] for f in SIX_FACES}
    wired = {f["key"]: [] for f in SIX_FACES}
    na = {f["key"]: [] for f in SIX_FACES}
    unclassified = []
    for row in rows:
        status = cell(row, "status").lower()
        text = " ".join([
            cell(row, "affected_control"), cell(row, "affected_screen"),
            cell(row, "data"), cell(row, "event"),
        ])
        hits = classify_faces(text)
        if not hits:
            unclassified.append(row)
            continue
        for key in hits:
            faces[key].append(row)
            if status in LINKAGE_WIRED_STATUS:
                wired[key].append(row)
            elif status in LINKAGE_NA_STATUS:
                na[key].append(row)
    covered = [k for k in faces if wired[k]]
    considered = [k for k in faces if faces[k]]
    all_na = bool(rows) and all(
        cell(r, "status").lower() in LINKAGE_NA_STATUS for r in rows)
    return {
        "faces": faces,
        "wired": wired,
        "na": na,
        "unclassified": unclassified,
        "covered": covered,
        "considered": considered,
        "all_na": all_na,
    }


def repo_root():
    return SYSTEM_ROOT
