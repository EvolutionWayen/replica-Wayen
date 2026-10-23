# tools/ —— 工具层（Python 3 标准库，无第三方依赖）

> 这一层的职责：**把「我觉得蓝图挺全的」变成「机器说它还差 11 条，第 3 条在第 47 行」**。
> 所有工具都读 `templates/blueprint/SCHEMAS.md` 定义的格式，不另立第二套标准。

## 0. 一分钟上手

```bash
cd <体系根>                                  # 或 cd <你的项目根>
python3 tools/blueprint_lint.py --project .            # 蓝图能不能拿去审？
python3 tools/menu_walk.py    --project . --check       # 菜单三条件齐了吗？
python3 tools/linkage_matrix.py --project .             # 六面哪几面还没 wire？
python3 tools/parity_score.py --project . --markdown     # 做到什么程度了？
```

**统一约定**（每个工具都一样，不用记）：

| 项 | 约定 |
|---|---|
| `--project` | 项目根目录，默认 `.`；所有路径相对它解析 |
| `--json` | 机读输出，末字段 `__RESULT__` 给门禁 grep 用 |
| 退出码 | `0` 干净／`1` 已完成检查但发现问题／`2` 用法或输入错误（**没做检查**） |
| 中文输出 | 错误信息写「出了什么事 + 下一步做什么」，不抛栈 |
| `--help` | 每个工具都有，含示例 |

缺文件时不会崩溃，而是给可操作的错误，例：

```
【错误】缺 features.csv
【下一步】先跑上一阶段生成它（例：缺 features.csv → 先跑 S1 取证 /replica-recon）
```

---

## 1. `blueprint_lint.py` —— 蓝图自检器

**用途**：产品官审查会前必跑。逐条报告蓝图能不能拿去审。

```bash
python3 tools/blueprint_lint.py --project .                  # 分节人读报告
python3 tools/blueprint_lint.py --project . --summary-only   # 一行结论 + 计数（给产品官）
python3 tools/blueprint_lint.py --project . --fix-hints      # 每条附修复动作
python3 tools/blueprint_lint.py --project . --json           # 机读（G2 门可直接用）
python3 tools/blueprint_lint.py --project . --only 契约,引用  # 只跑某几个分区（见下方警告）
```

**`--summary-only` 是给产品官的模式**（他不需要看 26 条明细）：

```
蓝图自检 · scheduling-clone
❌ 不可进入产品官审查
  ERROR 26 ／ 缺契约 11 份（被 26 处引用） ／ WARN 0 ／ must 契约覆盖 100.0%（13/13） ／ 契约文件 1 份
按修的顺序：
  缺契约文件（去重）          11
下一步：python3 tools/blueprint_lint.py --project . --fix-hints   # 每条附修法
```

⚠ **`--only` 是过滤输出，不是跳过载入**：前置步骤（读文件、载 CSV、算 must 覆盖率）永远执行，
只有"检查项"受过滤。且 `--only` 的结论会显式标「非全量检查，不能据此判可审」——
因为"只跑 ID 没报错"不等于蓝图干净（曾经的真实缺陷：`--only ID` 跳过数据载入 → 永远报 0 条）。

