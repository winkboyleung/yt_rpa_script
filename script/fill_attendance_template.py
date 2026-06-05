"""
按日增量填写考勤模板（默认：昨天）。
第 1 步请先跑 rpa_4_clock_in.py 生成整月异常表（方案 B：全月扫描）。
"""
import argparse
import os
import sys
from datetime import datetime, timedelta

import pandas as pd
from openpyxl import load_workbook
from openpyxl.comments import Comment

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.holiday_checker import is_holiday_or_weekend
from utils import workday_overtime
from utils.workday_overtime import refresh_workday_six_punch_employees_from_df
from utils.agency_attendance import get_agency_employee_keys
from utils.night_shift import collect_missing_night_start_dates
from utils.attendance_cells import (
    build_employee_anomaly_maps,
    merge_missing_night_start_anomalies,
    compute_attendance_cell,
    compute_overtime_cell,
)

FILES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "files"
)
DEFAULT_TEMPLATE = os.path.join(FILES_DIR, "6月办公室考勤模版.xlsx")
DEFAULT_PUNCH = os.path.join(FILES_DIR, "6月打卡.xls")
DEFAULT_ANOMALY = os.path.join(FILES_DIR, "6月打卡异常.xlsx")

# PyCharm 右击「运行」时生效：1=仅昨天，2=前天+昨天（不必配命令行参数）
DEFAULT_LOOKBACK_DAYS = 3

DAY_HEADER_ROW = 3
DATA_START_ROW = 5
DAY_COL_OFFSET = 3


def read_punch_df(path):
    try:
        return pd.read_excel(path, engine="xlrd")
    except Exception:
        return pd.read_excel(path, engine="openpyxl")


def parse_template_layout(ws):
    """{日号: 列号}, {姓名: (出勤行, 加班行)}"""
    day_to_col = {}
    for col in range(4, 50):
        val = ws.cell(DAY_HEADER_ROW, col).value
        if isinstance(val, int) and 1 <= val <= 31:
            day_to_col[val] = col

    name_to_rows = {}
    row = DATA_START_ROW
    max_row = ws.max_row or 500
    while row <= max_row:
        name = ws.cell(row, 2).value
        label = ws.cell(row, 3).value
        if name and str(label).strip() == "正常出勤":
            name = str(name).strip()
            name_to_rows[name] = (row, row + 1)
            row += 2
            continue
        if name is None and label is None and row > DATA_START_ROW + 4:
            break
        row += 1
    return day_to_col, name_to_rows


def infer_year_month(ws, punch_df, reference_date):
    title = ws.cell(1, 1).value or ""
    for text in (title, DEFAULT_TEMPLATE):
        s = str(text)
        if "年" in s and "月" in s:
            try:
                y = int(s.split("年")[0][-4:])
                m = int(s.split("年")[1].split("月")[0])
                return y, m
            except ValueError:
                pass
    start = punch_df["日期"].min()
    return start.year, start.month


def target_dates(year, month, reference_date, lookback_days):
    month_start = datetime(year, month, 1).date()
    if month == 12:
        month_end = datetime(year + 1, 1, 1).date() - timedelta(days=1)
    else:
        month_end = datetime(year, month + 1, 1).date() - timedelta(days=1)

    dates = []
    for i in range(1, lookback_days + 1):
        d = reference_date - timedelta(days=i)
        if month_start <= d <= month_end:
            dates.append(d)
    return sorted(dates)


def apply_cell(ws, row, col, value, comment_text):
    cell = ws.cell(row, col)
    cell.value = value
    if comment_text:
        cell.comment = Comment(comment_text, "系统")
    elif cell.comment:
        cell.comment = None


