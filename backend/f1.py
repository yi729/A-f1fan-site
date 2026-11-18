"""F1 数据（Jolpica / Ergast 维护分支）抓取与聚合。"""
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

import requests

import images

BASE = "https://api.jolpi.ca/ergast/f1"
DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# 简单内存缓存：key -> (过期时间戳, 数据)
_cache = {}


def _pos(entry):
    """安全取排名：老赛季 0 分车手/车队没有 position 字段，只有 positionText（'-'）。"""
    return entry.get("position") or entry.get("positionText") or "-"


def _rank(value):
    """把排名转 int 用于排序；异常值排到末尾。"""
    try:
        return int(value)
    except (TypeError, ValueError):
        return 10 ** 9


def _get(path, params=None, ttl=300):
    params = params or {}
    key = path + "|" + "&".join(f"{k}={v}" for k, v in sorted(params.items()))
    now = time.time()
    hit = _cache.get(key)
    if hit and hit[0] > now:
        return hit[1]
    url = BASE + path
    last_exc = None
    for attempt in range(4):
        try:
            resp = requests.get(url, params=params, timeout=30)
            if resp.status_code == 429:
                last_exc = requests.exceptions.RequestException(
                    "429 rate limited: " + url)
                time.sleep(5.0 * (attempt + 1))
                continue
            resp.raise_for_status()
            data = resp.json()
            _cache[key] = (time.time() + ttl, data)
            return data
        except requests.exceptions.RequestException as exc:
            last_exc = exc
            if attempt < 3:
                time.sleep(1.0 * (attempt + 1))
    raise last_exc


def _paginate(path, limit=100, ttl=86400):
    """分页抓取，返回合并后的列表（依据不同路径自动识别列表键）。

    Jolpica 单页上限为 100，这里按实际返回条数推进 offset，避免漏抓。
    """
    items = []
    offset = 0
    while True:
        data = _get(path, {"limit": str(limit), "offset": str(offset)}, ttl=ttl)
        mr = data["MRData"]
        if "RaceTable" in mr:
            batch = mr["RaceTable"]["Races"]
        elif "DriverTable" in mr:
            batch = mr["DriverTable"]["Drivers"]
        elif "StandingsTable" in mr:
            batch = mr["StandingsTable"]["StandingsLists"]
        else:
            batch = []
        items.extend(batch)
        total = int(mr["total"])
        offset += len(batch)
        if offset >= total or not batch:
            break
    return items


def get_seasons():
    data = _get("/seasons.json", {"limit": "100"}, ttl=86400)
    return [int(s["season"]) for s in data["MRData"]["SeasonTable"]["Seasons"]]


def get_all_drivers():
    drivers = _paginate("/drivers.json")
    return [
        {
            "driverId": d["driverId"],
            "code": d.get("code", ""),
            "givenName": d.get("givenName", ""),
            "familyName": d.get("familyName", ""),
            "nationality": d.get("nationality", ""),
            "dob": d.get("dateOfBirth", ""),
        }
        for d in drivers
    ]


def get_season_extras(season, up_to_round=None):
    """聚合赛季内各车手/车队的领奖台与杆位数（可截至某分站）。

    结果按条分页（跨页拆分的比赛会重复出现），按 driverId 累加即可，
    不会重复计数。MRData.total 统计的是结果条数而非比赛数。
    """
    drivers = {}
    constructors = {}
    offset = 0
    while True:
        data = _get(
            f"/{season}/results.json",
            {"limit": "100", "offset": str(offset)},
            ttl=86400,
        )
        mr = data["MRData"]
        races = mr["RaceTable"]["Races"]
        total = int(mr["total"])
        batch_total = 0
        if up_to_round is not None and races and int(races[0]["round"]) > up_to_round:
            break  # 结果按分站顺序排列，后面都在范围外
        for r in races:
            for res in r.get("Results", []):
                batch_total += 1
                if up_to_round is not None and int(r["round"]) > up_to_round:
                    continue
                pos = int(res.get("position") or res.get("positionText") or 0)
                did = res["Driver"]["driverId"]
                cid = res["Constructor"]["constructorId"]
                d = drivers.setdefault(did, {"podiums": 0, "poles": 0})
                c = constructors.setdefault(cid, {"podiums": 0, "poles": 0})
                if pos <= 3:
                    d["podiums"] += 1
                    c["podiums"] += 1
                if res.get("grid") == "1":
                    d["poles"] += 1
                    c["poles"] += 1
        offset += batch_total
        if offset >= total or not races or batch_total == 0:
            break
    return {"drivers": drivers, "constructors": constructors}


