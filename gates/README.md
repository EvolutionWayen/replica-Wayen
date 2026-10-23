# 门禁引擎

> 12 道门，manifest 驱动，四态输出，带自测。**没有假绿。**

---

## 用法

```bash
python3 gates/run.py --project <项目根>                 # 全部门
python3 gates/run.py --project . --stage G2             # 单门
python3 gates/run.py --project . --stage all --json     # 机读
python3 gates/run.py --project . --verbose               # 详细
```

或用便利包装（会自动往上找 `.replica/gate.manifest.yml` 定位项目根）：

```bash
./scripts/run-gates.sh G2
./scripts/run-gates.sh --project ~/projects/my-clone
```

**输出**：
```
── G2 行为蓝图 ──────────────────────────────────────────
  小结：(27 PASS / 5 FAIL / 0 BLOCKED / 0 NA)
  [PASS]  G2.contract-coverage  must 功能契约覆盖率 100%
  [FAIL]  G2.linkage-six-face   F-BOOK-PAGE 有跨页面联动条目
          期望: 每个 must 功能在 linkage.csv 至少 1 行
          实际: 0 行
          证据: BLUEPRINT/linkage.csv
          修复: 列出这个功能影响到的六个面（列表/角标/详情/日历/搜索/提醒）
------------------------------------------------------------------------------
合计：27 项判定 · PASS 22 / FAIL 5 / BLOCKED 0 / NA 0
结论：不通过。先修 FAIL —— 每条后面都有证据路径与修复动作。
__RESULT__ pass=22 fail=5 blocked=0 na=0
```

**退出码**：

| 码 | 含义 |
|---|---|
| `0` | 全 PASS（含已批准的 N/A） |
| `1` | 有 FAIL |
| `2` | 无 FAIL 但有 BLOCKED（环境问题，**不是通过**） |

**JSON 模式**：`--json` 输出纯 JSON（`__RESULT__` 作为最后一个键），可直接被 CI 或其他工具消费。

---

## 四态，不许假绿

| 态 | 含义 | 能绕过吗 |
|---|---|---|
| `PASS` | 通过 | — |
| `FAIL` | 不过 | 不能，必须修 |
| `BLOCKED` | 环境/依赖问题导致无法判定 | 不能。**BLOCKED ≠ PASS** |
| `NA` | 经批准的不适用 | 必须带理由，且 G3 冻结后不许新增 |

**BLOCKED 的典型场景**：没装依赖、目录不存在、文件读不了。这时**不许说"应该没问题"**——先解决环境再重跑。

**NA 的批准记录写在 manifest**：
```yaml
na_approved:
  - id: G11.commercial
    reason: "A 档本地自用，不做商店合规"
    approved_by: Wayen
    approved_at: "2026-10-23T10:40+08:00"
```

---

## 12 道门

| 门 | 阶段 | 核心判定 |
|---|---|---|
| **G0** | S0 立项 | 必需文件存在且非占位；不做清单 ≥5 条；档位 ∈ {A,B,C}；制品身份（SHA-256 或取证方式）；DECISIONS ≥3 条；REDLINES 覆盖 R1–R20；manifest 存在且 tier 合法 |
| **G1** | S1 取证 | recon.md 10 段齐；features.csv 列齐 + ID 唯一 + 格式；screens.csv 四态齐；unknowns.csv 每条有验证动作；evidence/ 有受控文件；每行有证据 |
| **G2** | S2 行为蓝图 | **must 功能契约覆盖率 100%**；契约 16 节齐且非空；菜单叶子有 command + contract + 三条件（按 type 分级）；六面联动覆盖；flows 四段齐；状态机与数据字典存在 |
| **G3** | S3 冻结 | BLUEPRINT-LOCK 含版本/时间/确认人；**实算 SHA-256 与记录逐字比对**；阻断级未知 = 0；accepted-risk 有决策记录 |
| **G4** | S4 架构 | ARCHITECTURE 三节齐；schema.sql 非空；TRACEABILITY 覆盖每个 must 功能且 entities/commands 非 `-`；竖切证据存在 |
| **G5** | S5 设计 | tokens.json 可解析且含关键键；对比度检查 0 失败；每组件状态齐（default/hover/focus/disabled/loading/error）；素材替换表无空项 |
| **G6** | S6 联动门 | **done 的功能其 linkage 全部 wired/verified/na 且测试 PASS**；没有 linkage 行的 done 功能 → FAIL；六面全 na → FAIL；四态齐；must 路径无 TODO/FIXME |
| **G7** | S7 后端 | 有故障注入用例且 PASS；有重启读回用例且 PASS；**测试代码无 `:memory:`**；退出冲刷有结构化结果；真临时文件用法存在 |
| **G8** | S8 测试 | 最新结果 failed=0 且 timeout=0；**连续 N 次（默认 3）全绿**；bugs.md 无 open 的 S1/S2；每个 must 功能 ≥1 用例 |
| **G9** | S9 一致性 | parity.md 存在；**功能分由 features.csv 实算并与报告比对（误差 ≤1）**；功能分 ≥ 阈值；缺失清单非空 |
| **G10** | S10 痛点 | feedback.md 存在；每条痛点带链接与计数；含样本量声明；无编造标记 |
| **G11** | S11 发布 | A 档：启动脚本可执行、runbook 含备份/恢复/迁移/卸载、有恢复演练记录与日期。C 档：品牌清扫 0 命中 + 上架合规 |

