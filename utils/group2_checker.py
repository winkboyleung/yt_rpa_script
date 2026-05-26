from datetime import datetime, timedelta, time, date as date_type


def check_group2_attendance(name, date, emp_id, punch_times):
    """
    检查数组2员工的考勤异常情况（4次基本卡员工）
    
    参数:
        name: 员工姓名
        date: 日期（datetime.date对象）
        emp_id: 员工编号
        punch_times: 打卡时间列表（datetime.time对象列表，已排序）
    
    返回:
        list: 异常记录列表，每条记录是一个字典
    """
    anomalies = []
    record_count = len(punch_times)

    # 打卡次数 <= 2，视为夜班，忽略
    if record_count <= 2:
        return anomalies

    # 打卡次数 = 4 或 6，正常（可能无异常）
    # 打卡次数 = 3 或 5，必有缺卡
    # 其他次数，也需要检查

    # 将time对象转换为datetime对象（用于计算时间差）
    base_date = datetime.combine(date, time(0, 0, 0))
    punch_datetimes = sorted([datetime.combine(date, t) for t in punch_times])

    # 识别的卡片
    identified_cards = {
        '上午上班卡': None,
        '上午下班卡': None,
        '下午上班卡': None,
        '下午下班卡': None,
        '加班上班卡': None,
        '加班下班卡': None
    }

    # 时间定义
    morning_end = base_date.replace(hour=9, minute=0)
    noon_start = base_date.replace(hour=11, minute=0)
    noon_end = base_date.replace(hour=13, minute=30)
    evening_start = base_date.replace(hour=17, minute=30)
    evening_end = base_date.replace(hour=19, minute=35)
    overtime_threshold = base_date.replace(hour=19, minute=36)

    # 开始识别每张卡
    used_indices = set()

    # 1. 识别上午上班卡（第一张卡，<= 9:00）
    if len(punch_datetimes) > 0 and punch_datetimes[0] <= morning_end:
        identified_cards['上午上班卡'] = punch_datetimes[0]
        used_indices.add(0)

    # 2. 识别上午下班卡（11:00-13:00）
    for i, pt in enumerate(punch_datetimes):
        if i not in used_indices and noon_start <= pt <= noon_end:
            identified_cards['上午下班卡'] = pt
            used_indices.add(i)
            break

    # 3. 识别下午上班卡（上午下班卡后1小时内）
    if identified_cards['上午下班卡']:
        noon_off = identified_cards['上午下班卡']
        afternoon_on_deadline = noon_off + timedelta(minutes=61)

        for i, pt in enumerate(punch_datetimes):
            if i not in used_indices and noon_off < pt <= afternoon_on_deadline:
                identified_cards['下午上班卡'] = pt
                used_indices.add(i)
                break

    # 4. 识别下午下班卡（17:30-18:30）
    for i, pt in enumerate(punch_datetimes):
        if i not in used_indices and evening_start <= pt <= evening_end:
            identified_cards['下午下班卡'] = pt
            used_indices.add(i)
            break

    # 5. 识别加班上班卡（下午下班卡后1小时内）
    if identified_cards['下午下班卡']:
        evening_off = identified_cards['下午下班卡']
        overtime_on_deadline = evening_off + timedelta(hours=1)

        for i, pt in enumerate(punch_datetimes):
            if i not in used_indices and evening_off < pt <= overtime_on_deadline:
                identified_cards['加班上班卡'] = pt
                used_indices.add(i)
                break

    # 6. 识别加班下班卡（>19:00）
    for i, pt in enumerate(punch_datetimes):
        if i not in used_indices and pt > overtime_threshold:
            identified_cards['加班下班卡'] = pt
            used_indices.add(i)
            break

    # 判断是否有加班
    has_overtime = (identified_cards['加班下班卡'] is not None) or (identified_cards['加班上班卡'] is not None)

    # 确定应有的卡片
    if has_overtime:
        required_cards = ['上午上班卡', '上午下班卡', '下午上班卡', '下午下班卡', '加班上班卡', '加班下班卡']
    else:
        required_cards = ['上午上班卡', '上午下班卡', '下午上班卡', '下午下班卡']

    # 找出缺失的卡片并记录
    for card in required_cards:
        if identified_cards[card] is None:
            # 使用第一次打卡时间作为记录时间
            first_time = punch_times[0] if punch_times else time(0, 0)
            
            anomalies.append({
                '姓名': name,
                '日期': date,
                '编号': emp_id,
                '打卡时间': str(first_time),
                '考勤异常情况': f'无打{card}'
            })
    
    return anomalies


if __name__ == "__main__":
    # 测试用例
    test_cases = [
        {
            'name': '陈章明 4.27',
            'date': '2026-4-27',
            'emp_id': 'EMP001',
            'times': ["2026-4-27 08:08", "2026-4-27 12:00", "2026-4-27 12:14", 
                      "2026-4-27 17:30", "2026-4-27 17:57", "2026-4-27 19:33"]
        },
    ]

    for test in test_cases:
        print(f"\n{'#' * 60}")
        print(f"# {test['name']}")
        print(f"{'#' * 60}")
        
        # 解析日期
        test_date = datetime.strptime(test['date'], '%Y-%m-%d').date()
        
        # 解析打卡时间（转换为 time 对象）
        punch_times = [datetime.strptime(t, '%Y-%m-%d %H:%M').time() for t in test['times']]
        
        # 调用函数
        result = check_group2_attendance(test['name'], test_date, test['emp_id'], punch_times)
        
        # 打印结果
        print(f"\n打卡时间: {test['times']}")
        if result:
            print(f"\n发现 {len(result)} 条异常:")
            for anomaly in result:
                print(f"  - {anomaly['考勤异常情况']}")
        else:
            print("\n✓ 无考勤异常")
        print(f"{'#' * 60}\n")
