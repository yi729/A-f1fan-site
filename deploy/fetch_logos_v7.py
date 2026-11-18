# 一次性脚本：在 ECS 上运行（python3）
# v7 精准补漏：已知维基文件名重试（Photon/wsrv）+ bing 改进查询
# 目标：cooper/surtees/march/osella(Photon PNG)、tyrrell/dallara/simtek/penske(wsrv SVG)
#      + 19 支车队的 bing 改进查询
import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

OUT = "/tmp/oldlogos7"
CANDS = os.path.join(OUT, "cands")
os.makedirs(CANDS, exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
PHOTON = ["i0.wp.com", "i1.wp.com", "i2.wp.com"]

# cid -> 已知的维基文件名（DBpedia 查到但上次下载失败）
EXACT = {
    "cooper": ["Cooper_car_company.png"],
    "surtees": ["Surteeslogo.png"],
    "march": ["March_Engineering.png"],
    "osella": ["Osella_emblem.png"],
    "tyrrell": ["Tyrrell.svg"],
    "dallara": ["Dallara_logo.svg"],
    "simtek": ["Simtek_logo.svg"],
    "penske": ["Team_Penske_logo.svg"],
}

# cid -> bing 改进查询
BING_Q2 = {
    "coloni": "Coloni motorsport F1 logo",
    "ensign": "Ensign Racing Formula One team logo",
    "maserati": "Maserati trident logo",
    "porsche": "Porsche crest logo",
    "renault": "Renault diamond logo",
    "fittipaldi": "Fittipaldi Automotive Copersucar logo",
    "onyx": "Onyx Grand Prix logo",
    "alfa": "Alfa Romeo classic roundel badge logo",
    "aston_martin": "Aston Martin classic wings badge",
    "honda": "Honda Racing F1 1960s emblem",
    "kurtis_kraft": "Kurtis Kraft logo",
    "eurobrun": "EuroBrun Formula One logo",
    "scarab": "Scarab Racing scorpion emblem",
    "ats": "ATS Formula One team logo",
    "ram": "RAM Racing Formula One logo",
    "spirit": "Spirit Racing Formula One logo",
    "martini": "Automobiles Martini racing logo",
    "rebaque": "Team Rebaque Formula One logo",
    "williams": "Williams Grand Prix Engineering classic logo",
}


def md5dirs(fn_u):
    h = hashlib.md5(fn_u.encode("utf-8")).hexdigest()
    return h[0], h[:2]


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
    path = os.path.join(CANDS, f"{cid}_{sub}{ext}")
    with open(path, "wb") as f:
        f.write(data)
    return path


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
            for k in ("murl", "turl"):
                if j.get(k):
                    urls.append(j[k])
        except Exception:
            continue
    return urls


def wsrv_patient(base, tries=8):
    """wsrv 对 429 时耐心重试；404 直接返回 None。"""
    u = "https://wsrv.nl/?url=" + urllib.parse.quote(base, safe="") + "&output=png"
    for i in range(tries):
        try:
            req = urllib.request.Request(u, headers=UA)
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
        except Exception:
            pass
        time.sleep(6 + i * 2)
    return None


print("=== Phase 1: 已知文件重试 ===", flush=True)
GOT = {}
for cid, fns in EXACT.items():
    for fn in fns:
        fn_u = fn.replace(" ", "_")
        d1, d2 = md5dirs(fn_u)
        qf = urllib.parse.quote(fn_u)
        is_svg = fn_u.lower().endswith(".svg")
        hit = False
        for repo in ["en", "commons"]:
            base = f"https://upload.wikimedia.org/wikipedia/{repo}/{d1}/{d2}/{qf}"
            if is_svg:
                data = wsrv_patient(base)
                tag = "wsrv"
                if data and is_img(data):
                    save(cid, data, "wsrv")
                    print(f"  HIT  {cid:12s} wsrv   {fn} [{len(data)}B]", flush=True)
                    GOT[cid] = True
                    hit = True
                    break
            else:
                for ph in PHOTON:
                    u = f"https://{ph}/{base.replace('https://', '')}"
                    data = try_get(u, timeout=40)
                    if data and is_img(data):
                        save(cid, data, "photon")
                        print(f"  HIT  {cid:12s} photon {fn} [{len(data)}B]", flush=True)
                        GOT[cid] = True
                        hit = True
                        break
                    time.sleep(0.3)
                if not hit:
                    # Photon 全挂再试 wsrv（PNG 也可能被 Photon 拒）
                    data = wsrv_patient(base, tries=5)
                    if data and is_img(data):
                        save(cid, data, "wsrv")
                        print(f"  HIT  {cid:12s} wsrv   {fn} [{len(data)}B]", flush=True)
                        GOT[cid] = True
                        hit = True
                        break
            if hit:
                break
        if hit:
            break
        time.sleep(0.4)
    if cid not in GOT:
        print(f"  MISS {cid:12s} {fns}", flush=True)

print("\n=== Phase 2: bing 改进查询 ===", flush=True)
for cid, q in BING_Q2.items():
    if cid in GOT:
        continue
    urls = bing_imgs(q)
    n = 0
    for u in urls:
        data = try_get(u, timeout=20)
        if data and is_img(data) and n < 8:
            save(cid, data, f"{n}")
            n += 1
        time.sleep(0.2)
    print(f"  bing {cid:12s} '{q}' -> {n} saved", flush=True)
    time.sleep(0.8)

print("\n=== DONE ===", flush=True)
for f in sorted(os.listdir(CANDS)):
    print(f, os.path.getsize(os.path.join(CANDS, f)), flush=True)
print("cands:", len(os.listdir(CANDS)), flush=True)