def get_driver_standings(season=None, round_no=None):
    """车手积分榜。season 为空取当前赛季；round 为空取赛季最终/最新积分。"""
    if season is None:
        data = _get("/current/driverStandings.json", {"limit": "100"}, ttl=300)
    elif round_no is not None:
        data = _get(f"/{season}/{round_no}/driverStandings.json", {"limit": "100"}, ttl=86400)
    else:
        data = _get(f"/{season}/driverStandings.json", {"limit": "100"}, ttl=86400)
    lists = data["MRData"]["StandingsTable"]["StandingsLists"]
    if not lists:
        return []
    season = lists[0].get("season")
    extras = get_season_extras(season, round_no)["drivers"]
    out = []
    for s in lists[0].get("DriverStandings", []):
        d = s["Driver"]
        c = s.get("Constructors") or [{}]
        ex = extras.get(d["driverId"], {"podiums": 0, "poles": 0})
        cid = c[0].get("constructorId", "")
        logo, color = images.logo_for(cid, season)
        out.append({
            "season": season,
            "position": _pos(s),
            "points": s["points"],
            "wins": s["wins"],
            "podiums": ex["podiums"],
            "poles": ex["poles"],
            "driverId": d["driverId"],
            "code": d.get("code", ""),
            "name": f'{d.get("givenName", "")} {d.get("familyName", "")}',
            "nationality": d.get("nationality", ""),
            "constructor": c[0].get("name", ""),
            "constructorId": cid,
            "teamLogo": logo,
            "teamColor": color,
            "headshot": images.headshot_for(
                d.get("givenName", ""), d.get("familyName", ""), season, cid),
        })
    return out


def get_current_driver_standings():
    return get_driver_standings(None, None)


def get_constructor_standings(season=None, round_no=None):
    """车队积分榜。参数含义同车手积分榜。"""
    if season is None:
        data = _get("/current/constructorStandings.json", {"limit": "100"}, ttl=300)
    elif round_no is not None:
        data = _get(f"/{season}/{round_no}/constructorStandings.json", {"limit": "100"}, ttl=86400)
    else:
        data = _get(f"/{season}/constructorStandings.json", {"limit": "100"}, ttl=86400)
    lists = data["MRData"]["StandingsTable"]["StandingsLists"]
    if not lists:
        return []
    season = lists[0].get("season")
    extras = get_season_extras(season, round_no)["constructors"]
    out = []
    for s in lists[0].get("ConstructorStandings", []):
        c = s["Constructor"]
        ex = extras.get(c["constructorId"], {"podiums": 0, "poles": 0})
        logo, color = images.logo_for(c["constructorId"], season)
        out.append({
            "season": season,
            "position": _pos(s),
            "points": s["points"],
            "wins": s["wins"],
            "podiums": ex["podiums"],
            "poles": ex["poles"],
            "constructorId": c["constructorId"],
            "name": c["name"],
            "nationality": c.get("nationality", ""),
            "logo": logo,
            "color": color,
        })
    return out


def get_current_constructor_standings():
    return get_constructor_standings(None, None)


def get_season_races(season):
    """赛季分站列表（含未开赛的分站），供前端做分站筛选。"""
    data = _get(f"/{season}.json", {"limit": "100"}, ttl=86400)
    races = data["MRData"]["RaceTable"]["Races"]
    out = []
    for r in races:
        out.append({
            "season": r["season"],
            "round": r["round"],
            "raceName": r["raceName"],
            "circuit": r["Circuit"]["circuitName"],
            "country": r["Circuit"]["Location"]["country"],
            "date": r["date"],
        })
    return out


def _round_standings(season, round_no, kind):
    """单站积分榜（kind: driver/constructor）；未开赛/取消的分站返回 None。"""
    data = _get(
        f"/{season}/{round_no}/{kind}Standings.json", {"limit": "100"}, ttl=86400)
    lists = data["MRData"]["StandingsTable"]["StandingsLists"]
    if not lists or not lists[0].get(
            "DriverStandings" if kind == "driver" else "ConstructorStandings"):
        return None
    return lists[0]


