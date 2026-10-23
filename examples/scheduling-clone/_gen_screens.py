#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 examples/scheduling-clone 的 screens.csv。多值字段用「；」分隔。"""
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent

COLS = ["screen_id","name","entry","exits","purpose","key_components",
        "state_filled","state_empty","state_loading","state_error","state_permission",
        "focus_restore","flows","notes"]

# (screen_id, name, entry, exits, purpose, key_components,
#  filled, empty, loading, error, permission, focus_restore, flows, notes)
S = [
 ("S-01","仪表盘",
  "登录后默认页；侧栏「预约」","点「查看预约页」跳 S-03；退出登录",
  "看近期预约与本周统计",
  "近期预约列表；侧栏导航；统计卡；列表行",
  "yes","yes","yes","yes","yes",
  "切回时恢复上次滚动位置与选中行","FL-03",
  "三处计数必须同源（LK-031）"),

 ("S-02","登录",
  "未登录时任何主理人页面重定向到此","登录成功跳 S-01",
  "确认主理人身份",
  "邮箱输入框；密码输入框；提交按钮；错误条",
  "yes","yes","yes","yes","-",
  "失败后焦点回到邮箱框","-",
  "A 档可简化为单用户直通（无密码）"),

 ("S-03","预约页",
  "链接直达 /host/event；主理人预览","-",
  "访客查看并选择时段",
  "主理人头像与名称；类型标题+时长；时区行；日期区；时段网格；底部下一步",
  "yes","yes","yes","yes","yes",
  "Esc 关闭时区菜单后焦点回时区行；翻周后焦点留在网格首项","FL-01；FL-02",
  "★ 有完整契约 contracts/C-F-BOOK-PAGE.md"),

 ("S-04","信息表单",
  "从 S-03 点「下一步」","提交成功跳 S-05；返回回 S-03",
  "收集访客信息",
  "姓名；邮箱；自定义问题；时区确认行；提交按钮",
  "yes","yes","yes","yes","-",
  "提交失败保留全部输入并把焦点移到第一个错误字段","FL-01；FL-02",
  "含重复提交幂等（T-106）"),

 ("S-05","成功页",
  "从 S-04 提交成功","-",
  "确认预约并提供后续动作",
  "确认号；时间与时长；时区；下载日历；改期；取消",
  "yes","-","yes","yes","-",
  "不适用","FL-01",
  "刷新后仍可见（按 bookingId 重查）"),

 ("S-06","预约类型",
  "侧栏「预约类型」","返回 S-01",
  "创建与编辑预约类型",
  "类型列表；新建按钮；时长选择；缓冲设置；问题编辑器",
  "yes","yes","yes","yes","yes",
  "保存后焦点回到该类型行","FL-06",
  "含可见但禁用的删除按钮（M-EVENT-DELETE）"),

 ("S-07","可用时段",
  "侧栏「可用时段」","返回 S-01",
  "设置每周可约时间",
  "周视图格子；时段编辑器；复制到其它天；时区提示条",
  "yes","yes","yes","yes","yes",
  "编辑后焦点留在该格子","T-201；T-202",
  "含冲突时段标红"),

 ("S-08","日历视图",
  "侧栏「日历」","点条目跳预约详情",
  "按时间看全部预约",
  "周/月切换；事件条；当日详情侧栏",
  "yes","yes","yes","yes","yes",
  "切换周时保留选中事件","FL-03",
  "取消的预约完全不显示（不保留灰占位）"),

 ("S-09","改期页",
  "从 S-05 或邮件链接进入","-",
  "访客改期或取消",
  "与原时段一致的网格；确认新时段；取消原因选择",
  "yes","yes","yes","yes","-",
  "冲突后焦点回网格首项","FL-04；FL-05",
  "取消需二次确认"),

 ("S-10","设置",
  "-","返回 S-01",
  "账户与偏好",
  "通知开关；时区；语言；品牌色；深色模式",
  "yes","yes","yes","yes","yes",
  "不适用","-",
  "A 档可裁剪到最小"),
]

with open(ROOT/"BLUEPRINT/screens.csv","w",newline="",encoding="utf-8") as f:
    w = csv.writer(f); w.writerow(COLS)
    for r in S: w.writerow(r)

rows = list(csv.DictReader(open(ROOT/"BLUEPRINT/screens.csv",encoding="utf-8")))
assert all(len(r) == len(COLS) and None not in r for r in rows), "列数不一致"
print(f"screens.csv: {len(rows)} 行，{len(COLS)} 列，ID 唯一={len({r['screen_id'] for r in rows})==len(rows)}")
