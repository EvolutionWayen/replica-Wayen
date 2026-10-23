# COMPAT · 上游 11 个技能 ↔ 本体系 12 阶段（哪些照用、哪些被覆盖、哪些必须改）

> 上游：`replica-skill/`（作者 Jake Schincariol，MIT，**原样 vendored，不修改**）。
> 本地：`00-体系总纲.md` v2.0 + `stages/` + `gates/` + `tools/` + `skills/`。
>
> **总原则**：上游给的是**方法与工具素材**，本地给的是**规则与门禁**。两者冲突时**以本地为准**；
> 本地没规定的，照上游做。本文只解释「为什么冲突」「冲突处怎么办」，不重写上游。

---

## 1. 映射表：11 个上游技能 → 12 个阶段

| 本地阶段 | 上游技能 | 用它的什么 | 本地额外要求（上游没有的） |
|---|---|---|---|
| **S0** 立项与边界 | （无） | — | `PROJECT.md` + 不做清单 ≥5 + 档位 + 制品 SHA-256（上游 recon 只问「哪一块切片」，不问档位与不做清单） |
| **S1** 取证 recon | `replica-recon` | 9 步动作序列、来源优先级表、屏幕/流程/组件/数据模型的记录颗粒度、`features.csv` 列定义思路 | **G1**：每条结论可指证据；屏幕四态齐；未知台账带补验动作；`evidence/MANIFEST.csv` 入版本控制；**A 档允许源码/二进制/数据库直读**（覆盖上游禁令，见 §2.1） |
| **S2** 行为蓝图 | `replica-recon`（仅取材） | 组件清单 → 设计系统的输入 | **本地上游没有等价物**：菜单三条件、16 节契约、六面联动、状态机、数据字典、`unknowns.csv` 全部是本地新增。执行手册见 `skills/replica-blueprint` |
| **S3** 审查与冻结 | （无） | — | 本地新增。产品官审查会 + `BLUEPRINT-LOCK.md` 哈希 + 冻结后改动即 FAIL（上游没有冻结概念） |
| **S4** 架构 | `replica-architect` | 默认技术栈表、schema 写法（主键/owner/index/枚举/时间/金额）、路由按 flow 组织、竖切优先的构建顺序、「会咬人的部分」清单 | **必须换成你自己的栈**（上游默认 Next.js+Postgres+Stripe，A 档本地自用通常是 SQLite + 桌面壳）；加 `TRACEABILITY.csv`；加「高风险竖切」判据 |
| **S5** 设计系统 | `replica-design` | 量而不猜的方法（颜色角色/字号阶梯/8px 间距/圆角阴影动效）、`tokens.json` 结构、组件规格块、`contrast.py` | **G5**：0 处对比度失败；每组件六态（default/hover/focus/disabled/loading/error）；**无原版素材残留** |
| **S6** 逐屏重建 | `replica-build` | 先壳后竖切再逐屏、每屏全状态、Definition of Done 七条、每屏一提交 | **G6 联动门**（本体系最严的那道）：done 的功能六面必须 wired + 有测试证据。上游只要求「勾 features.csv」，不管联动 |
| **S7** 后端与本地能力 | `replica-backend` | 认证/迁移/权限/邮件/作业的**结构与清单**（安全清单尤其有用） | **A 档要本地化改造**：不要 Stripe/Supabase/Resend —— 换成 SQLite + 本地通知 + 单用户。但**保留它的三条纪律**：官方 API + 用户自己的 key、密钥只进环境变量、先测试模式 |
| **S8** 测试 | `replica-test` | 从 flow 生成用例、Edge case 清单（时区/夏令时/双击/两标签页/离线/权限）、bug 分级 S1–S4、**「测你的克隆，不测原版服务器」** | **R1–R5 加严**：禁 `sleep` 等异步、真文件禁内存库、断言具体值、全量连跑 ≥3 次、故障注入。上游只说「写 Playwright」，不规定这些 |
| **S9** 一致性评分 | `replica-diff` | `parity.py`（加权算法）+ `imgdiff.py`（布局 edge-map 对比，忽略配色）+ 双分制的思想 + 「must 缺失即不可交付」 | 本地 `tools/parity_score.py` **复用**这两个算法并加：读本项目列名、双分报告模板、`--fail-under` 退出码、口径声明 |
| **S10** 痛点与差异化 | `replica-entrepreneur` | 「不编造、每条带链接与计数、样本量必须声明」的铁律、三个清单（恨什么/缺什么/没解决）、定位公式 | **G10**：改进项必须走 S2 契约补写，**不许直接进代码**（上游允许「加进 features.csv 就做」） |
| **S11** 品牌与发布 | `replica-brand` · `replica-launch` · `replica-deploy` | 品牌清扫 `sweep.py`、命名与商标检索清单、落地页结构、商店文案限额 `listing.py`、部署预检 preflight | **A 档只做本地 runbook**：启动/备份/恢复/迁移/卸载，不买域名、不做商店合规。C 档才全套 |

