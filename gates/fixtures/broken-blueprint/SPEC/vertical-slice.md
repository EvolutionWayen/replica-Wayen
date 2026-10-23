# 竖切证据：建 → 读 → 重启还在

## 1 执行命令
```bash
python3 -m app.cli create --title "写作" --due 2026-10-24 --all-day
python3 -m app.cli show --last
```

## 2 实测输出（2026-10-22T14:03+08:00）
```
created id=9f3c… dueDate=2026-10-24 allDay=1 revision=1
show      id=9f3c… dueDate=2026-10-24 allDay=1 revision=1
```

## 3 重启后复查（2026-10-22T14:05+08:00）
```bash
# 结束进程 → 重新启动 → 再次读取
python3 -m app.cli show --id 9f3c…
```
```
id=9f3c… dueDate=2026-10-24 allDay=1 revision=1
```
结论：重启后值一致，说明落的是真文件（`~/Library/Application Support/good-min/app.db`），不是内存库。
