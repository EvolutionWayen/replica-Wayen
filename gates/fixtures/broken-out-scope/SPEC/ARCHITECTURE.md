# 架构 · 本地日期任务

## 1 组件边界
| 组件 | 负责 | 依赖方向 |
|---|---|---|
| UI（view/） | 渲染屏幕与浮层，只调 ViewModel | → ViewModel |
| ViewModel | 命令分发、草稿与状态机 | → Repository |
| Repository | 事务、SQL、event 广播 | → SQLite 文件 |
| Flush 层 | 关窗冲刷、返回 FlushResult | → Repository |

依赖单向向下；UI 不直接访问数据库；Repository 不 import UI。

## 2 分层
- 表现层：S-01 主列表 / S-02 详情 / S-03 日历 / S-04 设置
- 应用层：命令（Cmd.*）与查询，含 revision 校验
- 领域层：重复规则求值、相对文案计算
- 基础设施层：SQLite 单文件、WAL、真文件路径

## 3 数据流
写入路径：UI → Cmd → ViewModel 状态机（SUBMITTING）→ Repository 事务 → 提交成功 → 广播事件 → 六面刷新 → FlushResult。
读取路径：UI → 查询 → Repository（同连接）→ 派生值计算 → 渲染。
事务边界：单命令单事务；事件在提交成功后才广播，保证「界面看到的一定已落库」。