**一句话结论**：上游覆盖 S1、S4–S11 的**方法**；S0、S2、S3 是本地**独有**；S9 是「复用其算法 + 加双分与门禁」。

---

## 2. 被本地覆盖的上游规则（逐条给理由）

### 2.1 【核心冲突】「不许看源码 / 反编译」→ A 档允许，但只当规格书

| 项 | 上游怎么说 | 本地怎么办 |
|---|---|---|
| 原文 | `replica-recon`：**"No source code, no private APIs. Do not read or save the app's JavaScript bundles, decompile its binary, or log its network calls to copy endpoints."** | A 档（本地自用、不外发）**允许**：源码/二进制的**静态**分析、数据库**只读副本**导出。目的仅限本地自用与个人研究 |
| 覆盖范围 | 全部档位 | 仅 A 档。**B 档保留原限制**（要给身边人用，风险外溢）；**C 档一律回到上游口径**（商业档还必须做品牌清扫与许可证台账） |
| 硬约束（不因为授权而放松） | — | **R9**：反编译/还原代码**只当规格书读，不编入产品**。数据表结构可照搬语义，代码必须自己重写并测试 |
| 为什么可以这样 | 上游是为「做竞品去卖」设计的（清干净法律风险）；本体系默认是「自己用的替代品」。**风险性质不同**：不外发＝不分发＝不构成对外提供 | 一旦要外发（B/C），这条豁免立刻失效 |
| 谁来判定 | — | 产品官在 S0 定档位；档位写进 `.replica/gate.manifest.yml` 的 `tier` 字段。**改档位＝改授权，必须重新确认** |

> 载入 `skills/replica-local-source` 时才展开具体手法；未载入时按上游口径（只看公开页面 + 自己的账号）。

### 2.2 「数据库」→ 默认操作副本

| 项 | 上游 | 本地 |
|---|---|---|
| 立场 | 从不直连原版数据库（没有这个概念） | A 档可直读，但 **`cp` 到工作副本再动**，禁止直接操作真实库 |
| 理由 | — | 00 §10-07 实测：直接对线上库操作会把真实数据搞坏；Core Data 还有 WAL 未 checkpoint 被覆盖的问题（§10-12） |
| 落地 | — | 路径约定 + 操作前后 SHA-256 比对 + 原始库 mtime 不变，见 `skills/replica-local-source` §3 |

### 2.3 「清房间重写」→ **继续生效，一个字都不放松**

