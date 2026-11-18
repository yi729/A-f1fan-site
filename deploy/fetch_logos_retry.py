# 一次性脚本：在 ECS 上运行
# 已知确切文件名(Jordan/DBpedia/探测结果),经 wsrv.nl 代理带退避重试下载
import hashlib
import json
import os
import time
import urllib.request
import urllib.parse

UA = "curl/8"
OUT = "/tmp/oldlogos2"
os.makedirs(OUT, exist_ok=True)

# 目标文件名: (输出名, 维基文件名, 首选repo顺序)
TARGETS = [
    ("jordan", "Jordan Grand Prix logo.png", ["en", "commons"]),
    ("benetton", "Benetton Formula logo.jpg", ["en", "commons"]),
    ("benetton", "Benetton Formula logo.png", ["en", "commons"]),  # 备选
    ("prost", "Prost Grand Prix Formula One Logo.png", ["en", "commons"]),
    ("super_aguri", "SuperAguri logo.svg", ["en", "commons"]),
    ("brawn", "Brawn GP logo.svg", ["en", "commons"]),
    ("hrt", "HRT F1 TEAM 2012.svg", ["en", "commons"]),
    ("caterham", "Caterham F1 Team logo.svg", ["en", "commons"]),
    ("toro_rosso", "Scuderia Toro Rosso logo.svg", ["en", "commons"]),
    ("mercedes", "Mercedes-Benz in Formula One logo.svg", ["en", "commons"]),
    ("red_bull", "Red bull racing.png", ["en", "commons"]),
    ("red_bull", "Red Bull Racing logo.svg", ["en", "commons"]),  # 备选
    ("toyota", "Panasonic Toyota Racing logo.png", ["en", "commons"]),
    ("toyota", "Toyota F1 logo.png", ["en", "commons"]),  # 备选
    ("bmw_sauber", "BMW Sauber logo.svg", ["en", "commons"]),
    ("bmw_sauber", "BMW Sauber logo.png", ["en", "commons"]),  # 备选
    ("renault_2000s", "Renault F1 Team logo 2016.svg", ["en", "commons"]),
    ("renault_2000s", "Renault F1 logo.png", ["en", "commons"]),  # 备选
    ("sauber_2000s", "Sauber logo.svg", ["en", "commons"]),
    ("sauber_2000s", "Sauber Petronas logo.png", ["en", "commons"]),  # 备选
    ("williams_2000s", "WilliamsF1 logo.png", ["en", "commons"]),
    ("williams_2000s", "Williams F1 logo.svg", ["en", "commons"]),  # 备选
    ("mclaren_2000s", "McLaren Racing logo.svg", ["en", "commons"]),
    ("lotus_f1", "Lotus F1 Team logo.svg", ["en", "commons"]),
    ("lotus_f1", "Lotus Renault GP logo.svg", ["en", "commons"]),  # 备选
    ("lotus_racing", "Team Lotus logo.svg", ["en", "commons"]),
    ("lotus_racing", "Lotus Racing logo.png", ["en", "commons"]),  # 备选
    ("marussia", "Marussia F1 Team logo.svg", ["en", "commons"]),
    ("marussia", "Marussia logo.svg", ["en", "commons"]),  # 备选
    ("manor", "Manor Marussia F1 Team logo.png", ["en", "commons"]),
    ("manor", "Manor Racing logo.png", ["en", "commons"]),  # 备选
    ("hrt", "HRT F1 Team logo.png", ["en", "commons"]),  # 备选
]

done = set()


def try_download(fn, repos, retries=4):
    fn_u = fn.replace(" ", "_")
    h = hashlib.md5(fn_u.encode("utf-8")).hexdigest()
    ext = ".svg" if fn_u.lower().endswith(".svg") else (
        ".jpg" if fn_u.lower().endswith((".jpg", ".jpeg")) else ".png")
    for repo in repos:
        up = f"https://upload.wikimedia.org/wikipedia/{repo}/{h[0]}/{h[:2]}/{urllib.parse.quote(fn_u)}"
        proxied = "https://wsrv.nl/?url=" + urllib.parse.quote(up, safe="")
        for attempt in range(retries):
            try:
                req = urllib.request.Request(proxied, headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=40) as r:
                    data = r.read()
                    ctype = r.headers.get("Content-Type", "")
                if ctype.startswith("image") and len(data) > 800:
                    return data, ext, repo
                break  # 非 429 类错误,不重试
            except urllib.error.HTTPError as e:
                body = e.read()[:100]
                if b"429" in body or e.code == 429:
                    time.sleep(8 + attempt * 10)  # 429 退避
                    continue
                break
            except Exception:
                time.sleep(3)
                continue
    return None, None, None


for cid, fn, repos in TARGETS:
    if cid in done:
        continue
    data, ext, repo = try_download(fn, repos)
    if data:
        with open(os.path.join(OUT, f"{cid}{ext}"), "wb") as f:
            f.write(data)
        done.add(cid)
        print(f"HIT  {cid:16s} {fn}  [{repo}] {len(data)}B")
    else:
        print(f"MISS {cid:16s} {fn}")
    time.sleep(2)  # 请求间隔,避免限流

print("\ndone:", sorted(done))
print("still missing:", sorted({t[0] for t in TARGETS} - done))
