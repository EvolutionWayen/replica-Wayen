# 数据字典

> 字段语义、类型、默认、空值、枚举、约束、关系、来源与本地映射。
> **「来源」列区分「实测观察」与「推断」**——推断的必须在 `unknowns.csv` 里有对应条目。
> **「本地映射」列是必填的**：同名不同义（本地日期 vs UTC 时刻）、双写字段（选哪个权威）都写在这里。

---

## 全局时间与日期口径

**这一节先于所有实体**，因为时间语义错了，所有实体的字段都会跟着错。

| 概念 | 存什么 | 例 | 陷阱 |
|---|---|---|---|
| **绝对时刻** | UTC 时间戳（带时区） | `2026-07-14T07:00:00Z` | 存成本地字符串 → 夏令时错一小时 |
| **钟面时间** | 某时区的墙上时间 | `14:00` | 存成 UTC 时刻 → 换时区显示乱 |
| **本地日期** | 某时区的日历日 | `2026-07-14` | 存成 UTC 时刻 → 跨日界的时段归属错一天 |
| **时区标识** | IANA ID | `Asia/Shanghai` | 只存 GMT+8 → 夏令时后偏移过期 |
| **全天标记** | 布尔 | `isAllDay=true` | 全天的时分秒仍有值 → 按时刻比较会错 |

**本项目的定案**：

- 业务表存**绝对时刻**（UTC）+ **时区标识**（IANA）。
- 访客看到的钟面时间**只在渲染层计算**。
- 边界日期（本周起点、日界线）按**主理人时区**算，并存主理人时区 ID。
- `isAllDay` 为真时，时分秒固定写 `00:00:00`，比较时按日期比，不按时刻比。

---

## E01 EventType 预约类型

| 字段 | 类型 | 默认 | 空值 | 枚举/约束 | 关系 | 来源 | 本地映射 |
|---|---|---|---|---|---|---|---|
| id | uuid | gen_random_uuid() | 否 | PK | — | 推断（标准建模） | 同 |
| hostId | uuid | — | 否 | FK → E04.Host | — | 推断 | 同 |
| slug | text | — | 否 | unique(hostId, slug) | — | 实测（URL 形如 /host/event） | 同 |
| name | text | — | 否 | 1–80 | — | 实测 | 同 |
| description | text | '' | 可空 | ≤ 2000 | — | 实测 | 同 |
| durationMin | int | 30 | 否 | 5–480，5 的倍数 | — | 实测 | 同 |
| bufferBeforeMin | int | 0 | 否 | 0–120 | — | 推断 | 同 |
| bufferAfterMin | int | 0 | 否 | 0–120 | — | 推断 | 同 |
| minNoticeMin | int | 240 | 否 | 0–10080 | — | 实测（默认 4 小时） | 同 |
| maxWindowDays | int | 60 | 否 | 1–365 | — | 推断 | 同 |
| timeZone | text | host.timeZone | 否 | IANA ID | — | 实测 | 同 |
| active | bool | true | 否 | — | — | 推断 | 同 |
| color | text | null | 可空 | hex | — | 推断 | 同 |
| questions | jsonb | [] | 否 | 自定义问题数组 | — | 实测 | 同 |
| createdAt | timestamptz | now() | 否 | — | — | 推断 | 同 |
| updatedAt | timestamptz | now() | 否 | — | — | 推断 | 同 |

**约束**：`CHECK (durationMin % 5 = 0)`；`CHECK (bufferBeforeMin + bufferAfterMin <= 480)`。

**本地映射说明**：
- 原版用分钟数还是「30 分钟」字符串？——用整数分钟，渲染时格式化。
- 原版时长是否允许 5 的倍数？——待验（U-003 之外的独立问题），当前按 5 的倍数实现并在设置界面校验。

---

## E02 Availability 可用规则

