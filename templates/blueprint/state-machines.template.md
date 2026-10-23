# state-machines · <目标应用名> <版本>

> 复制为 BLUEPRINT/state-machines.md。填不出来就说明还没想清楚。

<!-- 指引：状态机解决的是"同一件事在不同时刻表现不同"的问题。
     没有状态机的蓝图，实现时会把状态写成零散的 if，最后到处漏分支。
     每个状态机以 `## SM-xx <对象名>` 开头，其下三段顺序固定：
     `### 状态`（表格三列）、`### 转换`（表格六列）、`### 非法转换`（表格三列）。
     三段缺一段，G2 报错。
     
     判断一个对象该不该建状态机：**如果它能"卡住"**（加载中、保存中、冲突、失败待重试），就该建。
     只读展示的数据不需要状态机。
     
     不合格的写法：把状态写成动词（"正在修改""已完成修改"），或用界面元素当代状态（"按钮变灰时"）。
     状态必须是**能持久化或被明确求值的数据值**。 -->

---

## 状态机总览

| SM-id | 对象 | 状态数 | 为何需要 | 涉及功能 |
|---|---|---|---|---|
| SM-01 | 任务实体持久状态 | 4 | 完成/放弃/回收站三态决定它出现在哪些清单、能否编辑 | F-DATE-EDIT、F-REPEAT-WEEKDAY |
| SM-02 | 详情面板编辑会话 | 5 | 草稿与已提交值分离，决定失败时能否恢复 | F-DATE-EDIT |
| SM-03 | 写入命令生命周期 | 6 | 决定"结果未知"时能不能重试、会不会丢草稿 | 所有写入功能 |
| SM-04 | 提醒实例 | 5 | 决定到点弹不弹、延后后还算不算 | F-REMIND-SNOOZE |
| SM-05 | 重复规则生效域 | 4 | 决定改"这一次"还是"全部" | F-REPEAT-WEEKDAY |

---

## SM-01 任务实体持久状态

<!-- 指引：这是**唯一权威**的任务状态定义。所有其他文档（data-dictionary、契约 §9、linkage）
     提到任务状态都引用 SM-01，不许各写一套。
     状态值必须对应真实字段值，写清"哪个字段 = 什么值"。
     不合格：只写状态名不写对应字段值。
     反例："状态：未完成 / 已完成" —— 少了两态（已放弃、已删除），而原版 status=-1 是独立语义。 -->

### 状态

| 状态 | 含义 | 是否持久化 | 判据（字段取值） |
|---|---|---|---|
| `TODO` | 未完成，正常显示在清单里 | 是 | `E01.status == 0` 且 `E01.deleted == 0` |
| `COMPLETED` | 已完成，移入已完成分组 | 是 | `E01.status > 0` 且 `E01.deleted == 0`（完成时间写入 `completedTime`） |
| `ABANDONED` | 已放弃（不做了，不是做完） | 是 | `E01.status == -1` 且 `E01.deleted == 0`，UI 显示为"已放弃"而非"已完成" |
| `TRASHED` | 已进回收站，不进任何清单与搜索 | 是 | `E01.deleted == 1`（与 status 正交：回收站里可以是已完成或未完成） |

> 注意 `status` 与 `deleted` 是**两个正交维度**，不是一条链。`deleted=1` 时 `status` 保留原值，
> 恢复时按原 status 回到对应分组。把四个状态压成一条线性链是常见错误。

### 转换

| 从 | 事件 | 守卫条件 | 到 | 附带动作 | 异步结果处理 |
|---|---|---|---|---|---|
| TODO | `TaskCompleted{taskId}` | `deleted == 0` | COMPLETED | 写 `status=1`、`completedTime=now(UTC)`；若有重复规则，母任务非最后一次则同时生成下一实例 | 提交成功 → 广播 → 刷新六面；失败则回滚为 TODO 并在行内提示 |
| COMPLETED | `TaskUncompleted{taskId}` | `deleted == 0` | TODO | 写 `status=0`、`completedTime=null` | 同上 |
| TODO / COMPLETED | `TaskAbandoned{taskId}` | `deleted == 0` 且 非子任务 | ABANDONED | 只写 `status=-1`，不动 `completedTime` | 同上 |
| ABANDONED | `TaskUncompleted{taskId}` | `deleted == 0` | TODO | 写 `status=0` | 同上 |
| 任意 | `TaskDeleted{taskId}` | 有删除权限（本地版恒真） | TRASHED | 写 `deleted=1`，`deletedAt=now`；撤销栈记录原 status | 提交成功 → 从全部清单/搜索/日历移除；提醒调度撤销该任务全部定时器 |
| TRASHED | `TaskRestored{taskId}` | 回收站内未超保留期（本地版不限期） | 恢复为删除前的 status | 写 `deleted=0`，`deletedAt=null` | 提交成功 → 重新出现在原清单并按日期落位；提醒按当前时间重算是否补报 |
| TRASHED | `TaskPurged{taskId}` | 用户在回收站点"永久删除"并二次确认 | （终态，行被物理删除） | 物理删除 E01 行与 E03 提醒子行（同事务） | 不可恢复；撤销栈不再持有该 ID |

