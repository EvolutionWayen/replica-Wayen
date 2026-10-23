#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 examples/scheduling-clone 的示例蓝图（保证 CSV 引用正确）。"""
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent

LINKAGE_COLS = ["link_id", "source_id", "event", "affected_screen", "affected_control",
                "data", "refresh_timing", "state_handling", "test_ref", "status"]

L = [
 # ---------- 选时段 ----------
 ("LK-001","F-SLOT-PICK","SlotSelected{date,startAt}","S-03-预约页",
  "时段网格中该按钮变为选中态（描边+背景），其余全部取消选中","selectedSlot",
  "点击即生效（乐观）","保留焦点在被选按钮；网格不重排","T-103","wired"),
 ("LK-002","F-SLOT-PICK","SlotSelected{date,startAt}","S-03-预约页",
  "底部「继续」按钮从禁用变为可用，文案变为「下一步：填写信息」","selectedSlot",
  "点击即生效","不清空","T-103","wired"),
 ("LK-003","F-SLOT-PICK","SlotSelected{date,startAt}","S-03-预约页",
  "顶部汇总条显示「7月14日 周二 14:00–14:30（GMT+8）」，时长取自 eventType.duration",
  "selectedSlot + tz","点击即生效","不清空","T-104","wired"),
 # ---------- 时区 ----------
 ("LK-004","F-TZ-CONFIRM","TzChanged{tz}","S-03-预约页",
  "整个时段网格按新时区重新渲染；已选时段若在新时区下已过去则自动取消选中",
  "slotGrid(per tz)","切换后立即重新查询",
  "若当前选中时段失效→取消选中并把焦点移到网格首项","T-107","verified"),
 ("LK-005","F-TZ-CONFIRM","TzChanged{tz}","S-03-预约页",
  "顶部汇总条时区后缀更新（GMT+8 → GMT+9）","selectedSlot + tz","立即","不清空","T-107","verified"),
 ("LK-006","F-TZ-CONFIRM","TzChanged{tz}","S-04-信息表单",
  "表单里「我们记录的时区」隐藏字段更新","tz","进入表单时读取当前值","不清空","-","wired"),
 # ---------- 提交 ----------
 ("LK-007","F-FORM-SUBMIT","BookingCreated{bookingId}","S-05-成功页",
  "跳转到成功页并展示确认号、时间、时区、日历下载按钮","booking",
  "提交成功返回后","不适用（新页面）","T-105","verified"),
 ("LK-008","F-FORM-SUBMIT","BookingCreated{bookingId}","S-01-仪表盘",
  "近期预约列表顶部插入新行，显示「刚刚」","bookings","事件广播（本地同进程事件总线）",
  "保留滚动位置；若用户正停留在列表顶部则直接可见","T-301","wired"),
 ("LK-009","F-FORM-SUBMIT","BookingCreated{bookingId}","S-01-仪表盘",
  "侧栏「本周预约」角标 +1（口径：status=confirmed 且 startAt 在本周）","COUNT(*)",
  "事件广播后重算","不清空","T-301","wired"),
 ("LK-010","F-FORM-SUBMIT","BookingCreated{bookingId}","S-03-预约页",
  "该时段从可选列表移除；若整日已满则不显示该日","availability",
  "提交成功后使该日缓存失效","保留访客已选的其它筛选","T-104","wired"),
 ("LK-011","F-FORM-SUBMIT","BookingCreated{bookingId}","S-07-可用时段",
  "主理人侧该时段标记为已占用","availability",
  "主理人视图下次进入时重查（不做实时推送，明确记录为有意差异）","不清空","-","wired"),
 ("LK-012","F-FORM-SUBMIT","BookingCreated{bookingId}","S-08-日历视图",
  "新预约出现在对应日期与时刻","bookings","进入日历视图时查询","不清空","T-303","wired"),
 ("LK-013","F-FORM-SUBMIT","BookingCreated{bookingId}","（搜索）",
  "主理人搜索访客姓名/邮箱能命中新预约","searchIndex",
  "提交成功后异步重建该条索引（≤2s）","不清空","T-304","wired"),
 ("LK-014","F-FORM-SUBMIT","BookingCreated{bookingId}","（提醒调度）",
  "登记一条预约前 24h 的提醒任务","reminders","与预约同一事务内写入","不清空","T-501","verified"),
 ("LK-015","F-FORM-SUBMIT","BookingCreated{bookingId}","（邮件/通知）",
  "发送预约确认信","outbox","事务提交后投递（outbox 模式，失败重试 3 次）","不清空","T-505","wired"),
 # ---------- 改期 ----------
 ("LK-016","F-RESCHEDULE","BookingRescheduled{bookingId,oldStartAt,newStartAt}","S-03-预约页",
  "旧时段重新变为可选、新时段移除","availability","改期成功后","不清空","T-401","wired"),
 ("LK-017","F-RESCHEDULE","BookingRescheduled{bookingId,oldStartAt,newStartAt}","S-01-仪表盘",
  "列表中该行时间就地更新并按新时间重排位置","bookings","改期成功后",
  "保留该行选中；重排后焦点跟随该行","T-401","wired"),
 ("LK-018","F-RESCHEDULE","BookingRescheduled{bookingId,oldStartAt,newStartAt}","（提醒调度）",
  "取消旧提醒、登记新提醒（必须同一事务，否则会出现「改了但还提醒旧时间」）","reminders",
  "同一事务","不清空","T-402","verified"),
 ("LK-019","F-RESCHEDULE","BookingRescheduled{bookingId,oldStartAt,newStartAt}","（邮件/通知）",
  "向主理人与访客各发一封改期通知","outbox","事务提交后","不清空","T-505","wired"),
 # ---------- 取消 ----------
 ("LK-020","F-CANCEL","BookingCancelled{bookingId}","S-03-预约页",
  "该时段重新变为可选","availability","取消成功后","不清空","T-403","wired"),
 ("LK-021","F-CANCEL","BookingCancelled{bookingId}","S-01-仪表盘",
  "该行从「近期预约」移除，移入「已取消」；角标 -1","bookings","取消成功后",
  "若该行正被选中→焦点移到下一行","T-403","wired"),
 ("LK-022","F-CANCEL","BookingCancelled{bookingId}","S-08-日历视图",
  "该条从日历移除（不保留灰色占位）","bookings","取消成功后","不清空","T-404","wired"),
 ("LK-023","F-CANCEL","BookingCancelled{bookingId}","（提醒调度）",
  "取消该预约的全部待触发提醒","reminders","同一事务","不清空","T-402","verified"),
 # ---------- 可用时段 ----------
 ("LK-024","F-HOST-AVAIL","AvailabilityChanged{date}","S-03-预约页",
  "访客侧该日可选时段整体重算","availability",
  "主理人保存成功后使缓存失效（访客下次加载可见）",
  "保留访客当前已选时段；若已失效则提示并取消选中","T-201","wired"),
 ("LK-025","F-HOST-AVAIL","AvailabilityChanged{date}","S-01-仪表盘",
  "「本周可约时长」统计重算","availability","保存成功后","不清空","-","wired"),
 ("LK-026","F-HOST-AVAIL","AvailabilityChanged{date}","S-07-可用时段",
  "周视图该日格子更新，冲突时段标红","availability","保存成功后",
  "保留当前编辑的格子焦点","T-202","wired"),
 # ---------- 预约类型 ----------
 ("LK-027","F-EVENT-TYPE","EventTypeUpdated{typeId}","S-03-预约页",
  "时长变化 → 该类型所有时段的结束时间与网格切分方式全部重算","eventType",
  "保存成功后使该类型所有时段缓存失效",
  "若访客正在该页：保留已选时段；若因时长变化该时段不存在，取消选中并提示","T-203","wired"),
 ("LK-028","F-EVENT-TYPE","EventTypeUpdated{typeId}","S-03-预约页",
  "缓冲时间变化 → 相邻时段的间隔重算","eventType","同上","同上","T-203","wired"),
 ("LK-029","F-EVENT-TYPE","EventTypeUpdated{typeId}","S-01-仪表盘",
  "「按类型统计」图表与图例更新","eventType","进入仪表盘时查询","不清空","-","wired"),
 ("LK-030","F-EVENT-TYPE","EventTypeDeleted{typeId}","S-03-预约页",
  "该类型预约页返回友好 404（不静默跳到别的类型）","eventType","下次访问","不适用","T-204","wired"),
 # ---------- 计数同源 ----------
 ("LK-031","F-DASH-UPCOMING","BookingCreated|Rescheduled|Cancelled","S-01-仪表盘",
  "三处计数必须同源：列表行数、侧栏角标、标题「共 N 个」","COUNT(*)",
  "事件广播后统一重算（禁止各自硬算）","不清空","T-301;T-305","verified"),
 # ---------- 提醒 ----------
 ("LK-032","F-REMINDER-EMAIL","ReminderDue{bookingId}","（本地通知）",
  "弹出应用内提醒，含访客名、时间、时区、一键改期入口","reminders","定时器判定到期","不清空","T-501","wired"),
 ("LK-033","F-REMINDER-EMAIL","ReminderDue{bookingId}","S-01-仪表盘",
  "该行显示「已提醒」标记","reminders","提醒发出后","不清空","-","wired"),
 ("LK-034","F-REMINDER-EMAIL","ReminderDue{bookingId}","（提醒调度）",
  "一次性提醒发出后置为已触发，不重复","reminders","发出后同一事务","不清空","T-502","verified"),
]

with open(ROOT/"BLUEPRINT/linkage.csv","w",newline="",encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(LINKAGE_COLS)
    for row in L:
        w.writerow(row)

# 校验
rows = list(csv.DictReader(open(ROOT/"BLUEPRINT/linkage.csv",encoding="utf-8")))
assert all(len(r) == len(LINKAGE_COLS) for r in rows), "列数不一致"
assert all(r["status"] in ("pending","wired","verified") for r in rows), \
    [r["link_id"] for r in rows if r["status"] not in ("pending","wired","verified")]
print(f"linkage.csv: {len(rows)} 行，10 列，status 合法")
