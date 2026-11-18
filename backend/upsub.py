"""UP 主订阅流水线：轮询订阅 UP 的新视频/专栏 → DeepSeek 摘要 → 入库。

- 每轮每个 UP 有新增预算（PER_UP_BUDGET），先把最近的内容吃掉，
  剩余留到下一轮——首次订阅时避免一次跑太久、也能平滑回填历史。
- 增量检测靠 (source_type, source_id) 唯一索引去重，已收录的跳过，
  不重复消耗 AI 摘要配额。
- 视频摘要素材：标题+简介+CC 字幕（有字幕优先，无字幕标「简介」）；
  「直播回放」类视频没有简介/字幕、摘要无信息量，直接跳过；
  专栏摘要素材：全文（标「全文」）。
- 空间投稿接口对大号 UP 风控严（-412/-352），失败时按 UP 名搜索视频
  +作者名过滤兜底（实测覆盖近全部近期投稿）。
- AI 字幕可能发布后数小时才生成：recheck_subtitles 每周复查近期「简介」视频。
- 同一时刻只允许一个检查任务（含手动与定时）。
"""
import re
import threading
import time

import requests

import bilibili
import db
import summarize

# 每轮每个 UP 最多新增处理的条目数
PER_UP_BUDGET = 20

# 只收录最近 N 天发布的内容（订阅后不再回吃历史投稿）
MAX_AGE_DAYS = 30

# 字幕正文入库上限（前端弹窗浏览用，截断即可）
SUBTEXT_LIMIT = 8000

_run_lock = threading.Lock()
_single_lock = threading.Lock()


def check_up_mid(mid, name=""):
    """后台检查单个 UP（新增订阅后立即拉一轮），已有任务在跑则跳过。"""
    if _run_lock.locked() or not _single_lock.acquire(blocking=False):
        return False

    def _job():
        try:
            bilibili.load_cookie()
            summarize.load_config()
            _check_up(mid, name)
        except Exception:
            pass
        finally:
            _single_lock.release()

    threading.Thread(target=_job, daemon=True).start()
    return True


def is_running():
    return _run_lock.locked()


def resolve_up(text):
    """从「空间主页链接 / mid / UP 名称」解析 UP 主信息，失败返回 None。

    名称搜索取与输入完全一致的候选（避免同名 UP 误订阅）；
    资料接口 acc/info 可能被风控，兜底从最新视频/专栏的作者信息取昵称头像。
    """
    text = (text or "").strip()
    if not text:
        return None
    m = re.search(r"space\.bilibili\.com/(\d+)", text)
    if m:
        mid = int(m.group(1))
    elif re.fullmatch(r"\d{5,16}", text):
        mid = int(text)
    else:
        try:
            cands = bilibili.search_users(text) or []
        except Exception:
            return None
        if not cands:
            return None
        exact = [c for c in cands if (c.get("uname") or "") == text]
        cands = exact or cands
        mid = cands[0].get("mid")
        if not mid:
            return None

    name, face = "", ""
    try:
        info = bilibili.up_info(mid) or {}
        name = info.get("name") or ""
        face = info.get("face") or ""
    except Exception:
        pass
    if not name:
        try:
            vids = bilibili.up_videos(mid, ps=1)
            if vids:
                d = bilibili.video_detail(vids[0]["bvid"])
                owner = d.get("owner") or {}
                name = owner.get("name") or ""
                face = owner.get("face") or ""
        except Exception:
            pass
    if not name:
        try:
            arts = bilibili.up_articles(mid, ps=1)
            if arts:
                au = arts[0].get("author") or {}
                name = au.get("name") or name
                face = au.get("face") or face
        except Exception:
            pass
    if not name:
        return None
    return {"mid": mid, "name": name, "avatar": face}


def run():
    if not _run_lock.acquire(blocking=False):
        return {"checked": 0, "added": 0, "errors": [], "busy": True}
    try:
        return _run()
    finally:
        _run_lock.release()


def _run():
    bilibili.load_cookie()
    summarize.load_config()
    checked = 0
    added = 0
    errors = []
    for t in db.crawl_targets():
        name = t.get("name") or ("mid=" + str(t["mid"]))
        checked += 1
        try:
            added += _check_up(t["mid"], name)
        except Exception as e:
            errors.append("%s: %s" % (name, e))
        time.sleep(8)  # UP 之间放宽节奏
    return {"checked": checked, "added": added, "errors": errors}