### 非法转换

| 尝试 | 期望拒绝方式 | 用户看到 |
|---|---|---|
| TRASHED → COMPLETED（直接勾选回收站里的任务） | 命令层拒绝，返回 `INVALID_STATE_TRANSITION`，不写库 | 回收站列表的勾选框不可点（置灰），tooltip"回收站内的任务不能勾选完成，请先恢复" |
| ABANDONED → COMPLETED | 拒绝；放弃不是完成 | 勾选框置灰，tooltip"已放弃的任务请先恢复为未完成" |
| TRASHED → 改日期（编辑回收站内任务） | 详情面板对该任务不渲染日期入口（`visibility_cond` 为假） | 双击回收站任务只显示只读详情，所有字段不可编辑 |
| TRASHED → 物理删除 且 该任务有未撤销的编辑命令在队列中 | 排队等待该命令完成后再执行删除，不允许交叉 | 用户看到"正在保存，删除将在完成后执行"的提示 |
| 任意状态 → COMPLETED 当 `status` 值非法（如 7） | 启动自检（R14）报告数据异常，按 TODO 展示并在日志记录原值 | 顶栏出现"发现 1 条数据异常"入口，可见但不阻断使用 |

---

## SM-02 详情面板编辑会话

<!-- 指引：这类"界面状态机"最容易被漏掉，但它是 R3（关窗冲刷）与 R4（失败不丢草稿）的落地依据。
     状态要能回答："此刻用户看到的日期，是库里的值还是草稿值？"
     不合格：把状态写成"打开了 / 关闭了"两种。
     反例："状态：详情打开 / 详情关闭" —— 无法回答"改了一半没保存时关闭会怎样"。 -->

### 状态

| 状态 | 含义 | 是否持久化 | 判据 |
|---|---|---|---|
| `IDLE` | 详情未打开 | 否 | `selectedTaskId == null` |
| `LOADING` | 已选中任务，正在读库 | 否 | `selectedTaskId != null && loadGeneration 未回执` |
| `CLEAN` | 已加载，显示值与库一致 | 否 | `draft == null` |
| `DIRTY` | 有未提交的修改，显示草稿值 | 否（草稿在内存） | `draft != null` |
| `SAVE_ERROR` | 提交失败，草稿保留 | 否 | `lastError != null && draft != null` |

### 转换

| 从 | 事件 | 守卫条件 | 到 | 附带动作 | 异步结果处理 |
|---|---|---|---|---|---|
| IDLE | `TaskSelected{taskId}` | 被选任务未在回收站 | LOADING | 记录 `entityId = taskId`（**入队时捕获，不在异步回调里再读当前选择**）；发起读库 | 读到后若 `generation` 仍匹配则转 CLEAN，否则丢弃结果 |
| LOADING | `LoadSucceeded` | `generation` 匹配当前选择 | CLEAN | 渲染全部字段 | 迟到结果（generation 不匹配）直接丢弃，不覆盖新任务 |
| LOADING | `LoadFailed` | — | CLEAN 并显示错误占位 | 显示"读取失败 · 重试" | 重试成功后转 CLEAN |
| CLEAN | `FieldEdited` | 字段通过基础校验（可先记为无效草稿） | DIRTY | 建草稿快照、启动防抖计时 | 防抖到点或失焦/Enter/关窗时提交 |
| DIRTY | `SubmitSucceeded` | 草稿版本 == 已提交版本 | CLEAN | 用返回的 `committedRevision` 更新基线 | 若提交期间又产生新草稿，保持 DIRTY 且不显示"已保存" |
| DIRTY | `SubmitFailed` | 可重试错误 | SAVE_ERROR | 保留草稿与 `lastError`、`diagnosticId` | 用户点重试 → 用同一草稿再次提交；点放弃 → 丢弃草稿回 CLEAN |
| SAVE_ERROR | `RetryClicked` | 草稿仍在 | DIRTY | 重新入队同一命令 | 同 DIRTY 提交分支 |
| SAVE_ERROR | `DraftDiscarded` | 用户显式确认放弃 | CLEAN | 丢弃草稿，回填库值 | — |
| 任意 | `TaskSelected{otherId}` | 有 DIRTY/SAVE_ERROR | 先冲刷再 LOADING | 把 A 的草稿命令入队，捕获 A 的 entityId；再发起读 B | A 的结果绝不写进 B 的显示；A 失败时给可返回的提示，不静默丢 |
| DIRTY / SAVE_ERROR | `AppQuitRequested` | — | `EXIT_PENDING`（应用级） | 冻结新输入、捕获全部草稿、建屏障 N | 屏障确认 ≤N 全有结果才退出；失败/超时 → 重试/取消退出/明确放弃 |

