# data-dictionary · <目标应用名> <版本>

> 复制为 BLUEPRINT/data-dictionary.md。填不出来就说明还没想清楚。

<!-- 指引：本文件是**字段语义的唯一定义处**。契约 §10/§11、schema.sql、TRACEABILITY 提到字段都引用这里。
     每个实体以 `## E01 <实体名>` 开头（脚本按 `E\d+\.` 收集字段引用），其下表头九列顺序固定：
     字段 | 类型 | 默认 | 空值 | 枚举/约束 | 关系 | 来源（原版观察/推断） | 本地映射 | 备注
     
     三条铁律：
     ① **来源必须分级**：`原版观察`（真库导出/真机可见）> `源码推断`（反编译/字符串表）> `猜测`。
        只有"原版观察"能直接用于建表；`猜测` 的字段必须同时出现在 unknowns.csv。
     ② **日期时间必须写清三件事**：存的是本地日期还是 UTC 时刻？有没有时区字段？全天怎么表达？
        这是整个项目最容易出静默错误的地方，一处含糊，跨月/跨时区全错。
     ③ **可空与默认必须分开**：`null` 表示"用户没设"，`0` 表示"设成了零值"，两者语义不同。
     
     不合格的写法："dueDate | DateTime | 截止时间"。缺默认、缺空值语义、缺时区口径，等于没定义。 -->

---

## 字段命名与通用约定

<!-- 指引：先写约定，再写字段。约定只写一次，逐字段引用，避免每行重复一堆话。 -->

| 约定项 | 规则 | 理由 |
|---|---|---|
| 字段名风格 | 沿用原版字段名（camelCase），不改成 snake_case | 便于把证据一行对一行核对，减少翻译错 |
| 持久化层命名 | 落库时按下表"本地映射"列转换；映射必须一一对应，不许合并字段 | 合并字段是"看起来实现了其实丢了语义"的根源 |
| 时刻 vs 日期 | 带 `Time`/`At` 后缀的（`remindTime`、`completedTime`）= 时刻；`dueDate`/`startDate`/`endDate` 命名保留原版，语义见各行 | 命名不统一是原版历史遗留，照抄但必须逐行说明 |
| 软删除 | 一律用 `deleted` 标记，不物理删除；物理删除只发生在回收站"永久删除"与级联子表 | 撤销与恢复依赖软删除 |
| 时间存储口径 | **UTC 时刻以 ISO 8601 带 `Z` 存；业务日历日以本地日期（`YYYY-MM-DD`）存；两者不混用同一列** | 混用会导致跨时区静默偏移一天 |
| 布尔 | 用三态（`true` / `false` / `null`），`null` 表示"未设置过"，不等同 `false` | 原版多处布尔字段可空（如 `isAllDay`） |
| 枚举 | 存储用整数或大写字符串，不用中文；展示文案另在本地化资源里定义 | 中文入库后无法稳定比较 |

---

## E01 TaskModel（任务）

<!-- 指引：这是核心实体。字段多达数十个，本模板只列**与日期/重复/状态相关、且必须明确的**那一批，
     其余用一行汇总说明"未列入的字段见 evidence/taskmodel-export.csv"。
     不许把所有字段都塞进来又每个都写"待确认"——那是最典型的糊弄。
     
     本实体必须讲清的四组概念（缺一组就是细节不到位）：
     ① 三日期模型：startDate / dueDate / endDate 各自何时出现、能否单独存在
     ② 全天与时间：isAllDay 与时分的关系，切全天时时分去哪了
     ③ 时区：timeZone + isFloating 的组合语义
     ④ 重复：repeatFlag 的编码格式、repeatFrom 的基准、exDate 的例外
     
     反例（真实踩过）："dueDate | DateTime | 截止时间 | 可空 | - | - | 观察 | DATETIME | -"
     —— 没写时区口径、没写全天时取什么值、没写清除日期后是 null 还是 1900-01-01，实现时必错。 -->