---

## 判定原则（三条）

### 1. manifest 驱动，零硬编码

门禁**不写死**任何项目路径或数字。阈值、必需要件、NA 批准全从 `.replica/gate.manifest.yml` 读。

```yaml
project: my-clone
tier: A
target: "目标应用名 8.x"
baseline_commit: "77503da"
thresholds:
  parity_feature: 80
  consecutive_runs: 3
required:
  evidence_dirs: [evidence, screens]
  contract_sections: 16
  vertical_slice_evidence: SPEC/vertical-slice.md
na_approved: []
```

**为什么**：v1 的 `rea-gate.sh` 写死了 `if (len(t) == 68)`、只打印 SHA-256 不比对、G8 只要"任意受控证据 > 0"就算过——这类门禁不能作为自动放行依据。**门禁必须对项目一无所知也能给出正确判断。**

### 2. 查行为，不查关键词

**反例**（v1 真实教训）：`Assert.True(dataSaved || hasClosingFlush)` —— 数据已丢，只要代码里出现 Flush 字样仍然绿。

**所以门禁不扫"有没有写这个词"，而查"该有的证据在不在"**：
- G3 实算文件哈希并与冻结记录比对（不是看"锁文件存在吗"）
- G7 检查**故障注入用例存在且通过**（不是看"有没有 try/catch"）
- G8 读**连续多次的运行结果**（不是看"测试文件存在吗"）

### 3. 环境阻断不伪装成通过

依赖缺失 → `BLOCKED`，不是 `PASS`，不是 `FAIL`。
`BLOCKED` 的退出码是 2，和"全过"的 0 明确区分。

---

### 4. 按类型分级，不搞"一律"

同一条规则对不同节点类型的要求不同，**不能一刀切**——一刀切会逼人写废话，而门禁又禁不了
"不适用"这种写法，最后训练出的是糊弄行为，正好违背体系初衷。

**菜单三条件（`menus.csv`）**：

| type | 显示条件 | 可用条件 | 选中条件 |
|---|---|---|---|
| `radio` / `checkbox` | 必填 | 必填 | **必填**（有真正的选中态） |
| `submenu` / `action` | 必填 | 必填 | 允许 `-` 或 `不适用：<理由≥6字>` |
| `separator` / `label` | 跳过 | 跳过 | 跳过 |

理由：submenu 是容器、action 是一次性动作，**本来就没有"当前选中哪个"**。
禁用词（`按原版`/`视情况`/`同前`/`TBD`/`待定`）对**所有列**依然生效，只是对允许为空的列跳过"空"判定。

**`linkage.csv` 的 `na`（SCHEMAS §5）**：

- `status ∈ {pending, wired, verified, na}`
- `na` = "这一面**想过之后**确认不受影响"：理由写 `state_handling`，`affected_control` 写「不适用：…」，
  `test_ref` 允许 `-`，`refresh_timing` 仍要填（写「不适用」）
