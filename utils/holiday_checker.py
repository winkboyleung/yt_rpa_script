import datetime
import chinese_calendar as calendar

def is_holiday_or_weekend(date):
    """
    判断指定日期是否为法定节假日或周末
    
    参数:
        date: datetime.date对象
    
    返回:
        bool: True表示是节假日或周末，False表示是工作日
    """
    return calendar.is_holiday(date)

def get_overtime_missing_card_type(date):
    """获取节假日/周末缺卡异常类型，节假日优先。"""
    if get_holiday_name(date):
        return '节假日加班缺卡'
    if is_holiday_or_weekend(date):
        return '周末加班缺卡'
    return None

def is_workday(date):
    """
    判断指定日期是否为工作日
    
    参数:
        date: datetime.date对象
    
    返回:
        bool: True表示是工作日，False表示是节假日或周末
    """
    return calendar.is_workday(date)

def get_holiday_name(date):
    """
    获取指定日期的节假日名称
    
    参数:
        date: datetime.date对象
    
    返回:
        str: 节假日名称，如果不是节假日则返回None
    """
    try:
        detail = calendar.get_holiday_detail(date)
        return detail[1] if detail else None
    except:
        return None
