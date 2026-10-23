#!/usr/bin/env bash
# 启动脚本（A 档）：建库、启动自检、可选备份模式。
set -euo pipefail
DB_HOME="$HOME/Library/Application Support/good-min"
DB="$DB_HOME/app.db"
mkdir -p "$DB_HOME"

if [ "${1:-}" = "--backup-only" ]; then
  mkdir -p backups
  sqlite3 "$DB" "PRAGMA wal_checkpoint(TRUNCATE);" >/dev/null 2>&1 || true
  cp "$DB" "backups/app-$(date +%Y%m%d-%H%M).db"
  echo "backup written to backups/"
  exit 0
fi

# R14：启动期自检「声称 vs 实际」
python3 - <<'PY'
import os, sqlite3
db = os.path.join(os.path.expanduser("~"), "Library", "Application Support", "good-min", "app.db")
os.makedirs(os.path.dirname(db), exist_ok=True)
conn = sqlite3.connect(db)
tables = conn.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchone()[0]
indexes = conn.execute("SELECT count(*) FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%'").fetchone()[0]
fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
print("db tables=%d indexes=%d foreign_keys=%d" % (tables, indexes, fk))
PY

echo "good-min 已启动（本机 macOS，本地单文件库）"
