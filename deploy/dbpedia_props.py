# 一次性脚本：在 ECS 上运行
# 导出 DBpedia 上 7 支车队条目的全部属性,找含文件名/图像的值
import json
import time
import urllib.request
import urllib.parse

TEAMS = [
    ("bmw_sauber", "BMW Sauber"),
    ("toro_rosso", "Scuderia Toro Rosso"),
    ("toyota", "Toyota Racing"),
    ("marussia", "Marussia F1 Team"),
    ("jaguar", "Jaguar Racing (Formula One team)"),
    ("sauber", "Sauber Motorsport"),
    ("lotus_racing", "Team Lotus (2010-11)"),
    ("super_aguri", "Super Aguri"),
    ("brawn", "Brawn GP"),
    ("hrt", "HRT Formula 1 Team"),
    ("caterham", "Caterham F1"),
]

for cid, article in TEAMS:
    res = "http://dbpedia.org/resource/" + urllib.parse.quote(article.replace(" ", "_"))
    q = "SELECT ?p ?v WHERE { <" + res + "> ?p ?v . FILTER(STRSTARTS(STR(?p), 'http://dbpedia.org/ontology/') || STRSTARTS(STR(?p), 'http://dbpedia.org/property/') || STRSTARTS(STR(?p), 'http://xmlns.com/foaf/')) }"
    data = urllib.parse.urlencode({"query": q, "format": "json"}).encode()
    req = urllib.request.Request("https://dbpedia.org/sparql", data=data,
                                 headers={"User-Agent": "f1-research/1.0",
                                          "Content-Type": "application/x-www-form-urlencoded",
                                          "Accept": "application/sparql-results+json"})
    try:
        d = json.load(urllib.request.urlopen(req, timeout=60))
    except Exception as ex:
        print(f"== {cid} ({article}) FAIL {ex}")
        time.sleep(1)
        continue
    print(f"== {cid} ({article})")
    for b in d["results"]["bindings"]:
        p = b["p"]["value"].rsplit("/", 1)[-1]
        v = b["v"]["value"]
        if any(k in (p + v).lower() for k in ["logo", "image", "thumb", "depict", "picture", "photo", "file"]):
            print(f"   {p:20s} {v[:110]}")
    time.sleep(0.6)
