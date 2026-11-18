"""车手头像与车队队徽/颜色。

数据源：
- 车手头像：F1 官方 CDN（media.formula1.com，国内可访问）按赛季分目录存放
  官方头像：common/f1/{年}/{车队}/{编码}/{年}{车队}{编码}right.webp，
  与 formula1.com 官网页面所用图片完全一致。CDN 仅保留 2024 及以后赛季，
  因此 2024 起显示官方头像，更早赛季回退彩色首字母徽章。
  已结束的 2024/2025 赛季用预生成、经校验的静态映射
  （backend/headshots_static.json，一次性脚本 deploy/build_headshots_static.py）；
  当前及未来赛季运行时抓取官网 results/{年}/drivers 页面解析（缓存 30 天）。
  车手编码由姓名推导（名字前3 + 姓氏前3 + 01，如 lewham01），与官网一致。
- 车队队徽：本地静态资源 frontend/assets/team-logos/*.png。2024 起为现行
  F1 官方彩色队徽（一次性脚本 deploy/fetch_colored_logos.py 下载）；
  2019-2023 为当年旧版官网队徽（一次性脚本 deploy/fetch_historic_logos.py
  下载，文件名 h{年}-{slug}.png）；1958-2018 为维基百科/DBpedia/bing 等
  来源的老队徽（old-*.png，一次性脚本 deploy/fetch_logos_v4~v7*.py 下载并
  人工校验，查不到的年代回退 2019 旧版队徽，再没有回退
  「队名首字母 + 车队色」徽章）。
"""
import json
import re
import threading
import time
import unicodedata
from pathlib import Path

import requests

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_CACHE_FILE = DATA_DIR / "headshots.json"
_STATIC_FILE = Path(__file__).resolve().parent / "headshots_static.json"

# 头像最早可用赛季（CDN 上 2023 及更早已删除）
HEADSHOT_MIN_SEASON = 2024

# Cloudinary 变换：人脸居中裁剪，z_0.6 拉远镜头，露出头和较大范围上身
IMG_TF = "c_thumb,g_face,w_96,h_96,z_0.6"
CDN = f"https://media.formula1.com/image/upload/{IMG_TF}/q_auto/v1740000001/common/f1"
PAGE_URL = "https://www.formula1.com/en/results/{year}/drivers"

# 官网车队目录名（仅用于页面抓取失败时按车队直接构造地址的兜底）
YEAR_SLUGS = {
    2024: {"mercedes": "mercedes", "ferrari": "ferrari", "mclaren": "mclaren",
           "red_bull": "redbullracing", "rb": "rb", "alpine": "alpine",
           "haas": "haasf1team", "williams": "williams",
           "aston_martin": "astonmartin", "sauber": "kicksauber"},
    2025: {"mercedes": "mercedes", "ferrari": "ferrari", "mclaren": "mclaren",
           "red_bull": "redbullracing", "rb": "racingbulls", "alpine": "alpine",
           "haas": "haasf1team", "williams": "williams",
           "aston_martin": "astonmartin", "sauber": "kicksauber"},
    2026: {"mercedes": "mercedes", "ferrari": "ferrari", "mclaren": "mclaren",
           "red_bull": "redbullracing", "rb": "racingbulls", "alpine": "alpine",
           "haas": "haasf1team", "audi": "audi", "williams": "williams",
           "aston_martin": "astonmartin", "cadillac": "cadillac"},
}

# constructorId -> (队徽文件名, 车队主色)
# 队徽为 F1 官方彩色版（media.formula1.com，一次性脚本 deploy/fetch_colored_logos.py 下载）
TEAMS = {
    "mercedes": ("mercedes.png", "#00D7B6"),
    "ferrari": ("ferrari.png", "#ED1131"),
    "mclaren": ("mclaren.png", "#F47600"),
    "red_bull": ("red_bull.png", "#4781D7"),
    "rb": ("rb.png", "#6C98FF"),
    "alphatauri": (None, "#2E4E6F"),
    "toro_rosso": (None, "#469BFF"),
    "racing_point": (None, "#F596C8"),
    "renault": (None, "#F7E017"),
    "alpine": ("alpine.png", "#00A1E8"),
    "haas": ("haas.png", "#9C9FA2"),
    "audi": ("audi.png", "#F50537"),
    "williams": ("williams.png", "#1868DB"),
    "aston_martin": ("aston_martin.png", "#229971"),
    "cadillac": ("cadillac.png", "#909090"),
    "sauber": (None, "#4DD52E"),
    "alfa": (None, "#9E0000"),
}