| 项 | 内容 |
|---|---|
| 输入 | `BLUEPRINT/{recon.md, features.csv, screens.csv, menus.csv, flows.md, linkage.csv, unknowns.csv, contracts/*.md}` |
| 检查分区 | `文件` `CSV` `ID` `契约` `引用` `菜单树` `禁用词` `覆盖`（8 类，可用 `--only` 选） |
| 联动 `na` | `status=na` 合法，但必须写「不适用：<理由>」进 `state_handling`；`test_ref` 可填 `-` |
| 关键检查 | 契约 16 节逐字存在且非空非占位；CSV 列名与顺序；ID 唯一+格式；`features.contract_ref` 指向的文件存在；`linkage.source_id` 在 features 里；`test_ref` 形如 `T-\d{3}`（`na` 行可 `-`）；`flows.md` 引用的 `S-xx` 都存在；菜单 `parent_id` 闭合无环；禁用词（按原版/TBD/待定/视情况/同前）；must 功能契约覆盖率 |
| ID 双标准 | **`screen_id` 严格 `S-\d{2}`**（主键，被 features/menus/linkage/flows 引用，带后缀报专门码 `SCREEN-ID-FORMAT`）；**`features.area` 允许后缀**（描述字段，如 `S-03-预约页`，可读性优先） |
| 双报与去重 | 同一份缺失契约会被 features 与 menus 各报一次（**故意双报**：按文件修时能看出修完这一处消几条）；汇总里给**去重后的文件数** `missing_contract_files` + 引用处数 `missing_contract_refs` |
| `ORDER-DUP` | 本工具判 **WARN**（不阻断体检）；**门禁 G2 判 ERROR**（不放行）。工具是"体检"，门禁是"放行"，严度可以不同 |
| 输出 | 分节人读 / `--summary-only` 一行结论 / `--json`；ERROR 决定退出码，WARN 只提示 |
| 退出码 | `0` 无 ERROR（可进审查）／`1` 有 ERROR／`2` 输入错误 |

**典型判据**：`must_in=12, must_with_contract=12 (100.0%)` 才允许 `--only 覆盖` 通过。

---

## 2. `menu_walk.py` —— 菜单树穷举器

**用途**：把「该灰的不灰、该藏的没藏」这类翻车在 S2 就暴露。

```bash
python3 tools/menu_walk.py --project . --tree           # 缩进树（▸子菜单 ●动作 ◉单选 ☑多选 ──分隔 ¶文字）
python3 tools/menu_walk.py --project . --cards           # 每个叶子一张三条件卡
python3 tools/menu_walk.py --project . --gaps            # 缺项表：缺 command/契约/三条件
python3 tools/menu_walk.py --project . --check           # 门禁用：有问题退出码 1
python3 tools/menu_walk.py --project . --from-screens --screens screens/
                                                         # 按截图数量打印分层截图指引 + 生成待填骨架
```

| 项 | 内容 |
|---|---|
| 输入 | `BLUEPRINT/menus.csv`（`--from-screens` 另读截图目录的文件名与数量） |
| 输出 | 树 / 三条件卡 / 缺项表 / 退出码；`--json` 时给 `nodes/roots/leaves/gap_count/problems` |
| 特别注意 | `--from-screens` **只搭结构、只写说明**，不联网、不猜原版行为；骨架里全是「待填」 |
| 退出码 | `0` 干净／`1` 有缺项或结构问题（`--check`）／`2` 输入错误 |

树里会直接标出缺项，例：

```
▸ 日期   [M-DATE] (order 1)
    ● 今天   [M-DATE-TODAY] (order 1) 快捷键 ⌘T
    ● 清除日期   [M-DATE-CLEAR] (order 9) ⚠ 缺 选中条件
```

---

## 3. `linkage_matrix.py` —— 联动矩阵（功能 × 六面，四态）

**用途**：回答「这个功能改完，六个面哪几个要跟着变、变了没」。防 00 §10-01「功能清单齐、内部不联动」。

**四态口径**（SCHEMAS §5 的 `status` 枚举 = `pending` / `wired` / `verified` / `na`）：

| 标记 | 状态 | 含义 |
|---|---|---|
| `●` | `wired` / `verified` | 已接上（`● 已验` 表示该面所有条目都 verified） |
| `◐` | `pending` | 有条目但还没接 |
| `×` | `na` | **确认不适用**（必须真想过，理由写进 `state_handling`） |
| `·` | 无条目 | 漏了 |

**关键口径**：
- **缺面数 = 无条目数**（不含 `na`，也不含 `pending` —— pending 是已登记待做，不算漏）
- `na` **不计入 missing，但计入"已考虑面数"**：这样「穷举过六面」与「漏了三面」能区分开
- **六面全 `na` = 等同于没做联动分析**（防滥用），单独报 ⛔
- **六面无任何条目 = 完全没做过联动分析**，同样单独报 ⛔
- `na` 行必须写「不适用：<理由>」进 `state_handling`，`test_ref` 可填 `-`