def _trend_cache_path(season):
    return DATA_DIR / f"trend_{season}.json"


_trend_locks = {}
_trend_locks_guard = threading.Lock()


def _read_trend_cache(season, path):
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if raw.get("season") == season:
            return raw
    except Exception:
        return None
    return None


def get_points_trend(season):
    """逐站累计积分走势（车手 + 车队）。

    按分站取官方积分榜（含冲刺赛积分；results 接口不含冲刺行，
    自行累加会少算），已结束的分站从 R1 起连续，遇到首个无数据
    的分站即停止。车队积分直接用官方车队积分榜（车手季中转队时
    积分归属原车队，按车手当前车队聚合会错）。

    结果落盘缓存：已结束赛季永久缓存，进行中赛季 24h（避免每次
    服务重启后为 40+ 个请求打 Jolpica）。同赛季并发请求共享一把
    锁，只构建一次（构建约 30s，避免多请求同时打爆上游限流）。
    """
    try:
        season = int(season)
    except (TypeError, ValueError):
        return {"season": 0, "rounds": [], "drivers": [], "constructors": []}
    races = get_season_races(season)
    if not races:
        return {"season": season, "rounds": [], "drivers": [], "constructors": []}
    path = _trend_cache_path(season)
    cached = _read_trend_cache(season, path)
    today = date.today().isoformat()
    finished = all((r["date"] or "") < today for r in races)
    if cached and (finished or time.time() - cached.get("fetched_at", 0) < 86400):
        return {
            "season": cached["season"],
            "rounds": cached["rounds"],
            "drivers": cached["drivers"],
            "constructors": cached["constructors"],
        }
    with _trend_locks_guard:
        lock = _trend_locks.setdefault(season, threading.Lock())
    with lock:
        cached = _read_trend_cache(season, path)  # 双检：等待期间可能已由他人建成
        if cached and (finished or time.time() - cached.get("fetched_at", 0) < 86400):
            return {
                "season": cached["season"],
                "rounds": cached["rounds"],
                "drivers": cached["drivers"],
                "constructors": cached["constructors"],
            }
        try:
            out = _build_trend(season, races)
        except Exception:
            if cached:  # 网络失败时用旧缓存兜底
                return {
                    "season": cached["season"],
                    "rounds": cached["rounds"],
                    "drivers": cached["drivers"],
                    "constructors": cached["constructors"],
                }
            raise
        out["fetched_at"] = time.time()
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass
    return {
        "season": out["season"],
        "rounds": out["rounds"],
        "drivers": out["drivers"],
        "constructors": out["constructors"],
    }


def _build_trend(season, races):
    rounds_data = {}  # round -> {"drivers": [...], "constructors": [...]}
    for start in range(1, len(races) + 1, 4):
        batch = list(range(start, min(start + 4, len(races) + 1)))
        with ThreadPoolExecutor(max_workers=4) as ex:
            got = list(ex.map(
                lambda r: (_round_standings(season, r, "driver"),
                           _round_standings(season, r, "constructor")),
                batch))
        stop = False
        for r, (ds, cs) in zip(batch, got):
            if ds is None or cs is None:
                stop = True
                break
            rounds_data[r] = {"drivers": ds, "constructors": cs}
        if stop:
            break
    if not rounds_data:
        return {"season": season, "rounds": [], "drivers": [], "constructors": []}
    rounds = [r for r in races if int(r["round"]) in rounds_data]
    drivers = {}
    constructors = {}
    for r in sorted(rounds_data):
        ds = rounds_data[r]["drivers"]["DriverStandings"]
        for s in ds:
            d = s["Driver"]
            c = (s.get("Constructors") or [{}])[0]
            cid = c.get("constructorId", "")
            _, color = images.logo_for(cid, season)
            dd = drivers.setdefault(d["driverId"], {
                "driverId": d["driverId"],
                "code": d.get("code", ""),
                "name": f'{d.get("givenName", "")} {d.get("familyName", "")}',
                "points": [],
            })
            dd["points"].append(float(s["points"]))
            dd["color"] = color  # 最后一场的车队色
        cs = rounds_data[r]["constructors"]["ConstructorStandings"]
        for s in cs:
            c = s["Constructor"]
            cid = c["constructorId"]
            _, color = images.logo_for(cid, season)
            cc = constructors.setdefault(cid, {
                "constructorId": cid,
                "name": c["name"],
                "points": [],
            })
            cc["points"].append(float(s["points"]))
            cc["color"] = color
    def _sort(series):
        items = sorted(series.values(), key=lambda x: x["points"][-1], reverse=True)
        return items
    return {
        "season": season,
        "rounds": [{
            "round": r["round"],
            "raceName": r["raceName"],
            "date": r["date"],
        } for r in rounds],
        "drivers": _sort(drivers),
        "constructors": _sort(constructors),
    }


