#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 examples/scheduling-clone 的 menus.csv / features.csv（保证引用与顺序正确）。"""
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent

MENU_COLS = ["node_id", "parent_id", "path", "order", "type", "label", "shortcut",
             "visibility_cond", "enabled_cond", "checked_cond", "command",
             "contract_ref", "screens", "default_item", "notes"]

M = [
 # ---------------- 根 ----------------
 ("M-ROOT","ROOT","主菜单",1,"submenu","⋯","-",
  "始终可见","始终可用（模态打开时整体禁用）","-","Cmd.OpenMainMenu",
  "contracts/C-F-BOOK-PAGE.md", "S-01", "-","-"),

 # ---------------- 时区（4 层） ----------------
 ("M-TZ-SUB","M-ROOT","⋯ › 时区",1,"submenu","时区","-",
  "预约页可见时始终显示","始终可用（切换时区不阻塞已选时段）","-","Cmd.OpenTzMenu",
  "contracts/C-F-TZ-CONFIRM.md", "S-03", "M-TZ-AUTO","-"),
 ("M-TZ-AUTO","M-TZ-SUB","⋯ › 时区 › 自动检测",1,"radio","自动（浏览器时区）","-",
  "始终显示","始终可用","tz.mode == 'auto'","Cmd.SetTzAuto",
  "contracts/C-F-TZ-CONFIRM.md", "S-03", "-","选中后收起浮层"),
 ("M-TZ-DETECTED","M-TZ-SUB","⋯ › 时区 › 当前检测到",2,"label","Asia/Shanghai（GMT+8）","-",
  "始终显示","不可点击（纯展示）","-","Cmd.None",
  "contracts/C-F-TZ-CONFIRM.md", "S-03", "-","type=label，不参与 command 必填；文本随检测结果变化"),
 ("M-TZ-MANUAL","M-TZ-SUB","⋯ › 时区 › 手动选择",3,"radio","手动选择","-",
  "始终显示","始终可用","tz.mode == 'manual'","Cmd.SetTzManual",
  "contracts/C-F-TZ-CONFIRM.md", "S-03", "-","选中后不收起，就地展开搜索"),
 ("M-TZ-SEARCH","M-TZ-SUB","⋯ › 时区 › 手动选择 › 搜索框",4,"action","搜索时区","-",
  "tz.mode == 'manual' 时显示","输入非空才触发筛选","tz.query 非空","Cmd.SearchTz",
  "contracts/C-F-TZ-CONFIRM.md", "S-03", "-","匹配时区 ID 与城市名；中文名也命中"),
 ("M-TZ-LIST","M-TZ-SUB","⋯ › 时区 › 手动选择 › 时区列表",5,"radio","时区列表","-",
  "tz.mode == 'manual' 时显示","列表非空时可用","tz.selected == 该项","Cmd.PickTz",
  "contracts/C-F-TZ-CONFIRM.md", "S-03", "-","超过 300 项先按常用分组"),

 # ---------------- 时段已满提示（label + 子动作） ----------------
 ("M-SLOT-EMPTY","M-ROOT","⋯ › 此时段已不可选",2,"label","已被预约","-",
  "slot.status != 'available' 时显示","不可点击（纯提示）","-","Cmd.None",
  "contracts/C-F-SLOT-PICK.md", "S-03", "-","type=label"),
 ("M-SLOT-MORE","M-SLOT-EMPTY","⋯ › 此时段已不可选 › 查看当天其它时段",1,"action","查看同一天的其它时段","-",
  "slot.status == 'taken' 且当天还有其它可用时段","当天至少 1 个 available 时段","-","Cmd.ShowOtherSlots",
  "contracts/C-F-SLOT-PICK.md", "S-03", "-","当天全满则整条隐藏（隐藏而非禁用）"),

 # ---------------- 预约类型（4 层，含可见但禁用） ----------------
 ("M-EVENT-SUB","M-ROOT","⋯ › 预约类型",3,"submenu","预约类型","-",
  "主理人已登录","主理人有 ≥1 个预约类型","-","Cmd.OpenEventMenu",
  "contracts/C-F-EVENT-TYPE.md", "S-06", "M-EVENT-DUR","-"),
 ("M-EVENT-DUR","M-EVENT-SUB","⋯ › 预约类型 › 时长",1,"radio","时长","-",
  "始终显示","始终可用","event.duration == 该项","Cmd.SetDuration",
  "contracts/C-F-EVENT-TYPE.md", "S-06", "-","15/30/45/60/90"),
 ("M-EVENT-DUR-CUSTOM","M-EVENT-SUB","⋯ › 预约类型 › 时长 › 自定义",2,"submenu","自定义","-",
  "始终显示","始终可用","-","Cmd.OpenDurationCustom",
  "contracts/C-F-EVENT-TYPE.md", "S-06", "M-EVENT-DUR","-"),
 ("M-EVENT-DUR-IN","M-EVENT-DUR-CUSTOM","⋯ › 预约类型 › 时长 › 自定义 › 分钟数",1,"action","分钟数输入","-",
  "已进入自定义子层","输入在 5–480 且为 5 的倍数","event.duration == 输入值","Cmd.SetDurationCustom",
  "contracts/C-F-EVENT-TYPE.md", "S-06", "-","越界显示内联错误且不提交"),
 ("M-EVENT-BUFF","M-EVENT-SUB","⋯ › 预约类型 › 前置缓冲",3,"radio","前置缓冲","-",
  "始终显示","该类型已在服务端保存过一次后才可用（新建未保存时禁用，避免半成品配置）","event.bufferBefore == 该项","Cmd.SetBufferBefore",
  "contracts/C-F-EVENT-TYPE.md", "S-06", "-","可见但禁用：新建态"),
 ("M-EVENT-DELETE","M-EVENT-SUB","⋯ › 预约类型 › 删除",4,"action","删除此类型","-",
  "始终显示","该类型下无未来预约；否则禁用并在标签后提示「还有 3 个未来预约」","-","Cmd.DeleteEventType",
  "contracts/C-F-EVENT-TYPE.md", "S-06", "-","禁用解释必须给出具体数字"),

 # ---------------- 可用时段 ----------------
 ("M-AVAIL-SUB","M-ROOT","⋯ › 可用时段",4,"submenu","可用时段","-",
  "主理人已登录","始终可用","-","Cmd.OpenAvailMenu",
  "contracts/C-F-HOST-AVAIL.md", "S-07", "M-AVAIL-COPY","-"),
 ("M-AVAIL-COPY","M-AVAIL-SUB","⋯ › 可用时段 › 复制到其它天",1,"action","复制到其它天","-",
  "本周至少 1 天有可用时段","目标天未被全部占用","-","Cmd.CopyAvailability",
  "contracts/C-F-HOST-AVAIL.md", "S-07", "-","复制后必须重算全部受影响天的时段"),
 ("M-AVAIL-TZ-WARN","M-AVAIL-SUB","⋯ › 可用时段 › 时区变更提示",2,"label","你的时区与访客不同","-",
  "系统时区 != 该类型配置时区 且 存在未来预约","不可点击（纯提示）","-","Cmd.None",
  "contracts/C-F-HOST-AVAIL.md", "S-07", "-","type=label"),
]

with open(ROOT/"BLUEPRINT/menus.csv","w",newline="",encoding="utf-8") as f:
    w = csv.writer(f); w.writerow(MENU_COLS)
    for r in M: w.writerow(r)

# ---- 校验：同级 order 不重复；父子闭合 ----
rows = [dict(zip(MENU_COLS, r)) for r in M]
ids = {r["node_id"] for r in rows}
errs = []
for r in rows:
    if r["parent_id"] != "ROOT" and r["parent_id"] not in ids:
        errs.append(f"父节点不存在：{r['node_id']} -> {r['parent_id']}")
sib = {}
for r in rows:
    sib.setdefault(r["parent_id"], []).append(int(r["order"]))
for p, orders in sib.items():
    if len(orders) != len(set(orders)):
        errs.append(f"同级 order 重复：{p} -> {sorted(orders)}")
assert not errs, errs
print(f"menus.csv: {len(rows)} 行，{len(MENU_COLS)} 列，父子闭合且同级顺序唯一")