# 2019-2023 各赛季 constructorId -> 官网目录名
# （队徽为旧版官网资源，一次性脚本 deploy/fetch_historic_logos.py 下载，
#   文件名 h{年}-{slug}.png；2018 及更早 CDN 已清除）
HIST_GRIDS = {
    2019: {"mercedes": "mercedes", "ferrari": "ferrari", "red_bull": "red-bull-racing",
           "mclaren": "mclaren", "renault": "renault", "racing_point": "racing-point",
           "toro_rosso": "toro-rosso", "alfa": "alfa-romeo-racing",
           "haas": "haas-f1-team", "williams": "williams"},
    2020: {"mercedes": "mercedes", "ferrari": "ferrari", "red_bull": "red-bull-racing",
           "mclaren": "mclaren", "renault": "renault", "racing_point": "racing-point",
           "alphatauri": "alphatauri", "alfa": "alfa-romeo-racing",
           "haas": "haas-f1-team", "williams": "williams"},
    2021: {"mercedes": "mercedes", "ferrari": "ferrari", "red_bull": "red-bull-racing",
           "mclaren": "mclaren", "alpine": "alpine", "aston_martin": "aston-martin",
           "alphatauri": "alphatauri", "alfa": "alfa-romeo-racing",
           "haas": "haas-f1-team", "williams": "williams"},
    2022: {"mercedes": "mercedes", "ferrari": "ferrari", "red_bull": "red-bull-racing",
           "mclaren": "mclaren", "alpine": "alpine", "aston_martin": "aston-martin",
           "alphatauri": "alphatauri", "alfa": "alfa-romeo-racing",
           "haas": "haas-f1-team", "williams": "williams"},
    2023: {"mercedes": "mercedes", "ferrari": "ferrari", "red_bull": "red-bull-racing",
           "mclaren": "mclaren", "alpine": "alpine", "aston_martin": "aston-martin",
           "alphatauri": "alphatauri", "alfa": "alfa-romeo-racing",
           "haas": "haas-f1-team", "williams": "williams"},
}

HIST_MIN_SEASON, HIST_MAX_SEASON = 2019, 2023
LOGO_MIN_SEASON = 2024  # 现行队徽（TEAMS）适用赛季
OLD_MIN_SEASON = 1958  # 老队徽最早适用赛季（1958 年车队积分榜开始）

