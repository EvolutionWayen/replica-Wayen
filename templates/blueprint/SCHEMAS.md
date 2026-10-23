# 数据契约（SCHEMAS）—— 模板、门禁、工具共用的唯一格式定义

> 本文件是**机器契约**：所有 CSV 的列、所有契约文件的节、所有枚举值都在这里定义一次。
> 模板照此填写；`gates/run.py` 照此校验；`tools/` 照此计算。**改动本文件 = 改动门禁，须走变更单。**

版本：1.0 · 2026-10-23

---

## 0. 通用规则

1. **CSV 用 UTF-8、逗号分隔、首行为表头**。字段内含逗号或换行时用双引号包围（标准 CSV）。
2. **表头列名与顺序照本文件**。新增列只允许加在末尾，不改名、不删列、不改顺序。
3. **ID 一经分配永不复用**。删除用 `progress=skip` 或 `status=deprecated` 标记，不删行。
4. **空值写 `-`**，不写空白、不写 `待定`、不写 `TBD`。`-` 与「缺失」的区别是：`-` 表示经确认不适用，缺失表示还没做（门禁按缺失报 FAIL）。
5. **优先级枚举**：`must` / `should` / `could`（兼容 `P0`/`P1`/`P2`，脚本统一映射）。
6. **进度枚举**：`yes` / `partial` / `no` / `skip`。
7. **状态枚举**（仅 `STATE.md` 与 `BLUEPRINT-LOCK.md` 使用）：`DRAFT` / `APPROVED` / `BUILT` / `SELF-TESTED` / `VERIFIED` / `ACCEPTED` / `RELEASED`。
8. **档位枚举**：`A`（本地自用）/ `B`（半自用）/ `C`（商业）。
9. **一切「原版是这样的」断言**，同行必须有 `evidence` 或 `original_ref`（`S-xx` / `M-xx` / 证据路径）。
10. **时间一律 ISO 8601 带时区**，例：`2026-10-23T10:40+08:00`。

---

## 1. `BLUEPRINT/recon.md` —— 逆向地图

固定一级/二级标题（脚本按标题取段，标题文字必须完全一致）：

```
# recon · <目标应用名> <版本>
## 1 目标制品与身份
## 2 信息架构（屏幕树）
## 3 全部入口清单
## 4 核心用户流程
## 5 模块与依赖关系
## 6 数据模型概览
## 7 可见区域与不可见区域
## 8 未知与待验项
## 9 证据索引
## 10 规模判断与建议
```

| 段 | 必含 |
|---|---|
| 1 | 名称、版本、平台形态、获取方式、SHA-256、取证日期、档位 |
| 2 | 树状或表格：`S-id` + 名称 + 父子关系 |
| 3 | 桌面端：窗口/菜单栏/托盘/快捷键/命令行/深链；Web：URL 路由/直达链接/分享链 |
| 4 | `FL-id` 列表 + 每个流程的屏幕序列 + 点击数 |
| 5 | 模块 → 依赖模块 → 依赖方向（防循环） |
| 6 | 实体列表（明细进 `data-dictionary.md`） |
| 7 | 明确列出「看不到的部分」：权限后、付费墙后、服务端、硬件相关 |
| 8 | 与 `unknowns.csv` 一一对应 |
| 9 | 证据文件名 + 采集方式 + 采集时间 |
| 10 | S/M/L/XL + 理由 + 最难的三处 |

---

## 2. `BLUEPRINT/features.csv` —— 功能索引

列（11 列，顺序固定）：

| 列 | 含义 | 取值 |
|---|---|---|
| `feature_id` | 稳定 ID | `F-<域>-<短名>`，全大写连字符，例 `F-DATE-EDIT` |
| `feature` | 用户能做的一件事（动词开头，一句话） | 文本 |
| `area` | 所属屏幕/模块 | `S-xx` 名 或 模块名 |
| `priority` | 优先级 | `must/should/could` |
| `scope` | 是否在本版范围 | `in` / `out` |
| `original` | 原版有没有 | `yes` / `no`（`no` = 你新增的差异化功能） |
| `progress` | 本版实现进度 | `yes/partial/no/skip` |
| `contract_ref` | 契约文件 | `contracts/C-F-XXX.md` |
| `acceptance_ref` | 验收/测试号 | `T-xxx`（多值用 `;` 分隔） |
| `evidence` | 原版行为证据 | `S-xx` / `M-xx` / 证据路径 |
| `notes` | 补充 | 文本；`skip` 必须写理由 |

