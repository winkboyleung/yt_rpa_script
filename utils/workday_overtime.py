"""
工作日加班工时规则（当前仅处理指定名单员工）。
"""
from utils.group2_checker import identify_group2_cards

TARGET_WORKDAY_OVERTIME_EMPLOYEES = {
    "莫淑兰",
    "许丽霞",
    "刘天梅",
    "朱颖",
    "梁海雯",
    "罗鼎成",
    "吴金娜",
    "杨丽娟",
    "梅宇轩",
    "周映文",
    "林芷珊",
    "王李婷",
    "陈燕兰",
}

TARGET_WORKDAY_SIX_PUNCH_EMPLOYEES = {
    "王思杰",
    "陈章明",
    "吴锦乐",
    "梁伟强",
    "苏华",
    "谭文俊",
}


def _time_to_minutes(t):
    return t.hour * 60 + t.minute


def _round_overtime_start_forward(t):
    """
    加班上班卡向前取整到半点。
    例如：17:42 -> 18:00
    人性化规则：18:00~18:05 仍按 18:00 计算。
    """
    mins = _time_to_minutes(t)
    if 18 * 60 <= mins <= 18 * 60 + 5:
        return 18 * 60
    if mins % 30 == 0:
        return mins
    return ((mins // 30) + 1) * 30


def _round_overtime_end_backward(t):
    """
    加班下班卡向后取整到半点。
    例如：20:12 -> 20:00
    """
    mins = _time_to_minutes(t)
    return (mins // 30) * 30


def calc_workday_overtime(name, date, emp_id, day_times):
    """
    工作日加班计算（当前规则）：
    - 六次卡名单员工：
      - 2次打卡且末卡>18:00：末卡向下取整后，若早于19:30则减17:30，否则减18:00
      - 其他次数：用 group2_checker 识别加班下班卡；缺失则异常，否则工时=加班下班卡(向下取整)-18:00
    - 2次打卡：仅按末卡判断（首卡忽略）
      - 末卡<=18:30：无加班，忽略
      - 末卡>18:30：加班=末卡(向后取整)-17:30
        - 若工时<2：按原值
        - 若工时>=2：减0.5小时晚餐
    - 4次打卡：取排序后第3次/第4次作为加班上班卡/下班卡，计算工时
    - 3次打卡（>2且<4）：标记异常
    - 大于4次打卡：标记异常
    - 其他次数：暂不处理
    """
    count = len(day_times)

    if name in TARGET_WORKDAY_SIX_PUNCH_EMPLOYEES:
        if count < 2:
            return {"status": "异常", "hours": None, "reason": f"打卡次数为{count}次，少于2次"}

        sorted_times = sorted(day_times)
        if count == 2:
            clock_out = sorted_times[1]
            if _time_to_minutes(clock_out) > 18 * 60:
                end_mins = _round_overtime_end_backward(clock_out)
                start_mins = 17 * 60 + 30 if end_mins < 19 * 60 + 30 else 18 * 60
                if end_mins <= start_mins:
                    return {"status": "正常", "hours": 0, "reason": "末卡向下取整后不晚于基准下班时间"}
                return {"status": "正常", "hours": (end_mins - start_mins) / 60.0, "reason": ""}
            return {"status": "正常", "hours": 0, "reason": "两次打卡且末卡不晚于18:00，无加班"}

        identified = identify_group2_cards(date, sorted_times)
        overtime_off = identified.get("加班下班卡")
        if overtime_off is None:
            return {"status": "异常", "hours": None, "reason": "缺失加班下班卡"}

        end_mins = _round_overtime_end_backward(overtime_off.time())
        start_mins = 18 * 60
        if end_mins <= start_mins:
            return {"status": "正常", "hours": 0, "reason": "加班下班卡向下取整后不晚于18:00"}
        return {"status": "正常", "hours": (end_mins - start_mins) / 60.0, "reason": ""}

    if count < 2:
        return {"status": "异常", "hours": None, "reason": f"打卡次数为{count}次，少于2次"}
    if count == 2:
        sorted_times = sorted(day_times)
        clock_out = sorted_times[1]

        # 下班卡在18:30内视为无加班
        if _time_to_minutes(clock_out) <= 18 * 60 + 30:
            return {"status": "正常", "hours": 0, "reason": "下班卡不晚于18:30，无加班"}

        end_mins = _round_overtime_end_backward(clock_out)
        base_start = 17 * 60 + 30
        if end_mins <= base_start:
            return {"status": "正常", "hours": 0, "reason": "取整后下班时间不晚于17:30"}

        hours = (end_mins - base_start) / 60.0
        if hours >= 2:
            hours -= 0.5
        return {"status": "正常", "hours": hours, "reason": ""}

    if 2 < count < 4:
        return {"status": "异常", "hours": None, "reason": "打卡次数为3次，疑似缺卡"}
    if count > 4:
        return {"status": "异常", "hours": None, "reason": f"打卡次数为{count}次，超过4次"}
    if count != 4:
        return {"status": "暂不处理", "hours": None, "reason": f"打卡次数为{count}次"}

    sorted_times = sorted(day_times)
    overtime_start = sorted_times[2]
    overtime_end = sorted_times[3]
    start_mins = _round_overtime_start_forward(overtime_start)
    end_mins = _round_overtime_end_backward(overtime_end)

    if end_mins <= start_mins:
        return {"status": "正常", "hours": 0, "reason": "加班下班卡早于或等于加班上班卡"}

    return {"status": "正常", "hours": (end_mins - start_mins) / 60.0, "reason": ""}
