# 一次性脚本：在 ECS 上运行
# 用 cn.bing 图片搜索的 async 接口采集 2000-2018 历史车队队徽候选图
# 每个车队多个查询词，每个查询取前若干条，优先下载原始图（murl，可达时），
# 失败则下载 Bing 缩略图（turl，国内 CDN 一定可达），供本地人工筛选
import json
import os
import re
import urllib.request
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
OUT = "/tmp/binglogos"
os.makedirs(OUT, exist_ok=True)

# constructorId -> 查询词列表
QUERIES = {
    "jordan": ["Jordan Honda F1 team logo", "乔丹F1车队"],
    "bar": ["British American Racing F1 logo", "英美车队F1"],
    "benetton": ["Benetton Formula F1 team logo", "贝纳通F1车队"],
    "jaguar": ["Jaguar Racing F1 team logo", "捷豹F1车队"],
    "prost": ["Prost Grand Prix logo"],
    "toyota": ["Panasonic Toyota Racing F1 logo", "丰田F1车队"],
    "super_aguri": ["Super Aguri F1 team logo", "超级亚久里车队"],
    "bmw_sauber": ["BMW Sauber F1 team logo", "宝马索伯F1车队"],
    "brawn": ["Brawn GP F1 logo", "布朗GP车队"],
    "force_india": ["Force India F1 team logo", "印度力量车队队徽"],
    "hrt": ["HRT F1 team logo", "Hispania Racing F1 Team logo"],
    "lotus_racing": ["Team Lotus 2010 F1 logo", "Lotus Racing F1 2010 logo"],
    "caterham": ["Caterham F1 Team logo", "卡特汉姆F1车队"],
    "lotus_f1": ["Lotus F1 Team logo", "Lotus Renault GP logo"],
    "marussia": ["Marussia F1 Team logo", "玛鲁西亚F1车队"],
    "manor": ["Manor Marussia F1 Team logo", "Manor Racing F1 logo"],
    "toro_rosso": ["Scuderia Toro Rosso logo", "红牛二队车队队徽"],
    "renault": ["Renault F1 Team logo", "雷诺F1车队队徽"],
    "sauber": ["Sauber Petronas F1 logo", "索伯车队队徽"],
    "williams": ["WilliamsF1 logo 2000s", "Williams BMW F1 team logo"],
    "mclaren": ["West McLaren Mercedes logo", "Vodafone McLaren Mercedes logo"],
    "mercedes": ["Mercedes GP Petronas F1 logo"],
}

manifest = {}


def bing_images(q, count=20):
    url = ("https://cn.bing.com/images/async?q=" + urllib.parse.quote(q)
           + f"&first=0&count={count}&mmasync=1")
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"})
    html = urllib.request.urlopen(req, timeout=25).read().decode("utf-8", "ignore")
    items = re.findall(r'm="({&quot;.*?})"', html)
    out = []
    for it in items:
        try:
            d = json.loads(it.replace("&quot;", '"').replace("&amp;", "&"))
            if d.get("murl"):
                out.append(d)
        except Exception:
            pass
    return out


def download(url, path):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": "https://cn.bing.com/"})
        with urllib.request.urlopen(req, timeout=12) as r:
            data = r.read()
        if len(data) < 1500 or len(data) > 4_000_000:
            return False
        with open(path, "wb") as f:
            f.write(data)
        return True
    except Exception:
        return False


def ext_of(url, ctype_hint=""):
    low = url.lower()
    for e in (".png", ".jpg", ".jpeg", ".webp", ".gif"):
        if e in low:
            return e[1:]
    return "png"


def harvest(cid, q):
    try:
        items = bing_images(q)
    except Exception as ex:
        print(f"{cid:14s} [{q}] SEARCH-FAIL {ex}")
        return
    got = 0
    for it in items:
        if got >= 5:
            break
        murl, turl = it["murl"], it.get("turl", "")
        host = murl.split("/")[2] if "://" in murl else "x"
        # 先尝试原图
        for src, url, tag in ((murl, murl, "orig"), (turl, turl, "thumb")):
            if not url:
                continue
            path = os.path.join(OUT, f"{cid}__{len(manifest.get(cid, [])):02d}_{tag}.{ext_of(url)}")
            if download(url, path):
                manifest.setdefault(cid, []).append(
                    {"file": os.path.basename(path), "query": q, "src": tag, "murl": murl[:300]})
                got += 1
                break
        else:
            continue
    print(f"{cid:14s} [{q}] items={len(items)} saved={got}")


jobs = [(cid, q) for cid, qs in QUERIES.items() for q in qs]
with ThreadPoolExecutor(max_workers=4) as ex:
    list(ex.map(lambda j: harvest(*j), jobs))

with open(os.path.join(OUT, "manifest.json"), "w", encoding="utf-8") as f:
    json.dump(manifest, f, ensure_ascii=False, indent=1)

total = sum(len(v) for v in manifest.values())
print(f"\nDONE total files: {total}")
print("teams with 0 files:", [cid for cid in QUERIES if not manifest.get(cid)])
