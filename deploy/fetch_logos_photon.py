# 一次性脚本：在 ECS 上运行
# 终版：DBpedia 补查文件名 + Photon(i0/i1/i2.wp.com) 下载维基队徽
# SVG 通过维基缩略图渲染成 PNG
import hashlib
import json
import os
import time
import urllib.request
import urllib.parse

OUT = "/tmp/oldlogos3"
os.makedirs(OUT, exist_ok=True)

# ---------- Phase 1: DBpedia 补查 ----------
EXTRA_QUERIES = {
    "toyota": ["Panasonic Toyota Racing", "Toyota Racing", "Toyota Motorsport GmbH"],
    "bmw_sauber": ["BMW Sauber"],
    "lotus_racing": ["Team Lotus (2010–11)", "Lotus Racing", "Team Lotus"],
    "lotus_f1": ["Lotus F1 Team", "Lotus Renault GP"],
    "marussia": ["Marussia F1 Team", "Marussia Virgin Racing", "Marussia"],
    "manor": ["Manor Racing", "Manor Marussia F1 Team", "Manor Grand Prix"],
    "williams_2000s": ["WilliamsF1", "Williams Grand Prix Engineering", "Williams Racing"],
    "mclaren_2000s": ["McLaren", "McLaren Racing"],
    "jaguar": ["Jaguar Racing (Formula One team)", "Jaguar Racing Formula One team"],
    "sauber_2000s": ["Sauber Motorsport", "Sauber"],
    "renault_2000s": ["Renault F1", "Renault Sport F1 Team", "Renault in Formula One"],
    "mercedes_2010": ["Mercedes GP", "Mercedes AMG Petronas Formula One Team"],
    "hrt": ["HRT Formula 1 Team", "Hispania Racing"],
    "caterham": ["Caterham F1", "Caterham Racing"],
    "super_aguri": ["Super Aguri", "Super Aguri F1"],
    "benetton": ["Benetton Formula"],
    "prost": ["Prost Grand Prix"],
    "brawn": ["Brawn GP"],
    "jordan": ["Jordan Grand Prix"],
    "toro_rosso": ["Scuderia Toro Rosso"],
}


def dbpedia_files(article):
    """查一个条目的 thumbnail/logo/image 属性,返回候选文件名列表。"""
    res = "http://dbpedia.org/resource/" + urllib.parse.quote(article.replace(" ", "_"))
    props = ["http://dbpedia.org/ontology/thumbnail",
             "http://dbpedia.org/property/logo",
             "http://dbpedia.org/property/image",
             "http://xmlns.com/foaf/0.1/depiction"]
    out = []
    for p in props:
        q = f"SELECT ?v WHERE {{ <{res}> <{p}> ?v }} LIMIT 3"
        data = urllib.parse.urlencode({"query": q, "format": "json"}).encode()
        req = urllib.request.Request("https://dbpedia.org/sparql", data=data,
                                     headers={"User-Agent": "f1-research/1.0",
                                              "Content-Type": "application/x-www-form-urlencoded",
                                              "Accept": "application/sparql-results+json"})
        try:
            d = json.load(urllib.request.urlopen(req, timeout=40))
            for b in d.get("results", {}).get("bindings", []):
                v = b.get("v", {}).get("value", "")
                if "Special:FilePath/" in v:
                    out.append(urllib.parse.unquote(v.split("Special:FilePath/")[1].split("?")[0]))
                elif v and not v.startswith("http") and "." in v and len(v) < 90:
                    out.append(v)
        except Exception:
            pass
        time.sleep(0.3)
    return out


