"""以 app_icon_master.png 为唯一标准图，生成窗口与 exe 共用的图标。"""

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent
MASTER = ROOT / "app_icon_master.png"
PNG_PATH = ROOT / "app_icon.png"
ICO_PATH = ROOT / "app_icon.ico"
ICO_SIZES = [256, 128, 64, 48, 32, 16]


def _load_master() -> Image.Image:
    if not MASTER.exists():
        raise FileNotFoundError(
            f"缺少标准图标文件: {MASTER}\n"
            "请将你确认满意的图（图二）保存为该文件名。"
        )
    return Image.open(MASTER).convert("RGB")


def main() -> None:
    master = _load_master()
    if master.size != (1024, 1024):
        master = master.resize((1024, 1024), Image.Resampling.LANCZOS)

    master.save(PNG_PATH, format="PNG", optimize=True)

    icons = [
        master.resize((size, size), Image.Resampling.LANCZOS) for size in ICO_SIZES
    ]
    icons[0].save(ICO_PATH, format="ICO", sizes=[(s, s) for s in ICO_SIZES])

    print(f"标准图: {MASTER}")
    print(f"已生成: {PNG_PATH}")
    print(f"已生成: {ICO_PATH}")
    print("窗口图标与 exe 图标将使用同一套文件。")


if __name__ == "__main__":
    main()
