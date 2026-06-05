"""在 PyCharm 中右键运行本文件即可打包 exe；成功后自动删除 .spec 文件。"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENTRY = "attendance_app.py"
NAME = "attendance_app"
SPEC_FILE = ROOT / f"{NAME}.spec"


def run(cmd: list[str]) -> None:
    print(f"> {' '.join(cmd)}")
    subprocess.run(cmd, cwd=ROOT, check=True)


def main() -> None:
    print("== 安装依赖 ==")
    run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])

    print("\n== 开始打包 ==")
    run([
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--windowed",
        "--name",
        NAME,
        ENTRY,
    ])

    if SPEC_FILE.exists():
        SPEC_FILE.unlink()
        print(f"\n已删除 {SPEC_FILE.name}")

    exe_path = ROOT / "dist" / f"{NAME}.exe"
    print(f"\n打包完成: {exe_path}")


if __name__ == "__main__":
    main()
