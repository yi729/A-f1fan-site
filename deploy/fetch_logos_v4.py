# 一次性脚本：在 ECS 上运行（python3）
# Part A: DBpedia 用修正过的资源名补查文件名
# Part B: 测试可用的维基代理（allorigins / codetabs / corsproxy / cors.sh / jina）
# Part C: 用可用通道下载全部剩余队徽到 /tmp/oldlogos4
# Part D: 未命中的走 cn.bing 图搜 turl 兜底
import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

OUT = "/tmp/oldlogos4"
os.makedirs(OUT, exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

# ---------------- Part A: DBpedia ----------------
DBP_TEAMS = [
    ("toyota",       ["Toyota Racing (Formula One team)", "Toyota Motorsport GmbH", "Toyota F1"]),
    ("bmw_sauber",   ["BMW Sauber", "BMW Sauber F1 Team"]),
    ("marussia",     ["Marussia F1", "Marussia F1 Team", "Marussia Motors"]),
    ("jaguar",       ["Jaguar Racing", "Jaguar Racing F1 Team", "Jaguar (Formula One team)"]),
    ("lotus_racing", ["Lotus Racing", "Lotus Racing F1 Team"]),
    ("super_aguri",  ["Super Aguri F1", "Super Aguri F1 Team", "Super Aguri"]),
]


def dbpedia_files(article):
    res = "http://dbpedia.org/resource/" + urllib.parse.quote(article.replace(" ", "_"))
    props = ["http://dbpedia.org/ontology/thumbnail",
             "http://dbpedia.org/property/logo",
             "http://dbpedia.org/property/image",
             "http://xmlns.com/foaf/0.1/depiction"]
    out = []
    for p in props:
        q = "SELECT ?v WHERE { <" + res + "> <" + p + "> ?v } LIMIT 3"
        data = urllib.parse.urlencode({"query": q, "format": "json"}).encode()
        req = urllib.request.Request("https://dbpedia.org/sparql", data=data, headers=UA)
        try:
            d = json.load(urllib.request.urlopen(req, timeout=40))
            for b in d.get("results", {}).get("bindings", []):
                v = b.get("v", {}).get("value", "")
                if "Special:FilePath/" in v:
                    fn = urllib.parse.unquote(v.split("Special:FilePath/")[1].split("?")[0])
                    out.append(fn)
        except Exception:
            pass
        time.sleep(0.3)
    return out


DBP_FOUND = {}
print("=== Part A: DBpedia ===", flush=True)
for cid, arts in DBP_TEAMS:
    hit = None
    for a in arts:
        files = dbpedia_files(a)
        if files:
            print(f"  {cid:14s} {a:38s} -> {files}", flush=True)
            DBP_FOUND.setdefault(cid, [])
            for f in files:
                if f not in DBP_FOUND[cid]:
                    DBP_FOUND[cid].append(f)
            hit = files[0]
            break
    if not hit:
        print(f"  {cid:14s} (no hit)", flush=True)
    time.sleep(0.5)

# ---------------- Part B: 代理测试 ----------------
print("\n=== Part B: proxy tests ===", flush=True)
TEST_URLS = {
    "jpg_direct": "https://upload.wikimedia.org/wikipedia/commons/a/a9/Example.jpg",
    "svg_thumb": "https://upload.wikimedia.org/wikipedia/commons/thumb/e/ea/Ambox_current_red.svg/200px-Ambox_current_red.svg.png",
}
PROXIES = {
    "allorigins": lambda u: "https://api.allorigins.win/raw?url=" + urllib.parse.quote(u, safe=""),
    "codetabs":   lambda u: "https://api.codetabs.com/v1/proxy?quest=" + urllib.parse.quote(u, safe=""),
    "corsproxy":  lambda u: "https://corsproxy.io/?url=" + urllib.parse.quote(u, safe=""),
    "corssh":     lambda u: "https://proxy.cors.sh/" + u,
    "jina":       lambda u: "https://r.jina.ai/" + u,
    "wsrv":       lambda u: "https://wsrv.nl/?url=" + urllib.parse.quote(u, safe=""),
}

WORKING = {}
for pname, maker in PROXIES.items():
    ok = []
    for tname, u in TEST_URLS.items():
        hdrs = dict(UA)
        if pname == "corssh":
            hdrs["x-cors-api-key"] = "temp_9521a4b01cbc2d2b6d51c2eeb9c3f59d"
        if pname == "corsproxy":
            hdrs["Origin"] = "https://example.com"
        try:
            req = urllib.request.Request(maker(u), headers=hdrs)
            with urllib.request.urlopen(req, timeout=25) as r:
                data = r.read()
            good = len(data) > 500 and (data[:4] == b"\x89PNG" or data[:3] == b"\xff\xd8\xff")
            ok.append((tname, good, len(data)))
        except Exception as ex:
            ok.append((tname, False, str(ex)[:60]))
    status = " ".join(f"{t}:{'Y' if g else 'N'}({s})" for t, g, s in ok)
    print(f"  {pname:11s} {status}", flush=True)
    WORKING[pname] = [t for t, g, s in ok if g]
    time.sleep(1)

# ---------------- Part C: 下载 ----------------
print("\n=== Part C: download ===", flush=True)
TARGETS = [
    ("brawn",        "Brawn GP logo.svg",                ["commons"],            "svg"),
    ("hrt",          "HRT F1 TEAM 2012.svg",             ["commons"],            "svg"),
    ("caterham",     "Caterham F1 Team logo.svg",        ["commons"],            "svg"),
    ("toro_rosso",   "Scuderia Toro Rosso logo.svg",     ["commons"],            "svg"),
    ("super_aguri",  "SuperAguri_logo.svg",              ["commons", "en"],      "svg"),
    ("sauber",       'Sauber "S" logo 2000\'s.gif',      ["commons", "en"],      "raster"),
    ("sauber2",      "Logo Sauber F1.png",               ["en", "commons"],      "raster"),
    ("bmw_sauber",   "BMW Sauber logo.svg",              ["en", "commons"],      "svg"),
    ("bmw_sauber",   "BMW Sauber logo.png",              ["en", "commons"],      "raster"),
    ("bmw_sauber",   "BMW Sauber F1 Team logo.png",      ["en", "commons"],      "raster"),
    ("toyota",       "Panasonic Toyota Racing logo.png", ["en", "commons"],      "raster"),
    ("toyota",       "Toyota F1 logo.png",               ["en", "commons"],      "raster"),
    ("toyota",       "Toyota Racing logo.png",           ["en", "commons"],      "raster"),
    ("marussia",     "Marussia F1 Team logo.svg",        ["en", "commons"],      "svg"),
    ("marussia",     "Marussia F1 Team logo.png",        ["en", "commons"],      "raster"),
    ("marussia",     "Marussia logo.svg",                ["en", "commons"],      "svg"),
    ("jaguar",       "Jaguar Racing logo.png",           ["en", "commons"],      "raster"),
    ("jaguar",       "Jaguar Racing logo.svg",           ["en", "commons"],      "svg"),
    ("jaguar",       "Jaguar Racing F1 logo.png",        ["en", "commons"],      "raster"),
    ("lotus_racing", "Lotus Racing logo.svg",            ["en", "commons"],      "svg"),
    ("lotus_racing", "Lotus Racing logo.png",            ["en", "commons"],      "raster"),
    ("lotus_racing", "Team Lotus logo.svg",              ["en", "commons"],      "svg"),
]
for cid, files in DBP_FOUND.items():
    for f in files:
        TARGETS.append((cid, f, ["commons", "en"], "svg" if f.lower().endswith(".svg") else "raster"))

GOT = {}
PHOTON = ["i0.wp.com", "i1.wp.com", "i2.wp.com"]


def md5dirs(fn_u):
    h = hashlib.md5(fn_u.encode("utf-8")).hexdigest()
    return h[0], h[:2]


def is_img(data):
    return len(data) > 600 and (data[:4] == b"\x89PNG" or data[:3] == b"\xff\xd8\xff" or data[:6] == b"GIF87a" or data[:6] == b"GIF89a")


def try_get(url, headers=None):
    try:
        req = urllib.request.Request(url, headers=headers or UA)
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read()
    except Exception:
        return None


def build_urls(fn, repo, kind):
    """返回该文件的候选 wikimedia 相对路径（不含代理前缀）。"""
    fn_u = fn.replace(" ", "_")
    d1, d2 = md5dirs(fn_u)
    base = f"https://upload.wikimedia.org/wikipedia/{repo}/{d1}/{d2}/" + urllib.parse.quote(fn_u)
    urls = []
    if kind == "svg":
        thumb = (f"https://upload.wikimedia.org/wikipedia/{repo}/thumb/{d1}/{d2}/"
                 f"{urllib.parse.quote(fn_u)}/400px-{urllib.parse.quote(fn_u)}.png")
        urls.append(thumb)
    urls.append(base)
    return urls


def save(cid, data, note):
    ext = ".png" if data[:4] == b"\x89PNG" else (".jpg" if data[:3] == b"\xff\xd8\xff" else ".gif")
    path = os.path.join(OUT, cid + ext)
    with open(path, "wb") as f:
        f.write(data)
    GOT[cid] = (note, len(data))
    print(f"  HIT  {cid:14s} {note} [{len(data)}B]", flush=True)


for cid, fn, repos, kind in TARGETS:
    if cid in GOT:
        continue
    urls = []
    for repo in repos:
        urls += build_urls(fn, repo, kind)
    got_now = False
    # 光栅文件优先 Photon（最稳）
    if kind == "raster":
        for u in urls:
            for ph in PHOTON:
                data = try_get(f"https://{ph}/{u.replace('https://', '')}")
                if data and is_img(data):
                    save(cid, data, f"photon:{fn}")
                    got_now = True
                    break
            if got_now:
                break
    if got_now:
        continue
    # 可用代理（thumb png 优先）
    for pname, tests in WORKING.items():
        if not tests:
            continue
        for u in urls:
            if pname == "wsrv":
                u2 = "https://wsrv.nl/?url=" + urllib.parse.quote(u, safe="") + "&output=png"
            else:
                u2 = PROXIES[pname](u)
            hdrs = dict(UA)
            if pname == "corssh":
                hdrs["x-cors-api-key"] = "temp_9521a4b01cbc2d2b6d51c2eeb9c3f59d"
            if pname == "corsproxy":
                hdrs["Origin"] = "https://example.com"
            data = try_get(u2, hdrs)
            if data and is_img(data):
                save(cid, data, f"{pname}:{fn}")
                got_now = True
                break
        if got_now:
            break
    if not got_now:
        print(f"  MISS {cid:14s} {fn}", flush=True)
    time.sleep(0.4)

# ---------------- Part D: bing 兜底 ----------------
print("\n=== Part D: bing fallback ===", flush=True)
BING_Q = {
    "brawn": "Brawn GP logo",
    "hrt": "HRT F1 Team logo",
    "caterham": "Caterham F1 Team logo",
    "toro_rosso": "Scuderia Toro Rosso logo",
    "super_aguri": "Super Aguri F1 logo",
    "sauber": "Sauber Petronas logo 2000",
    "bmw_sauber": "BMW Sauber F1 logo",
    "toyota": "Panasonic Toyota Racing logo",
    "marussia": "Marussia F1 Team logo",
    "jaguar": "Jaguar Racing F1 logo",
    "lotus_racing": "Lotus Racing F1 logo",
}


def bing_imgs(q):
    u = ("https://cn.bing.com/images/async?q=" + urllib.parse.quote(q) +
         "&first=0&count=35&mmasync=1&mkt=en-US")
    try:
        req = urllib.request.Request(u, headers=UA)
        html = urllib.request.urlopen(req, timeout=25).read().decode("utf-8", "ignore")
    except Exception:
        return []
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


for cid, q in BING_Q.items():
    if cid in GOT:
        continue
    urls = bing_imgs(q)
    print(f"  {cid:14s} query='{q}' -> {len(urls)} candidates", flush=True)
    for i, u in enumerate(urls[:8]):
        data = try_get(u)
        if data and is_img(data):
            save(cid, data, f"bing:{u[:60]}")
            break
        time.sleep(0.3)
    time.sleep(1)

print("\n=== 结果 ===", flush=True)
print("got:", json.dumps(GOT, indent=1), flush=True)
missing = sorted({c for c, _, _, _ in TARGETS} - set(GOT))
print("missing:", missing, flush=True)
