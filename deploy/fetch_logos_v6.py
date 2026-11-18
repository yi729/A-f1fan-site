# 一次性脚本：在 ECS 上运行（python3）
# 1958-1999 老车队队徽：DBpedia 查文件名 -> Photon/wsrv 下载 -> bing 兜底
import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

OUT = "/tmp/oldlogos6"
CANDS = os.path.join(OUT, "cands")
os.makedirs(CANDS, exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
PHOTON = ["i0.wp.com", "i1.wp.com", "i2.wp.com"]

# cid -> 维基百科条目候选（查到一个有图的就停）
TEAMS = {
    "connaught": ["Connaught Engineering"],
    "vanwall": ["Vanwall"],
    "maserati": ["Maserati in motorsport", "Maserati"],
    "cooper": ["Cooper Car Company"],
    "porsche": ["Porsche in motorsport", "Porsche in Formula One"],
    "brm": ["British Racing Motors"],
    "team_lotus": ["Team Lotus"],
    "ferrari": ["Scuderia Ferrari"],
    "kurtis_kraft": ["Kurtis Kraft"],
    "aston_martin": ["Aston Martin in Formula One", "Aston Martin"],
    "scarab": ["Scarab (constructor)", "Reventlow Automobiles"],
    "brabham": ["Brabham"],
    "lola": ["Lola Cars", "Lola Racing Cars"],
    "alfa": ["Alfa Romeo in Formula One"],
    "eagle": ["Anglo American Racers", "Eagle (constructor)"],
    "matra": ["Matra", "Equipe Matra Sports"],
    "mclaren": ["McLaren", "Bruce McLaren Motor Racing"],
    "surtees": ["Surtees Racing Organisation", "Surtees"],
    "march": ["March Engineering"],
    "tyrrell": ["Tyrrell Racing"],
    "tecno": ["Tecno (motorsport)"],
    "iso_marlboro": ["Iso-Marlboro"],
    "shadow": ["Shadow Racing Cars"],
    "ensign": ["Ensign (racing team)"],
    "parnelli": ["Vel's Parnelli Jones Racing"],
    "penske": ["Team Penske", "Penske Racing"],
    "hesketh": ["Hesketh Racing"],
    "fittipaldi": ["Fittipaldi Automotive"],
    "williams": ["Williams Racing", "Williams Grand Prix Engineering"],
    "kojima": ["Kojima Engineering"],
    "wolf": ["Walter Wolf Racing"],
    "ligier": ["Equipe Ligier", "Ligier"],
    "renault": ["Renault in Formula One", "Renault Sport"],
    "theodore": ["Theodore Racing"],
    "osella": ["Osella"],
    "toleman": ["Toleman"],
    "zakspeed": ["Zakspeed"],
    "ags": ["Automobiles Gonfaronnaises Sportives", "AGS (Formula One)"],
    "coloni": ["Enzo Coloni Racing Car Systems", "Coloni"],
    "larrousse": ["Larrousse"],
    "rial": ["Rial Racing", "Rial (racing team)"],
    "eurobrun": ["EuroBrun"],
    "dallara": ["Dallara", "BMS Scuderia Italia"],
    "onyx": ["Onyx Grand Prix"],
    "leyton": ["Leyton House Racing"],
    "lambo": ["Lamborghini in Formula One", "Lambo (Formula One team)"],
    "fondmetal": ["Fondmetal"],
    "footwork": ["Footwork Arrows", "Arrows Grand Prix International"],
    "moda": ["Andrea Moda Formula"],
    "simtek": ["Simtek"],
    "pacific": ["Pacific Racing"],
    "forti": ["Forti"],
    "stewart": ["Stewart Grand Prix"],
    "amon": ["Chris Amon Racing", "Amon (Formula One team)"],
    "maki": ["Maki Engineering"],
    "merzario": ["Merzario"],
    "trojan": ["Trojan-Tauranac Racing"],
    "token": ["Token (racing team)"],
    "connew": ["Connew"],
    "hill": ["Embassy Hill"],
    "lds": ["LDS (racing)"],
    "de_tomaso": ["De Tomaso", "Scuderia Serenissima"],
    "gilby": ["Gilby Engineering"],
}
# cid -> bing 查询词
BING_Q = {
    "connaught": "Connaught Engineering logo",
    "vanwall": "Vanwall F1 logo",
    "maserati": "Maserati logo",
    "cooper": "Cooper Car Company logo",
    "porsche": "Porsche logo",
    "brm": "BRM Formula 1 logo",
    "team_lotus": "Team Lotus F1 logo",
    "ferrari": "Ferrari logo",
    "kurtis_kraft": "Kurtis Kraft logo",
    "aston_martin": "Aston Martin logo",
    "scarab": "Scarab F1 logo",
    "brabham": "Brabham F1 logo",
    "lola": "Lola Cars logo",
    "alfa": "Alfa Romeo F1 logo",
    "eagle": "Anglo American Racers Eagle logo",
    "matra": "Matra F1 logo",
    "mclaren": "McLaren F1 logo classic",
    "surtees": "Surtees F1 logo",
    "march": "March Engineering logo",
    "tyrrell": "Tyrrell Racing logo",
    "tecno": "Tecno F1 logo",
    "iso_marlboro": "Iso Marlboro F1 logo",
    "shadow": "Shadow F1 team logo",
    "ensign": "Ensign F1 logo",
    "parnelli": "Parnelli Jones logo",
    "penske": "Team Penske logo",
    "hesketh": "Hesketh Racing logo",
    "fittipaldi": "Fittipaldi Automotive logo",
    "williams": "Williams F1 logo classic",
    "kojima": "Kojima Engineering logo",
    "wolf": "Walter Wolf Racing logo",
    "ligier": "Ligier F1 logo",
    "renault": "Renault F1 logo classic",
    "theodore": "Theodore Racing logo",
    "osella": "Osella F1 logo",
    "toleman": "Toleman F1 logo",
    "zakspeed": "Zakspeed logo",
    "ags": "AGS F1 team logo",
    "coloni": "Coloni F1 logo",
    "larrousse": "Larrousse F1 logo",
    "rial": "Rial F1 logo",
    "eurobrun": "EuroBrun logo",
    "dallara": "Dallara logo",
    "onyx": "Onyx F1 logo",
    "leyton": "Leyton House logo",
    "lambo": "Lamborghini logo",
    "fondmetal": "Fondmetal logo",
    "footwork": "Footwork F1 logo",
    "moda": "Andrea Moda Formula logo",
    "simtek": "Simtek logo",
    "pacific": "Pacific Racing logo",
    "forti": "Forti F1 logo",
    "stewart": "Stewart Grand Prix logo",
    "amon": "Amon F1 logo",
    "maki": "Maki Engineering logo",
    "merzario": "Merzario F1 logo",
    "trojan": "Trojan F1 logo",
    "token": "Token F1 logo",
    "connew": "Connew F1 logo",
    "hill": "Embassy Hill F1 logo",
    "lds": "LDS F1 logo",
    "de_tomaso": "De Tomaso logo",
    "gilby": "Gilby Engineering logo",
}


def md5dirs(fn_u):
    h = hashlib.md5(fn_u.encode("utf-8")).hexdigest()
    return h[0], h[:2]


def is_img(data):
    return len(data) > 600 and (data[:4] == b"\x89PNG" or data[:3] == b"\xff\xd8\xff" or data[:6] in (b"GIF87a", b"GIF89a"))


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
    return path


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
                    if fn not in out:
                        out.append((p.rsplit("/", 1)[-1], fn))
        except Exception:
            pass
        time.sleep(0.25)
    return out


# ---------------- Phase 1: DBpedia ----------------
print("=== Phase 1: DBpedia ===", flush=True)
FILES = {}  # cid -> [(prop, filename)]
for cid, arts in TEAMS.items():
    got = None
    for a in arts:
        files = dbpedia_files(a)
        if files:
            got = (a, files)
            break
    if got:
        print(f"  {cid:14s} {got[0]:38s} {got[1]}", flush=True)
        FILES[cid] = got[1]
    time.sleep(0.3)

# ---------------- Phase 2: 下载 ----------------
print("\n=== Phase 2: download ===", flush=True)
GOT = {}
for cid, fl in FILES.items():
    for prop, fn in fl:
        if cid in GOT:
            break
        for repo in ["en", "commons"]:
            fn_u = fn.replace(" ", "_")
            d1, d2 = md5dirs(fn_u)
            qf = urllib.parse.quote(fn_u)
            base = f"https://upload.wikimedia.org/wikipedia/{repo}/{d1}/{d2}/{qf}"
            if fn_u.lower().endswith(".svg"):
                urls = [("wsrv", "https://wsrv.nl/?url=" + urllib.parse.quote(base, safe="") + "&output=png")]
            else:
                urls = [(ph, f"https://{ph}/{base.replace('https://', '')}") for ph in PHOTON]
            for tag, u in urls:
                data = try_get(u)
                if data and is_img(data):
                    save(cid, data, f"{tag}:{fn}", sub=f"_{prop}")
                    GOT[cid] = (prop, fn, tag, len(data))
                    print(f"  HIT  {cid:14s} {tag:6s} [{prop}] {fn} [{len(data)}B]", flush=True)
                    break
            if cid in GOT:
                break
        time.sleep(0.3)
    if cid not in GOT:
        print(f"  MISS {cid:14s} {[f for _, f in fl]}", flush=True)

# ---------------- Phase 3: bing 兜底（存候选供人工挑） ----------------
print("\n=== Phase 3: bing ===", flush=True)


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


for cid, q in BING_Q.items():
    if cid in GOT:
        continue
    urls = bing_imgs(q)
    n = 0
    for u in urls:
        data = try_get(u, timeout=20)
        if data and is_img(data) and n < 8:
            save(cid, data, f"bing:{u[:50]}", sub=f"_{n}")
            n += 1
        time.sleep(0.2)
    print(f"  bing {cid:14s} '{q}' -> {n} saved", flush=True)
    time.sleep(0.8)

print("\n=== DONE ===", flush=True)
for f in sorted(os.listdir(OUT)):
    print(f, os.path.getsize(os.path.join(OUT, f)), flush=True)
print("cands:", len(os.listdir(CANDS)), flush=True)