# 2027 赛历（FIA 2026-09-16 公布版，正赛日为周日；Jolpica 收录后自动切换）
CALENDAR_2027 = [
    {"round": 1, "raceName": "巴林大奖赛", "circuit": "巴林国际赛车场", "country": "巴林", "date": "2027-03-14"},
    {"round": 2, "raceName": "沙特阿拉伯大奖赛", "circuit": "吉达滨海赛道", "country": "沙特阿拉伯", "date": "2027-03-21"},
    {"round": 3, "raceName": "澳大利亚大奖赛", "circuit": "阿尔伯特公园赛道", "country": "澳大利亚", "date": "2027-04-04"},
    {"round": 4, "raceName": "日本大奖赛", "circuit": "铃鹿赛道", "country": "日本", "date": "2027-04-11"},
    {"round": 5, "raceName": "中国大奖赛", "circuit": "上海国际赛车场", "country": "中国", "date": "2027-04-18"},
    {"round": 6, "raceName": "迈阿密大奖赛", "circuit": "迈阿密国际赛道", "country": "美国", "date": "2027-05-02"},
    {"round": 7, "raceName": "加拿大大奖赛", "circuit": "吉尔斯·维伦纽夫赛道", "country": "加拿大", "date": "2027-05-23"},
    {"round": 8, "raceName": "摩纳哥大奖赛", "circuit": "蒙特卡洛街道赛道", "country": "摩纳哥", "date": "2027-06-06"},
    {"round": 9, "raceName": "葡萄牙大奖赛", "circuit": "阿尔加维国际赛道", "country": "葡萄牙", "date": "2027-06-20"},
    {"round": 10, "raceName": "英国大奖赛", "circuit": "银石赛道", "country": "英国", "date": "2027-07-04"},
    {"round": 11, "raceName": "奥地利大奖赛", "circuit": "红牛环", "country": "奥地利", "date": "2027-07-11"},
    {"round": 12, "raceName": "比利时大奖赛", "circuit": "斯帕-弗朗科尔尚赛道", "country": "比利时", "date": "2027-07-25"},
    {"round": 13, "raceName": "匈牙利大奖赛", "circuit": "亨格罗林赛道", "country": "匈牙利", "date": "2027-08-01"},
    {"round": 14, "raceName": "意大利大奖赛", "circuit": "蒙扎赛道", "country": "意大利", "date": "2027-09-05"},
    {"round": 15, "raceName": "西班牙大奖赛", "circuit": "加泰罗尼亚赛道", "country": "西班牙", "date": "2027-09-12"},
    {"round": 16, "raceName": "阿塞拜疆大奖赛", "circuit": "巴库城市赛道", "country": "阿塞拜疆", "date": "2027-09-26"},
    {"round": 17, "raceName": "土耳其大奖赛", "circuit": "伊斯坦布尔公园赛道", "country": "土耳其", "date": "2027-10-03"},
    {"round": 18, "raceName": "新加坡大奖赛", "circuit": "滨海湾街道赛道", "country": "新加坡", "date": "2027-10-10"},
    {"round": 19, "raceName": "美国大奖赛", "circuit": "美洲赛道", "country": "美国", "date": "2027-10-24"},
    {"round": 20, "raceName": "墨西哥城大奖赛", "circuit": "罗德里格斯兄弟赛道", "country": "墨西哥", "date": "2027-10-31"},
    {"round": 21, "raceName": "圣保罗大奖赛", "circuit": "因特拉戈斯赛道", "country": "巴西", "date": "2027-11-07"},
    {"round": 22, "raceName": "拉斯维加斯大奖赛", "circuit": "拉斯维加斯街道赛道", "country": "美国", "date": "2027-11-21"},
    {"round": 23, "raceName": "卡塔尔大奖赛", "circuit": "卢赛尔国际赛道", "country": "卡塔尔", "date": "2027-12-05"},
    {"round": 24, "raceName": "阿布扎比大奖赛", "circuit": "亚斯码头赛道", "country": "阿联酋", "date": "2027-12-12"},
]


