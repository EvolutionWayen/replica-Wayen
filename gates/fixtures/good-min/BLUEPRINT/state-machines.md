# state-machines · 状态机

## SM-01 任务日期

### 状态
| 状态 | 含义 | 是否持久化 |
|---|---|---|
| idle | 无进行中的写入 | 否 |
| SUBMITTING | 已提交，等待落库完成信号 | 否 |
| conflict | revision 冲突，等待用户选择 | 否 |
| error | 写入失败，草稿保留 | 否 |

### 转换
| 从 | 事件 | 守卫条件 | 到 | 附带动作 | 异步结果处理 |
|---|---|---|---|---|---|
| idle | SubmitDateChange | revision 匹配 | SUBMITTING | 入写队列，捕获 entityId | await FlushResult |
| SUBMITTING | FlushOk | FlushResult.ok | idle | 广播 TaskDateChanged，刷新六面 | 过期 generation 丢弃 |
| SUBMITTING | FlushError | FlushResult.error | error | 保留草稿，显示重试 | 记录脱敏日志 |
| SUBMITTING | RevisionConflict | 库中 revision 更大 | conflict | 提示「已在别处修改」 | 重读最新值 |
| error | Retry | 磁盘可写 | SUBMITTING | 沿用同一 revision | await FlushResult |
| conflict | Reload | 用户点「查看最新」 | idle | 用最新值刷新界面 | - |

### 非法转换
| 尝试 | 期望拒绝方式 | 用户看到 |
|---|---|---|
| error → idle（跳过重试） | 拒绝，必须经 Retry 或 Reload | 提示条保持「保存失败，已保留修改」 |
| SUBMITTING → SUBMITTING（重复提交） | 幂等，直接返回首个 FlushResult | 无重复提示 |
| conflict → SUBMITTING（不重读） | 拒绝 | 提示「请先查看最新版本」 |

## SM-02 重复规则

### 状态
| 状态 | 含义 | 是否持久化 |
|---|---|---|
| none | 不重复 | 是（repeat.rule 为空） |
| weekly | 每周固定星期 | 是 |
| workdays | 每周工作日（周一至周五） | 是 |
| custom | 自定义 byday 集合 | 是 |

### 转换
| 从 | 事件 | 守卫条件 | 到 | 附带动作 | 异步结果处理 |
|---|---|---|---|---|---|
| none | SetWorkdays | 可写 | workdays | 写 byday=[1,2,3,4,5] | await FlushResult |
| workdays | ClearRepeat | 可写 | none | 清空 byday 与下次发生 | await FlushResult |
| weekly | SetWorkdays | 可写 | workdays | 覆盖 byday | await FlushResult |

### 非法转换
| 尝试 | 期望拒绝方式 | 用户看到 |
|---|---|---|
| 重复中修改日期到过去 | 允许修改，但下次发生按规则顺延 | 下次发生日期立即更新 |
| custom 且 byday 为空 | 拒绝，回退到 none | 提示「至少选择一天」 |
