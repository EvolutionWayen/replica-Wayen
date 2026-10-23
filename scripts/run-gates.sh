#!/usr/bin/env bash
# ============================================================
# 一键跑门（在任意项目目录里用）
#
# 用法：
#   ./scripts/run-gates.sh                 # 跑全部门
#   ./scripts/run-gates.sh G6              # 只跑 G6
#   ./scripts/run-gates.sh all --json      # 机读输出
#   ./scripts/run-gates.sh --project /path/to/project
#
# 说明：门禁引擎在体系根（本文件的上一级）的 gates/run.py。
#      本脚本只是给"在项目目录里工作"加一层便利包装。
# ============================================================
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KIT="$(cd "$HERE/.." && pwd)"
ENGINE="$KIT/gates/run.py"

PROJECT="."
STAGE="all"
EXTRA=()

while [ $# -gt 0 ]; do
  case "$1" in
    --project) PROJECT="$2"; shift 2 ;;
    -h|--help) sed -n '2,12p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) if [ "$STAGE" = "all" ]; then STAGE="$1"; else EXTRA+=("$1"); fi; shift ;;
  esac
done

if [ ! -f "$ENGINE" ]; then
  echo "门禁引擎缺失：$ENGINE" >&2
  echo "体系整合尚未完成，或路径不对。" >&2
  exit 2
fi

# 自动定位项目根（找 .replica/gate.manifest.yml）
if [ ! -f "$PROJECT/.replica/gate.manifest.yml" ]; then
  d="$(cd "$PROJECT" && pwd)"
  while [ "$d" != "/" ]; do
    if [ -f "$d/.replica/gate.manifest.yml" ]; then PROJECT="$d"; break; fi
    d="$(dirname "$d")"
  done
fi

echo "体系根：$KIT"
echo "项目根：$(cd "$PROJECT" && pwd)"
echo "阶段：  $STAGE"
echo

python3 "$ENGINE" --project "$PROJECT" --stage "$STAGE" "${EXTRA[@]+"${EXTRA[@]}"}"
code=$?

echo
case "$code" in
  0) echo "门禁结果：全部通过（或已批准的 N/A）" ;;
  1) echo "门禁结果：存在 FAIL —— 不许进下一阶段" ;;
  2) echo "门禁结果：存在 BLOCKED —— 环境/依赖问题，不是通过" ;;
  *) echo "门禁结果：引擎异常（退出码 $code）" ;;
esac
exit "$code"
