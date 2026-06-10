"""
工作日加班工时规则（当前仅处理指定名单员工）。
"""
from datetime import timedelta

from utils.group2_checker import check_group2_attendance, identify_group2_cards
from utils.night_shift import (
    is_night_morning_out,
    is_night_evening_in,
    pair_night_shift_starting,
    try_four_punch_night_overtime,
    check_four_punch_night_anomaly,
)
from utils.agency_attendance import collect_agency_check_dates
from utils.office_overtime_config import DEFAULT_OFFICE_OVERTIME_EMPLOYEES

TARGET_WORKDAY_OVERTIME_EMPLOYEES = set(DEFAULT_OFFICE_OVERTIME_EMPLOYEES)

# 由 refresh_workday_six_punch_employees_from_df 根据打卡表动态填充
TARGET_WORKDAY_SIX_PUNCH_EMPLOYEES = set()


def set_workday_overtime_employees(employees):
    """设置办公室工作日加班名单。"""
    global TARGET_WORKDAY_OVERTIME_EMPLOYEES
    TARGET_WORKDAY_OVERTIME_EMPLOYEES = set(employees)


def set_workday_six_punch_employees(employees):
    """设置六次卡工作日加班名单（通常为四次基本卡部门员工）。"""
    global TARGET_WORKDAY_SIX_PUNCH_EMPLOYEES
    TARGET_WORKDAY_SIX_PUNCH_EMPLOYEES = set(employees)


def refresh_workday_six_punch_employees_from_df(punch_df):
    """从打卡表按 FOUR_PUNCH_DEPARTMENTS 刷新六次卡名单。"""
    from utils.punch_config import get_four_punch_employee_names

    names = get_four_punch_employee_names(punch_df)
    set_workday_six_punch_employees(names)
    return names


BASIC_FOUR_CARDS = ("上午上班卡", "上午下班卡", "下午上班卡", "下午下班卡")
REQUIRED_SIX_CARDS = BASIC_FOUR_CARDS + ("加班上班卡", "加班下班卡")

DAY_SHIFT_START_MINUTES = 8 * 60 + 30
ROUND_NEAR_HALF_HOUR_MINUTES = 3
REST_DAY_FOUR_BREAK_HOURS = 1.0
REST_DAY_SIX_BREAK_HOURS = 1.5


def _has_complete_basic_four_cards(identified):
    return all(identified.get(card) is not None for card in BASIC_FOUR_CARDS)


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


def _has_complete_six_cards(identified):
    return all(identified.get(card) is not None for card in REQUIRED_SIX_CARDS)


