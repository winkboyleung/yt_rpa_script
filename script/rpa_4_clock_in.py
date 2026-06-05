import argparse
import pandas as pd
from datetime import datetime, time
import os
import sys

# 添加项目根目录到系统路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.holiday_checker import is_holiday_or_weekend, get_overtime_missing_card_type, is_workday
from utils.workday_overtime import check_four_punch_employee
from utils.agency_attendance import (
    get_agency_employee_keys,
    build_punches_by_date,
    check_agency_employee,
    collect_agency_check_dates,
)
from utils.punch_config import (
    get_four_punch_employee_names,
    TWO_PUNCH_OVERRIDE_NAMES,
    AUTO_WORKDAY_PRESENT_NAMES,
    is_auto_workday_present,
)

FILES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "files"
)

# ── PyCharm 右击「运行」默认配置 ──
INPUT_FILE = os.path.join(FILES_DIR, "6月打卡.xls")
OUTPUT_FILE = os.path.join(FILES_DIR, "6月打卡异常.xlsx")
# ── 以上默认值 ──

# 考勤规则
WORK_START_TIME = time(8, 33, 59)
WORK_END_TIME = time(17, 30)

# 员工分组
EMPLOYEE_GROUP_1 = ['林达玲', '梁海雯']  # 只检查缺卡
EMPLOYEE_GROUP_2 = []  # 小部分人（4次基本卡），程序运行时自动填充
EMPLOYEE_GROUP_3 = []  # 待定


def check_missing_card(name, date, emp_id, times, record_count):
    """检查缺卡情况（适用于数组1，所有缺卡都检查）"""
    anomalies = []
    if record_count < 2:
        if record_count == 1:
            clock_time = times[0]

            anomaly_type = get_overtime_missing_card_type(date)
            if anomaly_type is None:
                if clock_time < time(12, 0):
                    anomaly_type = '无打下班卡'
                else:
                    anomaly_type = '无打上班卡'

            anomalies.append({
                '姓名': name,
                '日期': date,
                '编号': emp_id,
                '打卡时间': str(clock_time),
                '考勤异常情况': anomaly_type
            })
    return anomalies


def check_missing_card_default(name, date, emp_id, times, record_count):
    """检查缺卡情况（适用于大部分人，2次基本卡）"""
    anomalies = []

    # 打卡次数 = 2 或 4，正常
    if record_count == 2 or record_count == 4:
        return anomalies

    # 打卡次数为单数（1 或 3），缺卡
    if record_count in [1, 3]:
        overtime_missing_card_type = get_overtime_missing_card_type(date)

        if record_count == 1:
            clock_time = times[0]
            if overtime_missing_card_type:
                anomaly_type = overtime_missing_card_type
            else:
                if clock_time < time(12, 0):
                    anomaly_type = '无打下班卡'
                else:
                    anomaly_type = '无打上班卡'

            anomalies.append({
                '姓名': name,
                '日期': date,
                '编号': emp_id,
                '打卡时间': str(clock_time),
                '考勤异常情况': anomaly_type
            })
        elif record_count == 3:
            first_time = times[0]
            anomaly_type = overtime_missing_card_type or '缺卡'

            anomalies.append({
                '姓名': name,
                '日期': date,
                '编号': emp_id,
                '打卡时间': str(first_time),
                '考勤异常情况': anomaly_type
            })

    return anomalies


def check_late_early(name, date, emp_id, times, record_count):
    """检查迟到早退情况"""
    anomalies = []
    if record_count >= 2:
        first_time = times[0]
        last_time = times[-1]

        if first_time > WORK_START_TIME:
            anomalies.append({
                '姓名': name,
                '日期': date,
                '编号': emp_id,
                '打卡时间': str(first_time),
                '考勤异常情况': '上班迟到'
            })

        if last_time < WORK_END_TIME:
            anomalies.append({
                '姓名': name,
                '日期': date,
                '编号': emp_id,
                '打卡时间': str(last_time),
                '考勤异常情况': '下班早退'
            })
    return anomalies


def check_absence(df, skip_employee_keys=None):
    """工作日零打卡记为缺勤"""
    anomalies = []
    skip_employee_keys = skip_employee_keys or set()
    employees = df[['姓名', '编号']].drop_duplicates()
    start_date = df['日期'].min()
    end_date = df['日期'].max()
    punched_days = set(df.groupby(['姓名', '日期', '编号']).groups.keys())

    for _, row in employees.iterrows():
        name, emp_id = row['姓名'], row['编号']
        if is_auto_workday_present(name):
            continue
        if (name, emp_id) in skip_employee_keys:
            continue
        for day in pd.date_range(start_date, end_date):
            date = day.date()
            if not is_workday(date):
                continue
            if (name, date, emp_id) not in punched_days:
                anomalies.append({
                    '姓名': name,
                    '日期': date,
                    '编号': emp_id,
                    '打卡时间': '',
                    '考勤异常情况': '缺勤'
                })
    return anomalies


