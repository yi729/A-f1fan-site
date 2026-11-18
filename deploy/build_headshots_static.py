"""一次性脚本：生成 backend/headshots_static.json（2024/2025 官方头像映射）。

- 2025：直接解析 F1 官网 results/2025/drivers 页面里的官方头像 URL。
- 2024：官网历史页面不含图片，按「车队目录名 + 姓名编码」构造 CDN 地址，
  再逐一 HEAD 校验（404 时尝试同赛季其他车队目录，处理中途转队车手）。

用法: py build_headshots_static.py
"""
import json
import re
import threading
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

PROJ = Path(__file__).resolve().parent.parent
OUT = PROJ / "backend" / "headshots_static.json"

YEAR_SLUGS = {
    2024: ["mercedes", "ferrari", "mclaren", "redbullracing", "rb", "alpine",
           "haasf1team", "williams", "astonmartin", "kicksauber"],
}
# Jolpica constructorId -> 官网车队目录名（2024）
CONSTRUCTOR_SLUG = {
    "mercedes": "mercedes", "ferrari": "ferrari", "mclaren": "mclaren",
    "red_bull": "redbullracing", "rb": "rb", "alpine": "alpine",
    "haas": "haasf1team", "williams": "williams",
    "aston_martin": "astonmartin", "sauber": "kicksauber",
}

CDN = "https://media.formula1.com/image/upload/c_lfill,w_96/q_auto/v1740000001/common/f1"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) F1DataCenter/1.0"}


def norm(s):
    s = unicodedata.normalize("NFKD", str(s or ""))
    return "".join(ch for ch in s if ch.isascii() and ch.isalpha()).lower()


def f1_code(given, family):
    g = norm(given).split()
    f = norm(family).split()
    if not g or not f:
        return ""
    return g[0][:3] + f[0][:3] + "01"


def scrape_year(season):
    """解析官网当季/上季页面里的头像 URL（仅页面含图的赛季有效）。"""
    url = f"https://www.formula1.com/en/results/{season}/drivers"
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    urls = set(re.findall(
        r'https://media\.formula1\.com/image/upload/[^\s"\'<>]+\.webp', resp.text))
    out = {}
    for u in urls:
        m = re.search(
            rf"common/f1/{season}/([a-z0-9]+)/([a-z0-9]+)/{season}\1\2(right|left)\.webp", u)
        if not m:
            continue
        code, side = m.group(2), m.group(3)
        clean = re.sub(r"d_[^/]+/", "", u)          # 去掉占位剪影缺省图参数
        clean = re.sub(r"c_lfill,w_\d+", "c_lfill,w_96", clean)
        if code not in out or side == "right":
            out[code] = clean
    return out


def build_2024():
    """Jolpica 2024 积分榜 -> 构造地址 -> HEAD 校验。"""
    data = requests.get(
        "https://api.jolpi.ca/ergast/f1/2024/driverStandings.json",
        params={"limit": "100"}, headers=HEADERS, timeout=30,
    ).json()
    entries = []
    for s in data["MRData"]["StandingsTable"]["StandingsLists"][0]["DriverStandings"]:
        d, cs = s["Driver"], s.get("Constructors") or [{}]
        cid = cs[0].get("constructorId", "")
        code = f1_code(d.get("givenName", ""), d.get("familyName", ""))
        if code and cid in CONSTRUCTOR_SLUG:
            entries.append((code, CONSTRUCTOR_SLUG[cid]))
    out = {}

    def check(item):
        code, slug = item
        candidates = [slug] + [s for s in YEAR_SLUGS[2024] if s != slug]
        for cand in candidates:
            u = f"{CDN}/2024/{cand}/{code}/2024{cand}{code}right.webp"
            try:
                r = requests.head(u, headers=HEADERS, timeout=15)
                if r.status_code == 200:
                    return code, u
            except requests.exceptions.RequestException:
                pass
        return code, None

    with ThreadPoolExecutor(max_workers=8) as ex:
        for code, u in ex.map(check, entries):
            if u:
                out[code] = u
            else:
                print("  未找到 2024 头像:", code)
    return out


def main():
    static = {}
    print("解析官网 2025 页面 …")
    y2025 = scrape_year(2025)
    print("  2025 头像数:", len(y2025))
    static["2025"] = y2025
    print("构造并校验 2024 …")
    y2024 = build_2024()
    print("  2024 头像数:", len(y2024))
    static["2024"] = y2024
    OUT.write_text(json.dumps(static, ensure_ascii=False, indent=1), encoding="utf-8")
    print("写入:", OUT)


if __name__ == "__main__":
    main()
