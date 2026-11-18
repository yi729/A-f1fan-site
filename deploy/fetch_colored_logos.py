"""下载 F1 官方 2026 彩色队徽（media.formula1.com，国内可访问）并转 PNG。

用法: py fetch_colored_logos.py
输出: frontend/assets/team-logos/*.png（替换旧的单色 AVIF）
"""
import os
from pathlib import Path

import requests
from PIL import Image

PROJ = Path(__file__).resolve().parent.parent
OUT = PROJ / "frontend" / "assets" / "team-logos"
CDN = "https://media.formula1.com/image/upload/q_auto/v1740000001/common/f1/2026"

# cdn 目录名 -> 本地文件名
TEAMS = {
    "mercedes": "mercedes",
    "ferrari": "ferrari",
    "mclaren": "mclaren",
    "redbullracing": "red_bull",
    "racingbulls": "rb",
    "alpine": "alpine",
    "haasf1team": "haas",
    "audi": "audi",
    "williams": "williams",
    "astonmartin": "aston_martin",
    "cadillac": "cadillac",
}

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) F1DataCenter/1.0"}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    # 清理旧的单色 AVIF
    for old in OUT.glob("*.avif"):
        old.unlink()
        print("删除旧文件:", old.name)
    for cdn_name, local_name in TEAMS.items():
        url = f"{CDN}/{cdn_name}/2026{cdn_name}logo.webp"
        print("下载:", url)
        r = requests.get(url, headers=HEADERS, timeout=30)
        r.raise_for_status()
        tmp = OUT / f"{local_name}.webp"
        tmp.write_bytes(r.content)
        im = Image.open(tmp).convert("RGBA")
        png = OUT / f"{local_name}.png"
        im.save(png)
        tmp.unlink()
        print("  ->", png.name, im.size)


if __name__ == "__main__":
    main()
