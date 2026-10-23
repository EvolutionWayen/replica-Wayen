# 取证路径摘要（A 档实战记录，可照做一遍）

> **来源**：`case-todo/`（这是本体系的实证来源，不是规范）。
> 本文只是把"实际怎么走过来的"压缩成可照做的顺序，**含具体数字的条目都带复算命令或出处文件**。
> 数字如果不带出处，一律当"待复核"处理。
>
> 基线：本轮工作记录于 2026-10-21 ～ 10-23；仓库基线 commit `77503da`（见 `04-团队编排` §9 的口径纪律）。

---

## 0. 先看这一段：这个案例最容易误导人的三件事

| 误解 | 事实 |
|---|---|
| "目标应用是 Electron 应用，可以直接读 `server.mjs`" | **不是。** macOS 是原生 Swift/ObjC（47MB Mach-O + 39 framework，全 app 仅 2 个 JS 文件）；Windows 是 Inno Setup 封装的 .NET/WPF。此前那个 `目标应用-逆向全案/`（1.4GB，来自 `第三方本地客户端 1.4.0` + Chrome 扩展）与这两个官方安装包**无关**，证据不可混用 |
| "反编译出 69 万行 C#，等于拿到源码" | **不等于。** 里面 **1,163 个方法（1.9%）是空壳**（签名在、方法体被清零），能编译能跑但读任何属性都是默认值。这比报错更危险，因为静默（R8/R9 的来源） |
| "名字最像总闸门的那个类，功能一定走它" | **不能推出。** 该类 `__objc_selrefs` 实测调用点 **0**、`__objc_classrefs` 里没有它、全二进制仅 2 个指针指向类名字符串。它是一个死代码类 |

---

## 1. 锁定制品（30 分钟）

```bash
# macOS：找实际运行的那个包
shasum -a 256 "/Applications/<TargetApp>.app/Contents/MacOS/目标应用"
codesign -dv --verbose=4 "/Applications/<TargetApp>.app" 2>&1 | head -20

# Windows
shasum -a 256 "<target-app>_win_setup_x64.exe"
```

**本次实测身份**（`docs/00-总报告-逆向结论.md:15-16`）：

| 制品 | SHA-256（前缀…后缀） | 真实技术栈 |
|---|---|---|
| `<target-app>_mac_8.x.dmg` | `5212a592…50749b08` | macOS 原生 Swift + ObjC |
| `<target-app>_win_setup_x64.exe` | `29481787…c694d23` | Inno Setup 6.7.0 → .NET/WPF |

⚠️ **本案例的诚实项**：`binaries/` 目录的 SHA-256 **未做逐文件比对**，所以只能算"有制品副本"，**不能算"制品身份已锁定"**。这正是 G1 强制要求逐文件哈希的原因。

---

## 2. 判形态（先证伪，不靠猜）

```bash
ls "<TargetApp>.app/Contents/Resources/" | grep -E "app.asar|electron"   # → 无命中，排除 Electron
file "<TargetApp>.app/Contents/MacOS/目标应用"                          # → Mach-O universal
otool -l "<TargetApp>.app/Contents/MacOS/目标应用" | grep -c __objc_classlist  # → 命中，原生
```

Windows 侧：PE overlay 起点 `0x127000`，magic `zlb\x1a` → Inno Setup；解压后首个 PE 的 CLR 头 v4.0.30319 → .NET。

**这一步错了后面全白做**：形态决定工具链（asar/ILSpy/Mach-O 解析）。

---

## 3. 数据层优先（最值钱的资产）

### 3.1 找到数据库

```bash
# macOS 实际位置（本次实测，见 evidence/pro-gate-analysis.md:89）
~/Library/Group Containers/<TEAMID>.com.target.task.mac/OSXCoreDataObjC.storedata
```

### 3.2 复制副本（**绝不直接操作原库**）

```bash
mkdir -p /tmp/replica-work
cp "$HOME/Library/Group Containers/<TEAMID>.com.target.task.mac/OSXCoreDataObjC.storedata" \
   /tmp/replica-work/app.db
shasum -a 256 "/原库路径" /tmp/replica-work/app.db      # 两行必须一致

# 只在副本上导出结构
sqlite3 /tmp/replica-work/app.db ".schema" > evidence/schema/coredata.sql
sqlite3 /tmp/replica-work/app.db "SELECT name FROM sqlite_master WHERE type='table';" \
  > evidence/schema/tables.txt

# 记下原库未被动过
shasum -a 256 "/原库路径"                                # 与上面一致
```

### 3.3 两端数据模型（带复算命令）

| 事实 | 值 | 复算命令 |
|---|---|---|
| Windows 具名表数 | **68** | `python3 -c "import json;print(len(json.load(open('evidence/schema/win-sqlite-schema.json'))['tables']))"` |
| Windows 有列定义的模型 | **58** | `len(models)` |
| Windows 字段数 | **814** | 累加各模型列数 |
| Windows **无列定义**的表 | **10**（不是"7 张损坏"） | `set(tables) - set(models)` |
| macOS Core Data 实体 | **56** | `len(json.load(open('evidence/schema/coredata-entities.json')))` |
| macOS 属性 / 关系 | **680 / 51** | 累加 |
| API 端点常量 | **207**（含 AI 11 个） | `grep -c . evidence/api-constants.txt` |
| ObjC 类数 | **1,208** | `len(json.load(open('evidence/objc-classes-methods.json')))` |