def get_calendar(year):
    """赛历：优先 Jolpica（已收录时），2027 未收录用静态官方版。"""
    try:
        year = int(year)
    except (TypeError, ValueError):
        year = 0
    races = get_season_races(year)
    if races:
        return {"year": year, "source": "jolpica", "note": "", "races": races}
    if year == 2027:
        return {
            "year": year,
            "source": "static",
            "note": "FIA 官方 2026-09-16 公布版，仍可能微调；季前测试 2 月 24-27 日（巴林）。",
            "races": CALENDAR_2027,
        }
    return {"year": year, "source": "jolpica", "note": "", "races": []}


def get_race_results(season, round_no):
    """单场分站详情：正赛结果 + 排位赛 + 冲刺赛（有的话）。"""
    offset = 0
    combined = {}
    order = []
    meta = None
    while True:
        data = _get(
            f"/{season}/{round_no}/results.json",
            {"limit": "100", "offset": str(offset)},
            ttl=600,
        )
        mr = data["MRData"]
        races = mr["RaceTable"]["Races"]
        total = int(mr["total"])
        batch_total = 0
        for r in races:
            if meta is None:
                meta = {
                    "season": r["season"],
                    "round": r["round"],
                    "raceName": r["raceName"],
                    "circuit": r["Circuit"]["circuitName"],
                    "country": r["Circuit"]["Location"]["country"],
                    "date": r["date"],
                }
            for res in r.get("Results", []):
                batch_total += 1
                did = res["Driver"]["driverId"]
                if did in combined:
                    continue
                combined[did] = res
                order.append(did)
        offset += batch_total
        if offset >= total or not races or batch_total == 0:
            break
    if meta is None:
        return None
    results = []
    fastest = None
    for did in order:
        res = combined[did]
        fl = res.get("FastestLap") or {}
        d = res["Driver"]
        c = res["Constructor"]
        logo, color = images.logo_for(c["constructorId"], season)
        results.append({
            "position": _pos(res),
            "points": res["points"],
            "grid": res["grid"],
            "laps": res["laps"],
            "status": res["status"],
            "driverId": did,
            "code": d.get("code", ""),
            "name": f'{d.get("givenName", "")} {d.get("familyName", "")}',
            "headshot": images.headshot_for(
                d.get("givenName", ""), d.get("familyName", ""), season, c["constructorId"]),
            "constructor": c["name"],
            "constructorId": c["constructorId"],
            "logo": logo,
            "color": color,
            "flRank": fl.get("rank", ""),
            "flTime": (fl.get("Time") or {}).get("time", ""),
        })
        if fl.get("rank") == "1":
            fastest = {
                "driver": f'{d.get("givenName", "")} {d.get("familyName", "")}',
                "code": d.get("code", ""),
                "time": (fl.get("Time") or {}).get("time", ""),
                "lap": fl.get("lap", ""),
            }
    results.sort(key=lambda x: _rank(x["position"]))
    meta["fastestLap"] = fastest
    meta["results"] = results
    meta["qualifying"] = get_qualifying(season, round_no)
    meta["sprint"] = get_sprint(season, round_no)
    return meta


def _driver_brief(d, c, season):
    """车手/车队公共字段（头像、队徽、颜色），排位与冲刺表共用。"""
    logo, color = images.logo_for(c["constructorId"], season)
    return {
        "driverId": d["driverId"],
        "code": d.get("code", ""),
        "name": f'{d.get("givenName", "")} {d.get("familyName", "")}',
        "headshot": images.headshot_for(
            d.get("givenName", ""), d.get("familyName", ""), season, c["constructorId"]),
        "constructor": c["name"],
        "constructorId": c["constructorId"],
        "logo": logo,
        "color": color,
    }


def get_qualifying(season, round_no):
    """排位赛结果（Q1/Q2/Q3 成绩）；无数据返回 None。"""
    data = _get(f"/{season}/{round_no}/qualifying.json", {"limit": "100"}, ttl=600)
    races = data["MRData"]["RaceTable"]["Races"]
    if not races or not races[0].get("QualifyingResults"):
        return None
    out = []
    for q in races[0]["QualifyingResults"]:
        row = _driver_brief(q["Driver"], q["Constructor"], season)
        row.update({
            "position": _pos(q),
            "q1": q.get("Q1", ""),
            "q2": q.get("Q2", ""),
            "q3": q.get("Q3", ""),
        })
        out.append(row)
    return out


