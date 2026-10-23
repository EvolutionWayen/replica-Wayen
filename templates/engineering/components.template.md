# components —— 组件规格（每组件六态）

> 复制为 `SPEC/DESIGN/components.md`。
> **G5 判定方式**：每个组件一个 `## 组件名` 标题块，块内必须有一张含「状态」列的表，且六态文字都出现：default / hover / focus / disabled / loading / error。
> 判定问句（写完自检）：「hover 与 focus 同时成立时显示什么？」答不出来说明没定完。

## 使用约定

- 写界面时**只许引用令牌**（`tokens.json` / `tokens.css`），不许硬编码色值、圆角、间距。
- 缺某个组件 → 先在本文件加规格（含六态），再写代码。**不许在界面里临时手搓样式。**
- 「替换表」与「令牌索引」不是组件，不要用它们充当组件块。

---

## Button · 主按钮

| 状态 | 背景 | 文字 | 边框 | 其他 |
|---|---|---|---|---|
| default | `--accent` | `--on-accent` | 无 | 圆角 `--r-ctl`，内边距 8/16 |
| hover | `--accent` @ 0.92 不透明 | `--on-accent` | 无 | `--motion-state`（120ms ease-out） |
| focus | `--accent` | `--on-accent` | 2px `#0071E3` 外环 | 外环与背景对比 ≥3:1；键盘可见 |
| disabled | `--border` | `--text-muted` | 无 | 不响应点击；ToolTip 说明原因 |
| loading | `--accent` | `--on-accent` | 无 | 转圈替换文字但**宽度不变**（防跳变） |
| error | `--danger` | `--on-accent` | 无 | 可重试；文案说人话 |

行为：`Enter` / `Space` 触发；`Esc` 不触发；hover 与 focus 同时成立时**以外环为准**，背景取 hover 值。

## Checkbox · 列表勾选框

| 状态 | 视觉 | 触发条件 | 其他 |
|---|---|---|---|
| default 默认 | 1px `--border` 方框 16×16，居中在 40×44 热区内 | 未完成 | 点热区内任意位置都切换勾选 |
| hover 悬停 | 边框 `--text-muted` | 指针进入热区 | 不改变行选中态 |
| focus 聚焦 | 2px `--accent` 外环 | Tab 到达 | 与行选中态**视觉可区分** |
| disabled 禁用 | 方框 `--surface`，无边框 | 行处于只读或冲刷阶段 | 不响应点击 |
| loading 加载中 | 方框内显示 12px 转圈 | 提交中 | 尺寸不变 |
| error 错误 | 方框描边 `--danger` | 提交失败 | 旁边给 11px 错误文字 + 重试 |

行为：点勾选框**不得**触发行选中打开详情（两条路径必须解耦）。

## DateField · 日期块

| 状态 | 视觉 | 触发条件 | 其他 |
|---|---|---|---|
| default 默认 | 显示格式化日期（`11月5日 周三`）；无日期显示「设置日期」灰色 | — | 整块可点，点开弹日历 |
| hover 悬停 | 背景 `--surface` | 指针进入 | 不改文本 |
| focus 聚焦 | 2px `--accent` 外环 | Tab 到达 | 此时按 Enter 打开弹层 |
| disabled 禁用 | 文字 `--text-muted`，无 hover | 任务已删除或只读 | 不弹层 |
| loading 加载中 | 文本处显示骨架条 | 首次读取中 | 不显示占位日期（防误点） |
| error 错误 | 文本 `--danger` + 可复制错误码 | 读取/写入失败 | 保留上次成功值，不显示空 |

行为：**禁止数值微调控件**（`CalendarDatePicker` 之类自带的上下箭头必须去掉）；改动后给 5 秒撤销。

## MenuItem · 菜单项

| 状态 | 视觉 | 触发条件 | 其他 |
|---|---|---|---|
| default 默认 | 文字 `--text`，高 28，左内边距 12 | — | 右侧可显示快捷键 |
| hover 悬停 | 背景 `--surface` | 指针进入 | 有子项的右侧显示箭头 |
| focus 聚焦 | 背景 `--surface` + 2px `--accent` 左条 | 键盘上下移动 | 焦点与 hover 视觉一致 |
| disabled 禁用 | 文字 `--text-muted` | 见 `menus.csv` 的 `enabled_cond` | **必须有解释**（ToolTip 或右侧灰字原因） |
| loading 加载中 | 该项显示转圈，其他项可用 | 该项动作提交中 | 不锁整个菜单 |
| error 错误 | 文字 `--danger` | 动作失败 | 菜单不关闭，显示错误行 |

行为：`radio`/`checkbox` 点后关闭菜单；`action` 点后关闭；`submenu` 悬停展开（延迟见契约 §3）。

## Toast · 撤销条

| 状态 | 视觉 | 触发条件 | 其他 |
|---|---|---|---|
| default 默认 | 底部浮层，`--surface`，高 36，圆角 `--r-box` | 一次可撤销的改动后 | **必须浮层，不许挤压布局** |
| hover 悬停 | 背景加深至 `--border` | 指针进入 | 「撤销」按钮 hover 再加下划线 |
| focus 聚焦 | 「撤销」按钮 2px 外环 | Tab 到 | 可直接按 Enter 撤销 |
| disabled 禁用 | 不适用（无禁用态） | — | 计时中始终可点 |
| loading 加载中 | 「撤销」变转圈 | 撤销请求提交中 | 宽度不变 |
| error 错误 | 整条变 `--danger` 底 | 撤销失败 | 文案「撤销失败，改动已保留」 |

行为：5000ms 后自动消失且改动保留；连续改动用同一条（重置计时），不堆叠。

---

## 替换表（不是组件，不参与六态判定）

| 原版资产 | 类型 | 替换方案 | 验证方法 |
|---|---|---|---|
| 系统符号库图标 | 专有 | 自绘矢量 Path，描边 1.4px 圆头，尺寸 12/15/16/17 | 同尺寸描边粗细差 ≤0.2px、端点圆角一致 |
| 专有字体 | 授权 | 开源等效（写字体名 + 许可证 + 下载来源） | 字号档位与行高不破版 |
| 原版图标形状 | 版权 | 重画，只保留功能语义 | 并排看不构成实质相似 |
| 原版文案 | 版权 | 全部重写（功能名可同，句式必须不同） | `sweep.py` 0 命中 |

## 令牌索引（不是组件，不参与六态判定）

| 类别 | 令牌 | 值 |
|---|---|---|
| 色 | `--bg` / `--surface` / `--border` / `--text` / `--text-muted` / `--accent` / `--on-accent` / `--danger` / `--success` / `--warning` | 见 `tokens.json` |
| 字 | `--font-title` 21 / `--font-h2` 13 / `--font-body` 13 / `--font-caption` 11 | 4 档 |
| 间距 | `--space-xs` 4 / `sm` 8 / `md` 12 / `lg` 16 / `xl` 24 | 全为 4 的倍数 |
| 圆角 | `--r-ctl` 6 / `--r-box` 8 / `--r-pop` 14 / `--r-pill` 999 | 3 档 + 胶囊 |
| 阴影 | `--shadow-pop` `0 6 24 0 #22000000` | 全局唯一一档 |
| 动效 | `--motion-state` 120ms ease-out / `pop-in` 180ms / `pop-out` 120ms | 可中断 |