# 已知文件名(此前 DBpedia 查到/猜测)
KNOWN = {
    "jordan": ["Jordan Grand Prix logo.png"],
    "benetton": ["Benetton Formula logo.jpg", "Benetton Formula logo.png"],
    "prost": ["Prost Grand Prix Formula One Logo.png", "Prost Grand Prix logo.png"],
    "super_aguri": ["SuperAguri logo.svg", "Super Aguri F1 logo.png"],
    "brawn": ["Brawn GP logo.svg", "Brawn GP logo.png"],
    "hrt": ["HRT F1 TEAM 2012.svg", "HRT F1 Team logo.png"],
    "caterham": ["Caterham F1 Team logo.svg", "Caterham F1 Team logo.png"],
    "toro_rosso": ["Scuderia Toro Rosso logo.svg", "Scuderia Toro Rosso logo.png"],
    "mercedes_2010": ["Mercedes-Benz in Formula One logo.svg", "Mercedes GP logo.png"],
    "red_bull": ["Red bull racing.png", "Red Bull Racing logo.svg", "Infiniti Red Bull Racing logo.png"],
    "sauber_2000s": ["Sauber logo.svg", "Sauber Petronas logo.png", "Sauber logo.png"],
    "williams_2000s": ["WilliamsF1 logo.png", "Williams F1 logo.svg", "Williams logo.svg",
                       "AT&T Williams logo.png", "Williams Grand Prix Engineering logo.png"],
    "mclaren_2000s": ["McLaren Racing logo.svg", "West McLaren Mercedes logo.png",
                      "Vodafone McLaren Mercedes logo.png"],
    "renault_2000s": ["Renault F1 logo.png", "Renault F1 Team logo 2016.svg",
                      "Renault Sport F1 Team logo.png", "Renault F1 Team logo.svg"],
    "lotus_f1": ["Lotus F1 Team logo.svg", "Lotus Renault GP logo.svg", "Lotus F1 Team logo.png"],
    "lotus_racing": ["Team Lotus logo.svg", "Lotus Racing logo.png", "Lotus Racing logo.svg",
                     "Team Lotus 2010 logo.png"],
    "marussia": ["Marussia F1 Team logo.svg", "Marussia logo.svg", "Marussia F1 Team logo.png",
                 "Marussia logo.png"],
    "manor": ["Manor Marussia F1 Team logo.png", "Manor Racing logo.png", "Manor MRT logo.png",
              "Manor Racing MRT logo.png"],
    "bmw_sauber": ["BMW Sauber logo.svg", "BMW Sauber logo.png"],
    "jaguar": ["Jaguar Racing logo.png", "Jaguar Racing logo.svg", "Jaguar Racing F1 logo.png",
               "Jaguar Racing Formula One Team logo.png"],
    "toyota": ["Panasonic Toyota Racing logo.png", "Toyota F1 logo.png", "Toyota Racing logo.png",
               "Toyota F1 Team logo.png"],
}

print("=== Phase 1: DBpedia 补查 ===", flush=True)
for cid, arts in EXTRA_QUERIES.items():
    for a in arts:
        files = dbpedia_files(a)
        if files:
            print(f"  {cid:16s} {a:40s} -> {files}", flush=True)
            for f in files:
                if f not in KNOWN.get(cid, []):
                    KNOWN.setdefault(cid, []).insert(0, f)
            break  # 该车队查到一个就停

print("\n=== Phase 2: Photon 下载 ===", flush=True)
REPOS = ["en", "commons"]
PHOTON = ["i0.wp.com", "i1.wp.com", "i2.wp.com"]


def md5dirs(fn_u):
    h = hashlib.md5(fn_u.encode("utf-8")).hexdigest()
    return h[0], h[:2]


def photon_urls(fn, repo):
    """返回该文件的所有可尝试 URL（原样 + svg 缩略图渲染 png）。"""
    fn_u = fn.replace(" ", "_")
    d1, d2 = md5dirs(fn_u)
    base = f"upload.wikimedia.org/wikipedia/{repo}/{d1}/{d2}/{urllib.parse.quote(fn_u)}"
    urls = [base]
    if fn_u.lower().endswith(".svg"):
        urls.insert(0, f"upload.wikimedia.org/wikipedia/{repo}/thumb/{d1}/{d2}/"
                       f"{urllib.parse.quote(fn_u)}/480px-{urllib.parse.quote(fn_u)}.png")
    return urls


def fetch(url_path):
    """经 Photon 下载,返回 bytes 或 None。"""
    for ph in PHOTON:
        try:
            req = urllib.request.Request(f"https://{ph}/{url_path}",
                                         headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=25) as r:
                data = r.read()
            if len(data) > 800:
                return data
        except urllib.error.HTTPError:
            continue
        except Exception:
            continue
    return None


got = {}
for cid, files in KNOWN.items():
    if cid in got:
        continue
    for fn in files:
        for repo in REPOS:
            for up in photon_urls(fn, repo):
                data = fetch(up)
                if data:
                    ext = ".png" if up.endswith(".png") else (
                        ".svg" if up.endswith(".svg") else ".jpg")
                    path = os.path.join(OUT, f"{cid}{ext}")
                    with open(path, "wb") as f:
                        f.write(data)
                    got[cid] = (fn, repo, len(data))
                    print(f"HIT  {cid:16s} {fn:45s} [{repo}] {len(data)}B", flush=True)
                    break
            if cid in got:
                break
        if cid in got:
            break
    if cid not in got:
        print(f"MISS {cid:16s} tried: {files}", flush=True)
    time.sleep(0.5)

print("\n=== 结果 ===", flush=True)
print("got:", sorted(got.keys()))
print("missing:", sorted(set(KNOWN) - set(got)))