### 非法转换

| 尝试 | 期望拒绝方式 | 用户看到 |
|---|---|---|
| DIRTY → IDLE（直接关闭详情不冲刷） | 关闭动作先冲刷；冲刷未完成前详情保持打开并显示"保存中" | 关闭按钮短暂转圈，完成后才真正关闭 |
| LOADING → DIRTY（加载中就允许编辑） | 输入框在 LOADING 期间只读 | 输入框呈禁用底色，无法键入 |
| SAVE_ERROR → CLEAN（把失败当成功） | 禁止；只有提交成功或显式放弃才能回 CLEAN | 顶部状态条显示"未保存"，不出现"已保存"字样 |
| 旧 generation 的 `LoadSucceeded` → CLEAN（迟到结果覆盖新选择） | 丢弃结果，状态不变 | 用户看不到任何变化（这是正确行为） |

---

## SM-03 写入命令生命周期

<!-- 指引：这是 R1–R3 的状态化表达。它回答三个致命问题：
     ① 命令发出后能不能点第二次？② 超时了到底存没存？③ 关窗前怎么知道写完了？
     所有写入类功能共用这一个状态机，不许每个功能各写一套"保存中/已保存"。 -->

### 状态

| 状态 | 含义 | 是否持久化 | 判据 |
|---|---|---|---|
| `QUEUED` | 已入串行队列，等待执行 | 否（队列可落盘以便崩溃后诊断，但业务上不承诺重放） | `enqueuedSeq > committedSeq` |
| `EXECUTING` | 正在执行事务 | 否 | 队列消费者已取出，事务未提交 |
| `COMMITTED` | 事务提交成功 | **是** | 事务返回且影响行数 == 1（0 行不算成功） |
| `REJECTED` | 校验失败或被拒绝，确定没写 | 否 | 返回 `VALIDATION_ERROR` / `INVALID_STATE_TRANSITION` / `NOT_FOUND_OR_DELETED` |
| `FAILED` | 存储错误，确定没写 | 否 | 返回 `STORAGE_ERROR`（只读、磁盘满、锁超时） |
| `UNKNOWN` | 结果未知（超时、连接断开） | 否 | 返回 `TIMEOUT_UNKNOWN` |

### 转换

| 从 | 事件 | 守卫条件 | 到 | 附带动作 | 异步结果处理 |
|---|---|---|---|---|---|
| （新建） | `Enqueue{cmd}` | 命令携带不可变 `entityId`、`patch`、`expectedRevision`、`operationId` | QUEUED | 分配递增 `seq`，登记到屏障表 | — |
| QUEUED | `Dequeue` | 队列非空 | EXECUTING | 启动事务 | — |
| EXECUTING | `TxCommit(rows==1)` | 影响行数恰为 1 | COMMITTED | 递增 `committedSeq`、广播事件、入撤销栈 | 通知所有 await 该 seq 的屏障 |
| EXECUTING | `TxCommit(rows==0)` | 影响行数为 0 | REJECTED | 区分"版本冲突"与"实体已删除"（按后续查询判定） | 提示用户并保留草稿 |
| EXECUTING | `TxRollback(validation)` | — | REJECTED | 记录拒绝原因 | 同上 |
| EXECUTING | `TxRollback(io)` | — | FAILED | 记录 `diagnosticId`（脱敏，不含用户输入） | 保留草稿；可重试 |
| EXECUTING | `Timeout` | 未在阈值内返回 | UNKNOWN | 不重复提交；登记待确认 | 查询实体 revision 确认是否已提交：已提交 → COMMITTED（补广播），未提交 → FAILED |
| UNKNOWN | `ResolveCommitted` | 实体 revision 已含该次修改 | COMMITTED | 补发事件（避免界面停在旧值） | — |
| UNKNOWN | `ResolveNotCommitted` | 实体 revision 未变 | FAILED | 允许用户用同一草稿重试 | — |
| QUEUED | `CancelBeforeStart` | 尚未出队 | （终态，作废） | 从屏障表移除，同时递减屏障计数 | 关窗场景下不允许取消，只允许等待 |