| 字段 | 类型 | 默认 | 空值 | 枚举/约束 | 关系 | 来源 | 本地映射 |
|---|---|---|---|---|---|---|---|
| id | uuid | gen_random_uuid() | 否 | PK | — | 推断 | 同 |
| eventTypeId | uuid | — | 否 | FK → E01 on delete cascade | — | 推断 | 同 |
| weekday | int | — | 否 | 0–6（0=周一） | — | 实测（每周重复） | **本地用 0=周一**，不用 .NET 的 0=周日 |
| startMin | int | — | 否 | 0–1439（当天第几分钟） | — | 推断 | 同 |
| endMin | int | — | 否 | 1–1440，> startMin | — | 推断 | 同 |
| createdAt | timestamptz | now() | 否 | — | — | 推断 | 同 |

**约束**：`UNIQUE (eventTypeId, weekday, startMin)`（防重复登记）。

**本地映射说明**：
- 跨午夜窗口（`endMin <= startMin`）**A 档不支持**，写入前拒绝（U-003）。
- 星期序号在跨语言/跨时区时最容易错，统一 0=周一，并在代码里用常量而非裸数字。

---

## E03 Booking 预约

| 字段 | 类型 | 默认 | 空值 | 枚举/约束 | 关系 | 来源 | 本地映射 |
|---|---|---|---|---|---|---|---|
| id | uuid | gen_random_uuid() | 否 | PK | — | 推断 | 同 |
| eventTypeId | uuid | — | 否 | FK → E01 | — | 实测 | 同 |
| hostId | uuid | — | 否 | FK → E04 | — | 推断 | 同 |
| startAt | timestamptz | — | 否 | 绝对时刻 | — | 实测 | **UTC 存储** |
| endAt | timestamptz | — | 否 | > startAt | — | 实测 | 同 |
| timeZone | text | — | 否 | IANA（**访客提交时的主理人时区**） | — | 推断 | 同 |
| guestName | text | — | 否 | 1–100，trim 后非空 | — | 实测 | 同 |
| guestEmail | text | — | 否 | 有效邮箱，≤ 320 | — | 实测 | 同 |
| guestTimeZone | text | — | 否 | IANA（访客的） | — | 实测 | 同 |
| answers | jsonb | '{}' | 否 | 自定义问题回答 | — | 实测 | 同 |
| status | text | 'pending' | 否 | pending/confirmed/rescheduled/cancelled | — | 推断 | 同 |
| rescheduledFrom | uuid | null | 可空 | FK → E03.id | — | 推断 | 同 |
| idempotencyKey | text | null | 可空 | unique（防重复提交） | — | 推断（U-007） | 同 |
| createdAt | timestamptz | now() | 否 | — | — | 推断 | 同 |
| updatedAt | timestamptz | now() | 否 | — | — | 推断 | 同 |

**关键约束（不是 UI 能解决的）**：
```sql
-- 两个访客不可能订到同一时段
alter table bookings
  add constraint no_overlapping_bookings
  exclude using gist (host_id with =, tstzrange(start_at, end_at) with &&)
  where (status not in ('cancelled'));
```
**为什么不用 UI 灰掉**：两个标签页、两台设备、慢网络下都会绕过。防超卖必须在数据库层。

**本地映射说明**：
- `status='rescheduled'` 的旧单**保留**（不是删除），因为要留历史与可追溯；`startAt` 保留原值，另用 `rescheduledFrom` 串链。
- `cancelled` 的单**不释放数据行**，但退出排除约束（因此时段释放）。这是"三态删除"思路的复用。

---

## E04 Host 主理人

| 字段 | 类型 | 默认 | 空值 | 枚举/约束 | 关系 | 来源 | 本地映射 |
|---|---|---|---|---|---|---|---|
| id | uuid | gen_random_uuid() | 否 | PK | — | 推断 | 同 |
| slug | text | — | 否 | unique | — | 实测（URL /host） | 同 |
| name | text | — | 否 | 1–80 | — | 实测 | 同 |
| email | text | — | 否 | 邮箱 | — | 实测 | 同 |
| timeZone | text | 'UTC' | 否 | IANA | — | 实测 | 同 |
| avatarUrl | text | null | 可空 | URL | — | 实测 | 同 |
| createdAt | timestamptz | now() | 否 | — | — | 推断 | 同 |