def _fmt_ts(ts):
    try:
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(int(ts)))
    except Exception:
        return ""


def _ts_too_old(ts, min_ts):
    """时间戳缺失视为不过期（列表接口一般都有）；超过窗口才跳过。"""
    try:
        return int(ts) > 0 and int(ts) < min_ts
    except (TypeError, ValueError):
        return False


def _abs_url(u):
    if not u:
        return ""
    return "https:" + u if u.startswith("//") else u


def _detail_with_retry(bvid):
    """视频详情：普通错误退避重试（最多 3 轮）。

    -412/-352 风控不重试直接抛——实测 ECS IP 被风控时 view 会持续数小时，
    重试 3 轮纯属浪费 ~48s；直接走 _detail_fallback（pagelist+列表项，不受风控影响）。
    """
    last = None
    for attempt in range(3):
        try:
            return bilibili.video_detail(bvid)
        except RuntimeError as exc:
            if "code=-412" in str(exc) or "code=-352" in str(exc):
                raise
            last = exc
            time.sleep(8 + attempt * 8)
        except requests.exceptions.RequestException as exc:
            last = exc
            time.sleep(8 + attempt * 8)
    raise last


def _detail_fallback(bvid, item):
    """view 被风控时兜底：pagelist 拿 cid、列表项拿 aid/标题，简介留空。"""
    try:
        d = requests.get(
            "https://api.bilibili.com/x/player/pagelist",
            params={"bvid": bvid}, headers=bilibili._headers(), timeout=15,
        ).json()
        cid = d["data"][0]["cid"]
    except Exception:
        return None
    return {
        "cid": cid,
        "aid": item.get("aid"),
        "title": item.get("title") or "",
        "desc": "",
        "owner": {"name": item.get("author") or "", "mid": item.get("mid")},
        "pic": item.get("pic") or "",
        "pubdate": item.get("created") or item.get("pubdate") or 0,
    }


def _check_up(mid, name=""):
    """轮询一个 UP：新视频 + 新专栏，逐个摘要入库，返回本轮新增数。"""
    budget = PER_UP_BUDGET
    added = 0
    min_ts = time.time() - MAX_AGE_DAYS * 86400

    # 1. 视频（发布倒序，只处理未收录的）
    try:
        vids = bilibili.up_videos(mid, ps=30) or []
    except Exception:
        vids = []
    if not vids and name:
        # 空间投稿接口被风控时，按 UP 名搜索 + 作者过滤兜底
        try:
            vids = bilibili.search_videos_by_up(name, 30) or []
        except Exception:
            vids = []
    for v in vids:
        if budget <= 0:
            break
        bvid = v.get("bvid")
        if not bvid or db.up_post_exists("video", bvid):
            continue
        if _ts_too_old(v.get("created") or v.get("pubdate"), min_ts):
            continue
        try:
            detail = _detail_with_retry(bvid)
        except Exception:
            detail = _detail_fallback(bvid, v)
            if not detail:
                time.sleep(2)
                continue
        # 直播回放无简介/字幕，摘要没有信息量，直接跳过
        if "直播回放" in (detail.get("title") or ""):
            continue
        cid = detail.get("cid")
        owner_mid = (detail.get("owner") or {}).get("mid")
        sub_text = ""
        sub_kind = "简介"
        if cid:
            try:
                sub_text = bilibili.ai_subtitle_text(bvid, detail.get("aid"), cid, owner_mid)
                if sub_text:
                    sub_kind = "AI字幕"
            except Exception:
                sub_text = ""
            if not sub_text:
                try:
                    sub_text = bilibili.video_subtitle_text(bvid, cid, detail.get("aid"))
                    if sub_text:
                        sub_kind = "字幕"
                except Exception:
                    sub_text = ""
        raw = "\n".join(filter(None, [
            detail.get("title") or "",
            detail.get("desc") or "",
            sub_text,
        ]))
        summary = summarize.summarize_up(raw, "视频")
        published = _fmt_ts(
            v.get("created") or v.get("pubdate") or detail.get("pubdate")
        )
        if db.add_up_post(
            mid, "video", bvid,
            detail.get("title") or "",
            (detail.get("owner") or {}).get("name") or "",
            "https://www.bilibili.com/video/" + bvid,
            _abs_url(v.get("pic")),
            published,
            summary,
            sub_kind,
            sub_text[:SUBTEXT_LIMIT] if sub_text else "",
        ):
            added += 1
            budget -= 1
        time.sleep(2.5)  # 放宽节奏，降低整批被风控的概率

    # 2. 专栏
    try:
        arts = bilibili.up_articles(mid, ps=12) or []
    except Exception:
        arts = []
    for a in arts:
        if budget <= 0:
            break
        cvid = a.get("id")
        if not cvid or db.up_post_exists("article", str(cvid)):
            continue
        if _ts_too_old(a.get("publish_time"), min_ts):
            continue
        try:
            art = bilibili.article_view(cvid)
        except Exception:
            time.sleep(1)
            continue
        content = art.get("content") or ""
        title = art.get("title") or a.get("title") or ""
        raw = title + "\n" + content
        summary = summarize.summarize_up(raw, "专栏")
        imgs = art.get("image_urls") or a.get("image_urls") or []
        au = art.get("author") or a.get("author") or {}
        published = _fmt_ts(art.get("publish_time") or a.get("publish_time"))
        if db.add_up_post(
            mid, "article", str(cvid),
            title,
            au.get("name") or "",
            "https://www.bilibili.com/read/cv%d" % cvid,
            _abs_url(imgs[0] if imgs else ""),
            published,
            summary,
            "全文" if content else "简介",
        ):
            added += 1
            budget -= 1
        time.sleep(1.2)

    return added