def fill_attendance_template(
    template_path,
    punch_path,
    anomaly_path,
    reference_date=None,
    lookback_days=1,
    output_path=None,
):
    reference_date = reference_date or datetime.now().date()
    output_path = output_path or template_path

    punch_df = read_punch_df(punch_path)
    punch_df["日期时间"] = pd.to_datetime(punch_df["日期时间"])
    punch_df["日期"] = punch_df["日期时间"].dt.date
    punch_df["打卡时间"] = punch_df["日期时间"].dt.time

    refresh_workday_six_punch_employees_from_df(punch_df)
    agency_keys = get_agency_employee_keys(punch_df)

    anomaly_df = pd.DataFrame()
    if os.path.exists(anomaly_path):
        anomaly_df = pd.read_excel(anomaly_path)
        anomaly_df["日期"] = pd.to_datetime(anomaly_df["日期"]).dt.date

    wb = load_workbook(template_path)
    ws = wb.active
    day_to_col, name_to_rows = parse_template_layout(ws)
    year, month = infer_year_month(ws, punch_df, reference_date)
    dates_to_fill = target_dates(year, month, reference_date, lookback_days)

    if not dates_to_fill:
        print(f"无落在 {year}年{month}月 内的目标日期（参考日 {reference_date}，回溯 {lookback_days} 天）")
        return

    month_start = datetime(year, month, 1).date()
    days_in_month = pd.Period(f"{year}-{month}").days_in_month
    month_end = datetime(year, month, days_in_month).date()

    print(f"模板: {template_path}")
    print(f"参考日: {reference_date}，填写日期: {[d.isoformat() for d in dates_to_fill]}")

    filled_cells = 0
    for name, (att_row, ot_row) in name_to_rows.items():
        emp_records = punch_df[punch_df["姓名"] == name]
        if emp_records.empty:
            emp_id = ""
            emp_punches_by_date = {}
            emp_punch_dates = set()
        else:
            emp_id = emp_records.iloc[0]["编号"]
            emp_punch_dates = set(emp_records["日期"])
            emp_punches_by_date = {}
            for d, group in emp_records.groupby("日期"):
                emp_punches_by_date[d] = sorted(group["打卡时间"].tolist())

        emp_anomalies, emp_anomaly_details = build_employee_anomaly_maps(
            name, anomaly_df
        )
        missing_night_start = {}
        is_four_punch = name in workday_overtime.TARGET_WORKDAY_SIX_PUNCH_EMPLOYEES
        if is_four_punch:
            missing_night_start = collect_missing_night_start_dates(
                emp_punches_by_date, month_start, month_end
            )
            merge_missing_night_start_anomalies(
                name, emp_anomalies, emp_anomaly_details, missing_night_start
            )

        is_agency = (name, emp_id) in agency_keys if emp_id else False

        for punch_date in dates_to_fill:
            day_num = punch_date.day
            col = day_to_col.get(day_num)
            if not col:
                continue

            att_val, att_comment = compute_attendance_cell(
                punch_date,
                emp_punch_dates,
                emp_punches_by_date,
                emp_anomalies,
                emp_anomaly_details,
                is_agency,
                is_four_punch,
                name=name,
            )
            if att_val is not None:
                apply_cell(ws, att_row, col, att_val, att_comment)
                filled_cells += 1

            ot_val, ot_comment = compute_overtime_cell(
                name,
                emp_id,
                punch_date,
                emp_punches_by_date,
                missing_night_start,
                is_agency,
                is_four_punch,
            )
            if ot_val is not None:
                apply_cell(ws, ot_row, col, ot_val, ot_comment)
                filled_cells += 1
            elif not is_holiday_or_weekend(punch_date):
                apply_cell(ws, ot_row, col, None, None)

    wb.save(output_path)
    print(f"已更新 {len(name_to_rows)} 名模板员工，写入 {filled_cells} 个单元格")
    print(f"已保存: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="按日填写考勤模板（默认昨天）")
    parser.add_argument("--template", default=DEFAULT_TEMPLATE, help="考勤模板路径")
    parser.add_argument("--punch", default=DEFAULT_PUNCH, help="打卡记录路径")
    parser.add_argument("--anomaly", default=DEFAULT_ANOMALY, help="异常表路径")
    parser.add_argument(
        "--days",
        type=int,
        default=DEFAULT_LOOKBACK_DAYS,
        help="回溯天数，默认见文件顶部 DEFAULT_LOOKBACK_DAYS",
    )
    parser.add_argument(
        "--reference-date",
        default=None,
        help="参考日期 YYYY-MM-DD，默认今天",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="输出路径，默认覆盖模板",
    )
    args = parser.parse_args()
    ref = (
        datetime.strptime(args.reference_date, "%Y-%m-%d").date()
        if args.reference_date
        else datetime.now().date()
    )
    fill_attendance_template(
        args.template,
        args.punch,
        args.anomaly,
        reference_date=ref,
        lookback_days=args.days,
        output_path=args.output,
    )


if __name__ == "__main__":
    main()
