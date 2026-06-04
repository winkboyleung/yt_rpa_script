"""跨日夜班配对与取整（中介、四次基本卡部门共用）。"""

from datetime import datetime, time, timedelta

NIGHT_SHIFT_OUT_START = time(7, 30)
NIGHT_SHIFT_OUT_END = time(12, 0)
NIGHT_SHIFT_IN_START = time(17, 30)
ROUND_NEAR_HALF_HOUR_MINUTES = 3
DAY_SHIFT_MIN_COUNT = 4
NIGHT_SHIFT_MAX_START_DAY_COUNT = 2
FOUR_PUNCH_STANDARD_HOURS = 8.0


def is_night_morning_out(t):
    return NIGHT_SHIFT_OUT_START <= t < NIGHT_SHIFT_OUT_END


def is_night_evening_in(t):
    return t >= NIGHT_SHIFT_IN_START


def _is_forced_day_shift_day(day_times):
    return len(day_times) >= DAY_SHIFT_MIN_COUNT


def pair_night_shift_starting(punches_by_date, shift_start_date):
    """当日 <=2 次且非早班：晚间上班卡 + 次日晨间下班卡。"""
    next_date = shift_start_date + timedelta(days=1)
    in_times = punches_by_date.get(shift_start_date, [])
    if _is_forced_day_shift_day(in_times) or len(in_times) > NIGHT_SHIFT_MAX_START_DAY_COUNT:
        return None
    out_times = punches_by_date.get(next_date, [])
    ins = [t for t in in_times if is_night_evening_in(t)]
    outs = [t for t in out_times if is_night_morning_out(t)]
    if not ins or not outs:
        return None
    return max(ins), min(outs)


