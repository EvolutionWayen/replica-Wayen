---
name: replica-local-source
description: >-
  本地自用档的源码 / 二进制 / 数据库分析技能。当用户说「分析这个 App 的源码」「看看它的数据库结构」
  「反编译这个程序」「把它扒下来做我自己的」「本地研究用」「拆一下它的数据模型」时使用。
  在 A 档（本地自用）下允许做上游 replica-recon 明确禁止的「看源码 / 反编译 / 直读数据库」，
  但强制两条硬约束：还原码只当规格书不编入产品（R9）、数据库默认操作副本。
  覆盖 macOS 原生 / Electron / .NET / Android 四类目标的取证手法与已知坑。
---

# 本地自用档 · 源码与数据分析

## 适用范围

**只在 A 档（本地自用）启用。** B 档（给身边人用）与 C 档（对外卖）不适用——那两个档位要遵守上游 `replica-skill` 的 clean-room 立场。

| 档位 | 能否看原版源码 / 反编译 / 直读原版数据库 |
|---|---|
| A 本地自用 | **可以**（仅作规格书与行为研究，见下方两条硬约束） |
| B 半自用 | 不可以 |
| C 商业 | 不可以 |

**判断档位的方法**：读项目 `.replica/gate.manifest.yml` 的 `tier`。没有这个文件 → 先问用户，不要默认。

---

## 两条硬约束（违反即不合格）

### 约束 1：还原码只当规格书，不编入产品（R9）

**为什么**：反编译产物里有大量**空壳方法**——签名在、方法体被清零。本次案例实测 **1,163 个方法（1.9%）是空壳**，波及 621 个类型。它们能编译、能跑，但读任何属性都是 `null`/`false`/`0`。**比报错更危险，因为静默。**

**怎么做**：
- ✅ 从还原码里**读**：字段语义、算法思路、默认值、业务规则、错误码、协议形状
- ✅ 从还原码里**抄**：数据模型（表结构、字段类型、约束）——这是"字段即需求"
- ❌ 不做：把 `.cs` / `.js` / `.swift` 文件拖进 `src/`
- ❌ 不做：把反编译的函数体改个名字就用
- ❌ 不做：把整包 class 复制过来"参考一下"

**自检**：
```bash
# 你的产品源码里不该出现反编译的痕迹
grep -rn "IL_\|__cil\|<Module>\|F::" src/ 2>/dev/null | head
# 也不该出现原版的包名/命名空间
grep -rn "com\.yourcompany\|目标应用\|Dida" src/ --include=* 2>/dev/null | head
```

### 约束 2：数据库默认操作副本

**为什么**：直接改真实库 = 可能毁掉用户的数据。本次案例里两次踩坑：① Core Data 库在 App 运行时会被服务端同步语义重置字段；② WAL 未 checkpoint 就改，写进 WAL 后被 App 覆盖。

**怎么做**：
```bash
# 1) 找库
find ~/Library -name "*.db" -o -name "*.sqlite*" 2>/dev/null | grep -i <app>

# 2) 复制到工作副本（绝不直接操作原库）
mkdir -p /tmp/replica-work
cp "<原库路径>" /tmp/replica-work/app.db

# 3) 校验副本与原库一致（这一步不能省）
shasum -a 256 "<原库路径>" /tmp/replica-work/app.db
# 两行哈希必须相同

# 4) 只在副本上操作
sqlite3 /tmp/replica-work/app.db ".schema" > evidence/schema.sql
sqlite3 /tmp/replica-work/app.db "SELECT name FROM sqlite_master WHERE type='table';" > evidence/tables.txt

# 5) 记录原库未被动过
shasum -a 256 "<原库路径>"   # 与第 3 步一致
```

**绝对禁止**：
```bash
sqlite3 "<原库路径>" "UPDATE ..."     # 永远不
sqlite3 "<原库路径>" "DELETE ..."     # 永远不
sqlite3 "<原库路径>" "PRAGMA ..."     # 永远不（PRAGMA 也可能改文件）
```

**如果确实要在 App 运行时改**（有时必须，因为 App 启动会重置字段）：
- 先 `PRAGMA wal_checkpoint(TRUNCATE)` → 改 → 再 `PRAGMA wal_checkpoint(TRUNCATE)` → **立刻重启 App 验证**
- 改的是副本，不是原库。要动原库必须先征得用户明确同意。

