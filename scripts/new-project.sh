#!/usr/bin/env bash
# ============================================================
# 新项目骨架生成器
#
# 用法：
#   ./scripts/new-project.sh <目标目录> --target "目标应用 8.x" --tier A
#   ./scripts/new-project.sh ../my-clone --target "Calendly" --tier A --name "预约系统"
#
# 作用：把 templates/ 下的模板复制成一份可开工的项目骨架，
#      生成 .replica/gate.manifest.yml，并立刻跑一次 G0 门。
#
# 退出码：0 = 骨架生成且 G0 可跑；1 = 失败
# ============================================================
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"

TARGET_DIR=""
TARGET_NAME=""
PROJECT_NAME=""
TIER="A"
TIER_EXPLICIT=0

usage() {
  sed -n '2,14p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
  exit "${1:-0}"
}

while [ $# -gt 0 ]; do
  case "$1" in
    --target) TARGET_NAME="$2"; shift 2 ;;
    --name)   PROJECT_NAME="$2"; shift 2 ;;
    --tier)   TIER="$2"; TIER_EXPLICIT=1; shift 2 ;;
    -h|--help) usage 0 ;;
    -*) echo "未知参数：$1" >&2; usage 1 ;;
    *) TARGET_DIR="$1"; shift ;;
  esac
done

[ -n "$TARGET_DIR" ] || { echo "缺少目标目录" >&2; usage 1; }
[ -n "$TARGET_NAME" ] || { echo "缺少 --target（目标制品名 + 版本）" >&2; usage 1; }
case "$TIER" in A|B|C) ;; *) echo "档位只能是 A / B / C" >&2; exit 1 ;; esac

# 创建目录（若已存在且非空，拒绝覆盖）
if [ -d "$TARGET_DIR" ] && [ -n "$(ls -A "$TARGET_DIR" 2>/dev/null)" ]; then
  echo "目录已存在且非空：$TARGET_DIR" >&2
  echo "换一个目录，或先手动清空。" >&2
  exit 1
fi
mkdir -p "$TARGET_DIR" || exit 1
TARGET_DIR="$(cd "$TARGET_DIR" && pwd)"
PROJECT_NAME="${PROJECT_NAME:-$(basename "$TARGET_DIR")}"

echo "=== 生成项目骨架 ==="
echo "  目录：$TARGET_DIR"
echo "  制品：$TARGET_NAME"
echo "  档位：$TIER"
echo "  名称：$PROJECT_NAME"
echo

# ---------- 目录结构 ----------
for d in .replica BLUEPRINT BLUEPRINT/contracts BLUEPRINT/CHANGES \
         SPEC SPEC/DESIGN BUILD BUILD/WORK-PACKAGES TEST TEST/results \
         REPORT REPORT/release evidence screens clone-screens src tests e2e _archive; do
  mkdir -p "$TARGET_DIR/$d"
done
echo "  ✅ 目录结构 22 个"

# ---------- 模板复制 ----------
copy_tpl() {  # $1 = 源模板相对路径, $2 = 目标相对路径
  local src="$ROOT/$1" dst="$TARGET_DIR/$2"
  if [ -f "$src" ]; then
    cp "$src" "$dst" && echo "  ✅ $2"
  else
    echo "  ⚠️  模板缺失：$1（跳过，稍后手动补）"
  fi
}

copy_tpl "templates/engineering/PROJECT.template.md"            "PROJECT.md"
copy_tpl "templates/engineering/DECISIONS.template.md"          "DECISIONS.md"
copy_tpl "templates/engineering/REDLINES.template.md"           "REDLINES.md"
copy_tpl "templates/engineering/AGENTS.template.md"             "AGENTS.md"
copy_tpl "templates/engineering/STATE.template.md"              "STATE.md"
copy_tpl "templates/engineering/ARCHITECTURE.template.md"       "SPEC/ARCHITECTURE.md"
copy_tpl "templates/engineering/components.template.md"         "SPEC/DESIGN/components.md"
copy_tpl "templates/engineering/test-plan.template.md"          "TEST/test-plan.md"
copy_tpl "templates/engineering/parity.template.md"             "REPORT/parity.md"
copy_tpl "templates/engineering/feedback.template.md"           "REPORT/feedback.md"
copy_tpl "templates/engineering/runbook.template.md"            "REPORT/release/local-runbook.md"
copy_tpl "templates/blueprint/recon.template.md"                "BLUEPRINT/recon.md"
copy_tpl "templates/blueprint/features.template.csv"            "BLUEPRINT/features.csv"
copy_tpl "templates/blueprint/screens.template.csv"             "BLUEPRINT/screens.csv"
copy_tpl "templates/blueprint/menus.template.csv"               "BLUEPRINT/menus.csv"
copy_tpl "templates/blueprint/flows.template.md"                "BLUEPRINT/flows.md"
copy_tpl "templates/blueprint/linkage.template.csv"             "BLUEPRINT/linkage.csv"
copy_tpl "templates/blueprint/unknowns.template.csv"            "BLUEPRINT/unknowns.csv"
copy_tpl "templates/blueprint/state-machines.template.md"       "BLUEPRINT/state-machines.md"
copy_tpl "templates/blueprint/data-dictionary.template.md"      "BLUEPRINT/data-dictionary.md"

