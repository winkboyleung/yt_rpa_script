"""办公室工作日加班名单：默认值、读取与保存。"""

import json
import sys
from pathlib import Path

DEFAULT_OFFICE_OVERTIME_EMPLOYEES = (
    "莫淑兰",
    "许丽霞",
    "刘天梅",
    "朱颖",
    "梁海雯",
    "罗鼎成",
    "吴金娜",
    "杨丽娟",
    "梅宇轩",
    "周映文",
    "林芷珊",
    "王李婷",
    "陈燕兰",
)

CONFIG_FILENAME = "office_overtime_employees.json"


def config_file_path() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / CONFIG_FILENAME
    return Path(__file__).resolve().parent.parent / CONFIG_FILENAME


def parse_names_text(text: str) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for line in (text or "").splitlines():
        name = line.strip()
        if not name or name in seen:
            continue
        seen.add(name)
        names.append(name)
    return names


def names_to_text(names) -> str:
    return "\n".join(names)


def load_office_overtime_employees() -> list[str]:
    path = config_file_path()
    if not path.exists():
        return list(DEFAULT_OFFICE_OVERTIME_EMPLOYEES)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            names = [str(x).strip() for x in data if str(x).strip()]
            if names:
                return names
    except (OSError, json.JSONDecodeError, TypeError):
        pass
    return list(DEFAULT_OFFICE_OVERTIME_EMPLOYEES)


def save_office_overtime_employees(names) -> Path:
    path = config_file_path()
    cleaned = parse_names_text(names_to_text(names))
    path.write_text(
        json.dumps(cleaned, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path