| 字段 | 类型 | 默认 | 空值 | 枚举/约束 | 关系 | 来源（原版观察/推断） | 本地映射 | 备注 |
|---|---|---|---|---|---|---|---|---|
| `E01.id` | string (UUID) | 新建时生成 | 不允许空 | 全局唯一；不可改 | 被 `E03.taskId`、`E01.parentId` 引用 | 原版观察 | `task.id TEXT PRIMARY KEY` | 撤销/恢复/联动命令全部靠它定位，**入队时捕获，不在异步回调里读"当前选中"** |
| `E01.projectId` | string | 无（必须指定） | 不允许空；"收集箱"用固定伪 ID `INBOX` | 外键 → `E02.id` | n—1 `E02` | 原版观察 | `task.project_id TEXT NOT NULL REFERENCES project(id)` | 原版用伪 ID 把"日历/习惯/全部"也当清单处理，本地版不移植伪 ID，改为独立查询口径 |
| `E01.parentId` | string \| null | `null` | `null` = 顶层任务 | 外键 → `E01.id`，不许自引用、不许成环（写入时校验） | 自引用 1—n | 原版观察 | `task.parent_id TEXT NULL REFERENCES task(id)` | 子任务与"清单项"是两个不同概念：子任务是独立任务（有自己的日期），清单项挂在 `E01.items` 里 |
| `E01.title` | string | - | 不允许空；trim 后为空则拒绝写入 | 长度 ≤ 200 字符（按 Unicode 标量计，UI 计数与服务端校验同口径） | - | 原版观察 | `task.title TEXT NOT NULL` | 空标题的快速添加必须被拒绝，不许建出无名任务 |
| `E01.content` | string \| null | `null` | 允许空 | Markdown 子集；长度 ≤ 20480 字符 | - | 原版观察 | `task.content TEXT NULL` | 不参与列表渲染，只在详情展示 |
| `E01.priority` | integer | `0`（无优先级） | 不允许空 | 枚举：`0` 无 / `1` 低 / `3` 中 / `5` 高 / `-1` 未设置（历史兼容）；**不是 0-5 连续值** | - | 原版观察 | `task.priority INTEGER NOT NULL DEFAULT 0 CHECK(priority IN (-1,0,1,3,5))` | 跨级取值（1→3→5）必须照搬，自行改成 1/2/3 会让从原版导入的数据全部降级 |
| `E01.status` | integer | `0` | 不允许空 | `0` 未完成 / `>0` 已完成 / `-1` 已放弃 | 参与 SM-01 | 原版观察 | `task.status INTEGER NOT NULL DEFAULT 0` | 三态语义见 `state-machines.md` SM-01；`-1` 不是"删除" |
| `E01.deleted` | integer | `0` | 不允许空 | `0` 正常 / `1` 已进回收站 | 与 `status` 正交 | 原版观察 | `task.deleted INTEGER NOT NULL DEFAULT 0` | 与 `status` 是两个维度：回收站里可以有已完成任务 |
| `E01.completedTime` | 时刻（UTC） | `null` | `null` = 未完成 | 进入 COMPLETED 时写入，回到 TODO 时清 `null` | - | 原版观察 | `task.completed_at TEXT NULL`（ISO 8601 带 Z） | **UTC 时刻**，不是本地日期；「今天完成了几条」按本地时区换算后统计，不许直接比 UTC 日期 |
| `E01.startDate` | 时刻或本地日期（见备注） | `null` | `null` = 未设开始 | 允许单独存在；若 `endDate` 存在则必须 `startDate <= endDate` | 三日期模型之一 | 源码推断（字段可见，语义未实测） | `task.start_at TEXT NULL` | **必须明确的点**：原版这是 `DateTime?`，但语义是"开始时刻"还是"开始日"未确认（U-015）。本行先按"与 `dueDate` 同口径的混合值"记录，验证后统一 |
| `E01.dueDate` | 时刻或本地日期（见备注） | `null` | `null` = 无截止日（不是"今天 00:00"） | 排序主键；清单成员判定依据 | 三日期模型核心 | 原版观察（UI 行为） / 推断（存储口径） | `task.due_at TEXT NULL` | **本项目最高风险字段，必须逐条确认**：① 落库是本地日期还是 UTC 时刻（U-015）② `isAllDay=true` 时是否仍存时分 ③ "清除日期"写 `null` 还是哨兵值（U-001）④ 跨时区时是否按"墙钟不变"处理 |
| `E01.endDate` | 时刻或本地日期 | `null` | `null` = 未设结束 | 必须 ≥ `startDate` | 三日期模型之一 | 源码推断 | `task.end_at TEXT NULL` | 本地版是否需要三日期，属产品取舍（DECISIONS.md D-00x）；若只做单日期，本行标 `N/A：本版仅保留 dueDate` 并记录理由 |
| `E01.isAllDay` | boolean \| null | `null` | `null` 按 `false` 渲染，但**不写回 `false`**（保留"用户从未设置"的信息） | 三态：true / false / null | 与 `dueDate` 的时分部分联动 | 原版观察 | `task.is_all_day INTEGER NULL CHECK(is_all_day IN (0,1) OR is_all_day IS NULL)` | 切到全天时时分怎么处理：本模板按"时分保留在内存草稿、落库存 00:00、取消全天后可还原原时分"记录，需实测确认 |
| `E01.timeZone` | string（IANA） | 创建时设备时区 | `null` = 回落设备当前时区 | 必须能被 IANA 时区库解析；非法值拒绝写入 | 与 `isFloating` 组合 | 原版观察 | `task.timezone TEXT NULL` | `isFloating=false` 时该字段是**解释 `dueDate` 的时区**，改系统时区后展示时刻随绝对时刻偏移 |
| `E01.isFloating` | boolean \| null | `null` | `null` 按 `false` 处理 | 三态 | 与 `timeZone` 互斥语义 | 源码推断 | `task.is_floating INTEGER NULL` | 浮动时间 = 不绑时区，跨时区**墙钟时间不变**（9:00 在东京还是 9:00）。两个字段的组合规则必须写成一张 2×2 表，不许口头约定 |
| `E01.repeatFlag` | string \| null | `null` | `null` = 不重复 | `RRULE` 字符串；私有扩展：`TT_SKIP=HOLIDAY,WEEKEND`、`TT_SKIP=OFFICIAL_WORKDAY`、`TT_WORKDAY=1`/-1、`FORGETTINGCURVE`、`NAME=CUSTOM`；**不许存解析后的对象 JSON** | 参与 SM-05 | 原版观察 | `task.repeat_flag TEXT NULL` | 每周工作日固定形如 `RRULE:FREQ=WEEKLY;INTERVAL=1;BYDAY=MO,TU,WE,TH,FR`（原版 BYDAY 顺序为 `WE,MO,TU,TH,FR`，顺序无语义，比较时必须先排序去重） |
| `E01.repeatFrom` | string \| null | `null` | `null` = 从截止日算 | 枚举：`DUEDATE` / `COMPLETED`（原版另有字符串形式，需实测） | - | 源码推断 | `task.repeat_from TEXT NULL` | "从完成日算"会导致完成时刻影响下一次日期，测试必须覆盖"延后完成" |
| `E01.repeatFirstDate` | 与原 `dueDate` 同口径 | 等于首次 `dueDate` | `null` = 不重复 | 若 `repeatFlag != null` 则必须非空（启动自检 R14 校验） | - | 源码推断 | `task.repeat_first_at TEXT NULL` | 与 `repeatFlag` 同事务写入；只写一个视为数据损坏 |
| `E01.exDate` / `E01.exDates` | string[] / string（JSON 串） | 空 | 空数组 = 无例外 | 每个元素是一个被跳过的原实例日期 | 参与 SM-05 | 源码推断 | `task.ex_dates TEXT NULL`（JSON 数组） | 原版同时有数组字段与字符串字段（`[Ignore]` 区别），本地只保留一份 JSON，不许两处并存 |
| `E01.remindTime` | 时刻（UTC） | `null` | `null` = 无下次提醒 | 由 `dueDate` + 提醒偏移派生，也允许用户手填绝对时刻 | 参与 SM-04 | 原版观察 | `task.remind_at TEXT NULL` | **延后只改这个字段，不改 `dueDate`**；改 `dueDate` 后必须重算此字段 |
| `E01.reminder` | string \| null | `null` | `null` = 不提醒 | 原版为字符串形式；本地版不移植此字段（改用 `E03` 子表） | - | 原版观察 | `N/A：本地版改用 E03 TaskReminder 子表` | 这条是"照抄字段名但换实现"的示例：语义保留，存储形态改，必须在备注写明 |
| `E01.reminders` | 数组（`[Ignore]`，不入库） | - | - | 运行时组装，来源 `E03` | 1—n `E03` | 原版观察 | `N/A：运行时组装` | `[Ignore]` 标记说明原版自己也不存它，本地版不要为它建列 |
| `E01.annoyingAlert` | integer \| null | `null` | `null` = 不启用 | 枚举待确认（推测 0/1/2 表示催促强度） | 参与 SM-04 | 源码推断 | `task.annoying_alert INTEGER NULL` | 若本版不做"持续催促"，标 `N/A` 并进 unknowns |
| `E01.sortOrder` | long | 创建时按 `268435456` 步长分配 | 不允许空 | 唯一有序；重新排序时取相邻两条的中点，差值耗尽则整体重排 | - | 原版观察 | `task.sort_order INTEGER NOT NULL` | 步长照搬原版；用浮点会积累精度误差 |
| `E01.etag` | string \| null | `null` | `null` = 本地新建未同步 | 同步版本戳 | - | 原版观察 | `N/A：本地单用户版不做同步，本版恒为 null` | **必须显式 N/A**，不许默默留着不用 |
| `E01.createdTime` / `E01.modifiedTime` | 时刻（UTC） | 创建/修改时写入 | 不允许空 | 只由写入协调器维护，UI 不许直接改 | - | 原版观察 | `task.created_at TEXT NOT NULL` / `task.modified_at TEXT NOT NULL` | `modifiedTime` 是"是否真的落库过"的判据之一，测试断言用它而非截图 |

