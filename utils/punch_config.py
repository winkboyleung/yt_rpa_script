"""打卡相关部门与员工名单配置。"""

FOUR_PUNCH_DEPARTMENTS = [
    "工程组",
    "乳化车间",
    "灌装车间",
    "工艺组（PIE）",
    "品保QC",
    "仓库",
]


def get_four_punch_employee_names(df):
    """从打卡表筛选 FOUR_PUNCH_DEPARTMENTS 部门下的员工姓名（去重）。"""
    if df is None or df.empty or "部门" not in df.columns or "姓名" not in df.columns:
        return set()
    mask = df["部门"].isin(FOUR_PUNCH_DEPARTMENTS)
    return set(df.loc[mask, "姓名"].dropna().astype(str).unique())
