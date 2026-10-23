# 一致性报告（功能分 + 界面分双分制）

功能分：85.7（由 BLUEPRINT/features.csv 实算：weight must=3 / should=2 / could=1，progress yes=1 / partial=0.5 / no=0，剔除 skip 与 original=no）
界面分：88（视觉与操作步数分开记录，**不参与抵消功能分**）

## 算法口径
- 分子 = Σ(weight × progress 值) = 3×1 + 3×1 + 1×0 = 6
- 分母 = Σ(weight) = 3 + 3 + 1 = 7
- 功能分 = 6 / 7 × 100 = 85.7（阈值 80，manifest.thresholds.parity_feature）

## 缺失清单
- F-SYNC-CLOUD：云同步未实现（could 级，本版不做；补做需先过 S2 契约）
- F-REPEAT-SET：自定义分支只支持工作日与按周，未支持「每月第 N 周」（accepted-risk，见 D-003）

## 界面差距（供下轮）
- 浮层圆角原版 12、我方 10
- 菜单行高原版 30、我方 32