⚠️ **一个重要更正**：旧文档多处写"7 张表类型名在元数据中损坏，故记 75 表"。实测是 **10 张表没有列定义**（68 − 58 = 10），且这 10 张**从未被提取**，不是"损坏"。所以"75 表"这个口径**已作废**——它不是另一种数法，是错误推断。

> **教训**：一个数字被抄进三份文档后，就没人再算它了。所以门禁要求**数字必须配复算命令**。

### 3.4 关键表（抄语义，不抄实现）

Core Data 表名带 `Z` 前缀，且用大写列名：

| 表 | 用途 | 关键列（实测） |
|---|---|---|
| `ZTTTASK` | 任务 | `ZTITLE` / `ZDATE` / `ZDATE_TYPE`（三日期模型的判别列） |
| `ZTTREMINDER` | 提醒 | 提醒数据存**二进制 plist**（Windows 端结构完全不同） |

> 账号与商业化相关的表不在采集范围内：它们是别人的商业边界，抄了也用不上，还越界。

**跨端不一致的实证**：Windows 用 `TaskModel`/`DueDate`，macOS 用 `ZTTTASK`/`ZDATE`。所以"照搬表结构"必须**逐端**看，不能假设两端同构。

---

## 4. 代码层：只提取规格，不提取实现

### 4.1 Windows（.NET）

```bash
# 前两轮：直接反编译 → 修元数据 → 逐类型回捞
python3 tools/repair_md_final.py win-payload/<target-app>.exe
export DOTNET_ROOT=$PWD/tools/dotnet10 && export PATH=$DOTNET_ROOT:$PATH
dotnet tools/ilspy11/tools/net10.0/any/ilspycmd.dll win-payload/<target-app>.exe -p -o win-csharp/目标应用
```

**三轮迭代实测**（`docs/00-总报告-逆向结论.md:30-34`）：

| 轮次 | 手段 | 可读文件 | 失败 | 行数 |
|---|---|---|---|---|
| 1 | 直接反编译 | 2,035 | 847 | 267,112 |
| 2 | 修复 2,666 处元数据越界字段 | 2,759 | 130 | 688,421 |
| 3 | ILSpy 9.1 逐类型回捞 + 签名补全 | **2,889** | **0** | **691,158** |

**必须同时做的三件事**（缺一件就会写出静默错的代码）：

1. **识别空壳方法**：实测 1,163 个（1.9%），波及 621 个类型
2. **提取数据模型注释**（字段即需求，最值钱）
3. **提取算法思路，不提取代码**（重复规则、三路合并）

**交叉验证技巧**：用**两个不同版本**的反编译引擎，不要重跑同一个。本次 ILSpy 9.1 救回了 11.1 失败的 70 个文件；但 9.1 的批量模式 `-p` 会崩，只能 `-t` 逐类型。

### 4.2 macOS（原生）

```bash
xcrun swift-demangle -simplified < symbols.txt > evidence/symbols/*.swift.txt   # 166,358 行
otool -oV "<TargetApp>.app/Contents/MacOS/目标应用" > evidence/objc-layout.txt    # Swift 类的权威布局
```

**三条硬坑**（详见 §7）。

---

## 5. 界面与交互取证（决定"像不像"）

**方法：一层层截图 + 逐层记录**。本次的实际结构（`docs/19-界面方案-基于原版实测.md`）：

```
窗口 1100 × 820
├─ 图标栏   62px  （#F5F5F5）
├─ 侧边栏  240px  （#FFFFFF，含智能清单/清单/过滤器）
├─ 主区    498px  （#FFFFFF）
└─ 详情    300px  （#FFFFFF，默认空）
```

**截图命令**（macOS，最可靠）：
```bash
screencapture -x -l $(osascript -e 'tell app "目标应用" to id of window 1') shot.png
```

**每层必须记的四件事**（这就是三条件的来源）：
1. 什么时候**出现**（显示条件）
2. 什么时候**是灰的**（可用条件）
3. 什么时候**打钩**（选中条件）
4. 层级怎么展开/收回、`Esc` 关到哪一层、鼠标跨层会不会误关

**一个具体实例**（`case-todo/失败模式库.md` X-02）：
> 日期菜单里 `清除日期` 在"已有日期"时可用；在"只有重复没有具体日期"时**可见但禁用**。

这两句话必须分列写进 `visibility_cond` 与 `enabled_cond`，否则实现时一定做错。
→ 这正是 `tools/menu_walk.py --cards` 要逼你分开填的原因。

---

## 6. 一次「方向对、结论错」的完整教训

这是本案例最值得学的一段，因为它演示了**静态证据不足以下结论**。

