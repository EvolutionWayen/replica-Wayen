#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 examples/scheduling-clone 的 unknowns.csv（避免逗号/引号出错）。"""
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent

COLS = ["unknown_id","area","description","impact","evidence_gap",
        "verification_action","owner","blocking","status"]

U = [
 ("U-001","时段生成",
  "访客时区与主理人时区不同时，跨日界线的时段归属哪一天",
  "F-SLOT-PICK","缺跨时区实测",
  "在主理人 Asia/Shanghai、访客 America/New_York 各选一次日界时段并记录归属日",
  "蓝图工","yes","open"),
 ("U-002","夏令时",
  "美东切换日 02:00–03:00 不存在时，槽位生成是跳过还是补齐",
  "F-SLOT-PICK；F-TZ-CONFIRM","缺 DST 实测",
  "在 2026-03-08 与 2026-11-01 各生成一次整周槽位并核对缺失小时",
  "蓝图工","yes","open"),
 ("U-003","可用时段",
  "可用窗口跨午夜（如 22:00–02:00）时如何切分",
  "F-HOST-AVAIL","缺原版观察",
  "原版设置界面配置一次跨午夜窗口并观察生成结果",
  "蓝图工","no","out-of-scope"),
 ("U-004","缓冲",
  "缓冲时间与相邻预约同时存在时谁优先",
  "F-EVENT-TYPE","缺优先级规则",
  "设 30 分钟缓冲并在相邻时段已有预约，观察是否仍生成",
  "蓝图工","no","open"),
 ("U-005","提醒",
  "预约改期后旧提醒是否一定被取消（跨事务失败场景）",
  "F-REMINDER-EMAIL；F-RESCHEDULE","缺故障注入",
  "注入提醒写入失败，观察旧提醒是否残留",
  "蓝图工","yes","open"),
 ("U-006","时区",
  "访客时区检测失败时的回退顺序（URL 参数／localStorage／浏览器／主理人时区）",
  "F-TZ-CONFIRM","缺规则文档",
  "禁用浏览器 Intl 后打开页面并记录实际时区来源",
  "蓝图工","no","open"),
 ("U-007","重复提交",
  "连续点击提交按钮是否产生两条预约",
  "F-FORM-SUBMIT","缺幂等键设计",
  "连点 5 次提交后查库记录条数",
  "蓝图工","yes","open"),
 ("U-008","通知",
  "访客取消后是否还要发确认邮件给主理人",
  "F-CANCEL","缺原版观察",
  "原版取消一次观察主理人是否收到邮件",
  "蓝图工","no","open"),
 ("U-009","定价",
  "原版按人头计价的真实档位与限制（用于差异化定位，不实现）",
  "F-FLAT-PRICING","缺公开定价页取证",
  "读原版公开定价页并记录档位与人数上限",
  "规划","no","out-of-scope"),
 ("U-010","短信",
  "原版是否真的完全没有短信提醒（决定 F-SMS-REMINDER 是否为真差异化）",
  "F-SMS-REMINDER","缺评价证据",
  "检索原版公开评价中的短信相关抱怨并记录条数与链接",
  "规划","no","open"),
]

with open(ROOT/"BLUEPRINT/unknowns.csv","w",newline="",encoding="utf-8") as f:
    w = csv.writer(f); w.writerow(COLS)
    for r in U: w.writerow(r)

rows = list(csv.DictReader(open(ROOT/"BLUEPRINT/unknowns.csv",encoding="utf-8")))
assert all(len(r)==len(COLS) and None not in r for r in rows)
assert all(r["blocking"] in ("yes","no") for r in rows)
assert all(r["status"] in ("open","resolved","accepted-risk","out-of-scope") for r in rows)
blocking_open = [r["unknown_id"] for r in rows if r["blocking"]=="yes" and r["status"]=="open"]
print(f"unknowns.csv: {len(rows)} 行，{len(COLS)} 列；阻断级仍 open 的 {len(blocking_open)} 条：{blocking_open}")