# 2000-2018 老队徽（维基百科等来源，脚本下载并人工校验）
# constructorId -> [(文件名, 起始赛季, 结束赛季), ...]
OLD_LOGOS = {
    # ---- 1958-1999（v6/v7 批次下载并人工校验）----
    "ags": [("old-ags.png", 1986, 1991)],
    "amon": [("old-amon.png", 1974, 1974)],
    "brabham": [("old-brabham.png", 1962, 1992)],
    "brm": [("old-brm.png", 1958, 1977)],
    "connaught": [("old-connaught.png", 1958, 1959)],
    "cooper": [("old-cooper.png", 1958, 1969)],
    "dallara": [("old-dallara.png", 1988, 1992)],
    "de_tomaso": [("old-de-tomaso.png", 1961, 1970)],
    "eagle": [("old-eagle.png", 1966, 1969)],
    "ensign": [("old-ensign.png", 1973, 1982)],
    "eurobrun": [("old-eurobrun.png", 1988, 1990)],
    "fittipaldi": [("old-fittipaldi.png", 1975, 1982)],
    "fondmetal": [("old-fondmetal.png", 1991, 1992)],
    "footwork": [("old-footwork.png", 1991, 1996)],
    "forti": [("old-forti.png", 1995, 1996)],
    "hesketh": [("old-hesketh.png", 1974, 1978)],
    "iso_marlboro": [("old-iso-marlboro.png", 1973, 1974)],
    "kojima": [("old-kojima.png", 1976, 1977)],
    "kurtis_kraft": [("old-kurtis-kraft.png", 1959, 1959)],
    "lambo": [("old-lambo.png", 1991, 1991)],
    "larrousse": [("old-larrousse.png", 1987, 1994)],
    "leyton": [("old-leyton.png", 1990, 1991)],
    "ligier": [("old-ligier.png", 1976, 1996)],
    "lola": [("old-lola.png", 1962, 1993)],
    "maki": [("old-maki.png", 1975, 1975)],
    "march": [("old-march.png", 1970, 1992)],
    "maserati": [("old-maserati.png", 1958, 1960)],
    "matra": [("old-matra.png", 1967, 1972)],
    "moda": [("old-moda.png", 1992, 1992)],
    "onyx": [("old-onyx.png", 1989, 1990)],
    "osella": [("old-osella.png", 1980, 1990)],
    "pacific": [("old-pacific.png", 1994, 1995)],
    "parnelli": [("old-parnelli.png", 1974, 1976)],
    "penske": [("old-penske.png", 1974, 1977)],
    "porsche": [("old-porsche.png", 1958, 1964)],
    "ram": [("old-ram.png", 1983, 1985)],
    "rebaque": [("old-rebaque.png", 1979, 1979)],
    "renault": [("old-renault-diamond.png", 1977, 1985),
                ("old-renault.svg", 2000, 2011)],
    "rial": [("old-rial.png", 1988, 1989)],
    "shadow": [("old-shadow.png", 1973, 1980)],
    "simtek": [("old-simtek.png", 1994, 1995)],
    "stewart": [("old-stewart.png", 1997, 1999)],
    "surtees": [("old-surtees.png", 1970, 1978)],
    "team_lotus": [("old-team-lotus.png", 1958, 1994)],
    "tecno": [("old-tecno.png", 1972, 1973)],
    "theodore": [("old-theodore.png", 1978, 1983)],
    "toleman": [("old-toleman.png", 1981, 1985)],
    "tyrrell": [("old-tyrrell.png", 1970, 1998)],
    "vanwall": [("old-vanwall.png", 1958, 1960)],
    "williams": [("old-williams.png", 1975, 1999)],
    "wolf": [("old-wolf.png", 1976, 1979)],
    "zakspeed": [("old-zakspeed.png", 1985, 1989)],
    "ats": [("old-ats.png", 1963, 1984)],
    # ---- 2000-2018（v4/v5 批次下载并人工校验）----
    "arrows": [("old-arrows.png", 1978, 2002)],
    "bar": [("old-bar.png", 1999, 2005)],
    "benetton": [("old-benetton.png", 1986, 2001)],
    "jordan": [("old-jordan.png", 1991, 2005)],
    "minardi": [("old-minardi.png", 1985, 2005)],
    "prost": [("old-prost.png", 1997, 2001)],
    "sauber": [("old-sauber.png", 1993, 2005), ("old-sauber-2010s.png", 2010, 2018)],
    "jaguar": [("old-jaguar.png", 2000, 2004)],
    "toyota": [("old-toyota.png", 2002, 2009)],
    "honda": [("old-honda.png", 2006, 2008)],
    "mf1": [("old-mf1.png", 2006, 2006)],
    "spyker_mf1": [("old-spyker-mf1.png", 2006, 2007)],
    "spyker": [("old-spyker.png", 2007, 2007)],
    "super_aguri": [("old-super-aguri.png", 2006, 2008)],
    "bmw_sauber": [("old-bmw-sauber.png", 2006, 2009)],
    "brawn": [("old-brawn.png", 2009, 2009)],
    "force_india": [("old-force-india.svg", 2008, 2018)],
    "toro_rosso": [("old-toro-rosso.png", 2006, 2018)],
    "hrt": [("old-hrt.png", 2010, 2012)],
    "lotus_racing": [("old-lotus-racing.png", 2010, 2011)],
    "virgin": [("old-virgin.png", 2010, 2011)],
    "caterham": [("old-caterham.png", 2012, 2014)],
    "lotus_f1": [("old-lotus-f1.png", 2012, 2015)],
    "marussia": [("old-marussia.png", 2012, 2014)],
    "manor": [("old-manor.png", 2016, 2017)],
    "mclaren": [("old-mclaren.png", 1966, 2013)],
    "haas": [("old-haas.png", 2016, 2018)],
}

# 引擎后缀年代（如 cooper-climax、lotus-ford）的车队别名 → 基础车队
ALIASES = {
    "lotus": "team_lotus",
    "tomaso": "de_tomaso",
}


def _base_cid(constructor_id):
    """把「车队-引擎」形式的 constructorId 归一到基础车队，供老赛季查队徽。"""
    cid = constructor_id or ""
    if "-" in cid:
        cid = cid.split("-", 1)[0]
    return ALIASES.get(cid, cid)

_lock = threading.Lock()
_scrape_mem = {}  # season(int) -> {"expires": float, "map": {f1code: url}}
_static = None