示例行：

```csv
feature_id,feature,area,priority,scope,original,progress,contract_ref,acceptance_ref,evidence,notes
F-DATE-EDIT,修改任务的日期与时间,S02-任务详情,must,in,yes,no,contracts/C-F-DATE-EDIT.md,T-101;T-102,screens/S02-date-menu-01.png,-
```

---

## 3. `BLUEPRINT/screens.csv` —— 屏幕清单

列（14 列）：

| 列 | 含义 |
|---|---|
| `screen_id` | `S-01` 起，两位数 |
| `name` | 屏幕名 |
| `entry` | 怎么进来（菜单/快捷键/URL/点击哪个控件） |
| `exits` | 怎么离开（返回/Esc/保存后/取消） |
| `purpose` | 用户来这里要完成什么 |
| `key_components` | 主要控件，逗号分隔 |
| `state_filled` | 有数据时的状态是否已记录（`yes/no`） |
| `state_empty` | 空态是否已记录 |
| `state_loading` | 加载态是否已记录 |
| `state_error` | 错误态是否已记录 |
| `state_permission` | 无权限/禁用态是否已记录（不适用填 `-` 并在 notes 说明） |
| `focus_restore` | 焦点/选中/滚动位置恢复行为 |
| `flows` | 经过此屏的流程 `FL-xx`（`;` 分隔） |
| `notes` | 备注 |

**G1 判定**：`state_filled/empty/loading/error` 四列必须为 `yes`（或 `-` 且 notes 有理由）。

---

## 4. `BLUEPRINT/menus.csv` —— 菜单树与三条件（最容易被糊弄的地方）

列（15 列，顺序固定）：

| 列 | 含义 | 示例 |
|---|---|---|
| `node_id` | 菜单节点 ID | `M-DATE-SUB-03` |
| `parent_id` | 父节点（顶层填 `ROOT`） | `M-DATE-SUB` |
| `path` | 完整路径，用 `›` 连接 | `日期 › 重复 › 每周` |
| `order` | 同级顺序（从 1 起） | `3` |
| `type` | 节点类型 | `submenu` / `action` / `radio` / `checkbox` / `separator` / `label` |
| `label` | 界面上的文字（原文照抄） | `每周工作日` |
| `shortcut` | 快捷键，无则 `-` | `⌘⇧W` |
| `visibility_cond` | **显示条件**：什么上下文/模式/数据状态下出现；隐藏后布局与焦点如何处理 | `当重复已开启 且 未处于完成态` |
| `enabled_cond` | **可用条件**：可见 ≠ 可用；禁用原因与提示 | `需有可写权限；退出冲刷阶段全菜单禁用` |
| `checked_cond` | **选中条件**：当前选中态由哪个持久值或草稿值决定 | `repeat.rule == 'WEEKLY' && repeat.byday 覆盖周一至周五` |
| `command` | 触发后执行的命令/动作 ID | `Cmd.SetRepeatWeeklyWorkdays` |
| `contract_ref` | 对应行为契约 | `contracts/C-F-REPEAT.md` |
| `screens` | 出现在哪些屏幕 | `S-02` |
| `default_item` | 打开菜单时**默认高亮/预选**哪一项；无默认填 `-`。这是契约 §3 要求的"默认项与当前项"，与 `checked_cond`（选中条件）不同：默认项是**首次打开时的焦点落点**，选中条件是**当前持久值是否与该选项匹配** | `M-DATE-TODAY`（打开日期菜单时高亮"今天"） |
| `notes` | 备注（含"未实现/原版无此层"等说明） | |

**G2 判定**：每个 `type != separator|label` 的节点必须有非 `-` 的 `command` 与 `contract_ref`；`visibility_cond`/`enabled_cond`/`checked_cond` 三列不得为空，且不得写「视情况」「按原版」「同前」。`default_item` 允许为 `-`，但若为 `submenu` 类型且子节点中有 `radio`，建议填写。

---

## 5. `BLUEPRINT/linkage.csv` —— 跨页面联动（防"页面有、内部不联动"的核心）

列（10 列）：

