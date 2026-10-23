# 脚本

三个脚本，都是"跑一次就懂"的。没有依赖，不需要安装。

| 脚本 | 作用 | 什么时候用 |
|---|---|---|
| `new-project.sh` | 生成一个新项目的完整骨架，并立刻跑一次 G0 | 开工第一天 |
| `run-gates.sh` | 在任意项目目录里一键跑门 | 每个阶段结束时 |
| `build-html.py` | 把整套体系合成一份自包含 HTML 手册 | 想分享/打印/离线看时 |

---

## `new-project.sh`

```bash
./scripts/new-project.sh <目标目录> --target "<制品名> <版本>" --tier A
```

| 参数 | 必填 | 说明 |
|---|---|---|
| `<目标目录>` | 是 | 不存在会创建；已存在且非空会**拒绝**（不覆盖） |
| `--target` | 是 | 目标制品名 + 版本，例：`"目标应用 8.x"` |
| `--tier` | 否 | `A`（本地自用，默认）/ `B`（半自用）/ `C`（商业） |
| `--name` | 否 | 项目名，默认取目录名 |

**它做什么**：
1. 建 22 个目录（`BLUEPRINT/` `SPEC/` `BUILD/` `TEST/` `REPORT/` `evidence/` `screens/` `clone-screens/` `src/` `tests/` `e2e/` `_archive/` `BLUEPRINT/contracts/` `BLUEPRINT/CHANGES/` 等）
2. 复制 20 份模板成可填文件（`PROJECT.md` `DECISIONS.md` `REDLINES.md` `AGENTS.md` `STATE.md` `BLUEPRINT/*` `SPEC/*` `TEST/*` `REPORT/*`）
3. 生成 `.replica/gate.manifest.yml`（写入项目名、档位、制品名、当前 commit）
4. 建空壳文件（`TRACEABILITY.csv` `schema.sql` `bugs.md` `build-log.md`）
5. 写 `.gitignore`（忽略 `_archive/` `*.db` 但保留 `evidence/**/*.db`）
6. 写 `START-HERE.md`
7. **立刻跑一次 G0**——预期失败，因为模板还没填。这是对的：它告诉你还差什么。

**退出码**：`0` 骨架生成成功（G0 结果另算）；`1` 参数错误或目录冲突。

---

## `run-gates.sh`

```bash
./scripts/run-gates.sh                    # 在项目目录里跑全部门
./scripts/run-gates.sh G6                 # 只跑 G6
./scripts/run-gates.sh G6 --json          # 机读
./scripts/run-gates.sh --project ~/p/x    # 指定项目
```

**它会自动往上找** `.replica/gate.manifest.yml` 定位项目根，所以可以在项目里任意子目录跑。

**退出码**（与门禁引擎一致）：

| 码 | 含义 | 你要做什么 |
|---|---|---|
| `0` | 全 PASS（含已批准的 N/A） | 可以进下一阶段 |
| `1` | 有 FAIL | 修，不许绕过 |
| `2` | 只有 BLOCKED | 解决环境/依赖，**BLOCKED 不是通过** |
| 其它 | 引擎异常 | 看报错 |

---

## `build-html.py`

```bash
python3 scripts/build-html.py                 # → 体系总览.html
python3 scripts/build-html.py --out /tmp/x.html
python3 scripts/build-html.py --only stages,case-todo    # 只渲染匹配章节
python3 scripts/build-html.py --list          # 只列章节
```

**输出特性**：
- **零外部依赖**：无 CDN、无外链字体、无外部图片，断网可用
- 左侧固定目录（章节 + 二级标题，点击跳转）
- 苹果风排版：中性灰阶 + 单一蓝色强调、充足留白、细边框
- 代码块/表格/任务列表/引用块都有样式
- 顶部进度条 + 回到顶部按钮
- 打印样式（`@media print`）：隐藏侧栏，避免分页切断代码块和表格
- 窄屏降级：<980px 隐藏侧栏，正文单列

**依赖**：`markdown`（`pip3 install markdown`）。没有它会明确报错，不会静默产出半成品。

**章节顺序**在脚本顶部的 `CHAPTERS` 列表里定义。目录项（以 `/` 结尾）会自动展开其中所有 `.md` 并按文件名排序。

---

## 典型组合

**开工第一天**
```bash
./scripts/new-project.sh ~/projects/my-clone --target "X 1.2.3" --tier A
# 填 PROJECT.md
./scripts/run-gates.sh G0 --project ~/projects/my-clone
```

**日常推进**
```bash
./scripts/run-gates.sh G2 --project ~/projects/my-clone   # 蓝图补齐后
python3 tools/blueprint_lint.py --project ~/projects/my-clone   # 细节自检
./scripts/run-gates.sh G3 --project ~/projects/my-clone   # 冻结前
```

**发布前**
```bash
./scripts/run-gates.sh all --project ~/projects/my-clone
python3 scripts/build-html.py   # 顺手更新手册
```

---

## 为什么只有三个脚本

多一个脚本就多一处要维护、多一处会和门禁不一致。能用一条 `python3 gates/run.py` 解决的事情，不再包一层。

`run-gates.sh` 存在的唯一理由是**自动定位项目根**；`new-project.sh` 存在的唯一理由是**把"新项目要建什么"固化成代码而不是清单**。