# 字幕复查：只复查最近 N 天发布、仍是「简介」的视频
RESUB_DAYS = 7

# 每轮最多复查的视频数（限流友好）
RESUB_BUDGET = 25


def recheck_subtitles():
    """复查近期「简介」视频的字幕：B站 AI 字幕可能发布后数小时~数天才生成。

    入库时已试过一次，这里定期补查把晚生成的字幕捞回来。
    全程走风控安全的接口链（pagelist 拿 cid、空间列表/搜索拿 aid），不碰 view。
    """
    bilibili.load_cookie()
    summarize.load_config()
    cutoff = time.strftime("%Y-%m-%d %H:%M", time.localtime(time.time() - RESUB_DAYS * 86400))
    posts = [p for p in db.list_up_posts(limit=300)
             if p.get("source_type") == "video"
             and (p.get("summary_type") or "") == "简介"
             and (p.get("published_at") or "") >= cutoff]
    by_mid = {}
    for p in posts:
        by_mid.setdefault(p.get("mid"), []).append(p)
    checked = 0
    upgraded = 0
    errors = []
    for mid, group in by_mid.items():
        if checked >= RESUB_BUDGET:
            break
        vids = []
        try:
            vids = bilibili.up_videos(mid, ps=30) or []
        except Exception:
            vids = []
        if not vids:
            try:
                vids = bilibili.search_videos_by_up((group[0].get("author") or "").strip(), 30) or []
            except Exception:
                vids = []
        aid_map = {v.get("bvid"): v.get("aid") for v in vids if v.get("bvid") and v.get("aid")}
        for p in group:
            if checked >= RESUB_BUDGET:
                break
            bvid = p.get("source_id")
            if not bvid or bvid not in aid_map:
                continue  # 投稿列表里已找不到（下架/过期），无 aid 走不了字幕接口
            checked += 1
            try:
                d = requests.get(
                    "https://api.bilibili.com/x/player/pagelist",
                    params={"bvid": bvid}, headers=bilibili._headers(), timeout=15,
                ).json()
                cid = d["data"][0]["cid"]
            except Exception:
                continue
            sub_text = ""
            sub_kind = "AI字幕"
            try:
                sub_text = bilibili.ai_subtitle_text(bvid, aid_map[bvid], cid, mid)
            except Exception:
                sub_text = ""
            if not sub_text:
                try:
                    sub_text = bilibili.video_subtitle_text(bvid, cid, aid_map[bvid])
                    sub_kind = "字幕"
                except Exception:
                    sub_text = ""
            if not sub_text:
                continue
            raw = "\n".join(filter(None, [p.get("title") or "", sub_text]))
            try:
                summary = summarize.summarize_up(raw, "视频")
            except Exception as e:
                errors.append("%s 摘要失败: %s" % (bvid, e))
                continue
            db.update_up_post_summary("video", bvid, summary, sub_kind,
                                      sub_text[:SUBTEXT_LIMIT])
            upgraded += 1
            time.sleep(2.5)
    return {"checked": checked, "upgraded": upgraded, "errors": errors}