| 列 | 含义 | 示例 |
|---|---|---|
| `link_id` | `LK-001` 起 |
| `source_id` | 触发源：功能/命令/事件 | `F-DATE-EDIT` |
| `event` | 具体事件 | `TaskDateChanged{taskId}` |
| `affected_screen` | 受影响的屏幕/面 | `S-01` |
| `affected_control` | 受影响的具体控件/区域（不许写"界面刷新"） | 主列表行日期徽标 |
| `data` | 关联数据/查询 | `TaskModel.dueDate` |
| `refresh_timing` | **刷新时点**（提交成功后 / 事件广播 / 下次进入时 / 定时） | `写入事务提交成功 → 同步刷新` |
| `state_handling` | 保留还是清空的状态（焦点/选中/滚动/筛选） | `保留选中；若该行因筛选移出，焦点落到下一行` |
| `test_ref` | 对应用例号；`status=na` 时填 `-` | `T-103` |
| `status` | `pending` / `wired` / `verified` / **`na`** | `wired` |

**六面必查清单**（每个 affecting 事件都要问一遍，不适用的**必须显式登记一行 `status=na` 并写理由**，而不是省略）：
`主列表` / `侧栏或标签角标计数` / `详情面板` / `日历或时间视图` / `搜索结果` / `提醒调度`

**`na` 的语义与纪律**：
- `na` 表示"这一面确认不受影响"，**必须真的想过**，理由写进 `state_handling`（例：`不适用：成功页无列表，无角标`）。
- `na` 行同样要填 `affected_control`（写"不适用：…"）与 `refresh_timing`（写"不适用"）。
- **`na` 不计入 `missing`，但会计入"已考虑面数"**——这样"穷举过六面"和"漏了三面"在报告里能区分开。
- 滥用 `na` 是造假，与 §9 的 R20 同罪：**六面全填 `na` 的功能等同于没有做过联动分析**，`tools/linkage_matrix.py` 会对"六面全 na"的功能单独报警。

**G6 判定**：`features.csv` 中 `progress=yes` 的功能，其作为 `source_id` 的所有 `linkage` 行必须 `status ∈ {wired, verified, na}`；其中 `wired`/`verified` 行的 `test_ref` 必须在 `TEST/results/` 最新结果中 PASS。

**六面判定的口径（v2.1 定案，勿再改）**：

| 判据 | 结论 |
|---|---|
| 一个 must 功能在 linkage 里一行都没有 | **FAIL**（做了个壳，从没想过联动） |
| 有行但六面**全部**是 `na` | **FAIL**（全 na = 懒得想，等同于没做分析） |
| 至少 1 面 `wired`/`verified` | **PASS**（其余面可以是 `na` + 理由） |
| `pending` 与 `na` | 都算"已考虑"，但 `pending` 不算"已接线" |

**为什么不再要求「≥2 个受影响屏幕」**：引入 `na` 之后，一个功能完全可能只影响一面（例：成功页只有日历下载），其余五面写 `na` 是正确表达。用"2 个屏幕"卡会把正确规格误判成不合格，逼人写假联动。

**为什么全 `na` 要 FAIL**：`na` 是"想过之后确认不影响"，六面全 `na` 意味着"一面都没想过"，两者必须区分开——这是 `na` 存在的全部意义。

**六面定义在哪**：唯一权威是 `shared/faces.json`（`gates/` 与 `tools/` 都读它）。改关键词只改那一处。

---

## 6. `BLUEPRINT/unknowns.csv` —— 未知台账

列（9 列）：

| 列 | 含义 |
|---|---|
| `unknown_id` | `U-001` 起 |
| `area` | 所属模块/屏幕 |
| `description` | 未知什么（具体到行为，不写"细节待定"） |
| `impact` | 影响哪些功能/字段/联动 |
| `evidence_gap` | 缺什么证据 |
| `verification_action` | **具体怎么补验**（可执行动作，不是"再研究一下"） |
| `owner` | 谁负责 |
| `blocking` | `yes` / `no`（`yes` 阻断开发） |
| `status` | `open` / `resolved` / `accepted-risk` / `out-of-scope` |

**G3 判定**：`blocking=yes` 且 `status=open` 的条数必须为 0。`out-of-scope` 必须在 `decisions.md` 有产品官批准记录。

