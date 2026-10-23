# STATE —— 状态台账（唯一现状来源）

> 复制为 项目根 `STATE.md`。**正文文档里不许写「已修复 / 已完成 / 当前进度」，一律写在这里。**
> 本文件是「现在到底做到哪」的唯一答案；其他文件只引用 ID。

## 七态定义（只能用这七个值）

| 态 | 含义 | 谁能置位 | 前置条件 |
|---|---|---|---|
| `DRAFT` | 草拟，可能有错 | 任何人 | — |
| `APPROVED` | 产品官批准的行为/契约 | **产品官** | G3 通过 |
| `BUILT` | 代码写完，能跑 | 实现者 | 契约 `APPROVED` |
| `SELF-TESTED` | 实现者自己测过（**不等于通过**） | 实现者 | 有测试输出 |
| `VERIFIED` | 独立验证官按契约重放通过 | 验证官 | `SELF-TESTED` + 证据 |
| `ACCEPTED` | 产品官真机确认手感 | **产品官** | `VERIFIED` |
| `RELEASED` | 进了发布包 | **产品官** | `ACCEPTED` |

三条铁律：

1. **跳态 = 造假。** `BUILT` 直接跳 `ACCEPTED` 是体系里最严重的违规。
2. `VERIFIED` 后因变更可回落到 `APPROVED`，但必须留一行历史。
3. 改状态**必须同时填证据路径**；没有证据的 `VERIFIED` 无效。

## 状态表

| ID | 类型 | 名称 | 当前态 | 证据路径 | 最后更新 | 负责人 |
|---|---|---|---|---|---|---|
| F-DATE-EDIT | feature | 修改任务日期与时间 | DRAFT | `BLUEPRINT/contracts/C-F-DATE-EDIT.md` | 2026-10-23T11:00+08:00 | blueprint |
| S-02 | screen | 任务详情面板 | DRAFT | `evidence/shots/S02-*.png` | 2026-10-23T11:00+08:00 | blueprint |
| C-F-DATE-EDIT | contract | 日期编辑契约 | DRAFT | `BLUEPRINT/contracts/C-F-DATE-EDIT.md` | 2026-10-23T11:00+08:00 | blueprint |
| WP-001 | work-package | 竖切：建→读→重启 | DRAFT | `SPEC/vertical-slice.md` | 2026-10-23T11:00+08:00 | lead |

## 各阶段典型条目（开工时先建这些行）

| 阶段 | 要建的行 |
|---|---|
| S1 | 每个 `S-`、每个 `F-`（`DRAFT`） |
| S2 | 每个 `C-F-`、`M-` 菜单树、`LK-` 联动（`DRAFT`） |
| S3 | 被确认的契约 → `APPROVED`（证据指 `BLUEPRINT-LOCK.md`） |
| S4 | `SPEC/` 各产物 + `WP-`（`DRAFT`） |
| S6 | 每个 `F-` → `BUILT` → `SELF-TESTED`（证据指 `TEST/results/*.json`） |
| S8 | `VERIFIED`（证据指独立验证报告） |
| S9/S11 | `ACCEPTED` → `RELEASED`（证据指验收记录与发布记录） |

## 证据路径写法（必须能点开验证）

| 态 | 证据路径长什么样 |
|---|---|
| `APPROVED` | `BLUEPRINT/BLUEPRINT-LOCK.md`（含该文件的哈希） |
| `BUILT` | `src/<具体文件路径>` 或 `BUILD/build-log.md` 的行 |
| `SELF-TESTED` | `TEST/results/<日期>-run<N>.json`（含该用例 `pass`） |
| `VERIFIED` | `TEST/results/*.json` + 独立验证报告路径 |
| `ACCEPTED` | 真机验收记录（截图路径 + 时间） |
| `RELEASED` | `REPORT/release/local-runbook.md` + 发布记录 |

反例（无效证据）：「已测试」「看代码」「应该没问题」「截图见附件」（没有路径）。

## 状态变更历史（只追加）

| 时间 | ID | 从 | 到 | 谁 | 依据 |
|---|---|---|---|---|---|
| | | | | | |

> 回落到低态、跳态被驳回、重新打开，都记在这张表里。这张表是事后追责与复盘的唯一依据。
