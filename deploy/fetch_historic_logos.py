"""一次性脚本：下载 F1 官方 CDN 上 2019-2023 各赛季车队队徽。

旧版官网资源仍在 CDN：
https://media.formula1.com/image/upload/content/dam/fom-website/teams/{年}/{slug}-logo.png
（96x96 透明底 PNG；2018 及更早已被清除）

输出：frontend/assets/team-logos/h{年}-{slug}.png
"""
import os
import time
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "..", "frontend", "assets", "team-logos")

# 各赛季实际参赛车队 slug（对应官网目录名）
GRIDS = {
    2019: ["mercedes", "ferrari", "red-bull-racing", "mclaren", "renault",
           "racing-point", "toro-rosso", "alfa-romeo-racing", "haas-f1-team", "williams"],
    2020: ["mercedes", "ferrari", "red-bull-racing", "mclaren", "renault",
           "racing-point", "alphatauri", "alfa-romeo-racing", "haas-f1-team", "williams"],
    2021: ["mercedes", "ferrari", "red-bull-racing", "mclaren", "alpine",
           "aston-martin", "alphatauri", "alfa-romeo-racing", "haas-f1-team", "williams"],
    2022: ["mercedes", "ferrari", "red-bull-racing", "mclaren", "alpine",
           "aston-martin", "alphatauri", "alfa-romeo-racing", "haas-f1-team", "williams"],
    2023: ["mercedes", "ferrari", "red-bull-racing", "mclaren", "alpine",
           "aston-martin", "alphatauri", "alfa-romeo-racing", "haas-f1-team", "williams"],
}

BASE = ("https://media.formula1.com/image/upload/content/dam/fom-website/"
        "teams/{year}/{slug}-logo.png")


def main():
    os.makedirs(OUT, exist_ok=True)
    ok = fail = 0
    for year, slugs in GRIDS.items():
        for slug in slugs:
            url = BASE.format(year=year, slug=slug)
            dest = os.path.join(OUT, f"h{year}-{slug}.png")
            if os.path.exists(dest) and os.path.getsize(dest) > 0:
                print("skip:", os.path.basename(dest))
                ok += 1
                continue
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=20) as r:
                    data = r.read()
                if len(data) < 500:
                    raise RuntimeError(f"too small ({len(data)}B)")
                with open(dest, "wb") as f:
                    f.write(data)
                print("got :", os.path.basename(dest), f"{len(data)}B")
                ok += 1
            except Exception as exc:
                print("FAIL:", url, exc)
                fail += 1
            time.sleep(0.2)
    print(f"done: ok={ok} fail={fail}")


if __name__ == "__main__":
    main()