### 6.1 最初判断（错在哪）

| 最初判断 | 实测结论 |
|---|---|
| 名字最像「总闸门」的那个类，功能一定走它 | **方向对，但它在本版本是死代码** |
| 它有 47 个可替换方法 | 实际 **50** 个（`otool -oV` 实测，entsize=12，relative 标志 `0x8000000c`） |
| 能改到它的方法，就能改到行为 | 改动**成功**，但**拦不到调用**（内部全走 Swift 静态派发） |

### 6.2 三重反证（静态）

```
selector 的 __objc_selrefs 槽位 = 1（只是方法定义本身），实际调用点 = 0
__objc_classrefs（235 个）里没有这个类
反汇编全文 459 万行中该类的关键选择器出现次数 = 0
```

### 6.3 实机反证（决定性）

在应用副本上装 8 个探针方法跑 10 秒，**调用计数 0**。

### 6.4 真正的收敛点

这次不是「代码里藏了个开关」，而是**功能归属判断从一开始就错了**：该能力由数据层的账号档位决定，不在代码分支里。

> **通用教训**：**命名像 ≠ 功能走这里**。任何"这个类/方法就是总闸门"的判断，必须配调用点证明才能进契约。
> 这就是 `unknowns.csv` 要标"证据等级（A 实测 / C 推断）"的原因——C 级推断不配进契约。

---

## 7. 已知坑清单（每条都有实测出处）

| # | 坑 | 正解 | 出处 |
|---|---|---|---|
| 1 | **arm64 chained fixup 掩码取 51 位** → 地址偏 6 字节 → 选择器读成 `"For:"` `"nt:"` 这种半截字符串 | 掩码 **48 位**：`value & 0x0000FFFFFFFFFFFF`。任何指针解码结果都要**抽样打印字符串**验形，不能只看数值合法 | `evidence/disasm/` 抽样记录 |
| 2 | **Swift 类 `class_ro_t` 布局不通用**：`data` 指针低 3 位带 tag，按标准布局解会整体错位 | 权威来源用 `otool -oV`，不自己猜布局 | `case-todo/README.md` §4 |
| 3 | **静态找到一个类就下结论**：命名最像总闸门，实际调用点为 0 | 先查 `__objc_selrefs` 证明调用点；Swift 内部调用走静态派发，绕过 `objc_msgSend` | `evidence/` 调用点统计 |
| 4 | **动了原程序就变空壳**：签名与权限链绑 Team ID，改动即失去容器访问权 | **只读不改**（R9）。取证只走副本与规格层，不动二进制、不动签名 | `00-体系总纲` §10-09 |
| 5 | **在原库上写会被覆盖**：外部写入被程序下次落盘覆盖，严重时数据损坏 | **只在副本上只读导出**；原库操作前后哈希必须一致（R4） | `00-体系总纲` §10-12 |
| 6 | **AX 自动化权限被拒**（System Events 报 `-10004`） | 只能靠截图 + 运行时探针取证，**承认自动化边界** | `04-团队编排` §4.2 |

---

## 8. 归档（30 分钟，不做就白做）

```
evidence/
├── MANIFEST.csv                 ← python3 tools/evidence_manifest.py --project . 生成
├── schema/                      ← 两端 schema JSON（含复算命令注释）
├── symbols/                     ← Swift 声明 / ObjC 类方法表
├── api-constants.txt            ← 207 个端点常量
├── objc-classes-methods.json    ← 1,208 类 / 15,916 方法
├── pro-gate-analysis.md         ← Pro 门禁完整链路 + 实机验证
└── disasm/                      ← 反汇编关键片段
```

规则：**只加不改**（重跑 manifest 只追加；同名文件哈希变化 → WARN 不覆盖）；敏感内容（账号、token、真实业务数据）不入库。

---

## 9. 这个案例的诚实清单（照抄到你的项目里，别装）

| 未做到 | 影响 | 下一步 |
|---|---|---|
| 蓝图未冻结（v1 根本没有蓝图层） | 行为理解散落在 00–06，没有一功能一契约 | 这就是 v2 加 S2/S3 的原因 |
| 实际使用覆盖不全 | 638 个界面里只复刻了一部分 | 用 S9 的 parity 给真实百分比 |
| 制品哈希未逐文件比对 | 无法证明"验的就是这个包" | v2 的 G1 强制要求 |
| 锚点验证机制缺失 | 本次锚点贴错 3 处，比裸行号更危险 | R15 + `blueprint_lint` |
| 商用合规未做 | A 档不需要 | 升 C 档走 S11 商业分支 |

---

## 10. 怎么用这份摘要

- **你是要开工新项目**：只读 §0（三个误解）、§7（坑清单）、§9（诚实清单）。**别读数据模型细节**——那是这一次的答案，不是你的答案。
- **你正在做同类 macOS 原生 Reverse**：§2–§4 + §7 全部适用，§6 是静态证据不足的样板。
- **你要复现这套流程**：`case-todo/取证路径.md` 是按阶段写的可执行序列，本文是它的压缩索引 + 坑的集中清单。