> 未列入本表的字段（`desc` / `tags` / `tag` / `kind` / `items` / `columnId` / `pinnedTime` / `progress` / `imgMode` / `hasLocation` / `location` / `attachmentCount` / `reminderCount` / `commentCount` / `childIds` / `children` / `childrenString` / `isOpen` / `creator` / `assignee` / `attendId` / `completedUserId` / `notionBlock` / `taskType` / `FocusSummaries` / `Attachments` / `Actions` / `Resources` / `label`）：
> 完整清单见 `evidence/taskmodel-export.csv`（77 个公开成员）。本版不做的字段必须在 `features.csv` 或本表以 `N/A` + 理由显式排除，**不许省略不写**——省略的后果是 S4 建表时"漏一列"，S8 测试时才发现。

<!-- 指引：字段级追问清单（每个怀疑的字段都问一遍，答"不确定"就进 unknowns.csv）：
     □ 这个字段为 null 时，UI 显示什么？（空白 / "未设置" / 省略整行）
     □ 这个字段有默认值吗？默认值是谁写的（UI 层还是库层）？
     □ 清空这个字段时，写 null 还是写哨兵值（0 / 空串 / 1970-01-01）？
     □ 这个字段改了这一条，还会影响哪张表、哪一行？
     □ 这个字段是从别的字段派生的吗？派生规则写在哪（不许说"代码里有"）？
     □ 这个字段有没有"改了但没生效"的静默降级路径（如时区解析失败）？ -->