def round_half_hour_up_minutes(t):
    mins = t.hour * 60 + t.minute
    lower = (mins // 30) * 30
    if mins - lower <= ROUND_NEAR_HALF_HOUR_MINUTES:
        return lower
    if mins % 30 == 0:
        return mins
    return lower + 30


def round_half_hour_out_minutes(t):
    mins = t.hour * 60 + t.minute
    lower = (mins // 30) * 30
    upper = lower + 30
    if upper - mins <= ROUND_NEAR_HALF_HOUR_MINUTES:
        return upper
    return lower


def _minutes_to_time(mins):
    return time(mins // 60, mins % 60)


def calc_night_shift_span_hours(clock_in, clock_out, shift_start_date):
    """取整后的跨日总工时，不扣休息。"""
    start_mins = round_half_hour_up_minutes(clock_in)
    end_mins = round_half_hour_out_minutes(clock_out)
    start_dt = datetime.combine(shift_start_date, _minutes_to_time(start_mins))
    end_dt = datetime.combine(
        shift_start_date + timedelta(days=1), _minutes_to_time(end_mins)
    )
    hours = (end_dt - start_dt).total_seconds() / 3600.0
    if hours <= 0:
        return None
    return round(hours, 2)


def calc_agency_night_shift_hours(clock_in, clock_out, shift_start_date):
    return calc_night_shift_span_hours(clock_in, clock_out, shift_start_date)


def calc_four_punch_night_overtime(clock_in, clock_out, shift_start_date, is_workday):
    """
    四次基本卡部门跨日夜班：
    - 工作日：日历格写 max(0, 总跨度-8)，统计进平时
    - 周末/节假日：日历格写总跨度，统计进休息日
    """
    span = calc_night_shift_span_hours(clock_in, clock_out, shift_start_date)
    if span is None:
        return {"status": "异常", "cell_hours": None, "weekday_ot": 0.0, "rest_ot": 0.0, "reason": "跨日夜班工时无效"}
    if is_workday:
        ot = max(0.0, round(span - FOUR_PUNCH_STANDARD_HOURS, 2))
        return {"status": "正常", "cell_hours": ot, "weekday_ot": ot, "rest_ot": 0.0, "reason": ""}
    return {"status": "正常", "cell_hours": span, "weekday_ot": 0.0, "rest_ot": span, "reason": ""}


def try_four_punch_night_overtime(punches_by_date, shift_start_date, is_workday):
    pair = pair_night_shift_starting(punches_by_date, shift_start_date)
    if not pair:
        return None
    clock_in, clock_out = pair
    result = calc_four_punch_night_overtime(clock_in, clock_out, shift_start_date, is_workday)
    result["clock_in"] = clock_in
    result["clock_out"] = clock_out
    return result


def is_morning_out_paired_from_previous_day(punches_by_date, punch_date, morning_time):
    """次晨下班卡是否已被前一自然日的跨日夜班配对消耗。"""
    prev_date = punch_date - timedelta(days=1)
    pair = pair_night_shift_starting(punches_by_date, prev_date)
    if not pair:
        return False
    _, clock_out = pair
    return clock_out == morning_time


def _is_empty_rest_day(punches_by_date, d):
    """FOUR_PUNCH：周末/节假日且当日零打卡 → 视为休息，不记跨日缺卡。"""
    from utils.holiday_checker import is_holiday_or_weekend

    if not is_holiday_or_weekend(d):
        return False
    return len(punches_by_date.get(d, [])) == 0


def find_missing_night_start_for_morning_out(punches_by_date, punch_date):
    """
    当日有次晨下班卡且未被前一日配对 → 前一日缺晚间上班卡。
    前一日若为「零打卡的休息日」则跳过（FOUR_PUNCH 专用）。
    返回 {"missing_date", "ref_time", "reason"} 或 None。
    """
    day_times = punches_by_date.get(punch_date, [])
    morning_outs = [t for t in day_times if is_night_morning_out(t)]
    if not morning_outs:
        return None

    prev_date = punch_date - timedelta(days=1)
    prev_times = punches_by_date.get(prev_date, [])
    if _is_forced_day_shift_day(prev_times):
        return None

    for mo in morning_outs:
        if is_morning_out_paired_from_previous_day(punches_by_date, punch_date, mo):
            continue
        prev_evening = [t for t in prev_times if is_night_evening_in(t)]
        if not prev_evening:
            if _is_empty_rest_day(punches_by_date, prev_date):
                continue
            return {
                "missing_date": prev_date,
                "ref_time": mo,
                "reason": "缺卡",
            }
    return None


def collect_missing_night_start_dates(punches_by_date, month_start, month_end):
    """{缺卡日期: {"ref_time", "reason"}}"""
    result = {}
    for punch_date in punches_by_date:
        if not (month_start <= punch_date <= month_end):
            continue
        info = find_missing_night_start_for_morning_out(punches_by_date, punch_date)
        if not info:
            continue
        missing_date = info["missing_date"]
        if month_start <= missing_date <= month_end:
            result[missing_date] = info
    return result


def should_count_as_attendance_day(punches_by_date, punch_date):
    """
    FOUR_PUNCH / 中介：是否计「正常出勤√」。
    当日仅有已被前一日夜班配对的次晨下班卡 → False。
    """
    day_times = punches_by_date.get(punch_date, [])
    if not day_times:
        return False

    for t in day_times:
        if is_night_evening_in(t):
            return True
        if not is_night_morning_out(t):
            return True
        if not is_morning_out_paired_from_previous_day(
            punches_by_date, punch_date, t
        ):
            return True
    return False


def check_four_punch_night_anomaly(punch_date, punches_by_date):
    """四次基本卡部门：有晚无晨 → 异；有晨无晚（前一日缺卡）→ 缺卡。"""
    day_times = punches_by_date.get(punch_date, [])
    if len(day_times) < DAY_SHIFT_MIN_COUNT:
        next_info = find_missing_night_start_for_morning_out(
            punches_by_date, punch_date + timedelta(days=1)
        )
        if next_info and next_info["missing_date"] == punch_date:
            return {
                "type": "缺卡",
                "ref_time": next_info["ref_time"],
            }

    if pair_night_shift_starting(punches_by_date, punch_date):
        return None
    if len(day_times) >= DAY_SHIFT_MIN_COUNT:
        return None
    next_times = punches_by_date.get(punch_date + timedelta(days=1), [])
    evening_ins = [t for t in day_times if is_night_evening_in(t)]
    morning_outs_next = [t for t in next_times if is_night_morning_out(t)]
    if evening_ins and not morning_outs_next:
        return {"type": "异", "ref_time": max(evening_ins)}
    return None
