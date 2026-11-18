"""F1 数据（Jolpica / Ergast 维护分支）抓取与聚合。"""
import time
from concurrent.futures import ThreadPoolExecutor

import requests

import images

BASE = "https://api.jolpi.ca/ergast/f1"

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
                time.sleep(1.5 * (attempt + 1))
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
