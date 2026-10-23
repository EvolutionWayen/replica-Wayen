# 本地运行手册（A 档）

## 1 启动
```bash
./scripts/start.sh            # 首次会建库并做启动自检（R14）
```
期望输出：`db tables=2 indexes=2 foreign_keys=1`，随后窗口打开。

## 2 备份
```bash
./scripts/start.sh --backup-only        # 生成的副本落在 backups/
sqlite3 backups/app-$(date +%Y%m%d-%H%M).db "PRAGMA integrity_check;"
```
先 `PRAGMA wal_checkpoint(TRUNCATE)` 再复制，否则会漏掉未合并的 WAL。

## 3 恢复
```bash
# 关闭应用后执行
cp backups/app-20261022-1403.db "$HOME/Library/Application Support/good-min/app.db"
./scripts/start.sh --verify                 # 逐表行数比对
```

## 4 迁移
```bash
# 换机器：整个数据目录打包，不迁移缓存
tar -czf good-min-data.tgz "$HOME/Library/Application Support/good-min"
# 新机解包到同一路径，启动自动迁移 schema（PRAGMA user_version 单调递增）
```

## 5 卸载
```bash
rm -rf "$HOME/Library/Application Support/good-min"   # 数据
rm -rf /Applications/good-min.app                      # 程序
# 验证无残留：
ls "$HOME/Library/Application Support" | grep -c good-min   # 期望 0
```

## 6 恢复演练记录
见 REPORT/release/restore-drill.md（2026-10-22 演练：备份 → 删库 → 恢复 → 逐行比对 128 行一致）。
