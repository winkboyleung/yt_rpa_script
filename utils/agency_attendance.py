"""中介部门（临时工）考勤：早班6次卡、夜班跨日2次卡。"""

from datetime import datetime, time, timedelta

from utils.group2_checker import identify_group2_cards
from utils.night_shift import (
    DAY_SHIFT_MIN_COUNT,
    NIGHT_SHIFT_MAX_START_DAY_COUNT,
    calc_agency_night_shift_hours,
    is_night_evening_in,
    is_night_morning_out,
    pair_night_shift_starting,
    round_half_hour_out_minutes,
    round_half_hour_up_minutes,
)

AGENCY_DEPARTMENT = "中介"
DAY_SHIFT_PUNCH_COUNT = 6
DAY_SHIFT_BASE_MINUTES = 8 * 60 + 30
DAY_SHIFT_END_MINUTES = 17 * 60 + 30
DAY_SHIFT_BREAK_HOURS = 1.5
DAY_SHIFT_FOUR_CARD_COUNT = 4
DAY_SHIFT_FIVE_CARD_COUNT = 5
DAY_SHIFT_NO_OT_BREAK_HOURS = 1.0

REQUIRED_DAY_CARDS = [
    "上午上班卡",
    "上午下班卡",
    "下午上班卡",
    "下午下班卡",
    "加班上班卡",
    "加班下班卡",
]


def is_agency_department(dept):
    if dept is None:
        return False
    return str(dept).strip() == AGENCY_DEPARTMENT


def build_punches_by_date(emp_df):
    """{date: [time, ...]}"""
    punches = {}
    for punch_date, group in emp_df.groupby("日期"):
        punches[punch_date] = sorted(group["打卡时间"].tolist())
    return punches


def collect_agency_check_dates(punches_by_date, month_start, month_end):
    """含打卡日及夜班上班日的次日（用于查晨间下班卡）。"""
    dates = set(punches_by_date.keys())
    for punch_date in list(dates):
        next_day = punch_date + timedelta(days=1)
        if month_start <= next_day <= month_end:
            dates.add(next_day)
    return sorted(d for d in dates if month_start <= d <= month_end)


