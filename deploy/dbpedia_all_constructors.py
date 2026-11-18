# 一次性脚本：在 ECS 上运行
# DBpedia 按 Formula One constructors 分类查所有车队条目缩略图文件名
import urllib.request
import urllib.parse
import json

q = """
PREFIX dbo: <http://dbpedia.org/ontology/>
PREFIX dbc: <http://dbpedia.org/resource/Category:>
PREFIX dct: <http://purl.org/dc/terms/>
SELECT ?r ?thumb WHERE {
  ?r dct:subject dbc:Formula_One_constructors .
  OPTIONAL { ?r dbo:thumbnail ?thumb }
} ORDER BY ?r LIMIT 60 OFFSET %d
"""
rows = []
for off in range(0, 300, 60):
    data = urllib.parse.urlencode({"query": q % off, "format": "json"}).encode()
    req = urllib.request.Request("https://dbpedia.org/sparql", data=data,
        headers={"User-Agent": "f1-research/1.0", "Content-Type": "application/x-www-form-urlencoded",
                 "Accept": "application/sparql-results+json"})
    d = json.load(urllib.request.urlopen(req, timeout=90))
    b = d["results"]["bindings"]
    if not b:
        break
    rows.extend(b)
print("total:", len(rows))
for b in rows:
    r = b["r"]["value"].rsplit("/", 1)[-1]
    t = b.get("thumb", {}).get("value", "")
    fn = urllib.parse.unquote(t.split("Special:FilePath/")[-1].split("?")[0]) if t else "-"
    print(f"{r}\t{fn}")
