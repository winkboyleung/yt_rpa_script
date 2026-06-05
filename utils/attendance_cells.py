"""单日考勤格、加班格取值（供整月生成与模板增量填写共用）。"""

from utils.holiday_checker import is_holiday_or_weekend, is_workday
from utils.workday_overtime import (
    TARGET_WORKDAY_OVERTIME_EMPLOYEES,
    calc_workday_overtime,
    calc_four_punch_department_rest_overtime,
)
from utils.agency_attendance import calc_agency_hours_for_shift_end_date
from utils.night_shift import (
    collect_missing_night_start_dates,
    should_count_as_attendance_day,
)
from utils.punch_config import uses_two_punch_override, is_auto_workday_present


def _format_overtime_hours(hours):
    text = f"{round(hours, 2):.2f}".rstrip("0")
    if text.endswith("."):
        text = text[:-1]
    return text


def _time_to_minutes(t):
    return t.hour * 60 + t.minute


def _round_clock_in_forward(t):
    mins = _time_to_minutes(t)
    if mins < 8 * 60 + 30:
        return 8 * 60 + 30
    remainder = mins % 30
    if remainder == 0:
        return mins
    if remainder < 5:
        return mins - remainder
    return (mins // 30 + 1) * 30


def _round_clock_out_backward(t):
    mins = _time_to_minutes(t)
    return (mins // 30) * 30


def calc_weekend_overtime_two_punches(clock_in, clock_out):
    start = _round_clock_in_forward(clock_in)
    end = _round_clock_out_backward(clock_out)
    if end <= start:
        return None
    hours = (end - start) / 60.0
    need_lunch = _time_to_minutes(clock_in) < 11 * 60 and (
        hours > 5 or _time_to_minutes(clock_out) > 14 * 60
    )
    if need_lunch:
        hours -= 1
    if _time_to_minutes(clock_out) > 19 * 60 + 30:
        hours -= 0.5
    return hours


def build_employee_anomaly_maps(name, anomaly_df):
    emp_anomalies = {}
    emp_anomaly_details = {}
    if anomaly_df is None or anomaly_df.empty:
        return emp_anomalies, emp_anomaly_details
    emp_anomaly_records = anomaly_df[anomaly_df["姓名"] == name]
    for _, anomaly in emp_anomaly_records.iterrows():
        d = anomaly["日期"]
        if d not in emp_anomalies:
            emp_anomalies[d] = []
            emp_anomaly_details[d] = []
        emp_anomalies[d].append(anomaly["考勤异常情况"])
        emp_anomaly_details[d].append({
            "时间": anomaly.get("打卡时间", ""),
            "异常": anomaly["考勤异常情况"],
        })
    return emp_anomalies, emp_anomaly_details


def merge_missing_night_start_anomalies(
    name, emp_anomalies, emp_anomaly_details, missing_night_start
):
    for missing_date, info in missing_night_start.items():
        if missing_date not in emp_anomalies:
            emp_anomalies[missing_date] = []
            emp_anomaly_details[missing_date] = []
        if "缺卡" not in emp_anomalies[missing_date]:
            emp_anomalies[missing_date].append("缺卡")
            emp_anomaly_details[missing_date].append({
                "时间": str(info["ref_time"]),
                "异常": "缺卡",
            })


def compute_attendance_cell(
    punch_date,
    emp_punch_dates,
    emp_punches_by_date,
    emp_anomalies,
    emp_anomaly_details,
    is_agency,
    is_four_punch,
    name=None,
):
    """
    返回 (cell_value, comment_text)。
    cell_value: None 表示不写入（休息日无打卡等保持模板原样时可由调用方决定）
    """
    if name and is_auto_workday_present(name) and is_workday(punch_date):
        return "√", None

    if punch_date in emp_anomalies:
        if any("缺勤" in a for a in emp_anomalies[punch_date]):
            value = "缺"
        else:
            value = "异"
        lines = []
        for detail in emp_anomaly_details[punch_date]:
            lines.append(
                f"{punch_date.strftime('%Y/%m/%d')}\n{detail['时间']}\n{detail['异常']}"
            )
        return value, "\n\n".join(lines)

    if punch_date in emp_punch_dates and not is_holiday_or_weekend(punch_date):
        mark_check = True
        if is_agency or is_four_punch:
            mark_check = should_count_as_attendance_day(
                emp_punches_by_date, punch_date
            )
        if mark_check:
            return "√", None

    if is_workday(punch_date):
        return "缺", f"{punch_date.strftime('%Y/%m/%d')}\n\n缺勤"

    return None, None


def compute_overtime_cell(
    name,
    emp_id,
    punch_date,
    emp_punches_by_date,
    missing_night_start,
    is_agency,
    is_four_punch,
):
    """返回 (cell_value, comment_text)。"""
    if is_auto_workday_present(name):
        return None, None

    day_times = emp_punches_by_date.get(punch_date, [])

    if is_agency:
        hours = calc_agency_hours_for_shift_end_date(
            emp_punches_by_date, punch_date
        )
        if hours is not None and hours > 0:
            return _format_overtime_hours(hours), None
        return None, None

    if is_holiday_or_weekend(punch_date):
        if is_four_punch:
            result = calc_four_punch_department_rest_overtime(
                punch_date, day_times, emp_punches_by_date
            )
            if (
                result["status"] == "正常"
                and result["hours"] is not None
                and result["hours"] > 0
            ):
                return _format_overtime_hours(result["hours"]), None
            if result["status"] == "异常":
                return "异", None
            if punch_date in missing_night_start:
                info = missing_night_start[punch_date]
                return "异", (
                    f"{punch_date.strftime('%Y/%m/%d')}\n{info['ref_time']}\n缺卡"
                )
        elif len(day_times) == 2:
            hours = calc_weekend_overtime_two_punches(
                day_times[0], day_times[1]
            )
            if hours is not None and hours > 0:
                return _format_overtime_hours(hours), None
        return None, None

    if (
        name in TARGET_WORKDAY_OVERTIME_EMPLOYEES
        or is_four_punch
        or uses_two_punch_override(name)
    ):
        result = calc_workday_overtime(
            name, punch_date, emp_id, day_times, emp_punches_by_date
        )
        if (
            result["status"] == "正常"
            and result["hours"] is not None
            and result["hours"] > 0
        ):
            return _format_overtime_hours(result["hours"]), None
        if result["status"] == "异常":
            return "异", None
        if punch_date in missing_night_start:
            info = missing_night_start[punch_date]
            return "异", (
                f"{punch_date.strftime('%Y/%m/%d')}\n{info['ref_time']}\n缺卡"
            )
    return None, None


def _agency_daily_comment(punch_date, emp_anomaly_details):
    lines = []
    for detail in emp_anomaly_details.get(punch_date, []):
        lines.append(
            f"{punch_date.strftime('%Y/%m/%d')}\n{detail['时间']}\n{detail['异常']}"
        )
    return "\n\n".join(lines) if lines else None


def compute_agency_template_daily_cell(
    punch_date,
    emp_punches_by_date,
    emp_anomalies,
    emp_anomaly_details,
):
    """
    中介模版每日一格：工时数字；无工时时统一按 0 > 缺 > 异（不区分工作日/休息日/节假日）。
    """
    hours = calc_agency_hours_for_shift_end_date(
        emp_punches_by_date, punch_date
    )
    if hours is not None and hours > 0:
        return _format_overtime_hours(hours), None

    day_anomalies = emp_anomalies.get(punch_date, [])
    is_absence = any("缺勤" in a for a in day_anomalies)
    has_other_anomaly = any("缺勤" not in a for a in day_anomalies)

    if not is_absence and not has_other_anomaly:
        return 0, None

    comment = _agency_daily_comment(punch_date, emp_anomaly_details)
    if is_absence:
        if not comment:
            comment = f"{punch_date.strftime('%Y/%m/%d')}\n\n缺勤"
        return "缺", comment

    return "异", comment
