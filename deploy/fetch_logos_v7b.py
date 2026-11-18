# 一次性脚本：在 ECS 上运行（python3）
# v7b：对 7 个 commons 文件的补漏——wikiwand 镜像 / bing 精确查询 / 360 图片搜索
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

OUT = "/tmp/oldlogos8"
os.makedirs(OUT, exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

FILES = {
    "surtees": "Surteeslogo.png",
    "march": "March_Engineering.png",
    "osella": "Osella_emblem.png",
    "tyrrell": "Tyrrell.svg",
    "dallara": "Dallara_logo.svg",
    "simtek": "Simtek_logo.svg",
    "penske": "Team_Penske_logo.svg",
}
QUERIES = {
    "surtees": ['"Surteeslogo"', "Surtees Racing logo png"],
    "march": ['"March_Engineering" logo', "March Engineering logo png"],
    "osella": ['"Osella emblem"', "Osella logo png"],
    "tyrrell": ['"Tyrrell.svg" logo', "Tyrrell Racing logo png"],
    "dallara": ['"Dallara logo" png', "Dallara logo"],
    "simtek": ['"Simtek logo" png', "Simtek F1 logo"],
    "penske": ['"Team Penske logo" png', "Team Penske logo"],
}


def is_img(data):
    if not data:
        return False
    return len(data) > 600 and (
        data[:4] == b"\x89PNG" or data[:3] == b"\xff\xd8\xff"
        or data[:6] in (b"GIF87a", b"GIF89a"))


def try_get(url, headers=None, timeout=30):
    try:
        req = urllib.request.Request(url, headers=headers or UA)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except Exception:
        return None


def save(cid, data, sub=""):
    ext = ".png" if data[:4] == b"\x89PNG" else (
        ".jpg" if data[:3] == b"\xff\xd8\xff" else ".gif")
    path = os.path.join(OUT, f"{cid}_{sub}{ext}")
    with open(path, "wb") as f:
        f.write(data)
    return path


# ---- Phase A: wikiwand 探测 ----
print("=== Phase A: wikiwand ===", flush=True)
html = try_get("https://www.wikiwand.com/en/Surtees", timeout=30)
if html:
    txt = html.decode("utf-8", "ignore")
    m = re.search(r'"https://upload\.wikimedia\.org[^"]*Surteeslogo[^"]*"', txt)
    print("  wikiwand reachable, len=", len(txt), "logo hit:", bool(m), flush=True)
    if m:
        print("  sample:", m.group(0)[:200], flush=True)
else:
    print("  wikiwand unreachable", flush=True)

# ---- Phase B: bing 精确查询（turl 优先）----
print("=== Phase B: bing ===", flush=True)


def bing_imgs(q, count=30):
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
            # turl 走 bing CDN，ECS 可访问；murl 可能是被墙的 wikimedia
            if j.get("turl"):
                urls.append(j["turl"])
            elif j.get("murl"):
                urls.append(j["murl"])
        except Exception:
            continue
    return urls


for cid, qs in QUERIES.items():
    n = 0
    for q in qs:
        urls = bing_imgs(q)
        for u in urls:
            if n >= 8:
                break
            data = try_get(u, timeout=20)
            if data and is_img(data):
                save(cid, data, f"b{n}")
                n += 1
            time.sleep(0.2)
        if n >= 8:
            break
        time.sleep(0.8)
    print(f"  bing {cid:10s} -> {n} saved", flush=True)

# ---- Phase C: 360 图片搜索 ----
print("=== Phase C: so360 ===", flush=True)


def so_imgs(q, pn=30):
    u = ("https://image.so.com/j?q=" + urllib.parse.quote(q) +
         f"&src=srp&sn=0&pn={pn}")
    data = try_get(u, timeout=25)
    if not data:
        return []
    try:
        j = json.loads(data.decode("utf-8", "ignore"))
    except Exception:
        return []
    out = []
    for it in j.get("list", []):
        for k in ("thumb", "img"):
            if it.get(k):
                out.append(it[k])
    return out


for cid, qs in QUERIES.items():
    n = 0
    for q in qs:
        urls = so_imgs(q)
        for u in urls:
            if n >= 6:
                break
            data = try_get(u, timeout=20)
            if data and is_img(data):
                save(cid, data, f"s{n}")
                n += 1
            time.sleep(0.2)
        if n >= 6:
            break
        time.sleep(0.5)
    print(f"  so360 {cid:10s} -> {n} saved", flush=True)

print("\n=== DONE ===", flush=True)
for f in sorted(os.listdir(OUT)):
    print(f, os.path.getsize(os.path.join(OUT, f)), flush=True)
