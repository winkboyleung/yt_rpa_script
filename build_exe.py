"""在 PyCharm 中右键运行本文件即可打包 exe；成功后自动删除 .spec 文件。"""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENTRY = "attendance_app.py"
NAME = "亚拓考勤统计模块"
ICON_FILE = ROOT / "app_icon.ico"
SPEC_FILE = ROOT / f"{NAME}.spec"


def run(cmd: list[str]) -> None:
    print(f"> {' '.join(cmd)}")
    subprocess.run(cmd, cwd=ROOT, check=True)


def main() -> None:
    print("== 安装依赖 ==")
    run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])

    icon_builder = ROOT / "build_app_icon.py"
    if icon_builder.exists():
        print("\n== 生成高清图标 ==")
        run([sys.executable, str(icon_builder)])

    print("\n== 开始打包 ==")
    pyinstaller_cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--windowed",
        "--name",
        NAME,
    ]
    if ICON_FILE.exists():
        pyinstaller_cmd.extend(["--icon", str(ICON_FILE)])
        pyinstaller_cmd.extend(["--add-data", f"{ICON_FILE}{os.pathsep}."])
    png_icon = ROOT / "app_icon.png"
    if png_icon.exists():
        pyinstaller_cmd.extend(["--add-data", f"{png_icon}{os.pathsep}."])
    pyinstaller_cmd.append(ENTRY)
    run(pyinstaller_cmd)

    if SPEC_FILE.exists():
        SPEC_FILE.unlink()
        print(f"\n已删除 {SPEC_FILE.name}")

    exe_path = ROOT / "dist" / f"{NAME}.exe"
    print(f"\n打包完成: {exe_path}")


if __name__ == "__main__":
    main()
