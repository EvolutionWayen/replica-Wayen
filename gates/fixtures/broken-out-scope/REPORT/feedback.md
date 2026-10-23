# 痛点与差异化（每条带链接与计数）

样本：App Store 中国区 1 星评论 42 条 + 小红书笔记 18 篇 + 少数派评论 7 条，采集于 2026-10-20。

## 原版被骂最多的五点

1. 全天任务在分享卡片里显示成 00:00，用户以为时间错了 —— 一星评论 9 条提到（https://apps.apple.com/cn/app/id1234567890?see-all=reviews），该帖 128 赞
2. 重复规则选完看不到「下次发生日期」，只能靠猜 —— 小红书笔记 12 条（https://www.xiaohongshu.com/explore/6f2a1c3d），累计 246 赞
3. 退出后最后一次编辑丢失，重开会回滚 —— 少数派评论区 7 条（https://sspai.com/post/887766#comments），46 赞
4. 日历跨月时重复任务只显示一半 —— 一星评论 5 条（https://apps.apple.com/cn/app/id1234567890?see-all=reviews），该帖 31 赞
5. 菜单里「今天/明天」没有快捷键提示，键盘党来回切 —— 小红书笔记 4 条（https://www.xiaohongshu.com/explore/7a1b2c3e），88 赞

## 我们的差异化（对应改进项）
| 痛点 | 我们的做法 | 落点 |
|---|---|---|
| 全天显示成 00:00 | 分享卡片保留「全天」语义 | features.csv 新增行（走 S2 契约） |
| 看不到下次发生 | 重复菜单项右侧直接显示下次发生日期 | 契约 C-F-REPEAT §8 |
| 退出丢编辑 | 关窗冲刷返回 FlushResult，error 时阻止关窗 | R3、契约 §13 |
| 跨月只显示一半 | 日历按可见窗口展开实例 | 契约 C-F-REPEAT §12 |
| 快捷键不可见 | 菜单项右侧常显快捷键 | components.md MenuItem |