def logo_for(constructor_id, season):
    """返回队徽静态路径（或 None）与车队色。

    2019-2023 用当年官方队徽（h{年}-{slug}.png），2024 起用现行队徽，
    1958-2018 用老队徽（old-*.png，含「车队-引擎」后缀归一，
    查不到回退 2019 旧版队徽），1958 年以前回退车队色徽章。
    """
    try:
        season = int(season)
    except (TypeError, ValueError):
        season = 0
    logo = None
    if HIST_MIN_SEASON <= season <= HIST_MAX_SEASON:
        slug = HIST_GRIDS.get(season, {}).get(constructor_id)
        if slug:
            logo = f"/assets/team-logos/h{season}-{slug}.png"
    elif season >= LOGO_MIN_SEASON:
        logo = TEAMS.get(constructor_id, (None, None))[0]
        if logo:
            logo = "/assets/team-logos/" + logo
    elif season >= OLD_MIN_SEASON:
        base = _base_cid(constructor_id)
        for fn, lo, hi in OLD_LOGOS.get(base, []):
            if lo <= season <= hi:
                logo = "/assets/team-logos/" + fn
                break
        if not logo:
            slug = HIST_GRIDS.get(2019, {}).get(base)
            if slug:
                logo = f"/assets/team-logos/h2019-{slug}.png"
    color = TEAMS.get(constructor_id, (None, None))[1]
    return logo, color or "#3a4170"


# ---------------- 车手头像 ----------------

def _norm(s):
    """去变音符、只留字母、转小写。"""
    s = unicodedata.normalize("NFKD", str(s or ""))
    return "".join(ch for ch in s if ch.isascii() and ch.isalpha()).lower()


def f1_code(given_name, family_name):
    """官网车手编码：名字前3 + 姓氏前3 + 01（如 lewham01）。"""
    g = _norm(given_name).split()
    f = _norm(family_name).split()
    if not g or not f:
        return ""
    return g[0][:3] + f[0][:3] + "01"


def _static_maps():
    """预生成并校验过的 {赛季: {编码: 头像URL}}。"""
    global _static
    if _static is None:
        try:
            _static = json.loads(_STATIC_FILE.read_text(encoding="utf-8"))
        except Exception:
            _static = {}
    return _static


def _load_disk():
    try:
        return json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_disk(data):
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        _CACHE_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def _scrape_year(season):
    """抓取官网 results/{年}/drivers 页面，返回 {编码: 头像URL}（无图返回 {}）。"""
    try:
        season = int(season)
    except (TypeError, ValueError):
        return {}
    now = time.time()
    with _lock:
        hit = _scrape_mem.get(season)
        if hit is None:
            disk = _load_disk().get("v5|" + str(season))
            hit = disk if isinstance(disk, dict) and disk.get("expires", 0) > now else None
        if hit and hit["expires"] > now:
            return hit["map"]
    try:
        resp = requests.get(
            PAGE_URL.format(year=season),
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) F1DataCenter/1.0"},
            timeout=20,
        )
        resp.raise_for_status()
        urls = set(re.findall(
            r'https://media\.formula1\.com/image/upload/[^\s"\'<>]+\.webp', resp.text))
    except Exception:
        return {}
    out = {}
    for u in urls:
        m = re.search(
            rf"common/f1/{season}/([a-z0-9]+)/([a-z0-9]+)/{season}\1\2(right|left)\.webp", u)
        if not m:
            continue
        code, side = m.group(2), m.group(3)
        clean = re.sub(r"d_[^/]+/", "", u)  # 去掉缺省占位剪影参数，缺图交给前端回退徽章
        # 统一换成人脸居中裁剪，圆圈头像里脸居中
        clean = re.sub(r"c_(?:lfill|fill|thumb)(?:,g_face)?,w_\d+(?:,h_\d+)?(?:,z_[\d.]+)?", IMG_TF, clean)
        if code not in out or side == "right":
            out[code] = clean
    if out:
        expires = now + 30 * 86400
        with _lock:
            _scrape_mem[season] = {"expires": expires, "map": out}
            disk = _load_disk()
            disk["v5|" + str(season)] = {"expires": expires, "map": out}
            _save_disk(disk)
    return out


def headshot_for(given_name, family_name, season, constructor_id=None):
    """车手官方头像 URL；找不到返回 None（前端回退车队色徽章）。"""
    try:
        season = int(season)
    except (TypeError, ValueError):
        return None
    if season < HEADSHOT_MIN_SEASON:
        return None
    code = f1_code(given_name, family_name)
    if not code:
        return None
    static = _static_maps().get(str(season))
    if static is not None:
        return static.get(code)
    scraped = _scrape_year(season)
    if scraped:
        return scraped.get(code)
    # 兜底：按车队目录名直接构造（页面抓取失败时）
    slug = (YEAR_SLUGS.get(season) or {}).get(constructor_id or "")
    if not slug:
        return None
    return f"{CDN}/{season}/{slug}/{code}/{season}{slug}{code}right.webp"