def analyze_attendance(input_file=None, output_file=None):
    """分析考勤异常情况（方案 B：整表打卡全月扫描，输出整月异常）"""
    input_file = input_file or INPUT_FILE
    output_file = output_file or OUTPUT_FILE
    try:
        df = pd.read_excel(input_file, engine='xlrd')
    except:
        try:
            df = pd.read_excel(input_file, engine='openpyxl')
        except:
            print("无法读取xls文件，请将文件转换为xlsx格式")
            return

    print("数据列名:", df.columns.tolist())
    print("\n前5行数据:")
    print(df.head())

    # 打印节假日信息
    print("\n" + "=" * 50)
    print("节假日信息（节假日和周末不检查迟到早退）")
    print("=" * 50)

    df['日期时间'] = pd.to_datetime(df['日期时间'])
    df['日期'] = df['日期时间'].dt.date
    df['打卡时间'] = df['日期时间'].dt.time

    # 自动识别并填充数组2：工程组、乳化车间、灌装车间的员工
    group2_employees = sorted(get_four_punch_employee_names(df))
    EMPLOYEE_GROUP_2.clear()
    EMPLOYEE_GROUP_2.extend(group2_employees)
    print(f"\n自动识别数组2员工（4次基本卡）: {EMPLOYEE_GROUP_2}")
    if TWO_PUNCH_OVERRIDE_NAMES:
        print(f"按两次卡规则（非数组2）: {sorted(TWO_PUNCH_OVERRIDE_NAMES)}")
    if AUTO_WORKDAY_PRESENT_NAMES:
        print(f"工作日默认出勤√（不计算）: {sorted(AUTO_WORKDAY_PRESENT_NAMES)}")

    anomalies = []
    processed_employees = set()
    grouped = df.groupby(['姓名', '日期', '编号'])
    agency_keys = get_agency_employee_keys(df)
    month_start = df['日期'].min()
    month_end = df['日期'].max()

    # 中介部门：早班6次卡 / 夜班跨日2次卡
    print("\n处理中介部门员工...")
    for name, emp_id in sorted(agency_keys):
        emp_df = df[(df['姓名'] == name) & (df['编号'] == emp_id)]
        punches_by_date = build_punches_by_date(emp_df)
        anomalies.extend(
            check_agency_employee(
                name, emp_id, punches_by_date, month_start, month_end
            )
        )
        for punch_date in collect_agency_check_dates(
                punches_by_date, month_start, month_end
        ):
            processed_employees.add((name, punch_date, emp_id))
    if agency_keys:
        print(f"  中介员工 {len(agency_keys)} 人")

    # 第一步：处理数组1的员工（只检查缺卡）
    print("\n处理数组1员工（只检查缺卡）...")
    for (name, date, emp_id), group in grouped:
        if is_auto_workday_present(name):
            processed_employees.add((name, date, emp_id))
            continue
        if name in EMPLOYEE_GROUP_1:
            records = group.sort_values('日期时间')
            record_count = len(records)
            times = records['打卡时间'].tolist()

            anomalies.extend(check_missing_card(name, date, emp_id, times, record_count))
            processed_employees.add((name, date, emp_id))

    # 第二步：处理数组2的员工（四次基本卡 + 跨日夜班）
    print("处理数组2员工（4次基本卡）...")
    for name in EMPLOYEE_GROUP_2:
        if is_auto_workday_present(name):
            continue
        emp_rows = df[df["姓名"] == name]
        if emp_rows.empty:
            continue
        emp_id = emp_rows.iloc[0]["编号"]
        emp_df = df[(df["姓名"] == name) & (df["编号"] == emp_id)]
        punches_by_date = build_punches_by_date(emp_df)
        anomalies.extend(
            check_four_punch_employee(
                name, emp_id, punches_by_date, month_start, month_end
            )
        )
        for punch_date in collect_agency_check_dates(
                punches_by_date, month_start, month_end
        ):
            processed_employees.add((name, punch_date, emp_id))

    # 第三步：处理数组3的员工（待定）
    print("处理数组3员工（待定）...")
    for (name, date, emp_id), group in grouped:
        if name in EMPLOYEE_GROUP_3 and (name, date, emp_id) not in processed_employees:
            # 待定规则，目前不处理
            processed_employees.add((name, date, emp_id))

    # 第四步：处理剩余员工（大部分人：2次基本卡 + 完整规则）
    print("处理剩余员工（2次基本卡 + 完整规则）...")
    for (name, date, emp_id), group in grouped:
        if is_auto_workday_present(name):
            processed_employees.add((name, date, emp_id))
            continue
        if (name, date, emp_id) not in processed_employees:
            records = group.sort_values('日期时间')
            record_count = len(records)
            times = records['打卡时间'].tolist()

            # 检查缺卡（无论是否节假日都要检查）
            anomalies.extend(check_missing_card_default(name, date, emp_id, times, record_count))

            # 判断是否为节假日或周末
            if is_holiday_or_weekend(date):
                # 节假日或周末，不检查迟到早退
                pass
            else:
                # 工作日，检查迟到早退
                anomalies.extend(check_late_early(name, date, emp_id, times, record_count))

    print("检查工作日缺勤（零打卡）...")
    anomalies.extend(check_absence(df))

    if anomalies:
        result_df = pd.DataFrame(anomalies)
        result_df.to_excel(output_file, index=False)
        print(f"\n共发现 {len(anomalies)} 条异常记录")
        print(f"已保存到: {output_file}")
        print("\n异常记录预览:")
        print(result_df.head(10))
    else:
        print("\n未发现考勤异常")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="考勤异常检测（整月打卡全量扫描）")
    parser.add_argument("--input", default=INPUT_FILE, help="打卡记录文件")
    parser.add_argument("--output", default=OUTPUT_FILE, help="异常输出文件")
    args = parser.parse_args()
    analyze_attendance(args.input, args.output)
