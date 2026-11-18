# 一次性脚本：在 ECS 上运行
# 通过 wsrv.nl 图片代理批量探测维基百科上的历史 F1 车队队徽文件并下载到 /tmp/oldlogos
import hashlib
import os
import sys
import urllib.request
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

OUT = "/tmp/oldlogos"
os.makedirs(OUT, exist_ok=True)

# constructorId -> 候选文件名列表（en.wikipedia 非自由文件多为 png；commons 上简单文字 logo 多为 svg）
CANDIDATES = {
    "arrows": ["Arrows Grand Prix International logo.png", "Arrows logo.png",
               "Arrows F1 logo.png", "Arrows Grand Prix logo.png", "Arrows F1 Team logo.png"],
    "bar": ["British American Racing logo.png", "BAR F1 logo.png",
            "British American Racing logo.svg", "Lucky Strike BAR Honda logo.png",
            "BAR Honda logo.png", "British American Racing F1 logo.png"],
    "benetton": ["Benetton Formula logo.png", "Benetton logo.png",
                 "Benetton Formula 1 logo.png", "Mild Seven Benetton Renault logo.png",
                 "Benetton Formula logo.svg"],
    "jaguar": ["Jaguar Racing logo.png", "Jaguar Racing F1 logo.png",
               "Jaguar Racing logo.svg", "Jaguar logo.png",
               "Jaguar Racing Formula One Team logo.png", "Jaguar Racing Formula 1 logo.png"],
    "jordan": ["Jordan Grand Prix logo.png", "Jordan GP logo.png", "Jordan logo.png",
               "Jordan Grand Prix logo.svg", "Jordan Grand Prix logo 1998.png",
               "Benson and Hedges Jordan logo.png"],
    "minardi": ["Minardi logo.png", "Minardi F1 Team logo.png", "Minardi logo.svg",
                "European Minardi logo.png", "Minardi Cosworth logo.png",
                "Minardi F1 logo.png"],
    "prost": ["Prost Grand Prix logo.png", "Prost Grand Prix logo.svg", "Prost GP logo.png",
              "Prost Acer logo.png", "Prost Grand Prix Formula One logo.png"],
    "toyota": ["Toyota F1 logo.png", "Panasonic Toyota Racing logo.png",
               "Toyota Racing logo.png", "Toyota F1 Team logo.png",
               "Toyota Formula 1 logo.png", "Panasonic Toyota Racing logo.svg"],
    "honda": ["Honda Racing F1 Team logo.png", "Honda F1 logo.png",
              "Honda Racing F1 Team logo.svg", "Lucky Strike Honda logo.png",
              "Honda Racing logo.png"],
    "mf1": ["MF1 Racing logo.png", "Midland F1 logo.png", "MF1 Racing logo.svg",
            "Midland F1 Racing logo.png", "Midland Group logo.png"],
    "spyker_mf1": ["Spyker MF1 Team logo.png", "Spyker MF1 logo.png"],
    "spyker": ["Spyker F1 Team logo.png", "Spyker F1 logo.png",
               "Etihad Aldar Spyker F1 Team logo.png", "Spyker F1 Team logo.svg",
               "Spyker logo.png"],
    "super_aguri": ["Super Aguri F1 Team logo.png", "Super Aguri F1 logo.png",
                    "Super Aguri logo.png", "Super Aguri F1 Team logo.svg",
                    "Super Aguri-Honda logo.png"],
    "force_india": ["Force India F1 Team logo.png", "Force India F1 Team logo.svg",
                    "Force India logo.png", "Sahara Force India F1 Team logo.png",
                    "Force India Formula One Team logo.png"],
    "bmw_sauber": ["BMW Sauber logo.png", "BMW Sauber F1 Team logo.png",
                   "BMW Sauber logo.svg", "BMW Sauber F1 Team logo.svg"],
    "brawn": ["Brawn GP logo.png", "Brawn GP Formula One Team logo.png", "Brawn GP logo.svg"],
    "hrt": ["HRT F1 Team logo.png", "Hispania Racing F1 Team logo.png", "HRT F1 logo.png",
            "HRT Formula One Team logo.png", "Hispania Racing logo.png",
            "HRT F1 Team logo.svg"],
    "lotus_racing": ["Lotus Racing logo.png", "Lotus Racing logo.svg",
                     "Team Lotus logo.png", "Team Lotus logo.svg",
                     "Lotus Racing F1 logo.png"],
    "virgin": ["Virgin Racing logo.png", "Virgin Racing logo.svg",
               "Marussia Virgin Racing logo.png", "Virgin Racing F1 logo.png"],
    "caterham": ["Caterham F1 Team logo.png", "Caterham F1 Team logo.svg",
                 "Caterham logo.png", "Caterham F1 logo.png",
                 "Caterham F1 Team logo 2014.png"],
    "lotus_f1": ["Lotus F1 Team logo.png", "Lotus F1 Team logo.svg",
                 "Lotus Renault GP logo.png", "Lotus F1 logo.png",
                 "Lotus Renault GP logo.svg", "Lotus F1 Team logo 2015.png"],
    "marussia": ["Marussia F1 Team logo.png", "Marussia F1 Team logo.svg",
                 "Marussia logo.png", "Marussia F1 logo.png",
                 "Marussia Manor Racing logo.png"],
    "manor": ["Manor Marussia F1 Team logo.png", "Manor Racing logo.png",
              "Manor Marussia logo.png", "Manor MRT logo.png",
              "Manor Racing MRT logo.png"],
    "toro_rosso": ["Scuderia Toro Rosso logo.png", "Scuderia Toro Rosso logo.svg",
                   "Toro Rosso logo.png", "Scuderia Toro Rosso logo 2018.png",
                   "Scuderia AlphaTauri logo.svg"],
    "renault": ["Renault F1 logo.png", "Renault F1 Team logo.png", "Renault F1 Team logo.svg",
                "Renault Sport F1 Team logo.png", "Renault Sport Formula One Team logo.svg",
                "Mild Seven Renault F1 logo.png", "Renault Sport F1 Team logo.svg"],
    "ferrari": ["Scuderia Ferrari logo.png", "Scuderia Ferrari Marlboro logo.png",
                "Scuderia Ferrari logo.svg", "Ferrari logo.png", "Scuderia Ferrari logo.svg"],
    "mclaren": ["McLaren logo.png", "Vodafone McLaren Mercedes logo.png",
                "Team McLaren Mercedes logo.png", "McLaren F1 logo.svg",
                "West McLaren Mercedes logo.png", "McLaren Mercedes logo.png",
                "McLaren Racing logo.svg"],
    "williams": ["WilliamsF1 logo.png", "Williams F1 logo.png",
                 "Williams Grand Prix Engineering logo.png", "Williams F1 logo.svg",
                 "AT&T Williams logo.png", "Williams Racing logo.svg"],
    "sauber": ["Sauber Motorsport logo.svg", "Sauber logo.png", "Sauber Petronas logo.png",
               "Sauber F1 Team logo.png", "Sauber C1.svg"],
    "mercedes": ["Mercedes GP logo.png", "Mercedes AMG Petronas F1 Team logo.svg",
                 "Mercedes-Benz in Formula One logo.svg", "Mercedes AMG Petronas logo.png",
                 "Mercedes-Benz Petronas logo.png"],
    "red_bull": ["Red Bull Racing logo.png", "Red Bull Racing logo.svg",
                 "Infiniti Red Bull Racing logo.png", "Red Bull Racing Formula One Team logo.png",
                 "Red Bull Racing F1 logo.png", "Red Bull Racing logo 2016.png"],
    "haas": ["Haas F1 Team logo.png", "Haas F1 Team logo.svg",
             "Haas Formula One Team logo.png", "Haas Automation logo.svg"],
}