---

## E02 Project（清单）

<!-- 指引：清单是最简单的实体，但"智能清单"（今天/最近7天/收集箱）不是清单行，
     而是**查询口径**。这一区分必须在表里写清，否则实现时会真的建出"今天"这个清单行。 -->

| 字段 | 类型 | 默认 | 空值 | 枚举/约束 | 关系 | 来源（原版观察/推断） | 本地映射 | 备注 |
|---|---|---|---|---|---|---|---|---|
| `E02.id` | string | 新建生成 | 不允许空 | 唯一；`INBOX` 为系统保留 ID | 1—n `E01` | 原版观察 | `project.id TEXT PRIMARY KEY` | `INBOX` 不可删除、不可改名 |
| `E02.name` | string | - | 不允许空 | ≤ 50 字符；同一父级下不重名（大小写不敏感） | - | 原版观察 | `project.name TEXT NOT NULL` | 重名检查在写入时做，不靠 UI 拦 |
| `E02.kind` | string | `USER` | 不允许空 | `USER` 用户清单 / `SYSTEM` 系统清单（收集箱） | - | 推断 | `project.kind TEXT NOT NULL DEFAULT 'USER'` | 智能清单**不是**此实体的行，而是 `E07 SavedQuery` 或在代码中硬定义的查询 |
| `E02.sortOrder` | long | 步长同上 | 不允许空 | 唯一有序 | - | 原版观察 | `project.sort_order INTEGER NOT NULL` | - |
| `E02.deleted` | integer | `0` | 不允许空 | `0/1` | 删除清单时，其下任务如何处理见备注 | 推断 | `project.deleted INTEGER NOT NULL DEFAULT 0` | **必须明确**：删清单是"连任务一起进回收站"还是"任务移到收集箱"。本地版按后者（不丢数据），并进 unknowns 确认 |

