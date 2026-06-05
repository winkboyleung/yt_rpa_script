"""打卡相关部门与员工名单配置。"""

FOUR_PUNCH_DEPARTMENTS = [
    "工程组",
    "乳化车间",
    "灌装车间",
    "工艺组（PIE）",
    "品保QC",
    "仓库",
]

# 部门属四次卡，但个人按「每天两次卡」规则（与办公室多数人一致）
TWO_PUNCH_OVERRIDE_NAMES = frozenset({
    "黄兴红",
    "潘玉玲",
    "吴锦乐"
})

# 工作日默认出勤√，不参与打卡异常与工时计算
AUTO_WORKDAY_PRESENT_NAMES = frozenset({
    "迟金龙",
    "肖蓉",
    "李红兰",
})


def get_four_punch_employee_names(df):
    """从打卡表筛选 FOUR_PUNCH_DEPARTMENTS 部门下的员工姓名（去重），排除两次卡特例。"""
    if df is None or df.empty or "部门" not in df.columns or "姓名" not in df.columns:
        return set()
    mask = df["部门"].isin(FOUR_PUNCH_DEPARTMENTS)
    names = set(df.loc[mask, "姓名"].dropna().astype(str).str.strip().unique())
    return names - set(TWO_PUNCH_OVERRIDE_NAMES)


def uses_two_punch_override(name):
    """是否按两次卡规则（不进四次卡 / 跨日夜班部门逻辑）。"""
    if name is None:
        return False
    return str(name).strip() in TWO_PUNCH_OVERRIDE_NAMES


def is_auto_workday_present(name):
    """是否工作日默认打勾、不计算考勤与加班。"""
    if name is None:
        return False
    return str(name).strip() in AUTO_WORKDAY_PRESENT_NAMES
