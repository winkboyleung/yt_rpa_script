from datetime import datetime


TARGET_EMPLOYEES = {
    "莫淑兰",
    "许丽霞",
    "刘天梅",
    "朱颖",
    "梁海雯",
    "罗鼎成",
    "吴金娜",
}


def to_minutes(dt_obj):
    return dt_obj.hour * 60 + dt_obj.minute


def round_overtime_start_forward(dt_obj):
    """
    加班上班卡向前取整到半点:
    17:42 -> 18:00
    """
    mins = to_minutes(dt_obj)
    if mins % 30 == 0:
        return mins
    return ((mins // 30) + 1) * 30


def round_overtime_end_backward(dt_obj):
    """
    加班下班卡向后取整到半点:
    20:12 -> 20:00
    """
    mins = to_minutes(dt_obj)
    return (mins // 30) * 30


def calc_workday_overtime_for_4_punches(punch_times):
    """
    仅处理工作日4次打卡的场景:
    第3次视为加班上班卡, 第4次视为加班下班卡
    """
    if len(punch_times) != 4:
        return None

    sorted_times = sorted(punch_times)
    overtime_start = sorted_times[2]
    overtime_end = sorted_times[3]

    start_mins = round_overtime_start_forward(overtime_start)
    end_mins = round_overtime_end_backward(overtime_end)

    if end_mins <= start_mins:
        return 0
    return (end_mins - start_mins) / 60


def evaluate_workday_overtime_status(punch_times):
    """
    根据打卡次数给出结果：
    - 4次：计算加班工时
    - 3次（>2且<4）：标记异常
    - 其他：暂不处理
    """
    count = len(punch_times)
    if 2 < count < 4:
        return {"status": "异常", "reason": "打卡次数为3次，疑似缺卡"}
    if count == 4:
        return {"status": "正常", "hours": calc_workday_overtime_for_4_punches(punch_times)}
    return {"status": "暂不处理", "reason": f"打卡次数为{count}次"}


def format_hhmm(total_minutes):
    return f"{total_minutes // 60:02d}:{total_minutes % 60:02d}"


if __name__ == "__main__":
    demo_employee = "莫淑兰"
    demo_times_str = [
        "2026-4-9 08:27",
        "2026-4-9 17:39",
        # "2026-4-9 17:57",
        "2026-4-9 21:29",
    ]

    if demo_employee not in TARGET_EMPLOYEES:
        print(f"员工 {demo_employee} 不在加班统计名单内")
    else:
        demo_times = [datetime.strptime(x, "%Y-%m-%d %H:%M") for x in demo_times_str]
        sorted_times = sorted(demo_times)
        result = evaluate_workday_overtime_status(demo_times)

        print("=== 工作日加班工时 Demo ===")
        print("原始打卡:")
        for t in sorted_times:
            print(f"- {t.strftime('%Y-%m-%d %H:%M')}")
        print(f"判定结果: {result['status']}")

        if result["status"] == "正常":
            ot_start = sorted_times[2]
            ot_end = sorted_times[3]
            ot_start_rounded = round_overtime_start_forward(ot_start)
            ot_end_rounded = round_overtime_end_backward(ot_end)
            print(f"加班上班卡(第3次): {ot_start.strftime('%H:%M')} -> {format_hhmm(ot_start_rounded)}")
            print(f"加班下班卡(第4次): {ot_end.strftime('%H:%M')} -> {format_hhmm(ot_end_rounded)}")
            print(f"加班工时: {result['hours']} 小时")
        else:
            print(f"说明: {result['reason']}")