**为什么要 `na`**：如果一个功能确实不影响某几面（成功页没有列表/角标/搜索），
不写就会逼人为了消警去写假联动——那恰好违背体系初衷。`na` 是"想过之后确认不影响"的合法登记。

```bash
python3 tools/linkage_matrix.py --project .                        # Markdown 矩阵
python3 tools/linkage_matrix.py --project . --md-out REPORT/linkage.md
python3 tools/linkage_matrix.py --project . --json                  # 供 G6
python3 tools/linkage_matrix.py --project . --strict                # 有未 wire 的面即退出码 1
python3 tools/linkage_matrix.py --project . --dump-config          # 打印当前六面（读自 shared/faces.json，用于核对）
python3 tools/linkage_matrix.py --project . --config faces.json          # 用自己的归类
```

| 项 | 内容 |
|---|---|
| 输入 | `BLUEPRINT/linkage.csv` + `features.csv` + `screens.csv` |
| 六面 | **定义在 `shared/faces.json`**（体系根下的唯一权威）。gates 与本工具**共用同一份**；改关键词只改那一处，两边自动跟随 |
| `--config` | 局部覆盖：数组 `[{"key":...}]` 或对象 `{"faces":[...]}` 都可以（后者就是 `shared/faces.json` 本身的形态） |
| 读不到 JSON 时 | 退回内置 `_FACE_FALLBACK`（只有 key/name + 空 keywords），stderr 警告一次。**不会瘫痪，但归类能力降级** |
| 输出统计（`--json` 的 `counts`） | `wired` / `pending` / `na` / `no_entry` / `considered` / `unwired_faces` / `zero_face_features` / `all_na_features` / `single_face_features` / `no_wired_features` |
| 归类规则 | 按 `affected_control` 的中文关键词归类（关键词来自 `shared/faces.json`）；可在 `affected_control` 末尾写 `#主列表` 强制归类 |
| 三个结论 | ① 每个 must 功能哪几面没 wire ② 「只有 1 面」的可疑功能（多半没想透）③ 联动条目自身缺刷新时点/缺测试号 |
| 输出 | Markdown 矩阵 + 待补清单 + 六面逐面归属；`--json` 里含 `counts` 与每个 must 的逐面状态 |
| 退出码 | `0` 通过／`1` `--strict` 且有不完整（默认只报不拦）／`2` 输入错误 |

---

## 4. `parity_score.py` —— 一致性评分（双分制）

**用途**：给出「做到什么程度」的**可反驳数字**。功能分回答「还能不能做完原来能做的事」，界面分回答「切换过来顺不顺手」。两者不互相抵消。

```bash
python3 tools/parity_score.py --project .                             # 终端摘要
python3 tools/parity_score.py --project . --markdown --md-out REPORT/parity.md
python3 tools/parity_score.py --project . --visual diffs/*.json        # 折入界面分
python3 tools/parity_score.py --project . --ui-dir screens clone-screens  # 自动配对跑 imgdiff
python3 tools/parity_score.py --project . --fail-under 80              # G9 用
python3 tools/parity_score.py --project . --no-upstream               # 强制内置实现
```

| 项 | 内容 |
|---|---|
| 算法来源 | **复用上游** `replica-skill/replica-diff/parity.py`（importlib 从路径加载，不写死路径）。加载失败/抛异常则用本文件内置的**等价实现**，并在输出里写明用的是哪一个 |
| 权重 | must 3 / should 2 / could 1；`yes`=1、`partial`=0.5、`no`=0；`skip` 与 `scope=out` 不进分母 |
| 双分 | 功能分（加权）+ 界面分（imgdiff 布局分均值，可缺省）；综合 = 80% 功能 + 20% 界面（无界面分时等于功能分） |
| 输出 | 终端摘要 / `--markdown` 报告（含「缺失清单」按建设顺序 + 「口径声明」供反驳）/ `--json` |
| 退出码 | `0` 达标／`1` 低于 `--fail-under` **或** must 未全绿（`--no-require-must` 可只报不拦，但仍会打印「不可交付」）／`2` 输入错误 |