- `na` 不计入 missing，但**计入"已考虑面数"** → 这样"穷举过六面"与"漏了三面"能区分开
- **六面全 `na` 的功能 = 没做联动分析 → FAIL**（G2 与 G6 都拦）
- `pending` 是"还没接上"，不会被误报成"全 na"

**`default_item`（`menus.csv` 第 14 列）**：打开菜单时默认高亮/预选哪一项。
**允许 `-`，不阻断**；G2 只出 PASS + 建议文本（含 radio/checkbox 子节点的 submenu 建议填写）。

### 5. lint 是 WARN，门禁是 ERROR

同一套 ID/菜单规则在 `tools/blueprint_lint.py` 里是**体检**（WARN 不阻断，适合边写边看），
在这里是**放行**（必须 FAIL）。典型例子：

| 规则 | lint | 门禁 | 为什么 |
|---|---|---|---|
| `MENU-ORDER-DUP`（同级 order 重复） | WARN | **G2 FAIL** | 重复 = 渲染顺序不确定，不能带着不确定进开发 |
| `SCREEN-ID-FORMAT`（screen_id 必须 `S-\d{2}`） | ERROR | **G1 FAIL** | screen_id 是被 features/menus/linkage/flows 引用的主键；带后缀的描述写进 `name` 或 `area` |

## 目录结构

```
gates/
├── run.py              唯一入口
├── rules/
│   ├── common.py       Result 类、CSV 读取、哈希、标题解析、manifest 读取
│   ├── g0.py … g11.py  12 个门的规则模块，各暴露 check(ctx) -> list[Result]
├── fixtures/           夹具项目（good-min / broken-* / no-manifest）
│   └── _make.py        夹具生成器（可重复生成，不手写哈希）
└── tests/
    └── test_gates.py   自测
```

**加一门**：在 `rules/` 加 `g12.py` → 在 `run.py` 的 `STAGES` 注册 → 在 `gates/fixtures/_make.py` 加夹具 → 在 `test_gates.py` 加断言 → 在 `00-体系总纲.md` §3 门禁总表补一行。**四处都要改，缺一处 CI 会红。**

---

## 自测

```bash
python3 -m unittest discover -s gates/tests -v
```

覆盖：
- good 夹具全 PASS，退出码 0
- 每个 broken 夹具在**对应门** FAIL，退出码 1
- 缺 manifest → 全部 BLOCKED，退出码 2（不崩）
- 空目录 → 任何门都不该 PASS
- 规则不写死项目路径
- 不 import 第三方包
- 各种具体缺陷能被检出（契约缺节、菜单条件写"按原版"、linkage 未 wired、哈希不符、契约分数与实算不符……）

---

## 夹具

```bash
python3 gates/fixtures/_make.py          # 重新生成全部夹具
```

**不要手写夹具里的 SHA-256**——用生成脚本，否则改一次内容就得手改哈希。

| 夹具 | 用途 |
|---|---|
| `good-min` | 最小完整项目，全门 PASS |
| `broken-blueprint` | 契约缺节 + 菜单条件写"按原版" + 缺 unknowns |
| `broken-linkage` | feature=yes 但 linkage 仍 pending → G6 FAIL |
| `broken-linkage-allna` | 某 must 功能六面全 `na` → G2 + G6 双拦（等同没做联动分析） |
| `broken-menu-order` | 同级 `order` 重复 → G2 FAIL（渲染顺序不确定） |
| `broken-project` | 不做清单清空 + 决策表只剩骨架行 → G0 FAIL（两个假绿回归） |
| `broken-lock` | 蓝图哈希与实际不符 → G3 FAIL |
| `no-manifest` | 有目录没 manifest → 全部 BLOCKED，退出码 2 |

每套 broken 夹具都**只在该失败的门上失败**（`test_each_broken_fixture_is_focused` 守着这条），
这样出问题能一眼定位是哪条规则在起作用。

---

## 常见误判