### 非法转换

| 尝试 | 期望拒绝方式 | 用户看到 |
|---|---|---|
| EXECUTING → 再次入队同一实体同一字段的命令 | 允许入队但携带新 `draftRevision`；执行时用**最新**已提交 revision 作为基线（单 actor）。若发现外部改动则转 REJECTED 冲突 | 连续改日期不报错，最后一次生效 |
| UNKNOWN → 直接重试同一 `operationId` | 拒绝：必须先确认原操作结果 | "正在确认保存结果，请稍候" |
| COMMITTED → 回滚 | 禁止；已提交不可回退，只能发一条新命令抵消 | 撤销 = 新命令，不是回滚 |
| 屏障等待时用 `sleep` 固定延时判完成（R1） | 禁止：必须 await 到 `committedSeq >= barrierSeq` | —（这是实现红线，不是用户可见行为） |
| 关窗时"不管结果都 finally 关闭"（R3） | 禁止：必须拿到结构化结果（成功/失败/未知）后才决定是否关闭 | 有未保存项时弹"重试/放弃并退出/取消退出" |

---

## SM-04 提醒实例

<!-- 指引：提醒最容易做成"到点弹一下"，然后延后、补报、重复弹全乱。
     状态要能回答："睡了两小时醒来，该弹几次？"
     不合格：只写"待提醒 / 已提醒"。
     反例："状态：未提醒、已提醒" —— 无法表达"延后中"与"已过期未补报"。 -->

### 状态

| 状态 | 含义 | 是否持久化 | 判据 |
|---|---|---|---|
| `SCHEDULED` | 已注册定时器，等待到点 | 是（`E01.remindTime`）+ 否（内存定时器） | `remindTime > now` 且定时器已注册 |
| `FIRING` | 正在弹气泡 | 否 | 已触发，UI 未完成展示 |
| `SNOOZED` | 用户点了延后 | 是 | `remindTime` 被改写为 `now + 偏移`，另记 `snoozeCount` |
| `DISMISSED` | 用户关闭气泡但未完成任务 | 否（仅内存去重集） | `dismissedKeys` 含 `(taskId, remindTime)` |
| `EXPIRED` | 到点时刻已过且不再补报 | 否 | 超过补报窗口（默认 24h）或任务已完成/进回收站 |

### 转换

| 从 | 事件 | 守卫条件 | 到 | 附带动作 | 异步结果处理 |
|---|---|---|---|---|---|
| （新建/改日期后） | `Schedule{taskId, remindTime}` | 任务 `status==0 && deleted==0 && remindTime != null` | SCHEDULED | 注册内存定时器；同任务旧定时器先撤销 | — |
| SCHEDULED | `TimerFired` | `now >= remindTime`（用窗口判据 `remindTime <= now && remindTime > lastCheck` 防跳秒漏报） | FIRING | 查去重集，已 `DISMISSED` 则不弹直接转 SCHEDULED 的下一次 | 弹窗失败（系统通知权限被拒）→ 降级为应用内横幅，不静默失败 |
| FIRING | `UserSnooze{minutes}` | 分钟数 ∈ {5,10,30,60} 或自定义正数 | SNOOZED | 写 `remindTime = now + minutes`；**不改 `dueDate`** | 提交成功 → 回 SCHEDULED 并注册新定时器 |
| FIRING | `UserDismiss` | — | DISMISSED | 把 `(taskId, remindTime)` 放入去重集 | 不写库 |
| FIRING | `UserComplete` | 任务未在回收站 | （任务转 SM-01 COMPLETED） | 顺带转 DISMISSED | 同 SM-01 |
| SNOOZED | `TimerFired` | 到新时刻 | FIRING | `snoozeCount++`；达上限（默认 5）后不再提供延后按钮 | — |
| SCHEDULED | `WakeFromSleep{gap}` | 睡眠跨越了 `remindTime` | FIRING（补报 1 次） | 用 `lastCheck` 窗口判定补报，不按"错过几次弹几次" | 多个任务同时补报时按 `remindTime` 升序依次弹，不并排堆叠 |
| 任意 | `TaskCompleted` / `TaskDeleted` / `DueDateCleared` | — | EXPIRED | 撤销定时器，清理去重集条目 | 已弹出的气泡不主动收回 |

### 非法转换