| 上游规则 | 本地 |
|---|---|
| 每一行代码自己写，绝不粘贴原版 HTML/CSS/JS/SVG/图片 | ✅ **继续生效**（R9）。反编译产物只读来写规格，不复制进 `src/` |
| 每个标签、按钮、空状态、邮件文案自己写 | ✅ 继续生效（S5 判据：无原版素材残留；C 档 `sweep.py` 0 命中） |
| 不用原版的 logo/图标/插画/字体 | ✅ 继续生效 |
| `features.csv` 的 `original` 列区分「原版有的」与「你新增的」 | ✅ 继续生效（本地 `scope` 另加 in/out 表示本版范围） |

### 2.4 「只读你有权读的」→ 部分覆盖（范围随档位）

| 上游禁止 | 本地 A 档 | 本地 B/C 档 |
|---|---|---|
| 登录别人的账号 | ❌ 仍然禁止 | ❌ 仍然禁止 |
| 越过付费墙 / 绕过付费 | ❌ 仍然禁止（见 §2.5） | ❌ 仍然禁止 |
| 对自己的账号做网络抓包看端点 | ⚠️ 允许**只读**观察自己的流量（A 档），但**不得**复制端点去调用原版服务 | ❌ 恢复上游禁令 |
| 抓取/爬取 | ❌ 仍然禁止（人类速度阅读，不批量下载） | ❌ 仍然禁止 |
| 打原版服务器做压测/模糊测试 | ❌ **永远禁止** | ❌ **永远禁止** |

### 2.5 「不碰别人的服务」→ **永远生效，不因档位放宽**

- **不改、不绕过、不重放原版线上服务**（包括用自己的账号绕过付费限制去调用付费接口）。
- **不拿原版私有端点做自己产品的后端**（上游：*never call the original app's private endpoints*）。
- **测试只打自己的克隆**（`replica-test`：*Test your clone, not the original*）。
- 本地 A 档的口径是**只读**：可以读、可以导出、可以当规格书，**不改本机二进制、不改签名、不改原应用的数据库、不绕付费**。这次实证已经说明：改二进制换来的是空壳，不是能力。

### 2.6 「必须先重新命名才能发布」→ A 档不适用，C 档加严

| 档位 | 品牌要求 |
|---|---|
| A 本地自用 | 不做品牌清扫、不买域名、不上架。但 `src/` 里**不许出现原版 logo 与素材**（避免以后想升级档位时返工） |
| B 半自用 | 要能给别人装：名称与图标必须自有，`sweep.py` 至少 0 命中名称与域名 |
| C 商业 | 全套：商标检索、域名、视觉文案全面切割、`sweep.py` 0 命中、`listing.py` 通过 |

### 2.7 「评分口径」→ 加严 + 加一条禁止

| 上游 | 本地 |
|---|---|
| 综合分 = 80% 功能 + 20% 布局 | ✅ 保留（`tools/parity_score.py` 实现一致） |
| must 缺失即 not shippable | ✅ 保留并加严：**默认 `--require-must`**，分数再高也不放行 |
| — | ➕ 本地新增：**界面分不得抵消功能缺失**；报告必须带「口径声明」供反驳；分数必须由 `features.csv` 实算，不许手填（G9） |

### 2.8 「测试怎么做」→ 全面加严（上游流程对，纪律不够）

| 上游 | 本地 |
|---|---|
| 写 Playwright 规格、跑 happy path 与 edge case | ✅ 保留 |
| 每 spec 失败于 console error / 5xx / axe | ✅ 保留 |
| — | ➕ R1 禁 `sleep` / `Task.Delay` 等异步（`grep` 计数必须为 0） |
| — | ➕ R4 持久化必须真文件，禁内存库；断言查具体值 |
| — | ➕ R5 全量连跑 ≥3 次（上游一次绿就算过） |
| — | ➕ R19 禁 `A || B` 式或放行 |
| — | ➕ 人工确认项必须显式列出，「假覆盖」比「没覆盖」更糟 |

---

## 3. 继续完全生效的上游规则（照抄，不解释）