def _round_rest_day_start_minutes(t):
    """周末/节假日首卡：8:30 前按 8:30；之后向上取整到半点（<=3 分钟贴上一半点）。"""
    mins = _time_to_minutes(t)
    if mins < DAY_SHIFT_START_MINUTES:
        return DAY_SHIFT_START_MINUTES
    lower = (mins // 30) * 30
    if mins - lower <= ROUND_NEAR_HALF_HOUR_MINUTES:
        return lower
    if mins % 30 == 0:
        return mins
    return lower + 30


def _calc_rest_day_hours(start_mins, end_mins, break_hours):
    hours = (end_mins - start_mins) / 60.0 - break_hours
    if hours <= 0:
        return 0.0
    return round(hours, 2)


def calc_four_punch_department_rest_overtime(date, day_times, punches_by_date=None):
    """
    四次基本卡部门员工在周末/节假日的加班：
    - 跨日 2 次夜班：整段工时进休息日
    - 4 次卡且基本卡齐全：末卡(向下取整) - 首卡(8:30下限+取整) - 1h
    - 6 次卡且六卡齐全：加班下班卡(向下取整) - 首卡 - 1.5h
    - 2 次卡同日：末卡 - 首卡，不扣休息
    """
    count = len(day_times)
    if count == 0:
        return {"status": "正常", "hours": 0, "reason": "无打卡"}

    if punches_by_date is not None:
        night = try_four_punch_night_overtime(punches_by_date, date, is_workday=False)
        if night is not None:
            if night["status"] == "正常":
                return {
                    "status": "正常",
                    "hours": night["cell_hours"] or 0,
                    "reason": "",
                }
            return {"status": "异常", "hours": None, "reason": night.get("reason", "跨日夜班异常")}
        if count == 1 and is_night_morning_out(day_times[0]):
            return {"status": "正常", "hours": 0, "reason": "夜班次晨下班，工时已归上班日"}

    sorted_times = sorted(day_times)
    start_mins = _round_rest_day_start_minutes(sorted_times[0])

    if count == 2:
        end_mins = _round_overtime_end_backward(sorted_times[1])
        return {
            "status": "正常",
            "hours": _calc_rest_day_hours(start_mins, end_mins, 0),
            "reason": "",
        }

    if count == 4:
        identified = identify_group2_cards(date, sorted_times)
        if not _has_complete_basic_four_cards(identified):
            return {
                "status": "异常",
                "hours": None,
                "reason": "四次打卡但基本卡不齐",
            }
        end_mins = _round_overtime_end_backward(sorted_times[-1])
        return {
            "status": "正常",
            "hours": _calc_rest_day_hours(start_mins, end_mins, REST_DAY_FOUR_BREAK_HOURS),
            "reason": "",
        }

    if count == 6:
        identified = identify_group2_cards(date, sorted_times)
        if not _has_complete_six_cards(identified):
            return {"status": "异常", "hours": None, "reason": "六次打卡但卡位不齐"}
        ot_out = identified["加班下班卡"]
        ot_time = ot_out.time() if hasattr(ot_out, "time") else ot_out
        end_mins = _round_overtime_end_backward(ot_time)
        return {
            "status": "正常",
            "hours": _calc_rest_day_hours(start_mins, end_mins, REST_DAY_SIX_BREAK_HOURS),
            "reason": "",
        }

    return {"status": "异常", "hours": None, "reason": f"打卡次数为{count}次，无法计算假期加班"}


def calc_workday_overtime(name, date, emp_id, day_times, punches_by_date=None):
    """
    工作日加班计算（当前规则）：
    - 六次卡名单员工（四次基本卡部门）：
      - 2次打卡且末卡>18:00：末卡向下取整后，若早于19:30则减17:30，否则减18:00
      - 4次打卡且四张基本卡齐全：无加班，工时=0
      - 4次打卡但基本卡不齐：异常
      - 5/6次等：用 group2_checker 识别加班下班卡；缺失则异常，否则工时=加班下班卡(向下取整)-18:00
    - 2次打卡：仅按末卡判断（首卡忽略）
      - 末卡向后取整后<18:00：无加班
      - 末卡向后取整后>=18:00：加班=取整末卡-17:30
        - 若工时>=2：减0.5小时晚餐
    - 4次打卡：取排序后第3次/第4次作为加班上班卡/下班卡，计算工时
    - 3次打卡（>2且<4）：标记异常
    - 大于4次打卡：标记异常
    - 其他次数：暂不处理
    """
    count = len(day_times)

    if name in TARGET_WORKDAY_SIX_PUNCH_EMPLOYEES:
        if count == 0:
            return {"status": "正常", "hours": 0, "reason": "无打卡"}

        sorted_times = sorted(day_times)

        if count == 6:
            identified = identify_group2_cards(date, sorted_times)
            if not _has_complete_six_cards(identified):
                return {"status": "异常", "hours": None, "reason": "六次打卡但卡位不齐"}
            overtime_off = identified["加班下班卡"]
            end_mins = _round_overtime_end_backward(overtime_off.time())
            start_mins = 18 * 60
            if end_mins <= start_mins:
                return {"status": "正常", "hours": 0, "reason": "加班下班卡向下取整后不晚于18:00"}
            return {"status": "正常", "hours": (end_mins - start_mins) / 60.0, "reason": ""}

        if count == 4:
            identified = identify_group2_cards(date, sorted_times)
            if _has_complete_basic_four_cards(identified):
                return {
                    "status": "正常",
                    "hours": 0,
                    "reason": "四次基本卡齐全，无加班",
                }
            return {
                "status": "异常",
                "hours": None,
                "reason": "四次打卡但基本卡不齐",
            }

        if count in (3, 5):
            return {"status": "异常", "hours": None, "reason": f"打卡次数为{count}次，疑似缺卡"}

        if punches_by_date is not None:
            night = try_four_punch_night_overtime(punches_by_date, date, is_workday=True)
            if night is not None:
                if night["status"] == "正常":
                    return {
                        "status": "正常",
                        "hours": night["cell_hours"] or 0,
                        "reason": "",
                    }
                return {"status": "异常", "hours": None, "reason": night.get("reason", "跨日夜班异常")}
            if count == 1 and is_night_morning_out(sorted_times[0]):
                return {"status": "正常", "hours": 0, "reason": "夜班次晨下班，工时已归上班日"}

        if count == 1:
            return {"status": "异常", "hours": None, "reason": "打卡次数为1次，疑似缺卡"}

        if count == 2:
            clock_out = sorted_times[1]
            if _time_to_minutes(clock_out) > 18 * 60:
                end_mins = _round_overtime_end_backward(clock_out)
                start_mins = 17 * 60 + 30 if end_mins < 19 * 60 + 30 else 18 * 60
                if end_mins <= start_mins:
                    return {"status": "正常", "hours": 0, "reason": "末卡向下取整后不晚于基准下班时间"}
                return {"status": "正常", "hours": (end_mins - start_mins) / 60.0, "reason": ""}
            return {"status": "正常", "hours": 0, "reason": "两次打卡且末卡不晚于18:00，无加班"}

        return {"status": "异常", "hours": None, "reason": f"打卡次数为{count}次，无法计算"}

    if count < 2:
        return {"status": "异常", "hours": None, "reason": f"打卡次数为{count}次，少于2次"}
    if count == 2:
        sorted_times = sorted(day_times)
        clock_out = sorted_times[1]
        end_mins = _round_overtime_end_backward(clock_out)
        if end_mins < 18 * 60:
            return {"status": "正常", "hours": 0, "reason": "下班取整后不晚于18:00，无加班"}

        base_start = 17 * 60 + 30
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


AFTERNOON_BASIC_CARDS = ("下午上班卡", "下午下班卡")


def check_four_punch_two_card_day_shift_gap(
    name, punch_date, emp_id, punch_times, punches_by_date
):
    """
    工作日 2 次卡、无晚班卡、跨日夜班未配对：
    能识别上午段但缺下午基本卡 → 报缺卡。
    """
    from utils.holiday_checker import is_workday

    if len(punch_times) != 2 or not is_workday(punch_date):
        return []
    if pair_night_shift_starting(punches_by_date, punch_date):
        return []
    if any(is_night_evening_in(t) for t in punch_times):
        return []

    identified = identify_group2_cards(punch_date, punch_times)
    has_morning = (
        identified.get("上午上班卡") is not None
        or identified.get("上午下班卡") is not None
    )
    if not has_morning:
        return []
    if any(identified.get(card) is not None for card in AFTERNOON_BASIC_CARDS):
        return []

    anomalies = []
    first = punch_times[0]
    for card in AFTERNOON_BASIC_CARDS:
        anomalies.append({
            "姓名": name,
            "日期": punch_date,
            "编号": emp_id,
            "打卡时间": str(first),
            "考勤异常情况": f"无打{card}",
        })
    return anomalies


def check_four_punch_attendance_on_date(name, punch_date, emp_id, punches_by_date):
    """四次基本卡部门：早班 group2 + 跨日夜班缺卡。"""
    day_times = punches_by_date.get(punch_date, [])
    n = len(day_times)

    if n >= 3:
        return check_group2_attendance(name, punch_date, emp_id, day_times)

    night_anomaly = check_four_punch_night_anomaly(punch_date, punches_by_date)
    if night_anomaly:
        return [{
            "姓名": name,
            "日期": punch_date,
            "编号": emp_id,
            "打卡时间": str(night_anomaly["ref_time"]),
            "考勤异常情况": night_anomaly["type"],
        }]

    if n == 2:
        return check_four_punch_two_card_day_shift_gap(
            name, punch_date, emp_id, day_times, punches_by_date
        )

    return []


def check_four_punch_employee(name, emp_id, punches_by_date, month_start, month_end):
    anomalies = []
    for punch_date in collect_agency_check_dates(
        punches_by_date, month_start, month_end
    ):
        anomalies.extend(
            check_four_punch_attendance_on_date(
                name, punch_date, emp_id, punches_by_date
            )
        )
    return anomalies