---

## 取证动作序列

### 第 0 步：锁定制品身份

```bash
# macOS
codesign -dv --verbose=4 "/Applications/X.app" 2>&1 | head -20
shasum -a 256 "/Applications/X.app/Contents/MacOS/X"

# Windows
shasum -a 256 "X.exe"
```

产出写进 `PROJECT.md` 的「目标制品」段。**做不到就写「未锁定」，不要假装锁定。**

### 第 1 步：判形态（先证伪，不靠猜）

| 命令 | 判断 |
|---|---|
| `ls "X.app/Contents/Resources/" \| grep -E "app.asar\|electron"` | Electron |
| `ls "X.app/Contents/Resources/" \| grep -E "\.dll$"` | .NET |
| `file "X.app/Contents/MacOS/X"` | 原生 Mach-O |
| `unzip -l X.apk \| grep -E "classes.*dex"` | Android |

**选错工具链，后面全白做。**

### 第 2 步：按形态取证

#### 2a. .NET（Windows 常见）

```bash
ilspycmd -p -o win-csharp-recovered "X.dll"
find win-csharp-recovered -name "*.cs" | wc -l
cat $(find win-csharp-recovered -name "*.cs") | wc -l
```

**必须同时做的三件事**：

1. **识别空壳方法**（这是最重要的检查）
```bash
# 方法体为空或只有 return null/default
grep -rn -A2 "^\s*\(public\|private\|internal\|protected\).*(" win-csharp-recovered --include=*.cs \
  | grep -E "^\S+-\s*\{\s*\}$|return null;|return default;|return 0;" | wc -l
```
实测 目标应用有 1,163 个。**这些方法读任何属性都是默认值。**

2. **提取数据模型注释**（最值钱）
3. **提取算法思路**（比如重复规则的 RRULE 解析、时区换算），**不提取代码**

**判定"提取够了"的标准**：你能不看原代码，把某段业务规则写成一张能生成正确结果的表。

#### 2b. Electron

```bash
npx asar extract app.asar app-unpacked

# 只找三样
grep -rn "router\.\|path:" app-unpacked --include=*.js | head -50
grep -rnoE "https?://[a-z0-9.-]+/[a-z0-9/_-]+" app-unpacked --include=*.js | sort -u > evidence/api-endpoints.txt
# i18n 文案单独抽（因为你必须重写文案）
grep -rn "i18n\|t(\"" app-unpacked --include=*.js | head -30
```

**不要做**：不要在 renderer 注入脚本抓别人的网络请求；不要试图"运行起来再改"。

#### 2c. macOS 原生

```bash
# 类与方法表
class-dump -H "X.app/Contents/MacOS/X" -o evidence/symbols/

# 布局：Swift 类的权威来源
otool -oV "X.app/Contents/MacOS/X" > evidence/objc-layout.txt

# 字符串
strings -a "X.app/Contents/MacOS/X" > evidence/strings.txt
```

**三条硬坑**（目标应用实证）：

| 坑 | 正解 |
|---|---|
| **arm64 chained fixup 指针掩码是 48 位** | `value & 0x0000FFFFFFFFFFFF`。用 51 位会多带 3 个头部位 → 地址偏 6 字节 → 读出空串或半截选择器（症状：选择器变成 `"For:"` `"nt:"`） |
| **Swift 类 `class_ro_t` 布局不通用** | `data` 指针低 3 位带 tag，按标准布局解会整体错位。**权威来源用 `otool -oV`** |
| **命名像 ≠ 功能走这里** | 必须先证明**有调用点**：`__objc_selrefs` 是 `objc_msgSend` 调用点的唯一来源。实测某 50 方法的类调用点为 0，是死代码 |

**补充**：Swift 内部调用走**静态派发**，绕过 `objc_msgSend`——只看 ObjC 派发会得出错误结论。证据等级只有到 A（有调用点 + 实测）才允许进契约。

#### 2d. Android

```bash
apktool d -f -o apk-out X.apk          # 资源 + manifest
jadx -d jadx-out X.apk                 # Java 源码（用 skill 里的 REA 工具更稳）
```

用 REA 的 `inspect_android_package` / `inspect_android_class` / `inspect_android_method` 更省事（不执行 APK）。

