# 组件规格（每个组件必须六态齐全）

## Button

| 状态 | 视觉 | 触发条件 |
|---|---|---|
| default | accent 填充，文字 on-accent，圆角 10 | 静止 |
| hover | accent 提亮 6%，阴影 card | 指针悬停 |
| focus | 外环 2px accent，偏移 2px | 键盘 Tab 聚焦 |
| disabled | surface 填充，文字 text-muted，指针 not-allowed | 不可写或保存中 |
| loading | 内嵌 16px 转圈，文字变「保存中…」，宽度不变 | 提交中 |
| error | 边框 danger 1px，图标 danger | 提交失败 |

## MenuItem

| 状态 | 视觉 | 触发条件 |
|---|---|---|
| default | 文字 text，行高 32，左右内边距 12 | 静止 |
| hover | 背景 surface | 指针悬停 |
| focus | 背景 surface + 左侧 2px accent 指示条 | 键盘上下移动 |
| disabled | 文字 text-muted，无悬停背景 | 条件不满足 |
| loading | 右侧 12px 转圈 | 该节点的异步动作进行中 |
| error | 右侧 danger 感叹号，tooltip 给原因 | 该节点动作失败 |

## 替换表（原版素材 → 开源替代）

| 原素材 | 替换为 | 来源 | 许可 |
|---|---|---|---|
| 原版图标集（不可再分发） | Lucide 线性图标集 | https://lucide.dev | ISC |
| 原版品牌字体 | Inter + 系统中文栈 PingFang SC | https://fonts.google.com/specimen/Inter | OFL-1.1 |
| 原版品牌主色 | 中性蓝 #2f5bea（自选） | 本项目 tokens.json | 自有 |