| 尝试 | 期望拒绝方式 | 用户看到 |
|---|---|---|
| SCHEDULED → FIRING 两次（同一 `remindTime` 重复弹） | 去重集拒绝 | 只弹一次 |
| DISMISSED → FIRING（关闭后又自己弹回来） | 拒绝；只有 `remindTime` 变化才重新进入 SCHEDULED | 无 |
| 对无 `dueDate` 的任务设置提醒 | 命令层拒绝 `VALIDATION_ERROR`（提醒必须挂在时间点上） | 详情"提醒"行置灰，tooltip"请先设置日期" |
| 延后时把 `dueDate` 一起改掉 | 拒绝：延后只允许改 `remindTime` | 任务在列表/日历里的日期不变 |
| 睡眠 8 小时后按"错过次数"连弹 8 次 | 拒绝：窗口判据只补报 1 次 | 只弹 1 次，气泡上标注"原定 09:00 提醒" |

---

## SM-05 重复规则生效域

<!-- 指引：这是"改一次还是改全部"的权威定义。原版是否有"仅此次/所有"的选择框尚未确认（U-003），
     所以本状态机先按"两种域并存"建模，验证后回改。 -->

### 状态

| 状态 | 含义 | 是否持久化 | 判据 |
|---|---|---|---|
| `NO_REPEAT` | 无重复规则 | 是 | `E01.repeatFlag == null` |
| `RULE_ONLY` | 有规则，未产生例外 | 是 | `repeatFlag != null && exDates 为空` |
| `RULE_WITH_EXCEPTION` | 有规则，且存在被单独改过的实例 | 是 | `exDates` 非空（每个例外日期是一条 `exDate`） |
| `RULE_ENDED` | 规则已到期/已达次数，不再产生新实例 | 是（派生） | 由 `until`/`count` 与已生成实例数派生，不单独存字段 |

### 转换

| 从 | 事件 | 守卫条件 | 到 | 附带动作 | 异步结果处理 |
|---|---|---|---|---|---|
| NO_REPEAT | `SetRepeat{rule}` | 任务有 `dueDate` | RULE_ONLY | 写 `repeatFlag`、`repeatFirstDate = dueDate` | 提交成功 → 展开未来 60 天实例 → 日历与提醒重排 |
| RULE_ONLY | `EditSingleInstance{date, newDate}` | 用户选择"仅此次"（若原版有该入口） | RULE_WITH_EXCEPTION | 在 `exDates` 追加原日期，并为新日期创建一条独立实例 | 同上；仅该实例移位，其余实例不动 |
| RULE_ONLY | `EditAllInstances{newRule}` | — | RULE_ONLY（规则替换） | 完整替换 `repeatFlag`；已完成的实例保留，未来的重新展开 | 旧未来实例删除 → 新实例生成，日历整体重算 |
| RULE_WITH_EXCEPTION | `EditAllInstances{newRule}` | — | RULE_WITH_EXCEPTION 或 RULE_ONLY | 替换规则；`exDates` 是否保留需按用户确认，默认保留 | 同上 |
| RULE_ONLY / RULE_WITH_EXCEPTION | `ClearRepeat` | — | NO_REPEAT | `repeatFlag=null`、`exDates` 清空；已生成的未来实例按"保留为独立任务 / 删除"策略处理（策略需确认） | 日历与提醒撤销未来实例 |
| 任意 | `ReachEnd` | `count` 已用尽或 `now > until` | RULE_ENDED | 无写入；派生态 | 任务仍显示在原日期，不再产生新实例 |

### 非法转换

| 尝试 | 期望拒绝方式 | 用户看到 |
|---|---|---|
| NO_REPEAT → 设置重复 但 `dueDate == null` | 拒绝 `VALIDATION_ERROR` | "重复"行置灰，tooltip"请先设置日期" |
| RULE_ONLY → 无提示地把某次编辑扩散到全部实例 | 禁止静默扩散：若原版确有"仅此次/所有"选择，未选择前不写入 | 出现二次选择框（若确认原版无此交互，则改为"编辑即改全部"并在此行记录证据） |
| RULE_ENDED → 继续生成实例 | 拒绝 | 无 |
| 删除已完成的实例后要求"退还次数" | 拒绝：次数按已生成计 | 结束条件文案不因删除而变 |

---

<!-- 指引（收尾自检）：
     ① 每个状态机是否都有"非法转换"表？没有非法转换说明你只想了正常路径。
     ② 非法转换的"用户看到"是否具体到文案与控件？写"提示错误"等于没写。
     ③ 状态判据是否都指向真实字段（E01.xxx / 内存变量名），而不是"界面看起来…"？
     ④ 有没有两个状态机在描述同一件事？有就合并，同一规则只能有一个权威定义。 -->
