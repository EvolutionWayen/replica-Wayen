# data-dictionary · 数据字典

> 字段 ID 写作 `E01.dueDate`，代码与测试按此引用。

## E01 TaskModel
| 字段 | 类型 | 默认 | 空值 | 枚举/约束 | 关系 | 来源（原版观察/推断） | 本地映射 |
|---|---|---|---|---|---|---|---|
| id | TEXT | - | 否 | 主键，UUID | 1→N Reminder | 原版观察（DB 导出） | TaskModel.id |
| title | TEXT | '' | 否 | 长度 ≤ 500 | - | 原版观察 | TaskModel.title |
| dueDate | TEXT | - | 是 | ISO 日期或空 | - | 原版观察 | TaskModel.dueDate |
| dueTime | INTEGER | 540 | 是 | 0..1439 分钟 | - | 推断（09:00 默认） | TaskModel.dueTime |
| allDay | INTEGER | 0 | 否 | 0/1 | - | 原版观察 | TaskModel.allDay |
| repeat | TEXT | - | 是 | NONE/WEEKLY/WORKDAYS/CUSTOM | 指向 E02 | 原版观察 | TaskModel.repeat |
| byday | TEXT | - | 是 | 逗号分隔的 1..7 | - | 推断 | TaskModel.byday |
| revision | INTEGER | 1 | 否 | 每次写入 +1 | - | 推断（并发控制） | TaskModel.revision |
| updatedAt | TEXT | - | 否 | ISO 8601 带时区 | - | 原版观察 | TaskModel.updatedAt |

## E02 Reminder
| 字段 | 类型 | 默认 | 空值 | 枚举/约束 | 关系 | 来源（原版观察/推断） | 本地映射 |
|---|---|---|---|---|---|---|---|
| id | TEXT | - | 否 | 主键，UUID | N→1 E01 | 原版观察 | Reminder.id |
| taskId | TEXT | - | 否 | 外键 → E01.id | - | 原版观察 | Reminder.taskId |
| fireAt | TEXT | - | 否 | ISO 8601 带时区 | - | 原版观察 | Reminder.fireAt |
| state | TEXT | pending | 否 | pending/fired/cancelled | - | 推断 | Reminder.state |