> 为什么带 `--no-require-must`：S6/S7 中途跑分时 must 必然还没全绿，那一步只想知道分数；
> 但**默认**仍按 G9 口径拦，防止「分数 82 就叫可交付」的假绿。

---

## 5. `contract_scaffold.py` —— 契约骨架生成

**用途**：把「写 16 节契约」从一座山拆成 16 道填空题。每节带该节的**必须写什么**（取自 SCHEMAS §8）与**一条具体反例**。

```bash
# 单个
python3 tools/contract_scaffold.py --feature F-DATE-EDIT --name "修改日期" --out BLUEPRINT/contracts/
# 批量：为 features.csv 里所有还没有契约的行生成
python3 tools/contract_scaffold.py --all --project .
# 只给 must 生成（先攻关键路径）
python3 tools/contract_scaffold.py --all --project . --only-must
# 预演
python3 tools/contract_scaffold.py --all --project . --dry-run
```

| 项 | 内容 |
|---|---|
| 输入 | `--feature`+`--name`，或 `--all` 读 `BLUEPRINT/features.csv` |
| 输出 | `BLUEPRINT/contracts/C-F-xxx.md`：16 个二级标题与 SCHEMAS §8 **逐字一致**，每节 `<!-- 必须写什么 -->` + `<!-- 反例 -->` + 一行「待填：…」问句 |
| 不覆盖 | 已存在同名文件默认跳过（要覆盖加 `--force`）；`--all` 会跳过 `contract_ref` 已指向真实文件的行 |
| 退出码 | `0` 有生成或预演／`1` 全部跳过（没写任何文件）／`2` 参数错（ID 格式不对、既没 `--feature` 也没 `--all`） |

> 骨架是脚手架不是契约：`blueprint_lint.py` 会把「待填」判为 ERROR，逼你填完。

---

## 6. `evidence_manifest.py` —— 证据清单

**用途**：把「我截过图」变成可核对的台账，并守住证据的不可变性。

```bash
python3 tools/evidence_manifest.py --project .                 # 增量更新 + 汇总
python3 tools/evidence_manifest.py --project . --json
python3 tools/evidence_manifest.py --project . --check          # 门禁：台账不一致退出码 1
python3 tools/evidence_manifest.py --project . --verify         # 只校验已登记，不登记新文件
python3 tools/evidence_manifest.py --project . --dirs evidence screens --init   # 只建表头
```

| 项 | 内容 |
|---|---|
| 输入 | 扫 `evidence/`、`screens/`（`--dirs` 可改） |
| 输出 | `evidence/MANIFEST.csv`：`path / sha256_16 / bytes / mtime_iso / capture_method / screen_id / first_seen / status / sha256_full / notes` |
| 三条硬规则 | ① **只加不改**（已有行永不重写）② **同名文件哈希变了 → WARN，不覆盖**（原版行为可能变了，旧结论要复核）③ **文件消失 → 标 `MISSING`，不删行** |
| 留空待填 | `capture_method`（截图/DB导出/HAR）与 `screen_id`（S-xx）由人填，工具只提示 |
| 退出码 | `0` 干净／`1` 有 CHANGED 或 MISSING（`--check`）／`2` 目录不存在等输入错误 |

---

## 7. 与门禁的组合关系

工具是**诊断**，门禁是**判决**。判据统一在 `.replica/gate.manifest.yml`，工具不写死阈值。