| 现象 | 真实原因 | 怎么办 |
|---|---|---|
| G2 报"缺列 default_item" | SCHEMAS 加了新列，CSV 还没跟上 | 按 `templates/blueprint/SCHEMAS.md` 的列名与顺序改表头 |
| G3 报哈希不符 | 冻结后有人改了蓝图 | 走变更单（`BLUEPRINT/CHANGES/`），版本 +1 后重新冻结 |
| G6 报"没有 linkage 行" | 功能标了 done 但没做过联动分析 | 六面逐个问一遍，不影响的面写 `status=na` + 理由 |
| G8 报"连续运行不绿" | flaky 或上次第跑没记录 | 每次跑测试都要写 `TEST/results/<日期>-<run>.json` |
| G9 报"分数与实算不符" | parity.md 里手填了分数 | 用 `tools/parity_score.py` 重新生成 |
| 全门 BLOCKED | manifest 缺失或 YAML 解析失败 | 看 JSON 模式的 `error` 字段 |

---

## 两张「有意不一致」的清单（别当 bug 去"统一"）

体系的严度在**工具**和**门禁**两处刻意不同：工具是体检（提示 + 不阻断），门禁是放行（不通过就进不了下一阶段）。

| 检查项 | `tools/` | `gates/` | 为什么 |
|---|---|---|---|
| 同级 `order` 重复（`MENU-ORDER-DUP` / `menu-order-dup`） | WARN | **ERROR** | 工具只提示；渲染顺序不确定不能放行 |
| 契约缺失引用（`REF-*-CONTRACT-MISSING`） | ERROR + 双报 | 按门统计覆盖率 | 工具按文件修（双报便于消项）；门禁只问"覆盖 100% 了吗" |
| 未归类控件（`unclassified`） | advisory | 不检 | 分类法够不到 ≠ 规格写错，工具提示补 `#面名` 注释 |

**规则**：工具的严度 ≤ 门禁的严度。工具可以更啰嗦，但不能比门禁松。

---

## 单一事实来源：六面定义

六面（主列表 / 角标计数 / 详情面板 / 日历时间 / 搜索 / 提醒通知）的关键词表**只有一份**：

```
shared/faces.json
```

`gates/rules/common.py` 与 `tools/linkage_matrix.py` 都从它读；读不到时各自退回内置副本并在 stderr 警告（保证文件缺失不会让门禁瘫痪）。

**改关键词只改 `shared/faces.json` 一处。** 曾经两处各存一份——那正是本体系明令禁止的双写（R9 的近亲）。

---

## G9 功能分的口径（容易被误解）

```
功能分 = Σ(权重 × 完成度) / Σ权重 × 100
权重  must=3 / should=2 / could=1
完成度 yes=1.0 / partial=0.5 / no=0.0
剔除  progress=skip 或 original=no 或 scope=out
```

**计入分母的是「这一版承诺要做的」**（`scope=in` 且 `original=yes` 且不是 `skip`）。

所以：
- `could` 级但 `scope=in` 且 `progress=no` → **计入分母、得 0 分**。这是对的，因为你在这一版承诺了它。
- 不想被扣分 → 把它改成 `scope=out` 并在 `notes` 写明理由（这是合法的范围决策），而不是改分数的算法。

实测：good-min 里 `F-SYNC-CLOUD` 是 could + scope=in + no，把 100 分拉到 85.7。**这是正确的扣分**，不是 bug。

### 为什么 `scope=out` 必须有理由（G1 拦）

`scope=out` 会让该行**退出分母**。所以存在一条作弊路径：

```
把 must 功能改成 scope=out → 功能分自动变高 → 重算 parity.md → 重算 BLUEPRINT-LOCK → 全绿
```

实测确认这条路走得通（95/96 PASS），因此加了 **`G1.out-scope-reason`**：
- 每行 `scope=out` 的 `notes` 必须 ≥8 字，且不能是占位词（`无`/`待定`/`-`/`TBD`/`todo`）
- 有理由 = 合法范围决策，放行
- 没理由 = 不是决策，是躲分数，FAIL

现在这条路径会同时被三道门抓到：

| 门 | 抓什么 |
|---|---|
| G1 `out-scope-reason` | 改 out 没写理由 |
| G3 `lock-hashes` | 改了 features.csv 没重算冻结哈希 |
| G9 `parity-computed` | 报告分数与实算不符 |