### 第 3 步：数据模型提取（最高价值资产）

```bash
sqlite3 /tmp/replica-work/app.db ".schema" > evidence/schema.sql
```

**把 schema 转成可复算的 JSON**，并记录：
- 表数（可复算命令）
- 字段数（可复算命令）
- **哪些表没有列定义**（目标应用实测有 10 张表根本没被提取——不是"损坏"，是"从未提取"）

**这一步的产出就是 `BLUEPRINT/data-dictionary.md` 的输入。**

### 第 4 步：交叉验证（源码推断 ≠ 真实行为）

**关键纪律**：**在源码里找到方法，不等于真实入口调用了它。**

| 证据等级 | 含义 | 怎么得 |
|---|---|---|
| A 实测 | 亲自操作看到的 | 跑原版（用自己的账号） |
| B 文档 | 官方文档明说的 | 读帮助中心 |
| C 推断 | 从 A/B 推出的 | **必须进 `unknowns.csv` + 给可执行补验动作** |

**每条 C 级推断都要能回答**：「我用什么动作能把它变成 A 级？」

### 第 5 步：归档（只加不改）

```
evidence/
├── MANIFEST.csv          # tools/evidence_manifest.py 生成
├── schema/
├── symbols/
└── pages/                # Web 制品的页面快照（含 SHA-256）
```

**Web 制品没有 SHA-256 怎么办**：保存关键页面的 HTML 快照（`evidence/pages/*.html`）并对快照算 SHA-256。这样"证据"仍然可复算、可复现。

---

## 改二进制：最后手段，不是第一手段

**优先走数据层**（改配置文件、数据库、缓存），不要碰二进制。

**不改二进制是红线（R9）**：改动原程序的可执行文件会破坏签名链，而 macOS 的应用组容器授权与签名里的 Team ID 绑定——改完不是"多了能力"，而是"账号态整个消失"。同理，改签名、改授权字段、绕过付费与授权机制，一律不做。

真正的收敛方式是**回到只读取证**：静态符号 + 数据层副本 + 界面实测。任何"必须改一下它才能看明白"的念头，说明取证路径选错了，不是红线该让路。

**`codesign --options` 接受整数值**：`0x12000` = runtime|csops（csops 允许运行时改已签名代码）。但 **csops 会关掉 library validation**，导致加载 vendor 签名的 framework 失败（"different Team IDs"）——需要把 framework 一起重签。

**改完必须验**：
```bash
codesign -v --verbose=2 "X.app"        # 必须通过
codesign -dv --verbose=4 "X.app" 2>&1 | grep -E "TeamIdentifier|flags"
```

---

## 产出的检查点

做完取证，在 `BLUEPRINT/recon.md` 里必须能回答：

- [ ] 制品身份（名称+版本+SHA-256 或页面快照哈希）？
- [ ] 形态判定（依据是什么，不是"看起来像"）？
- [ ] 数据模型可复算（表数/字段数 + 命令）？
- [ ] **哪些行为是 A 级实测、哪些是 C 级推断**？C 级是否都进了 `unknowns.csv`？
- [ ] 空壳/未还原的部分清单（不许装作"全部还原"）？
- [ ] 看不到的区域（权限后/付费墙后/服务端）？
- [ ] 原库没被动过（哈希前后一致）？

**跑门**：`python3 gates/run.py --stage G1 --project .`

---

## 边界（不许越）

| 不做 | 原因 |
|---|---|
| 登录别人账号 | 越权 |
| 绕过付费墙 | 越权 |
| 修改别人的线上服务 | 越权 |
| 把还原码编入产品 | R9 |
| 直接改用户真实库 | 约束 2 |
| 声称"全部功能已覆盖" | 看不到的区域永远存在 |

---

## 参考

- `case-todo/取证路径.md` —— 该产品的完整取证实录（可照着做一遍）
- `case-todo/失败模式库.md` —— 20 条实证失效模式（X-07 库安全、X-08 空壳、X-09 只读红线、X-10 掩码、X-11 调用点、X-12 副本原则）
- `00-体系总纲.md` §9 —— R1–R20 红线
- `templates/blueprint/SCHEMAS.md` —— `data-dictionary.md` / `unknowns.csv` 的格式