1. **公开资料与自己的账号**为默认来源；help center → pricing → changelog → 商店页 → 公开视频 → 自己的账号 → 公开 API 文档（这个优先级顺序很好用）。
2. **不要痴迷像素级对齐原版**：布局分是为了「切换过来不陌生」，不是「一模一样」。原版的确切外观是它的 trade dress。
3. **不许编造**：评论、引述、评分、用户数、来源，一条都不许编（`replica-entrepreneur`）。每条断言带链接与样本量。
4. **不许把用户评价当自己的推荐语**（reviewer 的话是研究材料，不是 testimonial）。
5. **不能用 `A || B` 式验收**（本地 R19 的表述，上游同源精神）。
6. **诚实报数**：62% 就说 62%；不许承诺「完美复刻」。
7. **工具都是标准库 Python、不联网**（`parity.py` / `imgdiff.py` / `contrast.py` / `sweep.py` / `listing.py` / `reviews.py`）——本地 `tools/` 沿用这条。
8. **`replica-deploy` 的「没有用户点头不许上线」**：A 档没有上线，但有等价物——**没有产品官点头不许进 S6 批量开发**。

---

## 4. 上游工具在本地的用法对照

| 上游脚本 | 原始用法 | 本地用法 | 备注 |
|---|---|---|---|
| `replica-diff/parity.py` | `parity.py replica/features.csv` | 被 `tools/parity_score.py` **importlib 动态加载**，喂本项目列名（`progress` 而非 `clone`） | 加载失败自动退回内置等价实现，并在输出里声明用的哪个 |
| `replica-diff/imgdiff.py` | `imgdiff.py a.png b.png --out d.png` | `tools/parity_score.py --ui-dir screens clone-screens` 自动配对调 `read_png` + `compare` | 也可直接命令行跑，`--json` 喂 `--visual` |
| `replica-design/contrast.py` | `contrast.py tokens.json` | S5 直接用（`tokens.json` 结构照上游） | 0 失败是 G5 判据 |
| `replica-brand/sweep.py` | `sweep.py . --avoid "名称"` | C 档 / B 档使用；A 档可选自检 | A 档不强制 |
| `replica-launch/listing.py` | `listing.py listing.json` | 仅 C 档 | A 档不需要 |
| `replica-entrepreneur/reviews.py` | `reviews.py reviews.csv` | S10 使用（A 档可只读自己看到的抱怨） | 编造 = 直接作废 |
| `replica-skill/tests/` | `python3 -m unittest discover -s tests -v` | 上游测试**保持原样**，不改造；本地另有 `tools/tests/` | 两套测试互不干扰 |

---

## 5. 一张表看清「三个技能的边界」

| 你手上的问题 | 找谁 |
|---|---|
| 「这套 12 阶段怎么跑、门怎么过、什么时候找产品官」 | `replica-os`（本技能） |
| 「这个菜单到底几个选项、三条件怎么写、16 节怎么填、六面怎么查」 | `replica-blueprint` |
| 「源码/二进制/数据库怎么安全地看进去、坑在哪」 | `replica-local-source`（**仅 A 档**） |
| 「上游某个技能具体怎么做这一步」 | 直接读 `replica-skill/replica-*/SKILL.md` |
| 「某道门判定什么」 | `gates/README.md`（由门禁任务卡产出） |
| 「某个工具怎么用」 | `tools/README.md` |

---

## 6. 版本与升级

- 上游版本：vendored 于 2026-10-03（`replica-skill/README.md` 的 11 个技能）。
- 本地版本：v2.0（2026-10-23）。
- **不改上游文件**。要覆盖某条规则，写在本目录（`COMPAT.md` + 本地技能），下一次升级上游时不会冲突。
- 上游升级后必做：重跑 `replica-skill/tests/`（13 个上游测试），确认 `parity.py` / `imgdiff.py` 的函数签名没变
  ——`tools/parity_score.py` 依赖 `score()` / `WEIGHT` / `read_png()` / `compare()` 这四个名字。