def get_sprint(season, round_no):
    """冲刺赛结果（2021 起部分分站有）；无数据返回 None。"""
    data = _get(f"/{season}/{round_no}/sprint.json", {"limit": "100"}, ttl=600)
    races = data["MRData"]["RaceTable"]["Races"]
    if not races or not races[0].get("SprintResults"):
        return None
    out = []
    for s in races[0]["SprintResults"]:
        row = _driver_brief(s["Driver"], s["Constructor"], season)
        row.update({
            "position": _pos(s),
            "grid": s["grid"],
            "laps": s["laps"],
            "points": s["points"],
            "status": s["status"],
        })
        out.append(row)
    return out


def get_driver_info(driver_id):
    data = _get(f"/drivers/{driver_id}.json", ttl=86400)
    drivers = data["MRData"]["DriverTable"]["Drivers"]
    if not drivers:
        return {}
    d = drivers[0]
    return {
        "driverId": d["driverId"],
        "code": d.get("code", ""),
        "givenName": d.get("givenName", ""),
        "familyName": d.get("familyName", ""),
        "nationality": d.get("nationality", ""),
        "dob": d.get("dateOfBirth", ""),
    }


def get_driver_career(driver_id):
    cache_key = f"career::{driver_id}"
    now = time.time()
    hit = _cache.get(cache_key)
    if hit and hit[0] > now:
        return hit[1]

    races = _paginate(f"/drivers/{driver_id}/results.json", ttl=86400)
    wins = podiums = poles = fastest_laps = 0
    points = 0.0
    seasons = {}

    for r in races:
        season = r["season"]
        for res in r.get("Results", []):
            pos = int(res.get("position") or res.get("positionText") or 0)
            if pos == 1:
                wins += 1
            if pos <= 3:
                podiums += 1
            if res.get("grid") == "1":
                poles += 1
            fl = res.get("FastestLap") or {}
            if fl.get("rank") == "1":
                fastest_laps += 1
            pts = float(res["points"])
            points += pts
            s = seasons.setdefault(season, {"races": 0, "wins": 0, "podiums": 0, "points": 0.0})
            s["races"] += 1
            s["wins"] += 1 if pos == 1 else 0
            s["podiums"] += 1 if pos <= 3 else 0
            s["points"] += pts

    championships = 0
    champion_seasons = []
    final_positions = {}

    def _season_position(season):
        # Jolpica 车手赛季排名接口路径为 /{season}/drivers/{id}/driverStandings.json
        data = _get(f"/{season}/drivers/{driver_id}/driverStandings.json", ttl=86400)
        lists = data["MRData"]["StandingsTable"]["StandingsLists"]
        if not lists or not lists[0].get("DriverStandings"):
            return season, ""
        return season, lists[0]["DriverStandings"][0].get("position", "")

    with ThreadPoolExecutor(max_workers=2) as ex:
        for season, pos in ex.map(_season_position, sorted(seasons)):
            final_positions[season] = pos
            if pos == "1":
                championships += 1
                champion_seasons.append(season)

    info = get_driver_info(driver_id)
    breakdown = []
    for season in sorted(seasons):
        s = dict(seasons[season])
        s["season"] = season
        s["points"] = round(s["points"], 2)
        s["championship"] = final_positions.get(season, "")
        breakdown.append(s)

    career = {
        "driverId": driver_id,
        "code": info.get("code", ""),
        "name": f'{info.get("givenName", "")} {info.get("familyName", "")}'.strip(),
        "nationality": info.get("nationality", ""),
        "dob": info.get("dob", ""),
        "seasons": len(seasons),
        "starts": sum(x["races"] for x in breakdown),
        "wins": wins,
        "podiums": podiums,
        "poles": poles,
        "fastestLaps": fastest_laps,
        "points": round(points, 2),
        "championships": championships,
        "championSeasons": champion_seasons,
        "seasonBreakdown": breakdown,
    }
    _cache[cache_key] = (now + 86400, career)
    return career


def compare_drivers(d1, d2):
    return {"drivers": [get_driver_career(d1), get_driver_career(d2)]}