**A 档特例**：单用户本地自用，`Host` 只有一行；`slug` 固定为 `me`，不暴露"切换主理人"的入口。

---

## E05 Reminder 提醒

| 字段 | 类型 | 默认 | 空值 | 枚举/约束 | 关系 | 来源 | 本地映射 |
|---|---|---|---|---|---|---|---|
| id | uuid | gen_random_uuid() | 否 | PK | — | 推断 | 同 |
| bookingId | uuid | — | 否 | FK → E03 on delete cascade | — | 推断 | 同 |
| triggerAt | timestamptz | — | 否 | 绝对时刻 | — | 推断 | 同 |
| offsetMin | int | 1440 | 否 | 提前分钟数 | — | 推断 | 同 |
| status | text | 'scheduled' | 否 | scheduled/firing/sent/cancelled/failed | — | 推断 | 同 |
| attempts | int | 0 | 否 | ≥0 | — | 推断 | 同 |
| sentAt | timestamptz | null | 可空 | — | — | 推断 | 同 |

**约束**：`CHECK (triggerAt < (select start_at from bookings where id = booking_id))` —— 提醒必须早于预约开始。

**本地映射说明**：
- A 档先做**本地应用内通知**，不接真实邮件/短信（`F-SMS-REMINDER` 是差异化但不在 A 档实现）。
- `status` 五态对应 `SM-03`。

---

## E06 Outbox 通知发件箱

| 字段 | 类型 | 默认 | 空值 | 枚举/约束 | 关系 | 来源 | 本地映射 |
|---|---|---|---|---|---|---|---|
| id | uuid | gen_random_uuid() | 否 | PK | — | 推断 | 同 |
| kind | text | — | 否 | booking_confirmed/rescheduled/cancelled/reminder | — | 推断 | 同 |
| bookingId | uuid | — | 否 | FK → E03 | — | 推断 | 同 |
| payload | jsonb | — | 否 | — | — | 推断 | 同 |
| status | text | 'pending' | 否 | pending/sent/failed | — | 推断 | 同 |
| attempts | int | 0 | 否 | ≥0 | — | 推断 | 同 |
| sentAt | timestamptz | null | 可空 | — | — | 推断 | 同 |

**为什么用 outbox 而不是"事务后直接发邮件"**：直接在事务后发邮件，若进程在事务提交与发信之间崩溃，邮件就丢了。outbox 让"要发的信"和"业务数据"在**同一事务**落库，然后由独立 worker 投递。

---

## 双写字段的处理（本地映射的关键决策）

| 字段对 | 本地选择 | 理由 |
|---|---|---|
| `content` vs `desc`（本次案例遗留） | 只保留 `description` | 一个含义两个名字必然不同步 |
| `tag` vs `tags`（本次案例遗留） | 只保留 `questions` / JSONB | 数组不需要再存一份序列化字符串 |
| `timeZone` vs `guestTimeZone` | **两个都留，但含义不同** | 主理人时区决定边界（周、日），访客时区决定显示。合并会导致跨时区旅行时算错 |

**原则**：语义不同的两个值，不许因为"看着像"就合并；语义相同的历史双写，只留一个。

---

## 索引与查询口径

| 查询 | 索引 | 口径 |
|---|---|---|
| 某主理人某周的预约 | `bookings (host_id, start_at)` | 按主理人时区算周区间 |
| 某类型某周的占用 | `bookings (event_type_id, start_at) where status <> 'cancelled'` | 只看未取消 |
| 主理人搜索访客 | `bookings (host_id) where lower(guest_email) like ...` | 名字与邮箱两个字段 |
| 近期预约列表 | `bookings (host_id, start_at desc)` | limit 50 + 游标 |
| 待触发提醒 | `reminders (trigger_at) where status = 'scheduled'` | 定时器扫 |
| 侧栏角标 | `COUNT(*)` on 同一索引 | 与列表同索引 → 口径必然同源 |

**「计数同源」的实现要求**：列表、角标、标题三处必须用**同一个查询的同一结果**，或同一索引上的等价 COUNT。不允许一处查全量、一处查截断后。
