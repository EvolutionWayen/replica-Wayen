# 质量红线（R 编号以 00-体系总纲.md §9 为唯一权威）

| 编号 | 红线 | 本项目怎么落地 |
|---|---|---|
| R1 | 不得用 sleep / 固定延时等待异步完成 | 等待一律用完成信号（FlushResult / await），测试里 grep 不到 sleep |
| R2 | 影响持久状态的异步写必须进串行链，并暴露可 await 的完成信号 | 写队列单线程串行，每条命令带不可变 entityId + revision |
| R3 | 关窗/退出前必须冲刷，且冲刷返回结构化结果 | flush() 返回 FlushResult{ok|unknown|error}，关窗流程消费它 |
| R4 | 持久化测试用真文件，禁内存库；断言查具体值 | tests 用 tempfile.mkdtemp() 下的真 SQLite 文件，断言 dueDate == 具体值 |
| R5 | 全量测试连跑 ≥3 次 | TEST/results 存 3 份连续结果，G8 校验 |
| R6 | 构建 0 错误 0 警告 | 构建日志进 BUILD/build-log.md |
| R7 | 不许注释掉报错来"通过" | 门禁扫 src 无 TODO/FIXME；不许改断言 |
| R8 | 不许空壳实现 | 每个命令有实现与测试；空壳函数体进评审清单 |
| R9 | 反编译/还原代码只当规格书读，不编入产品 | 只读证据在 evidence/，src 全部自己写 |
| R10 | 不破坏已通过的功能 | 改一处跑全量回归（3 次连跑） |
| R11 | 不能写成数值或步骤的体验要求 = 无效要求 | 契约 §15 写点击数、焦点、动效时长 |
| R12 | 性能必须带口径 | 契约给起点/终点/环境与 p50-p95 |
| R13 | catch 不得全吞异常 | 至少留脱敏日志与错误码 |
| R14 | 启动期做"声称 vs 实际"自检 | 启动自检建表数、索引数、PRAGMA foreign_keys 实测值 |
| R15 | 引用用可 grep 的文本锚点 | 证据写 文件:行 + baseline commit a1b2c3d |
| R16 | 只改必须改的 | 变更单 + 影响面清单 |
| R17 | 踩坑库每条标「当前是否已修」+ 时间 | 见 REPORT/feedback.md 与案例层 |
| R18 | 页面完成不等于功能完成 | 六面联动 + G6 门（linkage wired + 测试 pass） |
| R19 | 不得用 A || B 式或放行 | 断言取合取：数据落库 与 冲刷结果 都要满足 |
| R20 | BLOCKED 不得当 PASS；N/A 必须带理由 | 唯一 NA（G11.commercial）在 manifest.na_approved 登记 |
