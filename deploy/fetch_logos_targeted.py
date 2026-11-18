# 一次性脚本：在 ECS 上运行
# 定向下载:已知确切文件名,Photon 直下;SVG 走维基 thumb 渲染 PNG;另查 DBpedia foaf:depiction 补漏
import hashlib
import json
import os
import time
import urllib.request
import urllib.parse

OUT = "/tmp/oldlogos3"
os.makedirs(OUT, exist_ok=True)
# 清掉之前的错图
for f in ("jordan.jpg", "brawn.jpg", "toro_rosso.jpg", "renault_2000s.jpg",
          "lotus_racing.jpg", "sauber_2000s.png", "jaguar.png"):
    p = os.path.join(OUT, f)
    if os.path.exists(p):
        os.remove(p)

PHOTON = ["i0.wp.com", "i1.wp.com", "i2.wp.com"]


def paths(fn, repo):
    fn_u = fn.replace(" ", "_")
    h = hashlib.md5(fn_u.encode("utf-8")).hexdigest()
    base = f"upload.wikimedia.org/wikipedia/{repo}/{h[0]}/{h[:2]}/{urllib.parse.quote(fn_u)}"
    out = [base]
    if fn_u.lower().endswith(".svg"):
        out.insert(0, f"upload.wikimedia.org/wikipedia/{repo}/thumb/{h[0]}/{h[:2]}/"
                      f"{urllib.parse.quote(fn_u)}/480px-{urllib.parse.quote(fn_u)}.png")
    return out


def fetch(url_path):
    for ph in PHOTON:
        try:
            req = urllib.request.Request(f"https://{ph}/{url_path}", headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=25) as r:
                data = r.read()
            if len(data) > 800:
                return data, ph
        except Exception:
            continue
    return None, None


# (cid, 文件名, repos)
TARGETS = [
    ("jordan", "Jordan Grand Prix logo.png", ["en", "commons"]),
    ("brawn", "Brawn GP logo.svg", ["en", "commons"]),
    ("hrt", "HRT F1 TEAM 2012.svg", ["en", "commons"]),
    ("caterham", "Caterham F1 Team logo.svg", ["en", "commons"]),
    ("super_aguri", "SuperAguri logo.svg", ["en", "commons"]),
    ("toro_rosso", "Scuderia Toro Rosso logo.svg", ["en", "commons"]),
    ("bmw_sauber", "BMW Sauber logo.svg", ["en", "commons"]),
    ("marussia", "Marussia F1 Team logo.svg", ["en", "commons"]),
    ("toyota", "Panasonic Toyota Racing logo.png", ["en", "commons"]),
    ("toyota", "Toyota F1 logo.png", ["en", "commons"]),
    ("sauber_2000s", "Sauber logo.svg", ["en", "commons"]),
    ("sauber_2000s", "Sauber Petronas logo.png", ["en", "commons"]),
    ("jaguar", "Jaguar Racing logo.png", ["en", "commons"]),
    ("jaguar", "Jaguar Racing logo.svg", ["en", "commons"]),
    ("williams_2000s", "WilliamsF1 logo.png", ["en", "commons"]),
    ("williams_2000s", "AT&T Williams logo.png", ["en", "commons"]),
    ("red_bull_2010s", "Red bull racing.png", ["en", "commons"]),
    ("renault_2000s", "Renault F1 logo.png", ["en", "commons"]),
    ("renault_2000s", "Renault F1 Team logo 2016.svg", ["en", "commons"]),
]

got = {}
for cid, fn, repos in TARGETS:
    if cid in got:
        continue
    for repo in repos:
        for up in paths(fn, repo):
            data, ph = fetch(up)
            if data:
                ext = ".png" if up.endswith(".png") else (".svg" if up.endswith(".svg") else ".jpg")
                with open(os.path.join(OUT, f"{cid}{ext}"), "wb") as f:
                    f.write(data)
                got[cid] = fn
                print(f"HIT  {cid:16s} {fn:40s} [{repo}] {len(data)}B via {ph}", flush=True)
                break
        if cid in got:
            break
    if cid not in got:
        print(f"MISS {cid:16s} {fn}", flush=True)
    time.sleep(0.4)

print("\ngot:", sorted(got.keys()))
print("missing:", sorted({t[0] for t in TARGETS} - set(got)))