REPOS = ["wikipedia/en", "wikipedia/commons"]


def paths_for(fn):
    fn_u = fn.replace(" ", "_")
    h = hashlib.md5(fn_u.encode("utf-8")).hexdigest()
    for repo in REPOS:
        yield f"https://upload.wikimedia.org/{repo}/{h[0]}/{h[:2]}/{urllib.parse.quote(fn_u)}", repo


def try_fetch(cid, fn):
    for upurl, repo in paths_for(fn):
        proxied = "https://wsrv.nl/?url=" + urllib.parse.quote(upurl, safe="")
        try:
            req = urllib.request.Request(proxied, headers={"User-Agent": "curl/8"})
            with urllib.request.urlopen(req, timeout=30) as r:
                if r.status != 200:
                    continue
                ctype = r.headers.get("Content-Type", "")
                data = r.read()
                if not ctype.startswith("image") or len(data) < 800:
                    continue
                ext = ".svg" if "svg" in ctype or fn.lower().endswith(".svg") else ".png"
                out = os.path.join(OUT, f"{cid}{ext}")
                with open(out, "wb") as f:
                    f.write(data)
                return f"HIT  {cid:14s} {fn}  [{repo}] {len(data)}B {ctype}"
        except Exception:
            continue
    return None


jobs = [(cid, fn) for cid, fns in CANDIDATES.items() for fn in fns]
print(f"probing {len(jobs)} candidate filenames x {len(REPOS)} repos ...", flush=True)

results = {}
with ThreadPoolExecutor(max_workers=10) as ex:
    for res in ex.map(lambda j: try_fetch(*j), jobs):
        if res:
            print(res, flush=True)
            cid = res.split()[1]
            results.setdefault(cid, []).append(res)

print("\n=== summary ===")
missing = [cid for cid in CANDIDATES if cid not in results]
print("found:", sorted(results.keys()))
print("missing:", sorted(missing))
