# 一次性脚本：在 ECS 上运行
# 用 thefreedictionary（维基百科镜像）文章页提取 upload.wikimedia.org 图片 URL，
# 找到各历史车队条目里引用的队徽文件名
import re
import sys
import urllib.request

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"

# constructorId -> 镜像站文章标题
ARTICLES = {
    "jordan": "Jordan Grand Prix",
    "bar": "British American Racing",
    "benetton": "Benetton Formula",
    "jaguar": "Jaguar Racing (Formula One team)",
    "prost": "Prost Grand Prix",
    "toyota": "Toyota Racing",
    "arrows": "Arrows Grand Prix International",
    "minardi": "Minardi",
    "honda": "Honda Racing F1 Team",
    "mf1": "MF1 Racing",
    "spyker_mf1": "MF1 Racing",
    "spyker": "Spyker F1",
    "super_aguri": "Super Aguri F1",
    "bmw_sauber": "BMW Sauber",
    "brawn": "Brawn GP",
    "force_india": "Force India",
    "hrt": "HRT Formula 1 Team",
    "lotus_racing": "Team Lotus (2010–11)",
    "virgin": "Virgin Racing",
    "caterham": "Caterham F1",
    "lotus_f1": "Lotus F1 Team",
    "marussia": "Marussia F1 Team",
    "manor": "Manor Racing",
    "toro_rosso": "Scuderia Toro Rosso",
    "renault": "Renault in Formula One",
    "sauber": "Sauber Motorsport",
    "williams": "Williams Grand Prix Engineering",
    "ferrari": "Scuderia Ferrari",
    "mclaren": "McLaren",
    "mercedes": "Mercedes-Benz in Formula One",
    "red_bull": "Red Bull Racing",
    "haas": "Haas F1 Team",
}


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read().decode("utf-8", "ignore")


for cid, title in ARTICLES.items():
    url = "https://encyclopedia.thefreedictionary.com/" + urllib.parse.quote(title.replace(" ", "+"))
    try:
        html = fetch(url)
    except Exception as ex:
        print(f"{cid:14s} FETCH-FAIL {ex}")
        continue
    # 文章里的维基图片（带 /commons/ 或 /en/ 缩略图路径）
    imgs = sorted(set(re.findall(r"upload\.wikimedia\.org/wikipedia/(?:en|commons)/thumb/[0-9a-f]/[0-9a-f]{2}/([^/\"?]+)/", html)))
    logos = [f for f in imgs if "logo" in f.lower()]
    print(f"{cid:14s} {'; '.join(logos) if logos else '(no logo file: ' + '; '.join(imgs[:6]) + ')'}")
