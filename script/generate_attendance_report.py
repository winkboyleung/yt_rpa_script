import pandas as pd
from datetime import datetime
from openpyxl import Workbook
from openpyxl.styles import PatternFill, Alignment, Font, Border, Side
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.holiday_checker import is_holiday_or_weekend, is_workday

# 文件路径
PUNCH_FILE = "/Applications/ramsey_leung_files/all_files_from_redmi/yt_rpa_script/files/4月办公室打卡.xls"
ANOMALY_FILE = "/Applications/ramsey_leung_files/all_files_from_redmi/yt_rpa_script/files/四月打卡异常.xlsx"
OUTPUT_DIR = "/Applications/ramsey_leung_files/all_files_from_redmi/yt_rpa_script/files"


def generate_attendance_report():
    """生成考勤统计表"""
    
    # 读取原始打卡数据
    try:
        punch_df = pd.read_excel(PUNCH_FILE, engine='xlrd')
    except:
        try:
            punch_df = pd.read_excel(PUNCH_FILE, engine='openpyxl')
        except Exception as e:
            print(f"读取打卡文件失败: {e}")
            return
    
    punch_df['日期时间'] = pd.to_datetime(punch_df['日期时间'])
    punch_df['日期'] = punch_df['日期时间'].dt.date
    
    # 读取异常记录（如果文件不存在或读取失败，创建空DataFrame）
    anomaly_df = pd.DataFrame()
    if os.path.exists(ANOMALY_FILE):
        try:
            anomaly_df = pd.read_excel(ANOMALY_FILE)
            anomaly_df['日期'] = pd.to_datetime(anomaly_df['日期']).dt.date
        except Exception as e:
            print(f"读取异常文件失败（将继续生成不含异常标记的表格）: {e}")
    else:
        print(f"异常文件不存在: {ANOMALY_FILE}，将生成不含异常标记的表格")
    
    # 获取日期范围和员工列表
    start_date = punch_df['日期'].min()
    end_date = punch_df['日期'].max()
    month = start_date.month
    year = start_date.year
    days_in_month = pd.Period(f'{year}-{month}').days_in_month
    
    employees = punch_df[['姓名', '编号']].drop_duplicates()
    
    # 计算工作日和休息日
    workdays = sum(1 for day in range(1, days_in_month + 1) 
                   if is_workday(datetime(year, month, day).date()))
    rest_days = days_in_month - workdays
    
    # 创建工作簿
    wb = Workbook()
    ws = wb.active
    ws.title = f"{month}月"
    
    # 设置列宽
    ws.column_dimensions['A'].width = 5
    ws.column_dimensions['B'].width = 10
    ws.column_dimensions['C'].width = 10
    # 设置日期列宽度（D到AH列，共31列）
    date_cols = ['D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N', 'O', 'P', 'Q', 'R', 'S', 'T', 'U', 'V', 'W', 'X', 'Y', 'Z',
                 'AA', 'AB', 'AC', 'AD', 'AE', 'AF', 'AG', 'AH']
    for col in date_cols:
        ws.column_dimensions[col].width = 4
    
    # 样式定义
    gray_fill = PatternFill(start_color="FFF2CC", end_color="FFF2CC", fill_type="solid")  # 浅米色阴影
    center_align = Alignment(horizontal='center', vertical='center', wrap_text=True)
    thin_border = Border(
        left=Side(style='thin'),
        right=Side(style='thin'),
        top=Side(style='thin'),
        bottom=Side(style='thin')
    )
    title_font = Font(name='黑体', size=18, bold=True)
    normal_font = Font(name='宋体', size=10)
    header_font = Font(name='宋体', size=11)
    
    # 第1行：大标题
    ws.merge_cells('A1:AH1')
    ws['A1'] = f"{year}年{month}月份考勤确认表"
    ws['A1'].font = title_font
    ws['A1'].alignment = center_align
    ws.row_dimensions[1].height = 30
    
    # 第2行：单位信息（不合并，手动分三段）
    ws['A2'] = "单位:珠海亚拓生物科技有限公司"
    ws['A2'].font = header_font
    ws['A2'].alignment = Alignment(horizontal='left', vertical='center')
    
    ws.merge_cells('K2:R2')
    ws['K2'] = f"全勤天数{workdays}天，休{rest_days}天"
    ws['K2'].font = header_font
    ws['K2'].alignment = center_align
    
    ws.merge_cells('X2:AH2')
    ws['X2'] = "注：阴影部份为周六日出勤情况"
    ws['X2'].font = header_font
    ws['X2'].alignment = Alignment(horizontal='right', vertical='center')
    
    ws.row_dimensions[2].height = 20
    
    # 第3-4行：表头
    ws.merge_cells('A3:A4')
    ws['A3'] = "序号"
    ws['A3'].alignment = center_align
    ws['A3'].font = header_font
    ws['A3'].border = thin_border
    
    ws.merge_cells('B3:B4')
    ws['B3'] = "姓名"
    ws['B3'].alignment = center_align
    ws['B3'].font = header_font
    ws['B3'].border = thin_border
    
    ws.merge_cells('C3:C4')
    ws['C3'] = ""
    ws['C3'].border = thin_border
    
    ws.row_dimensions[3].height = 25
    ws.row_dimensions[4].height = 25
    
    # 写入日期列（1-31），从D列开始
    for day in range(1, days_in_month + 1):
        col_idx = 3 + day  # D列是第4列
        ws.merge_cells(start_row=3, start_column=col_idx, end_row=4, end_column=col_idx)
        cell = ws.cell(3, col_idx, day)
        cell.alignment = center_align
        cell.font = normal_font
        cell.border = thin_border
        
        # 节假日/周末加阴影
        date = datetime(year, month, day).date()
        if is_holiday_or_weekend(date):
            cell.fill = gray_fill
    
    # 填充员工数据，从第5行开始
    current_row = 5
    seq_num = 1
    
    for _, emp_row in employees.iterrows():
        name = emp_row['姓名']
        emp_id = emp_row['编号']
        
        # 获取该员工的打卡日期
        emp_punch_dates = set(punch_df[punch_df['姓名'] == name]['日期'])
        
        # 获取该员工的异常记录
        emp_anomalies = {}
        if not anomaly_df.empty:
            emp_anomaly_records = anomaly_df[anomaly_df['姓名'] == name]
            for _, anomaly in emp_anomaly_records.iterrows():
                date = anomaly['日期']
                if date not in emp_anomalies:
                    emp_anomalies[date] = []
                emp_anomalies[date].append(anomaly['考勤异常情况'])
        
        # 设置行高
        ws.row_dimensions[current_row].height = 20
        ws.row_dimensions[current_row + 1].height = 20
        
        # 序号（跨两行）
        ws.merge_cells(start_row=current_row, start_column=1, end_row=current_row+1, end_column=1)
        cell_seq = ws.cell(current_row, 1, seq_num)
        cell_seq.alignment = center_align
        cell_seq.font = normal_font
        cell_seq.border = thin_border
        
        # 姓名（跨两行）
        ws.merge_cells(start_row=current_row, start_column=2, end_row=current_row+1, end_column=2)
        cell_name = ws.cell(current_row, 2, name)
        cell_name.alignment = center_align
        cell_name.font = normal_font
        cell_name.border = thin_border
        
        # 第1行：正常出勤
        cell_label = ws.cell(current_row, 3, "正常出勤")
        cell_label.alignment = center_align
        cell_label.font = normal_font
        cell_label.border = thin_border
        
        # 填充每日考勤，从D列开始
        for day in range(1, days_in_month + 1):
            col_idx = 3 + day
            date = datetime(year, month, day).date()
            
            cell = ws.cell(current_row, col_idx)
            cell.font = normal_font
            cell.border = thin_border
            cell.alignment = center_align
            
            # 节假日/周末加阴影
            if is_holiday_or_weekend(date):
                cell.fill = gray_fill
            
            # 判断是否有异常
            if date in emp_anomalies:
                # 如果异常类型包含"缺勤"，显示"缺勤"
                if any('缺勤' in a for a in emp_anomalies[date]):
                    cell.value = "缺"
                else:
                    cell.value = "异"
            elif date in emp_punch_dates:
                cell.value = "√"
            elif is_workday(date):
                # 工作日无打卡=缺勤
                cell.value = "缺"
        
        # 第2行：加班工时
        current_row += 1
        cell_label2 = ws.cell(current_row, 3, "加班工时")
        cell_label2.alignment = center_align
        cell_label2.font = normal_font
        cell_label2.border = thin_border
        
        # 加班工时行的日期单元格也要加阴影
        for day in range(1, days_in_month + 1):
            col_idx = 3 + day
            date = datetime(year, month, day).date()
            cell = ws.cell(current_row, col_idx)
            cell.font = normal_font
            cell.border = thin_border
            cell.alignment = center_align
            if is_holiday_or_weekend(date):
                cell.fill = gray_fill
        
        current_row += 1
        seq_num += 1
    
    # 保存文件
    output_file = os.path.join(OUTPUT_DIR, f"{month}月考勤统计.xlsx")
    wb.save(output_file)
    print(f"考勤统计表已生成: {output_file}")
    print(f"共处理 {len(employees)} 名员工")


if __name__ == "__main__":
    generate_attendance_report()
