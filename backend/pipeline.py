"""抓取流水线：B站搜索 → 详情/评论 → AI 摘要 → 入库。

搜索分两层：
1. 逐站搜索：对当前赛季每场大奖赛用「F1 XX大奖赛」搜索并翻到第 2 页，
   保证各分站都有覆盖（实测「F1 XX站 前瞻/赛后」这类词被 B站拆词后
   只返回热门站内容，「XX大奖赛」才能命中本场帖子）。每轮只搜固定预算
   （RACE_SEARCH_BUDGET）且轮流起始，已覆盖的分站跳过——避免集中轰炸
   触发 B站搜索限流（限流表现为静默返回空结果）。
2. 通用搜索：覆盖「赛季整体」与往年内容。

帖子分类由标题/简介关键词决定（前瞻→赛前预判、策略→比赛策略、其余→赛后总结）。
入库前先查重（post_exists），已收录的帖子跳过，不重复消耗 AI 摘要配额；
同一时刻只允许一个抓取任务（含手动与定时）。
"""
import re
import threading
import time

import bilibili
import db
import race
import summarize

CATEGORIES = {
    "赛前预判": ["F1 赛前分析", "F1 前瞻", "F1 赛前预测"],
    "赛后总结": ["F1 赛后总结", "F1 复盘", "F1 赛后分析"],
    "比赛策略": ["F1 策略", "F1 进站策略", "F1 轮胎策略"],
}

# 每轮逐站搜索的预算（站数），避免短时间内大量搜索触发限流
# （实测连续搜 6 站左右会开始被静默限流，8 站一轮较稳）
RACE_SEARCH_BUDGET = 8

# 每个分站最多入库的候选数（多搜几条后按发布时间取最新的）
RACE_POST_LIMIT = 3

_PRE_WORDS = ("前瞻", "预测", "预告", "赛前", "展望", "押宝", "赛程")
_STRATEGY_WORDS = ("策略", "进站", "轮胎", "战术", "调校", "undercut")

_EM_RE = re.compile(r"</?em[^>]*>")

_run_lock = threading.Lock()


def is_running():
    return _run_lock.locked()


def _clean(s):
    """去掉 B站搜索标题/简介里的 <em> 高亮标签，否则会干扰分站关键词匹配。"""
    return _EM_RE.sub("", s or "")


def _collect(category, keywords, limit, seen):
    out = []
    for p in bilibili.collect_posts(category, keywords, limit=limit):
        if p["source_id"] not in seen:
            seen.add(p["source_id"])
            out.append(p)
    return out


def _match_race(title, desc, r):
    """标题/简介确实提到所搜分站才算数，过滤 B站宽松匹配带来的无关视频。"""
    return race.detect_race(_clean(title), _clean(desc)) == r


def _classify(title, desc):
    """按标题/简介关键词把帖子归入三个分类；默认归「赛后总结」（含正赛/集锦/回放）。"""
    text = (title + " " + desc).lower()
    if any(k in text for k in _STRATEGY_WORDS):
        return "比赛策略"
    if any(k in text for k in _PRE_WORDS):
        return "赛前预判"
    return "赛后总结"


def _search_race(r):
    """搜索某个分站：先搜「F1 XX大奖赛」第 1、2 页，不够再补「XX大奖赛」
    （实测墨西哥等站带 F1 前缀反而被热门站内容淹没）。取标题真提到该站的
    帖子补详情，最多留 5 条候选，按发布时间取最新的 RACE_POST_LIMIT 条。"""
    gp = race.to_gp_name(r)
    matched, seen_bvid = [], set()
    queries = [f"F1 {gp}", gp]
    for qi, q in enumerate(queries):
        pages = (1, 2) if qi == 0 else (1,)
        for page in pages:
            batch = []
            try:
                batch = bilibili.search_videos(q, page=page, page_size=10)
            except Exception:
                break
            if not batch and page == 1:
                # 空结果可能是限流，稍等重试一次
                time.sleep(4)
                try:
                    batch = bilibili.search_videos(q, page=1, page_size=10)
                except Exception:
                    break
            for it in batch:
                bvid = it.get("bvid")
                if not bvid or bvid in seen_bvid:
                    continue
                seen_bvid.add(bvid)
                if not bilibili._is_f1_related(it):
                    continue
                if not _match_race(it.get("title"), it.get("description"), r):
                    continue
                try:
                    matched.append(bilibili.get_post_data(bvid))
                except Exception:
                    continue
                time.sleep(0.8)
                if len(matched) >= 5:
                    break
            if len(matched) >= 5:
                break
            time.sleep(1.5)
        if len(matched) >= 5:
            break
    # 优先新帖子（用户在意时效）
    matched.sort(key=lambda x: x["published_at"] or "", reverse=True)
    return matched[:RACE_POST_LIMIT]


def run(limit_per_category=12, race_budget=RACE_SEARCH_BUDGET):
    if not _run_lock.acquire(blocking=False):
        return {"total": 0, "added": 0, "error": None, "busy": True}
    try:
        return _run(limit_per_category, race_budget)
    finally:
        _run_lock.release()


def _run(limit_per_category, race_budget):
    bilibili.load_cookie()
    summarize.load_config()
    total = 0
    added = 0
    searched = 0
    error = None
    try:
        buckets = {cat: [] for cat in CATEGORIES}
        seen = set()
        # 1. 逐站搜索（配额内优先保证各分站覆盖）
        races = race.SEASON_RACES
        start = db.run_count() % len(races) if races else 0
        for i in range(len(races)):
            r = races[(start + i) % len(races)]
            if db.race_covered(r):
                continue
            if searched >= race_budget:
                break
            searched += 1
            for p in _search_race(r):
                if p["source_id"] in seen:
                    continue
                seen.add(p["source_id"])
                cat = _classify(p["title"], p["raw_text"].split("【热门评论】")[0])
                buckets[cat].append(p)
            time.sleep(5)  # 分站之间稍作停顿，降低限流概率
        # 2. 通用搜索：赛季整体与往年内容
        for cat, keywords in CATEGORIES.items():
            buckets[cat] += _collect(cat, keywords, 4, seen)
        # 3. 按配额入库；已收录的跳过，不重复消耗 AI 摘要
        for cat in CATEGORIES:
            attempts = 0
            for p in buckets[cat]:
                if attempts >= limit_per_category:
                    break
                total += 1
                if db.post_exists("bilibili", p["source_id"]):
                    continue
                attempts += 1
                race_name = race.detect_race(
                    p["title"], p["raw_text"].split("【热门评论】")[0]
                )
                summary = summarize.summarize(p["raw_text"], cat)
                if db.add_post(
                    "bilibili", p["source_id"], p["title"], p["author"],
                    p["url"], p["published_at"], cat, p["raw_text"], summary, race_name,
                ):
                    added += 1
        db.log_run(total, added, None)
    except Exception as e:
        error = str(e)
        db.log_run(total, added, error)
    return {"total": total, "added": added, "error": error, "searchedRaces": searched}
