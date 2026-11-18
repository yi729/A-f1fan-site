# -*- coding: utf-8 -*-
"""把 2026 赛季车队队徽下载到 frontend/assets/team-logos/（一次性脚本）。

raw.githubusercontent 在国内常不可达，这里走 api.github.com 的 contents
接口（base64）拉取。用法: py -X utf8 deploy/fetch_logos.py
"""
import base64
import json
import os
import sys
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

REPO = "teresakrchen/f1-team-logo-2026"
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend", "assets", "team-logos")

FILES = [
    "Alpine.avif", "Aston Martin.avif", "Audi.avif", "Cadillac.avif",
    "Ferrari.avif", "Haas.avif", "Mclaren.avif", "Mercedes.avif",
    "Racing Bull.avif", "Red Bull Racing.avif", "Williams.avif",
]


def get_json(url, timeout=30):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/vnd.github+json",
    })
    return json.load(urllib.request.urlopen(req, timeout=timeout))


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    for name in FILES:
        meta = get_json(f"https://api.github.com/repos/{REPO}/contents/{urllib.parse.quote(name)}")
        data = base64.b64decode(meta["content"])
        out = os.path.join(OUT_DIR, name)
        with open(out, "wb") as fh:
            fh.write(data)
        print(f"{name}: {len(data)} 字节 -> {out}")
    print("完成")


if __name__ == "__main__":
    main()