---

## 7. `BLUEPRINT/flows.md` —— 用户流程

每个流程固定结构（脚本按 `## FL-xx` 与三个子标题切分）：

```markdown
## FL-01 修改任务日期

- 目标：<用户想达成什么>
- 起点：<从哪进来>
- 路径：S-01 → S-02 → 菜单 M-DATE → 结果
- 点击数：<happy path 点击数>

### 正常路径
1. <动作> → <可见结果>
2. ...

### 失败与取消
| 情形 | 用户看到 | 系统状态 | 可恢复动作 |
|---|---|---|---|

### 边界
| 边界 | 期望行为 | 依据 |
|---|---|---|
| 跨月 / 闰日 / 时区变更 / 全天切换 ... | | |

### 恢复
<误操作、保存失败、应用中途中止时的恢复路径>
```

---

## 8. `BLUEPRINT/contracts/C-F-xxx.md` —— 功能行为契约（16 节，一节不能少）

标题文字必须与下列**完全一致**（含序号与空格）。判定方式：逐字匹配二级标题。

```
# C-F-xxx · <功能名>
## 1 目标与入口
## 2 界面与层级
## 3 每个菜单选项
## 4 显示条件
## 5 可用与选择条件
## 6 筛选条件
## 7 业务实现逻辑
## 8 具体效果
## 9 状态变化
## 10 数据读取
## 11 数据写入
## 12 跨页面联动
## 13 并发与生命周期
## 14 撤销与恢复
## 15 体验标准
## 16 测试与证据
```

每节最小内容（缺内容 → FAIL；确定不适用 → 该节正文以 `N/A：` 开头 + 理由）：

| 节 | 最小内容 |
|---|---|
| 1 | 用户意图、全部入口（含快捷键与替代路径）、前置上下文 |
| 2 | 控件顺序与层级、浮层/子菜单关系、可滚动区、尺寸策略 |
| 3 | 每个菜单叶子：完整路径、顺序、类型（单选/多选/动作/分隔符）、默认项与当前项、打开关闭行为、鼠标跨层与键盘行为 |
| 4 | 出现条件、隐藏后的布局与焦点处理 |
| 5 | **可用 ≠ 已选中**：可用条件、禁用解释、互斥与组合、最大选择数、取消选择；选中态由哪个持久/草稿值决定 |
| 6 | AND/OR 与嵌套优先级、包含/排除、空值、边界日期与时区、排序、分组、分页、角标统计口径 |
| 7 | 规则求值顺序、默认规则、参数、校验、算法边界（不许只写"调用某服务"） |
| 8 | 每步操作后的文案、数值、位置、列表成员、计数、反馈；能被具体输入复算 |
| 9 | 原状态 → 事件 → 条件 → 目标状态 → 副作用；含加载/保存中/失败/冲突/重试/取消/撤销 |
| 10 | 实体与字段来源、查询条件、派生值、数据新鲜度、空库与异常库行为 |
| 11 | 命令与参数、精确字段、事务范围、约束、写入时点、完成信号、失败保留、必须不变的字段 |
| 12 | 列表/角标/详情/日历/搜索/提醒各自影响；刷新或失效机制、时序与一致性；对应 `LK-xxx` |
| 13 | 快速连点、重复提交、A→B 切换、迟到结果、防抖、关窗、退出、重启、睡眠唤醒 |
| 14 | 恢复哪些值、窗口期、连续编辑处理、保存失败重试、误操作保护 |
| 15 | 输入法组合、焦点返回、Esc/Enter、可访问性、布局稳定、滚动动效、性能起止点 |
| 16 | 正常/负向/边缘/跨页面/立即退出重启 用例号与断言值；截图不能代替落库证明 |

---

## 9. `BLUEPRINT/state-machines.md`

每个状态机固定结构：

```markdown
## SM-01 <对象名>

### 状态
| 状态 | 含义 | 是否持久化 |
|---|---|---|

### 转换
| 从 | 事件 | 守卫条件 | 到 | 附带动作 | 异步结果处理 |
|---|---|---|---|---|---|

### 非法转换
| 尝试 | 期望拒绝方式 | 用户看到 |
|---|---|---|
```

## 10. `BLUEPRINT/data-dictionary.md`