```
S1 取证 ── evidence_manifest ─┐
                              ├─→ blueprint_lint（整体体检）
S2 蓝图 ── menu_walk ──┬──────┤
          contract_scaffold ──┤
          linkage_matrix ─────┘
                              ↓
                       产品官审查会（人）
                              ↓
S3 冻结 ────────────→ G3（哈希比对，工具只提供清单）
S6 联动门 ───────────→ G6（读 linkage_matrix --json 的 counts + TEST/results）
S9 评分 ───────────→ G9（读 parity_score --json 的 feature_score/overall）
```

| 门 | 消费哪个工具 | 用什么字段/退出码 |
|---|---|---|
| G1 | `evidence_manifest --check` | 退出码 0 且无 MISSING |
| G2 | `blueprint_lint --json` + `menu_walk --check` | `counts.error==0`、`must_with_contract==must_in`、`gap_count==0` |
| G6 | `linkage_matrix --json --strict` | `counts.unwired_faces==0` + `problems==0` |
| G9 | `parity_score --json --fail-under <阈值>` | `feature_score` / `overall` / `must_all_green` |

**注意**：门禁的实现（`gates/run.py`）由另一张任务卡负责，本目录只保证 `--json` 的字段稳定、`__RESULT__` 末尾可 grep。
**六面定义两侧共用 `shared/faces.json`**（不是"各写一份再对齐"）：`linkage_matrix.py` 与
`gates/rules/common.py` 都从同一个文件读，`scripts/selfcheck.py` 的 `FACES-SSOT` 项验证三者一致。

---

## 8. 自测

```bash
cd <体系根>
python3 -m unittest discover -s tools/tests -v     # 56 个用例
```

覆盖：干净夹具全通、破夹具逐项报错、缺文件不崩、退出码语义、上游算法与内置实现同分、
证据台账的「只加不改」与「哈希变了不覆盖」。夹具都在临时目录构造，不依赖任何真实项目。

---

## 9. 设计约定（改这些工具前先读）

0. **六面关键词只有一份：`shared/faces.json`**。`gates/` 与 `tools/` 都从它读，`scripts/selfcheck.py`
   的 `FACES-SSOT` 项守护三者一致。**任何一侧内联关键词列表 = 制造漂移**，会被工具测试
   （`TestFacesSingleSource`）直接判红。要改六面：改 JSON 一处 → 跑 `scripts/selfcheck.py`。
0b. **schema 漂移时工具要能救命，不是一起罢工**：`menus.csv` 少了 `default_item` 这类非核心列时，
   `menu_walk` 仍然出树/卡片/缺项（只在输出里 WARN + `--check` 计入失败），因为「看不到任何东西」
   比「看到带警告的东西」更糟。只有 `node_id` / `parent_id` / `type` / `label` 缺失才硬退。
1. **唯一格式来源是 SCHEMAS.md**：列名与 16 节标题都**现场解析** SCHEMAS；解析失败才退回
   `replica_common.BUILTIN_COLUMNS / BUILTIN_SECTIONS`，并在输出里声明「用的是内置常量」。
2. **公共逻辑一律进 `replica_common.py`**：CSV 读取、ID 正则、Markdown 切节、禁用词扫描、
   错误类型、等宽表格。不要在单个工具里复制一份。
3. **不写死项目路径与数字**：路径来自 `--project`，阈值来自参数或 manifest。
4. **不抛栈**：输入问题一律 `ToolError(message, hint)` → 打印「错误 + 下一步」→ 退出码 2。
   只有真 bug 才允许 Traceback。
5. **`--json` 必须含 `tool` 与 `__RESULT__`**：门禁与 CI 只认这两个。
6. **判定口径要与 00 §3.2 / SCHEMAS 对得上**：改判据 = 改门禁语义，要么同步 gates，要么提变更单。
7. **严度可以不同，口径必须同源**：工具的严度 ≤ 门禁的严度（例：`ORDER-DUP` 工具 WARN、G2 ERROR）。
   但**定义**（六面关键词、CSV 列、16 节标题）只有一个来源：`shared/faces.json`、
   `templates/blueprint/SCHEMAS.md`。工具不复制定义，只读取。
