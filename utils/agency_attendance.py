"""中介部门（临时工）考勤：早班6次卡、夜班跨日2次卡。"""

from datetime import datetime, time, timedelta, date

from utils.group2_checker import identify_group2_cards

AGENCY_DEPARTMENT = "中介"
DAY_SHIFT_PUNCH_COUNT = 6
# 夜班：上班日在晚间打上班卡，次日上午打下班卡；工时归集在上班日
# 次晨下班卡：约 8 点前后，含 07:59 等略早于 8:00 的卡；上限 12:00 避免晚间卡误判
NIGHT_SHIFT_OUT_START = time(7, 30)
NIGHT_SHIFT_OUT_END = time(12, 0)
NIGHT_SHIFT_IN_START = time(17, 30)   # 当晚上班卡（含 21:52）
DAY_SHIFT_BASE_MINUTES = 8 * 60 + 30
DAY_SHIFT_END_MINUTES = 17 * 60 + 30  # 早班常规下班 17:30
ROUND_NEAR_HALF_HOUR_MINUTES = 3  # 与半点相差不超过此分钟数则向上取该半点
DAY_SHIFT_BREAK_HOURS = 1.5
DAY_SHIFT_FOUR_CARD_COUNT = 4
DAY_SHIFT_FIVE_CARD_COUNT = 5
DAY_SHIFT_NO_OT_BREAK_HOURS = 1.0  # 4/5次卡无晚间加班，只扣1小时休息
DAY_SHIFT_MIN_COUNT = 4  # 当日>=4次强制按早班处理，不走夜班配对
NIGHT_SHIFT_MAX_START_DAY_COUNT = 2  # 仅当日<=2次才尝试夜班配对；3次视为早班缺卡

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


def _is_night_morning_out(t):
    """次晨夜班下班卡：约 7:30~12:00，不含晚间 21:52 一类。"""
    return NIGHT_SHIFT_OUT_START <= t < NIGHT_SHIFT_OUT_END


def _is_night_evening_in(t):
    """当日晚间夜班上班卡。"""
    return t >= NIGHT_SHIFT_IN_START


def _is_forced_day_shift_day(day_times):
    """当日打卡>=4次：按早班处理，不参与夜班配对。"""
    return len(day_times) >= DAY_SHIFT_MIN_COUNT


def pair_night_shift_starting(punches_by_date, shift_start_date):
    """
    夜班配对（归集在 shift_start_date / 上班日）：
    当日 >=17:30 的上班卡 + 次日晨间下班卡。
    """
    next_date = shift_start_date + timedelta(days=1)
    in_times = punches_by_date.get(shift_start_date, [])
    if _is_forced_day_shift_day(in_times) or len(in_times) > NIGHT_SHIFT_MAX_START_DAY_COUNT:
        return None
    out_times = punches_by_date.get(next_date, [])
    ins = [t for t in in_times if _is_night_evening_in(t)]
    outs = [t for t in out_times if _is_night_morning_out(t)]
    if not ins or not outs:
        return None
    return max(ins), min(outs)