def _round_clock_out_backward_minutes(t):
    mins = t.hour * 60 + t.minute
    return (mins // 30) * 30


def _minutes_to_time(mins):
    return time(mins // 60, mins % 60)


def calc_agency_standard_day_no_ot_hours():
    hours = (DAY_SHIFT_END_MINUTES - DAY_SHIFT_BASE_MINUTES) / 60.0
    hours -= DAY_SHIFT_NO_OT_BREAK_HOURS
    return round(hours, 2)


def calc_agency_four_card_hours(punch_times):
    if len(punch_times) != DAY_SHIFT_FOUR_CARD_COUNT:
        return None
    first = punch_times[0]
    last = punch_times[-1]
    start_mins = round_half_hour_up_minutes(first)
    end_mins = _round_clock_out_backward_minutes(last)
    hours = (end_mins - start_mins) / 60.0 - DAY_SHIFT_NO_OT_BREAK_HOURS
    if hours <= 0:
        return None
    return round(hours, 2)


def calc_agency_day_shift_hours(punch_date, punch_times):
    if len(punch_times) != DAY_SHIFT_PUNCH_COUNT:
        return None
    identified = identify_group2_cards(punch_date, punch_times)
    ot_out = identified.get("加班下班卡")
    if ot_out is None:
        return None
    ot_time = ot_out.time() if isinstance(ot_out, datetime) else ot_out
    start_mins = round_half_hour_up_minutes(punch_times[0])
    end_mins = _round_clock_out_backward_minutes(ot_time)
    hours = (end_mins - start_mins) / 60.0 - DAY_SHIFT_BREAK_HOURS
    if hours <= 0:
        return None
    return round(hours, 2)


def calc_agency_hours_for_shift_end_date(punches_by_date, punch_date):
    day_times = punches_by_date.get(punch_date, [])
    n = len(day_times)
    if n == DAY_SHIFT_PUNCH_COUNT:
        return calc_agency_day_shift_hours(punch_date, day_times)
    if n == DAY_SHIFT_FOUR_CARD_COUNT:
        return calc_agency_four_card_hours(day_times)
    if n == DAY_SHIFT_FIVE_CARD_COUNT:
        return None
    if n <= NIGHT_SHIFT_MAX_START_DAY_COUNT:
        pair = pair_night_shift_starting(punches_by_date, punch_date)
        if pair:
            clock_in, clock_out = pair
            return calc_agency_night_shift_hours(clock_in, clock_out, punch_date)
    return None


def _anomaly_record(name, punch_date, emp_id, punch_time, anomaly_type):
    return {
        "姓名": name,
        "日期": punch_date,
        "编号": emp_id,
        "打卡时间": str(punch_time),
        "考勤异常情况": anomaly_type,
    }


def check_agency_day_shift_six_cards(name, punch_date, emp_id, punch_times):
    if len(punch_times) != DAY_SHIFT_PUNCH_COUNT:
        first = punch_times[0] if punch_times else time(0, 0)
        return [_anomaly_record(name, punch_date, emp_id, first, "缺卡")]

    identified = identify_group2_cards(punch_date, punch_times)
    anomalies = []
    first = punch_times[0]
    for card in REQUIRED_DAY_CARDS:
        if identified[card] is None:
            anomalies.append(
                _anomaly_record(name, punch_date, emp_id, first, f"无打{card}")
            )
    return anomalies


def check_agency_day_shift_missing_cards(name, punch_date, emp_id, punch_times):
    if not punch_times:
        return []
    identified = identify_group2_cards(punch_date, punch_times)
    anomalies = []
    first = punch_times[0]
    for card in REQUIRED_DAY_CARDS:
        if identified[card] is None:
            anomalies.append(
                _anomaly_record(name, punch_date, emp_id, first, f"无打{card}")
            )
    if not anomalies:
        anomalies.append(
            _anomaly_record(name, punch_date, emp_id, first, "缺卡")
        )
    return anomalies


def check_agency_attendance_on_date(name, punch_date, emp_id, punches_by_date):
    day_times = punches_by_date.get(punch_date, [])
    n = len(day_times)

    if n == DAY_SHIFT_FOUR_CARD_COUNT:
        return []

    if n == DAY_SHIFT_FIVE_CARD_COUNT:
        return check_agency_day_shift_missing_cards(
            name, punch_date, emp_id, day_times
        )

    if n == DAY_SHIFT_PUNCH_COUNT:
        return check_agency_day_shift_six_cards(
            name, punch_date, emp_id, day_times
        )

    if n == 3:
        return check_agency_day_shift_missing_cards(
            name, punch_date, emp_id, day_times
        )

    if pair_night_shift_starting(punches_by_date, punch_date):
        return []

    next_date = punch_date + timedelta(days=1)
    next_times = punches_by_date.get(next_date, [])
    evening_ins = [t for t in day_times if is_night_evening_in(t)]
    morning_outs = [t for t in day_times if is_night_morning_out(t)]
    morning_outs_next = [t for t in next_times if is_night_morning_out(t)]

    if morning_outs and evening_ins:
        return []

    if morning_outs and not evening_ins:
        return []

    if evening_ins and not morning_outs_next:
        ref = max(evening_ins)
        return [
            _anomaly_record(name, punch_date, emp_id, ref, "无打下班卡")
        ]

    if len(day_times) >= 1:
        first = day_times[0]
        return [_anomaly_record(name, punch_date, emp_id, first, "缺卡")]

    return []


def check_agency_employee(name, emp_id, punches_by_date, month_start, month_end):
    anomalies = []
    for punch_date in collect_agency_check_dates(
        punches_by_date, month_start, month_end
    ):
        anomalies.extend(
            check_agency_attendance_on_date(
                name, punch_date, emp_id, punches_by_date
            )
        )
    return anomalies


def get_agency_employee_keys(df):
    subset = df[df["部门"].apply(is_agency_department)]
    if subset.empty:
        return set()
    return set(zip(subset["姓名"], subset["编号"]))