```markdown
## E01 <实体名>
| 字段 | 类型 | 默认 | 空值 | 枚举/约束 | 关系 | 来源（原版观察/推断） | 本地映射 |
|---|---|---|---|---|---|---|---|
```

字段 ID 写作 `E01.dueDate`，脚本按 `E\d+\.` 收集引用。

## 11. `BLUEPRINT/BLUEPRINT-LOCK.md` —— 冻结记录

```markdown
# 蓝图冻结记录

| 项 | 值 |
|---|---|
| 蓝图版本 | v1.0 |
| 冻结时间 | 2026-10-23T10:40+08:00 |
| 确认人 | Wayen |
| 确认方式 | 逐条审阅 features.csv must 行 + contracts 12 节 + menus 三条件 |
| 门禁结果 | G1 PASS / G2 PASS |

## 文件哈希（SHA-256）

| 文件 | SHA-256 |
|---|---|
| BLUEPRINT/recon.md | <64 hex> |

## 确认要点
- [ ] 核心行为理解无误（列出你逐条确认的 must 功能 ID）
- [ ] 保留/改进项已记录（`DECISIONS.md` 中 D-xx）
- [ ] 阻断级未知为 0
```

**G3 判定**：版本号、时间、确认人齐；哈希表覆盖 `recon.md`/`features.csv`/`screens.csv`/`menus.csv`/`flows.md`/`linkage.csv`/`state-machines.md`/`data-dictionary.md`/`unknowns.csv` + 全部 `contracts/*.md`；实算与记录一致。

---

## 12. `SPEC/TRACEABILITY.csv` —— 追踪矩阵

列（9 列）：`feature_id` / `contract_ref` / `screen` / `menu_nodes` / `entities` / `commands` / `routes` / `tests` / `state`

**G4 判定**：`features.csv` 中 `priority=must & scope=in` 的功能，必须在此表有一行且 `entities`/`commands` 非 `-`。

## 13. `SPEC/DESIGN/tokens.json`

沿用上游 `replica-skill/replica-design/tokens.json` 结构（`contrast.py` 直接可用），必须含：
`color`（角色名：bg/surface/border/text/text-muted/accent/on-accent/danger/success/warning）、`font`、`space`、`radius`、`shadow`、`motion`、`pairs`（每个前景/背景组合）。

## 14. `TEST/test-plan.md` 与 `TEST/results/*.json`

`test-plan.md` 每个用例固定行：`| T-xxx | FL-xx | 类型(正常/负向/边缘/跨页面/生命周期) | 步骤 | 期望（具体值） | 自动化(是/否) |`

`TEST/results/<日期>-<run>.json` 结构：

```json
{
  "run": "2026-10-23T11:00+08:00",
  "suite": "e2e",
  "commit": "<基线 commit>",
  "total": 42, "passed": 42, "failed": 0, "timeout": 0,
  "cases": [{"id": "T-101", "status": "pass", "duration_ms": 812}]
}
```

**G6/G8 判定**：取**最新**结果文件；`linkage.test_ref` 指向的用例必须 `pass`；`consecutive_runs`（manifest 配置，默认 3）次连续结果必须全 `pass` 且 `failed=0`。

## 15. `.replica/gate.manifest.yml`

```yaml
project: rebuild
tier: A                     # A | B | C
target: "目标应用 8.x"
baseline_commit: "77503da"
thresholds:
  parity_feature: 80        # G9 功能分下限
  consecutive_runs: 3       # G8 连跑次数
required:
  evidence_dirs: [evidence, screens]
  contract_sections: 16
na_approved:                # 经批准的 N/A（G3 后不许新增）
  - id: G11.commercial
    reason: "A 档本地自用，不做商店合规"
    approved_by: Wayen
    approved_at: "2026-10-23T10:40+08:00"
```

`gates/run.py` 只读本文件，不写死任何项目路径或数字。

---

## 16. `STATE.md` —— 唯一现状来源

```markdown
| ID | 类型 | 名称 | 当前态 | 证据路径 | 最后更新 | 负责人 |
|---|---|---|---|---|---|---|
| F-DATE-EDIT | feature | 修改日期 | ACCEPTED | TEST/results/2026-10-23-run3.json | 2026-10-23T18:00+08:00 | lead |
```

规则：正文文档不写现状；改状态必须同时填证据路径。
