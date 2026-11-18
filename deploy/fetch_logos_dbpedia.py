# 一次性脚本：在 ECS 上运行
# DBpedia 查询车队条目的缩略图(含维基百科确切文件名) -> wsrv.nl 代理下载到 /tmp/oldlogos2
import hashlib
import json
import os
import time
import urllib.request
import urllib.parse

UA = "f1-site-research/1.0"
OUT = "/tmp/oldlogos2"
os.makedirs(OUT, exist_ok=True)

# constructorId -> DBpedia 文章名候选(依次尝试)
ARTICLES = {
    "jordan": ["Jordan Grand Prix"],
    "bar": ["British American Racing"],
    "benetton": ["Benetton Formula"],
    "jaguar": ["Jaguar Racing (Formula One team)", "Jaguar Racing"],
    "prost": ["Prost Grand Prix"],
    "toyota": ["Toyota Racing"],
    "super_aguri": ["Super Aguri", "Super Aguri F1"],
    "bmw_sauber": ["BMW Sauber"],
    "brawn": ["Brawn GP"],
    "force_india": ["Force India"],
    "hrt": ["HRT Formula 1 Team", "Hispania Racing"],
    "lotus_racing": ["Team Lotus (2010–11)", "Lotus Racing"],
    "virgin": ["Virgin Racing"],
    "caterham": ["Caterham F1", "Caterham F1 Team"],
    "lotus_f1": ["Lotus F1 Team", "Lotus Renault GP"],
    "marussia": ["Marussia F1 Team", "Marussia Virgin Racing"],
    "manor": ["Manor Racing", "Manor Marussia F1 Team"],
    "toro_rosso": ["Scuderia Toro Rosso"],
    "renault": ["Renault in Formula One", "Renault F1"],
    "sauber": ["Sauber Motorsport"],
    "williams": ["Williams Grand Prix Engineering", "WilliamsF1"],
    "mclaren": ["McLaren"],
    "mercedes": ["Mercedes-Benz in Formula One", "Mercedes AMG Petronas Formula One Team"],
    "ferrari": ["Scuderia Ferrari"],
    "red_bull": ["Red Bull Racing"],
    "renault_2000s": ["Renault F1"],
    "lotus_f1_2012": ["Lotus F1 Team"],
}

REPOS = ["wikipedia/commons", "wikipedia/en"]


def dbpedia_thumb(article):
    """返回 DBpedia dbo:thumbnail 的 Special:FilePath 文件名(或 None)。"""
    res = "http://dbpedia.org/resource/" + urllib.parse.quote(article.replace(" ", "_"))
    q = ("SELECT ?thumb WHERE { <" + res + "> <http://dbpedia.org/ontology/thumbnail> ?thumb } LIMIT 3")
    data = urllib.parse.urlencode({"query": q, "format": "json"}).encode()
    req = urllib.request.Request("https://dbpedia.org/sparql", data=data,
                                 headers={"User-Agent": UA,
                                          "Content-Type": "application/x-www-form-urlencoded",
                                          "Accept": "application/sparql-results+json"})
    try:
        d = json.load(urllib.request.urlopen(req, timeout=45))
    except Exception as ex:
        return None, f"ERR {ex}"
    for b in d.get("results", {}).get("bindings", []):
        u = b.get("thumb", {}).get("value", "")
        if "Special:FilePath/" in u:
            return urllib.parse.unquote(u.split("Special:FilePath/")[1].split("?")[0]), None
    return None, "no-thumb"


def wikimedia_download(fn):
    """按 MD5 路径经 wsrv.nl 从 commons/en 下载,返回 (bytes, ext) 或 (None, None)。"""
    fn_u = fn.replace(" ", "_")
    h = hashlib.md5(fn_u.encode("utf-8")).hexdigest()
    ext = ".svg" if fn_u.lower().endswith(".svg") else (
        ".jpg" if fn_u.lower().endswith((".jpg", ".jpeg")) else ".png")
    for repo in REPOS:
        up = f"https://upload.wikimedia.org/{repo}/{h[0]}/{h[:2]}/{urllib.parse.quote(fn_u)}"
        proxied = "https://wsrv.nl/?url=" + urllib.parse.quote(up, safe="")
        try:
            req = urllib.request.Request(proxied, headers={"User-Agent": "curl/8"})
            with urllib.request.urlopen(req, timeout=40) as r:
                data = r.read()
                ctype = r.headers.get("Content-Type", "")
            if r.status == 200 and ctype.startswith("image") and len(data) > 800:
                # svg 也请求一份 png 渲染版(小徽标用 png 兼容性更好)
                return (data, ext), (repo, fn)
        except Exception:
            continue
    return (None, None), (None, fn)


found, missing = {}, []
for cid, arts in ARTICLES.items():
    hit = None
    note = []
    for a in arts:
        fn, err = dbpedia_thumb(a)
        if err:
            note.append(f"{a}:{err}")
            time.sleep(0.4)
            continue
        (data, ext), (repo, used) = wikimedia_download(fn)
        if data:
            path = os.path.join(OUT, f"{cid}{ext}")
            with open(path, "wb") as f:
                f.write(data)
            hit = (a, used, repo, len(data))
            break
        note.append(f"{a}:{fn} download-fail")
        time.sleep(0.4)
    if hit:
        found[cid] = hit
        print(f"HIT  {cid:16s} <- {hit[0]:45s} {hit[1]} [{hit[2]}] {hit[3]}B")
    else:
        missing.append(cid)
        print(f"MISS {cid:16s} {'; '.join(note)[:120]}")

print("\nfound:", len(found), "missing:", missing)
