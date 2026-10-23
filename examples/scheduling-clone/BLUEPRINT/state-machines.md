# 状态机

> 每个状态机固定三张表：状态 / 转换 / 非法转换。缺「非法转换」表 = 没想透边界。

---

## SM-01 访客预约页加载状态

### 状态

| 状态 | 含义 | 持久化 |
|---|---|---|
| IDLE | 未加载 | 否 |
| LOADING | 骨架期 | 否 |
| READY | 网格可用 | 否 |
| EMPTY | 该周无可预约时段 | 否 |
| ERROR | 加载失败（已重试耗尽） | 否 |
| CONFLICT | 提交时该时段被占 | 否 |

### 转换

| 从 | 事件 | 守卫条件 | 到 | 附带动作 | 异步结果处理 |
|---|---|---|---|---|---|
| IDLE | 页面挂载 | — | LOADING | 拉 eventType + availability + bookings | 失败 → ERROR（经重试） |
| LOADING | 请求成功 | slots 非空 | READY | 渲染网格；写 viewDate | — |
| LOADING | 请求成功 | slots 为空 | EMPTY | 显示空态「这一天没有可预约时间」 | — |
| LOADING | 请求失败 | 重试次数 < 3 | LOADING | 退避 500 / 1500 / 3000 ms 重试 | 第 3 次仍失败 → ERROR |
| READY | 选槽位 | slot 仍 available | READY | 选中；更新汇总条与底栏 | — |
| READY | 选槽位 | slot 已不可用 | CONFLICT | 移除该槽位；toast；焦点回网格首项 | — |
| READY | 翻周 | — | LOADING | 旧网格半透明保留，新骨架覆盖 | 失败 → 回 READY（旧网格）+ toast |
| READY | 切换时区 | — | LOADING | 同上 | 失败 → 回 READY + toast |
| READY | 路由离开 | — | IDLE | 取消在途请求 | 迟到结果按 generation 丢弃 |
| CONFLICT | 关闭提示 | — | READY | 清冲突态 | — |
| ERROR | 点重试 | — | LOADING | 重置重试计数 | — |
| EMPTY | 翻周 | — | LOADING | — | — |

### 非法转换

| 尝试 | 期望拒绝方式 | 用户看到 |
|---|---|---|
| LOADING 时点槽位 | 按钮 `pointer-events: none` | 无反应，不报错 |
| EMPTY 时点底栏「下一步」 | `disabled` | 小字「请先选择一个时间」 |
| CONFLICT 时再次提交 | 提交按钮禁用直到重选 | 底栏红条常驻 |
| 在途请求返回时组件已卸载 | 丢弃结果 | 无 console 警告 |

---

## SM-02 预约单生命周期

### 状态

| 状态 | 含义 | 持久化 |
|---|---|---|
| PENDING | 已提交，未确认 | 是（status 列） |
| CONFIRMED | 已确认 | 是 |
| RESCHEDULED | 已被改期（原单保留为历史） | 是 |
| CANCELLED | 已取消（时段释放） | 是 |
| EXPIRED | 预约时间已过，未取消 | 是（由定时任务推导，不落库） |

### 转换

| 从 | 事件 | 守卫条件 | 到 | 附带动作 | 异步结果处理 |
|---|---|---|---|---|---|
| — | 访客提交 | 槽位仍可用 | PENDING | 创建 booking + reminder（同事务）；写 outbox | 事务失败 → 整体回滚，返回 SLOT_TAKEN |
| PENDING | 确认邮件投递成功 | — | CONFIRMED | — | 投递失败重试 3 次；booking 仍是 PENDING（不因邮件失败回滚） |
| PENDING | 访客改期 | 新槽位可用 | RESCHEDULED | 旧预约 startAt 置空；创建新预约；**取消旧 reminder + 建新 reminder（同事务）** | 同事务失败 → 全部回滚 |
| PENDING | 访客取消 | — | CANCELLED | 释放槽位；取消全部 reminder | — |
| CONFIRMED | 访客改期 | 新槽位可用 | RESCHEDULED | 同上 | 同上 |
| CONFIRMED | 访客取消 | — | CANCELLED | 同上 | — |
| PENDING | 超时未确认（> 30 分钟） | — | CANCELLED | 释放槽位；取消 reminder | 定时任务 |
| 任一 | 时间已过 | — | EXPIRED | 仅状态推导，不写库 | — |

### 非法转换

| 尝试 | 期望拒绝方式 | 用户看到 |
|---|---|---|
| 已 CANCELLED 再取消 | 幂等返回成功 | 「该预约已取消」 |
| EXPIRED 改期 | 拒绝 | 「该预约已过期，无法改期」 |
| PENDING 取消后又提交 | 重新走创建流程，槽位已释放 → 可能成功 | 正常 |
| RESCHEDULED 改期 | 允许（从新单改） | 正常 |
| 改期到与原单相同的时间 | 允许（等价于不���） | 正常 |
| 事务中途失败后状态半改 | 事务保证原子 | 页面回滚到改期前 |

---

## SM-03 提醒任务

### 状态

| 状态 | 含义 | 持久化 |
|---|---|---|
| SCHEDULED | 已登记，等待触发 | 是 |
| FIRING | 已到期，正在投递 | 是 |
| SENT | 已发出 | 是 |
| CANCELLED | 已取消（改期/取消预约） | 是 |
| FAILED | 投递失败且超过重试次数 | 是 |

### 转换

| 从 | 事件 | 守卫条件 | 到 | 附带动作 | 异步结果处理 |
|---|---|---|---|---|---|
| — | 预约创建 | — | SCHEDULED | 计算触发时刻 = startAt − 24h（早于 now 则不建） | 与 booking 同事务 |
| — | 预约改期 | — | SCHEDULED | **旧提醒 → CANCELLED；建新提醒**（同事务） | 同事务失败 → 回滚 |
| SCHEDULED | 预约取消 | — | CANCELLED | — | — |
| SCHEDULED | 到期 | — | FIRING | 标记并出队 | 投递结果决定下一态 |
| FIRING | 投递成功 | — | SENT | 发送通知；写「已提醒」标记 | 失败 → 退避重试，最多 3 次 |
| FIRING | 投递失败 | 重试 < 3 | SCHEDULED | 延后重试 | — |
| FIRING | 投递失败 | 重试 = 3 | FAILED | 记日志；仪表盘标记异常 | — |
| SENT | 预约改期 | — | CANCELLED | — | — |

### 非法转换

| 尝试 | 期望拒绝方式 | 用户看到 |
|---|---|---|
| 对 SENT 的提醒重复触发 | 幂等跳过 | 不重复通知 |
| 对 CANCELLED 的提醒触发 | 跳过 | 不通知 |
| 提醒触发时预约已取消 | 跳过（查询时二次确认） | 不通知 |
| 同事务内取消提醒失败 | 整体回滚 | 改期失败，错误提示 |
