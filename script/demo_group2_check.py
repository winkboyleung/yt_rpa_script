from datetime import datetime, timedelta


def analyze_group2_punches(punch_times_str):
    """
    分析数组2员工的打卡情况
    
    参数:
        punch_times_str: 打卡时间字符串列表，如 ["2026-4-18 08:12", "2026-4-18 12:17", ...]
    
    返回:
        dict: 包含识别的卡片类型和缺失的卡片
    """
    # 将字符串转换为datetime对象并排序
    punch_times = sorted([datetime.strptime(t.strip(), "%Y-%m-%d %H:%M") for t in punch_times_str])

    print(f"\n{'=' * 60}")
    print(f"分析打卡记录（共{len(punch_times)}次）:")
    for i, pt in enumerate(punch_times, 1):
        print(f"  第{i}次: {pt.strftime('%Y-%m-%d %H:%M:%S')} ({pt.strftime('%A')})")
    print(f"{'=' * 60}\n")

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
    morning_start = punch_times[0].replace(hour=8, minute=0, second=0)
    morning_end = punch_times[0].replace(hour=9, minute=0, second=0)
    noon_start = punch_times[0].replace(hour=11, minute=0, second=0)
    noon_end = punch_times[0].replace(hour=13, minute=0, second=0)
    evening_start = punch_times[0].replace(hour=17, minute=30, second=0)
    evening_end = punch_times[0].replace(hour=18, minute=30, second=0)
    overtime_threshold = punch_times[0].replace(hour=19, minute=0, second=0)

    # 开始识别每张卡
    used_indices = set()

    # 1. 识别上午上班卡（第一张卡，8:00-9:00）
    if len(punch_times) > 0 and punch_times[0] <= morning_end:
        identified_cards['上午上班卡'] = punch_times[0]
        used_indices.add(0)
        print(f"✓ 识别到上午上班卡: {punch_times[0].strftime('%H:%M:%S')}")

    # 2. 识别上午下班卡（11:00-13:00）
    for i, pt in enumerate(punch_times):
        if i not in used_indices and noon_start <= pt <= noon_end:
            identified_cards['上午下班卡'] = pt
            used_indices.add(i)
            print(f"✓ 识别到上午下班卡: {pt.strftime('%H:%M:%S')}")
            break

    # 3. 识别下午上班卡（上午下班卡后1小时内）
    if identified_cards['上午下班卡']:
        noon_off = identified_cards['上午下班卡']
        afternoon_on_deadline = noon_off + timedelta(hours=1)

        for i, pt in enumerate(punch_times):
            if i not in used_indices and noon_off < pt <= afternoon_on_deadline:
                identified_cards['下午上班卡'] = pt
                used_indices.add(i)
                time_diff = (pt - noon_off).total_seconds() / 60
                print(f"✓ 识别到下午上班卡: {pt.strftime('%H:%M:%S')} (距上午下班卡{time_diff:.0f}分钟)")
                break

    # 4. 识别下午下班卡（17:30-18:30）
    for i, pt in enumerate(punch_times):
        if i not in used_indices and evening_start <= pt <= evening_end:
            identified_cards['下午下班卡'] = pt
            used_indices.add(i)
            print(f"✓ 识别到下午下班卡: {pt.strftime('%H:%M:%S')}")
            break

    # 5. 识别加班上班卡（下午下班卡后1小时内）
    if identified_cards['下午下班卡']:
        evening_off = identified_cards['下午下班卡']
        overtime_on_deadline = evening_off + timedelta(hours=1)

        for i, pt in enumerate(punch_times):
            if i not in used_indices and evening_off < pt <= overtime_on_deadline:
                identified_cards['加班上班卡'] = pt
                used_indices.add(i)
                time_diff = (pt - evening_off).total_seconds() / 60
                print(f"✓ 识别到加班上班卡: {pt.strftime('%H:%M:%S')} (距下午下班卡{time_diff:.0f}分钟)")
                break

    # 6. 识别加班下班卡（>19:00）
    for i, pt in enumerate(punch_times):
        if i not in used_indices and pt > overtime_threshold:
            identified_cards['加班下班卡'] = pt
            used_indices.add(i)
            print(f"✓ 识别到加班下班卡: {pt.strftime('%H:%M:%S')}")
            break

    # 判断是否有加班
    has_overtime = (identified_cards['加班下班卡'] is not None) or (identified_cards['加班上班卡'] is not None)

    print(f"\n{'=' * 60}")
    print(f"加班判断: {'有加班' if has_overtime else '无加班'}")
    print(f"{'=' * 60}\n")

    # 确定应有的卡片
    if has_overtime:
        required_cards = ['上午上班卡', '上午下班卡', '下午上班卡', '下午下班卡', '加班上班卡', '加班下班卡']
    else:
        required_cards = ['上午上班卡', '上午下班卡', '下午上班卡', '下午下班卡']

    # 找出缺失的卡片
    missing_cards = []
    for card in required_cards:
        if identified_cards[card] is None:
            missing_cards.append(f"无打{card}")

    # 打印结果
    print("识别结果:")
    print("-" * 60)
    for card in required_cards:
        status = f"✓ {identified_cards[card].strftime('%H:%M:%S')}" if identified_cards[card] else "✗ 缺失"
        print(f"  {card}: {status}")

    if missing_cards:
        print(f"\n缺卡情况:")
        for missing in missing_cards:
            print(f"  ⚠️  {missing}")
    else:
        print(f"\n✓ 无缺卡")

    print(f"{'=' * 60}\n")

    return {
        'identified_cards': identified_cards,
        'has_overtime': has_overtime,
        'missing_cards': missing_cards,
        'required_cards': required_cards
    }


if __name__ == "__main__":
    # 测试用例
    test_cases = [
        {
            'name': '王思杰 4.18',
            'times': ["2026-4-18 08:12", "2026-4-18 12:17", "2026-4-18 13:07", "2026-4-18 22:06"]
        },
        {
            'name': '王思杰 4.29',
            'times': ["2026-4-29 07:57", "2026-4-29 18:13", "2026-4-29 18:35", "2026-4-29 21:14"]
        },
        {
            'name': '苏华 4.30',
            'times': ["2026-4-30 08:22", "2026-4-30 12:08", "2026-4-30 12:30", "2026-4-30 20:01"]
        },
        {
            'name': '苏华 4.26',
            'times': ["2026-4-26 08:20", "2026-4-26 12:01", "2026-4-26 12:52", "2026-4-26 20:02"]
        },
        {
            'name': '苏华 4.27',
            'times': ["2026-4-27 08:30", "2026-4-27 12:03", "2026-4-27 17:33", "2026-4-27 17:53", "2026-4-27 21:05"]
        },
        {
            'name': '王思杰 4.26',
            'times': ["2026-4-26 12:05","2026-4-26 18:08","2026-4-26 18:19","2026-4-26 20:08"]
        },

    ]

    for test in test_cases:
        print(f"\n{'#' * 60}")
        print(f"# {test['name']}")
        print(f"{'#' * 60}")
        result = analyze_group2_punches(test['times'])
