# 一次性脚本：在 ECS 上运行（python3）
# Phase A: Jaguar/Mercedes 文件名猜测探测（Photon 多语言库）+ bing 多候选下载
# Phase B: wsrv 耐心重试下载剩余 SVG 队徽（每 40 秒一次，最多 25 次）
import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

OUT = "/tmp/oldlogos5"
CANDS = os.path.join(OUT, "cands")
os.makedirs(CANDS, exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
PHOTON = ["i0.wp.com", "i1.wp.com", "i2.wp.com"]


def md5dirs(fn_u):
    h = hashlib.md5(fn_u.encode("utf-8")).hexdigest()
    return h[0], h[:2]


def is_img(data):
    return len(data) > 600 and (data[:4] == b"\x89PNG" or data[:3] == b"\xff\xd8\xff" or data[:6] == b"GIF87a" or data[:6] == b"GIF89a")


def try_get(url, headers=None, timeout=30):
    try:
        req = urllib.request.Request(url, headers=headers or UA)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except Exception:
        return None


def save(cid, data, note, sub=""):
    ext = ".png" if data[:4] == b"\x89PNG" else (".jpg" if data[:3] == b"\xff\xd8\xff" else ".gif")
    path = os.path.join(CANDS if sub else OUT, f"{cid}{sub}{ext}")
    with open(path, "wb") as f:
        f.write(data)
    print(f"  HIT  {cid:14s} {note} [{len(data)}B]", flush=True)
    return path


# ---------------- Phase A ----------------
print("=== Phase A: jaguar/mercedes 探测 + bing 多候选 ===", flush=True)
JAG_GUESSES = [
    "Jaguar Racing logo.png", "Jaguar Racing logo.svg", "Jaguar Racing F1 logo.png",
    "Jaguar Racing Formula One Team logo.png", "Jaguar F1 logo.png", "Jaguar F1 Team logo.png",
    "Jaguar Racing Team logo.png", "JaguarRacing.png", "Jaguar Racing Logo.jpg",
    "Jaguar Racing logo 2000.jpg", "Logo Jaguar Racing.png", "Jaguar Racing F1.png",
    "Jaguar Racing F1 Team.png", "Jaguar Racing 2001 logo.png", "Jaguar Formula 1 logo.png",
]
REPOS = ["en", "es", "it", "de", "fr", "commons"]

jag_got = False
for fn in JAG_GUESSES:
    for repo in REPOS:
        fn_u = fn.replace(" ", "_")
        d1, d2 = md5dirs(fn_u)
        u = f"https://upload.wikimedia.org/wikipedia/{repo}/{d1}/{d2}/" + urllib.parse.quote(fn_u)
        for ph in PHOTON:
            data = try_get(f"https://{ph}/{u.replace('https://', '')}", timeout=20)
            if data and is_img(data):
                save("jaguar", data, f"photon:{repo}:{fn}")
                jag_got = True
                break
        if jag_got:
            break
    if jag_got:
        break
    time.sleep(0.3)
if not jag_got:
    print("  jaguar probe: all MISS", flush=True)

MERC_GUESSES = [
    "Mercedes GP logo.png", "Mercedes AMG F1 logo.png", "Mercedes GP Petronas logo.png",
    "Mercedes AMG Petronas F1 logo.png", "Mercedes-Benz in Formula One logo.svg",
    "Mercedes AMG Petronas Formula One Team logo.png", "Mercedes Grand Prix logo.png",
]
merc_got = False
for fn in MERC_GUESSES:
    for repo in ["en", "commons"]:
        fn_u = fn.replace(" ", "_")
        d1, d2 = md5dirs(fn_u)
        u = f"https://upload.wikimedia.org/wikipedia/{repo}/{d1}/{d2}/" + urllib.parse.quote(fn_u)
        for ph in PHOTON:
            data = try_get(f"https://{ph}/{u.replace('https://', '')}", timeout=20)
            if data and is_img(data):
                save("mercedes", data, f"photon:{repo}:{fn}")
                merc_got = True
                break
        if merc_got:
            break
    if merc_got:
        break
    time.sleep(0.3)
if not merc_got:
    print("  mercedes probe: all MISS", flush=True)


def bing_imgs(q, count=35):
    u = ("https://cn.bing.com/images/async?q=" + urllib.parse.quote(q) +
         f"&first=0&count={count}&mmasync=1&mkt=en-US")
    html = try_get(u, timeout=25)
    if not html:
        return []
    html = html.decode("utf-8", "ignore")
    urls = []
    for m in re.finditer(r'm="(\{&quot;.*?\})"', html):
        try:
            j = json.loads(m.group(1).replace("&quot;", '"'))
            for k in ("murl", "turl"):
                if j.get(k):
                    urls.append(j[k])
        except Exception:
            continue
    return urls


BING_Q = {
    "jaguar": "Jaguar Racing F1 logo 2001",
    "brawn": "Brawn GP F1 logo",
    "super_aguri": "Super Aguri F1 logo",
    "toro_rosso": "Scuderia Toro Rosso logo white background",
}
for cid, q in BING_Q.items():
    if cid == "jaguar" and jag_got:
        continue
    urls = bing_imgs(q)
    print(f"  bing {cid:14s} '{q}' -> {len(urls)}", flush=True)
    n = 0
    for i, u in enumerate(urls):
        data = try_get(u, timeout=20)
        if data and is_img(data) and n < 12:
            save(cid, data, f"bing:{u[:50]}", sub=f"_{n}")
            n += 1
        time.sleep(0.25)
    time.sleep(1)

# ---------------- Phase B: wsrv 耐心重试 ----------------
print("\n=== Phase B: wsrv patient retry ===", flush=True)
SVG_FILES = [
    ("brawn",        "Brawn GP logo.svg",            "commons"),
    ("super_aguri",  "SuperAguri_logo.svg",         "commons"),
    ("super_aguri2", "SuperAguri_logo.svg",         "en"),
    ("toro_rosso2",  "Scuderia Toro Rosso logo.svg", "commons"),
    ("caterham2",    "Caterham F1 Team logo.svg",    "commons"),
]
for cid, fn, repo in SVG_FILES:
    if os.path.exists(os.path.join(OUT, cid + ".png")):
        continue
    fn_u = fn.replace(" ", "_")
    d1, d2 = md5dirs(fn_u)
    urls = [
        (f"https://upload.wikimedia.org/wikipedia/{repo}/thumb/{d1}/{d2}/"
         f"{urllib.parse.quote(fn_u)}/400px-{urllib.parse.quote(fn_u)}.png"),
        f"https://upload.wikimedia.org/wikipedia/{repo}/{d1}/{d2}/" + urllib.parse.quote(fn_u),
    ]
    done = False
    for attempt in range(25):
        for u in urls:
            w = "https://wsrv.nl/?url=" + urllib.parse.quote(u, safe="") + "&output=png"
            data = try_get(w, timeout=40)
            if data and is_img(data):
                save(cid, data, f"wsrv:{fn} (attempt {attempt+1})")
                done = True
                break
        if done:
            break
        if attempt % 5 == 4:
            print(f"  {cid:14s} retry {attempt+1}/25 still missing", flush=True)
        time.sleep(40)
    if not done:
        print(f"  {cid:14s} GIVE UP after 25 attempts", flush=True)

print("\n=== DONE ===", flush=True)
for f in sorted(os.listdir(OUT)):
    print(f, os.path.getsize(os.path.join(OUT, f)), flush=True)
