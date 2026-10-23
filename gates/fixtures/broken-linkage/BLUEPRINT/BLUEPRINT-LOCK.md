# 蓝图冻结记录

> 由 `python3 gates/fixtures/_make.py lock <项目>` 实算生成。改动蓝图必须重跑本命令并把蓝图版本 +1（00-体系总纲.md §8）。

| 项 | 值 |
|---|---|
| 蓝图版本 | v1.1 |
| 冻结时间 | 2026-10-23T10:40+08:00 |
| 确认人 | Wayen |
| 确认方式 | 逐条审阅 features must 行 + 2 份契约 16 节 + menus 三条件 |
| 门禁结果 | G1 通过；G2 通过 |

## 文件哈希（SHA-256）

| 文件 | SHA-256 |
|---|---|
| BLUEPRINT/recon.md | 7bcada3063f0e2238975d8eeb8cf37098a97620f57a1009e0a7f1ae28b6bb238 |
| BLUEPRINT/features.csv | 4c8a4fd44f6cf36f40be0d1f8c768ab34a5e1fbc6c69718dab229667633cdda8 |
| BLUEPRINT/screens.csv | 1047e0b9f906d5ee7cc549c6b76974b87f025d3a90f39b10cb7244813363e37d |
| BLUEPRINT/menus.csv | da1da4e03ab7f754df9a6bb0b722fd65a5f4f4199b4a316f6b79e457f4f70e52 |
| BLUEPRINT/flows.md | 74bfac8202915f7d26dfc6c2cfcf79c674cf9b02b9730e18a36469f3cf2b8017 |
| BLUEPRINT/linkage.csv | d619501be9a368a680adf1013f3179597e1d0bf4b7b90218cb0360ecbfb84d7e |
| BLUEPRINT/state-machines.md | 0ff3d89dc3fcceb132b3b844f660dab8c6a4c11199fc6e580919bc28b6b49ea9 |
| BLUEPRINT/data-dictionary.md | 72d253e4d6f65e3532e67b6284ab9707bfadbe00b50df3842f1c22616d56ff24 |
| BLUEPRINT/unknowns.csv | be7a46924cb1ea0e8ed4f7bd739cf1a5355fbda7dcde50b22e4236b0dda00c18 |
| BLUEPRINT/contracts/C-F-DATE-EDIT.md | 7b8b0de34c64f2084690670e1efa6a89ad05708d82e6783fe26e91d0142042da |
| BLUEPRINT/contracts/C-F-REPEAT.md | 0684b750fa841c8e3db8f844324d52f6e179f82e9f1597d13b9f3489d4c768ec |

## 确认要点
- [x] 核心行为理解无误：F-DATE-EDIT、F-REPEAT-SET 逐条过审
- [x] 保留与改进项已记录：DECISIONS.md D-001 到 D-004
- [x] 阻断级未知为 0（U-001 为 non-blocking；U-002 已经产品方批准为 accepted-risk）