# 空文件占位（模板里没有的，先建空壳，门禁会报缺失）
[ -f "$TARGET_DIR/BLUEPRINT/features.csv" ] || printf 'feature_id,feature,area,priority,scope,original,progress,contract_ref,acceptance_ref,evidence,notes\n' > "$TARGET_DIR/BLUEPRINT/features.csv"
[ -f "$TARGET_DIR/SPEC/TRACEABILITY.csv" ] || printf 'feature_id,contract_ref,screen,menu_nodes,entities,commands,routes,tests,state\n' > "$TARGET_DIR/SPEC/TRACEABILITY.csv"
[ -f "$TARGET_DIR/SPEC/schema.sql" ] || printf -- '-- 数据库结构。S4 产出。\n' > "$TARGET_DIR/SPEC/schema.sql"
[ -f "$TARGET_DIR/TEST/bugs.md" ] || printf '# 缺陷台账\n\n| ID | 严重度 | 状态 | 现象 | 复现步骤 | 证据 | 修复提交 |\n|---|---|---|---|---|---|---|\n' > "$TARGET_DIR/TEST/bugs.md"
[ -f "$TARGET_DIR/BUILD/build-log.md" ] || printf '# 构建日志\n\n| 屏幕 | 日期 | 状态 | 缺什么 | 比预想难的地方 |\n|---|---|---|---|---|\n' > "$TARGET_DIR/BUILD/build-log.md"
[ -f "$TARGET_DIR/BLUEPRINT/contracts/.gitkeep" ] || : > "$TARGET_DIR/BLUEPRINT/contracts/.gitkeep"

# ---------- manifest ----------
TIER_UPPER="$(printf '%s' "$TIER" | tr '[:lower:]' '[:upper:]')"
BASELINE="$(cd "$ROOT/../.." 2>/dev/null && git rev-parse --short HEAD 2>/dev/null || echo unknown)"
cat > "$TARGET_DIR/.replica/gate.manifest.yml" <<YAML
project: $PROJECT_NAME
tier: $TIER_UPPER
target: "$TARGET_NAME"
baseline_commit: "$BASELINE"
created_at: "$(date +%Y-%m-%dT%H:%M%z | sed 's/\(..\)$/:&/')"

thresholds:
  parity_feature: 80
  consecutive_runs: 3

required:
  evidence_dirs: [evidence, screens]
  contract_sections: 16
  vertical_slice_evidence: SPEC/vertical-slice.md

# 经批准的 N/A（G3 后不许新增）
na_approved: []
YAML
echo "  ✅ .replica/gate.manifest.yml"

# ---------- 代码与测试占位 ----------
[ -f "$TARGET_DIR/src/.gitkeep" ] || : > "$TARGET_DIR/src/.gitkeep"
[ -f "$TARGET_DIR/tests/.gitkeep" ] || : > "$TARGET_DIR/tests/.gitkeep"
[ -f "$TARGET_DIR/e2e/.gitkeep" ] || : > "$TARGET_DIR/e2e/.gitkeep"

# ---------- .gitignore ----------
if [ ! -f "$TARGET_DIR/.gitignore" ]; then
cat > "$TARGET_DIR/.gitignore" <<'GI'
.DS_Store
_archive/
node_modules/
dist/
build/
out/
__pycache__/
*.pyc
.venv/
.env
*.db
*.db-wal
*.db-shm
!evidence/**/*.db
GI
echo "  ✅ .gitignore"
fi

# ---------- 生成工作说明 ----------
cat > "$TARGET_DIR/START-HERE.md" <<'MD'
# 从这里开始

1. 填 `PROJECT.md`：一句话定位、档位、不做清单 ≥5 条、目标制品身份（含 SHA-256）。
2. 填 `DECISIONS.md` 前 3 条、确认 `REDLINES.md` 与 `AGENTS.md`。
3. 跑门：`python3 <体系根>/gates/run.py --project . --stage G0`
   G0 不过不许往下走。
4. 读 `<体系根>/stages/S0-立项.md`，完成 S0 全部动作。
5. 之后按 `<体系根>/stages/S1-取证.md` → `S2-行为蓝图.md` → `S3-审查与冻结.md` 推进。

**关键提醒**：S1/S2 没做完、蓝图没冻结（G3 没过），不写业务代码。
MD
echo "  ✅ START-HERE.md"

# ---------- 跑一次 G0 ----------
echo
echo "=== 首跑 G0（预期失败：模板还没填） ==="
if [ -f "$ROOT/gates/run.py" ]; then
  python3 "$ROOT/gates/run.py" --project "$TARGET_DIR" --stage G0 || true
else
  echo "  ⚠️  门禁引擎尚未就绪：$ROOT/gates/run.py"
  echo "     （体系整合完成后即可用）"
fi

echo
echo "=== 完成 ==="
echo "下一步：编辑 $TARGET_DIR/PROJECT.md，然后重跑 G0。"