---

## E03 TaskReminder（提醒）

| 字段 | 类型 | 默认 | 空值 | 枚举/约束 | 关系 | 来源（原版观察/推断） | 本地映射 | 备注 |
|---|---|---|---|---|---|---|---|---|
| `E03.id` | string | 新建生成 | 不允许空 | 唯一 | - | 源码推断 | `task_reminder.id TEXT PRIMARY KEY` | 原版该类字段可见，真库未定位到独立表（U-020） |
| `E03.taskId` | string | - | 不允许空 | 外键 → `E01.id`；任务物理删除时级联删 | n—1 `E01` | 源码推断 | `task_reminder.task_id TEXT NOT NULL REFERENCES task(id) ON DELETE CASCADE` | 级联必须显式声明，靠应用层删会漏 |
| `E03.trigger` | string | - | 不允许空 | 形如 `TRIGGER:-PT30M`（相对截止）或绝对时刻；含 `END` 表示绑结束时间 | - | 源码推断 | `task_reminder.trigger TEXT NOT NULL` | "提前 30 分钟"与"绝对 14:30"是两种不同语义：前者随 `dueDate` 移动，后者不动。**必须分列或前缀区分** |
| `E03.offsetMinutes` | integer \| null | `null` | `null` = 绝对时刻型 | 可为负（提前）；范围 [-43200, 43200] | 派生 `E01.remindTime` | 推断 | `task_reminder.offset_minutes INTEGER NULL` | 本地版显式化偏移量，避免每次解析 `trigger` 字符串 |

---

## E04 Tag（标签）

| 字段 | 类型 | 默认 | 空值 | 枚举/约束 | 关系 | 来源（原版观察/推断） | 本地映射 | 备注 |
|---|---|---|---|---|---|---|---|---|
| `E04.id` | string | 新建生成 | 不允许空 | 唯一 | n—n `E01`（经 `E05`） | 源码推断 | `tag.id TEXT PRIMARY KEY` | 原版把标签存在 `E01.tag` 的 JSON 串里，没有独立表；本地版规范化成独立表（这是**有意识的偏离**，必须在备注里写明并进 DECISIONS） |
| `E04.name` | string | - | 不允许空 | ≤ 30 字符；全局唯一（大小写不敏感） | - | 源码推断 | `tag.name TEXT NOT NULL UNIQUE` | - |

---

## 实体关系总图