def _round_clock_out_backward_minutes(t):
    """早班加班下班：单纯向下取整到半点。"""
    mins = t.hour * 60 + t.minute
    return (mins // 30) * 30


def _round_half_hour_up_minutes(t):
    """
    上班卡取整：
    - 若距离上一半点 <=3 分钟，贴上一半点（22:03→22:00）
    - 否则向上取整到下一半点（22:04→22:30）
    """
    mins = t.hour * 60 + t.minute
    lower = (mins // 30) * 30
    if mins - lower <= ROUND_NEAR_HALF_HOUR_MINUTES:
        return lower
    if mins % 30 == 0:
        return mins
    return lower + 30


def _round_half_hour_out_minutes(t):
    """
    下班卡：与上一半点相差 <=3 分钟则取上一半点（向上），否则向下取整。
    例：7:57、7:58→8:00；7:50→7:30。
    """
    mins = t.hour * 60 + t.minute
    lower = (mins // 30) * 30
    upper = lower + 30
    if upper - mins <= ROUND_NEAR_HALF_HOUR_MINUTES:
        return upper
    return lower


def _minutes_to_time(mins):
    return time(mins // 60, mins % 60)


def calc_agency_standard_day_no_ot_hours():
    """早班固定时段（无加班）：8:30~17:30，扣1小时休息。"""
    hours = (DAY_SHIFT_END_MINUTES - DAY_SHIFT_BASE_MINUTES) / 60.0
    hours -= DAY_SHIFT_NO_OT_BREAK_HOURS
    return round(hours, 2)


def calc_agency_four_card_hours(punch_times):
    """
    4次卡新规则：
    - 起点：首卡，8:30前按8:30；8:30后向上取整到下一半点
    - 终点：末卡向下取整到半点
    - 再减1小时午休
    """
    if len(punch_times) != DAY_SHIFT_FOUR_CARD_COUNT:
        return None
    first = punch_times[0]
    last = punch_times[-1]
    start_mins = _round_half_hour_up_minutes(first)
    end_mins = _round_clock_out_backward_minutes(last)
    hours = (end_mins - start_mins) / 60.0 - DAY_SHIFT_NO_OT_BREAK_HOURS
    if hours <= 0:
        return None
    return round(hours, 2)


def calc_agency_day_shift_hours(punch_date, punch_times):
    """早班6次卡：加班下班(向后取整) - 8:30 - 1.5h。"""
    if len(punch_times) != DAY_SHIFT_PUNCH_COUNT:
        return None
    identified = identify_group2_cards(punch_date, punch_times)
    ot_out = identified.get("加班下班卡")
    if ot_out is None:
        return None
    ot_time = ot_out.time() if isinstance(ot_out, datetime) else ot_out
    start_mins = _round_half_hour_up_minutes(punch_times[0])
    end_mins = _round_clock_out_backward_minutes(ot_time)
    hours = (end_mins - start_mins) / 60.0 - DAY_SHIFT_BREAK_HOURS
    if hours <= 0:
        return None
    return round(hours, 2)


def calc_agency_night_shift_hours(clock_in, clock_out, shift_start_date):
    """夜班：次晨下班(3分钟规则取整) - 当晚上班(向上取整到半点)。"""
    start_mins = _round_half_hour_up_minutes(clock_in)
    end_mins = _round_half_hour_out_minutes(clock_out)
    start_dt = datetime.combine(shift_start_date, _minutes_to_time(start_mins))
    end_dt = datetime.combine(
        shift_start_date + timedelta(days=1), _minutes_to_time(end_mins)
    )
    hours = (end_dt - start_dt).total_seconds() / 3600.0
    if hours <= 0:
        return None
    return round(hours, 2)


def calc_agency_hours_for_shift_end_date(punches_by_date, punch_date):
    """按上班日/当日计算中介工时（夜班归集在上班日）。"""
    day_times = punches_by_date.get(punch_date, [])
    n = len(day_times)
    if n == DAY_SHIFT_PUNCH_COUNT:
        return calc_agency_day_shift_hours(punch_date, day_times)
    if n == DAY_SHIFT_FOUR_CARD_COUNT:
        return calc_agency_four_card_hours(day_times)
    if n == DAY_SHIFT_FIVE_CARD_COUNT:
        # 5次卡视为应打6次但缺卡：只标异常，不计工时
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
    """早班6次卡：六类卡齐全，否则报缺卡。"""
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
    """早班未满6次（如3次、5次）：用 group2 标出缺哪类卡。"""
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
    """按自然日检查中介考勤异常。"""
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

    # 当日<=2次：仅按夜班规则检查
    if pair_night_shift_starting(punches_by_date, punch_date):
        return []

    next_date = punch_date + timedelta(days=1)
    next_times = punches_by_date.get(next_date, [])
    evening_ins = [t for t in day_times if _is_night_evening_in(t)]
    morning_outs = [t for t in day_times if _is_night_morning_out(t)]
    morning_outs_next = [t for t in next_times if _is_night_morning_out(t)]

    # 当日同时有「结束昨日夜班」的晨卡 + 「开始新夜班」的晚卡 → 正常
    if morning_outs and evening_ins:
        return []

    # 当日仅晨间下班（结束前一晚夜班）
    if morning_outs and not evening_ins:
        return []

    # 当日晚间上班，但次日没有晨间下班
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
    """返回 {(姓名, 编号), ...}"""
    subset = df[df["部门"].apply(is_agency_department)]
    if subset.empty:
        return set()
    return set(zip(subset["姓名"], subset["编号"]))