```
E02 Project 1 ──── n E01 TaskModel
                        │
                        ├─ 自引用 parentId（1 — n，子任务）
                        ├─ 1 ──── n E03 TaskReminder
                        └─ n ──── n E04 Tag（经 E05 TaskTag）
```

<!-- 指引：关系图后必须补一张"删除传播表"，否则实现时每个删除入口各写一套级联。
     这是漏数据/多删的高发点。 -->

### 删除传播（谁删了，谁跟着变）

| 操作 | E01 任务 | E03 提醒 | E05 任务-标签 | E02 清单 |
|---|---|---|---|---|
| 任务进回收站（`deleted=1`） | 本行改标记 | 不删（恢复时还在） | 不删 | 不受影响 |
| 任务永久删除 | 物理删 | 级联删 | 级联删 | 不受影响（清单计数重算） |
| 清单删除 | 移到 `INBOX`（不删） | 不删 | 不删 | 本行改标记 |
| 标签删除 | 不受影响 | 不受影响 | 级联删（任务保留） | 不受影响 |

---

## 全局时间与日期口径（跨实体，必须一次讲清）

<!-- 指引：这一节是 data-dictionary 的价值所在。四个概念各写一段，每段给出"存什么 + 比什么 + 显示什么"。 -->

| 概念 | 存储 | 比较/查询 | 显示 | 坑 |
|---|---|---|---|---|
| 业务日历日（"今天到期"） | 本地日期 `YYYY-MM-DD` | 与设备当前本地日期比较 | 按本地语言格式化 | 用 UTC 日期比较会在 UTC+8 的 00:00-08:00 之间错判一天 |
| 绝对时刻（提醒、完成时间） | UTC 时刻 ISO 8601 带 `Z` | 与 `now(UTC)` 比较 | 按任务 `timeZone` 或设备时区换算 | 用本地时刻存会导致跨时区提醒错点 |
| 浮动时间（`isFloating=true`） | 墙钟时间（不带时区） | 与设备当前墙钟比较 | 原样显示 | 出差改时区后提醒仍按旧墙钟响，这是**期望行为**不是 bug |
| DST 空档（02:30 不存在） | 顺延到有效时刻 | - | 显示原设定 + 一行说明 | 静默改成 03:30 而不提示，用户会以为没保存 |

---

## 本地映射与迁移

<!-- 指引：原版字段 → 本地字段不是 1:1 时，必须写清映射规则，否则导入原版数据会静默丢字段。 -->

| 原版字段 | 本地字段 | 映射规则 | 不可映射时 |
|---|---|---|---|
| `dueDate`（混合日期/时刻） | `task.due_at` + `task.is_all_day` | 若 `isAllDay=true` 则 `due_at` 存该日 00:00 UTC 偏移按 `timeZone` 折算 | 无法判定是否为全天时按定时处理并记日志 |
| `priority`（-1/0/1/3/5） | `task.priority` 同值 | 直接搬运，不归一化 | 出现其他值 → 置 0 并记异常（启动自检报告） |
| `tags`（JSON 串） | `tag` + `task_tag` 两张表 | 解析 JSON → 逐标签 upsert → 建关联 | 解析失败 → 任务保留，标签丢，记 `BUG-` 级告警 |
| `reminders`（`[Ignore]` 不入库） | `task_reminder` 表 | 原版不入库，故导入时只能从 `reminder` 字符串解析 | 解析不出 → `remind_at = null`，不猜 |

---

<!-- 指引（收尾自检）：
     ① 每个字段的"空值"列是否都填了？（`-` 只允许用在确实不适用的行，不许图省事）
     ② 有没有哪个字段的"来源"是 `猜测` 却没进 unknowns.csv？有就是违规。
     ③ 日期/时刻类字段是否都在"全局时间与日期口径"表里有归属？
     ④ schema.sql 是否还没有？（本文件是 S1-S2 产出，schema.sql 是 S4；两者字段名必须一致，G4 会核对）
     ⑤ 有没有"照抄了原版字段名但语义已变"的？有就必须在备注里写清偏离原因。 -->
