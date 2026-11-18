"""评论区观点汇总：分层采样 + DeepSeek 观点聚类。

- 采样分层：热度层（热评翻页）+ 时间层（老接口最新评论）+ 长评层（字数过滤）
  + 争论层（高回复低赞的主评论及其楼中楼）。
- 样本打散喂 AI 做观点聚类（不按点赞排序），保证技术探讨/站队争论等
  不同阵营各自成簇，不被高赞玩梗淹没。
- 延迟抓取：发布 24 小时后评论才发酵；一周内每个视频最多汇总 1~2 轮
  （汇总满 3 天可刷新一次），每轮预算控制请求量。
- 全程走评论接口（已实测 ECS IP 无风控），不碰 view/空间接口。
"""
import json
import re
import threading
import time

import bilibili
import db
import summarize

FERMENT_HOURS = 24      # 发布多久后才采评论
MAX_AGE_HOURS = 7 * 24  # 超过一周的旧视频不补
BUDGET_PER_RUN = 6      # 每轮最多处理的视频数
POSTS_BUDGET = 4        # 每轮最多处理的帖子页 B站帖子数
POSTS_MAX_AGE_HOURS = 30 * 24  # 帖子页只补近 30 天的
HOT_PAGES = 4           # 热评翻页数
NEWEST_N = 20           # 最新评论条数
LONG_MIN_LEN = 80       # 长评字数阈值
ARGUE_RCOUNT = 5        # 争论层：主评论回复数阈值
INLINE_SUBS = 3         # 每条主评论最多采的楼中楼数
MAX_SAMPLES = 120       # 进 AI 的样本上限
MIN_SAMPLES = 10        # 少于该数不摘要
SLEEP_BETWEEN = 5       # 视频间隔秒数
REFRESH_SECONDS = 3 * 86400  # 汇总满 3 天可刷新

_lock = threading.Lock()


def is_running():
    return _lock.locked()


def run():
    if not _lock.acquire(blocking=False):
        return {"checked": 0, "errors": ["busy"]}
    try:
        return _run()
    except Exception as e:
        return {"checked": 0, "errors": [repr(e)]}
    finally:
        _lock.release()


def _parse_ts(s):
    if not s:
        return 0
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return time.mktime(time.strptime(str(s).strip(), fmt))
        except Exception:
            continue
    return 0


def _clean(text):
    t = (text or "").strip().replace("\n", " ")
    if len(t) < 4:
        return False
    if "http" in t or "www." in t or "加v" in t or "＋v" in t:
        return False  # 带链接/引流号多为广告
    if not re.search(r"[\u4e00-\u9fa5A-Za-z0-9]", t):
        return False  # 纯表情符号
    return True


def _norm(r):
    return {
        "text": bilibili._msg_text(((r.get("content") or {}).get("message") or "")),
        "like": r.get("like") or 0,
        "rcount": r.get("rcount") or 0,
        "ctime": r.get("ctime") or 0,
        "is_sub": False,
    }


def _flatten_main(r, seen, out):
    """主评论 + 前几条楼中楼（争论常在回复链里）。"""
    row = _norm(r)
    row["is_sub"] = False
    if row["text"] not in seen:
        seen.add(row["text"])
        out.append(row)
    for s in (r.get("replies") or [])[:INLINE_SUBS]:
        sub = _norm(s)
        sub["is_sub"] = True
        if sub["text"] not in seen:
            seen.add(sub["text"])
            out.append(sub)


def _sample_for_video(aid):
    """分层采样，返回 (AI 样本行, 统计, 时间线样本)；样本不足返回空。"""
    seen = set()
    rows = []
    hot_end = False
    for pg in range(1, HOT_PAGES + 1):
        try:
            d = bilibili.reply_main(aid, 3, pg)
        except Exception:
            break
        reps = (d.get("replies") or [])
        for r in reps:
            _flatten_main(r, seen, rows)
        if not reps or (d.get("cursor") or {}).get("is_end"):
            hot_end = True
            if not reps:
                break
        time.sleep(1.5)
    try:
        for r in bilibili.reply_newest(aid, NEWEST_N):
            _flatten_main(r, seen, rows)
    except Exception:
        pass
    rows = [r for r in rows if _clean(r["text"])]
    # 复读机去重：同文本只留一条
    uniq = {}
    for r in rows:
        uniq.setdefault(r["text"], r)
    rows = list(uniq.values())

    mains = [r for r in rows if not r["is_sub"]]
    picked = []
    pick = picked.append

    def add(r):
        if r not in picked and len(picked) < MAX_SAMPLES:
            picked.append(r)

    # 热度层：按赞取前 25 条主评论
    for r in sorted(mains, key=lambda r: -r["like"])[:25]:
        add(r)
    # 时间层：最新接口返回的已在 rows 里，取低赞尾部 15 条近似「新鲜评论」
    # （老接口按时间倒序返回，取整体列表中后段低赞部分）
    low = [r for r in mains if r["like"] <= 3]
    for r in low[-15:]:
        add(r)
    # 长评层
    for r in sorted([r for r in rows if len(r["text"]) >= LONG_MIN_LEN],
                    key=lambda r: -r["like"])[:15]:
        add(r)
    # 争论层：回复多但赞不突出（骂战现场特征）+ 其楼中楼
    argue = [r for r in mains if r["rcount"] >= ARGUE_RCOUNT and r["like"] < r["rcount"]]
    for r in sorted(argue, key=lambda r: -r["rcount"])[:10]:
        add(r)
    # 楼中楼兜底
    for r in [r for r in rows if r["is_sub"]][:30]:
        add(r)
    if len(picked) < MIN_SAMPLES:
        return [], {}, []
    lines = ["赞%d 回%d | %s" % (r["like"], r["rcount"], r["text"][:120]) for r in picked]
    samples = [{
        "t": r["ctime"], "like": r["like"], "rcount": r["rcount"],
        "text": r["text"][:120], "sub": r["is_sub"],
    } for r in picked]
    return lines, {"total": len(picked), "long": sum(1 for r in picked if len(r["text"]) >= LONG_MIN_LEN)}, samples


def _aid_map(mid, group):
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
    return {v.get("bvid"): v.get("aid") for v in vids if v.get("bvid") and v.get("aid")}


def _aid_by_bvid(bvid):
    """按 BV 号搜索拿 aid（不限 UP、不限新旧，实测 5/5 命中）。"""
    try:
        items = bilibili.search_videos(bvid, page=1, page_size=10) or []
        hit = next((i for i in items if i.get("bvid") == bvid and i.get("aid")), None)
        if hit:
            return hit["aid"]
    except Exception:
        pass
    return None


SAMPLES_BACKFILL_BUDGET = 8  # 每轮最多补时间线样本的条数（只采样不重摘要）


def _backfill_samples():
    """已有观点汇总但缺时间线样本的行：只补采样，不重新调用 AI。"""
    done = 0
    errors = []
    ups = [p for p in db.list_up_posts(limit=300)
           if p.get("source_type") == "video" and p.get("mid")
           and p.get("comment_summary") and not p.get("comment_samples")]
    by_mid = {}
    for p in ups:
        by_mid.setdefault(p["mid"], []).append(p)
    for mid, group in by_mid.items():
        if done >= SAMPLES_BACKFILL_BUDGET:
            break
        aid_map = _aid_map(mid, group)
        for p in group:
            if done >= SAMPLES_BACKFILL_BUDGET:
                break
            bvid = p.get("source_id")
            if not bvid or bvid not in aid_map:
                continue
            done += 1
            try:
                lines, _stats, samples = _sample_for_video(aid_map[bvid])
            except Exception as e:
                errors.append("%s 采样失败: %s" % (bvid, e))
                time.sleep(SLEEP_BETWEEN)
                continue
            if not lines:
                time.sleep(SLEEP_BETWEEN)
                continue
            db.set_up_post_comments(bvid, p["comment_summary"],
                                    json.dumps(samples, ensure_ascii=False))
            time.sleep(SLEEP_BETWEEN)
    for p in db.list_posts():
        if done >= SAMPLES_BACKFILL_BUDGET:
            break
        if (p.get("platform") or "") != "bilibili" or not p.get("source_id"):
            continue
        if not p.get("comment_summary") or p.get("comment_samples"):
            continue
        aid = _aid_by_bvid(p["source_id"])
        if not aid:
            continue
        done += 1
        try:
            lines, _stats, samples = _sample_for_video(aid)
        except Exception as e:
            errors.append("%s 采样失败: %s" % (p["source_id"], e))
            time.sleep(SLEEP_BETWEEN)
            continue
        if not lines:
            time.sleep(SLEEP_BETWEEN)
            continue
        db.set_post_comments(p["source_id"], p["comment_summary"],
                             json.dumps(samples, ensure_ascii=False))
        time.sleep(SLEEP_BETWEEN)
    return done, errors


def _run():
    bilibili.load_cookie()
    summarize.load_config()
    now = time.time()
    bf_done, bf_errors = _backfill_samples()
    errors = list(bf_errors)
    posts = [p for p in db.list_up_posts(limit=300)
             if p.get("source_type") == "video" and p.get("mid")]
    targets = []
    for p in posts:
        age = now - _parse_ts(p.get("published_at"))
        if age < FERMENT_HOURS * 3600 or age > MAX_AGE_HOURS * 3600:
            continue
        if p.get("comment_summary"):
            cat = now - _parse_ts(p.get("comment_at"))
            if cat < REFRESH_SECONDS:
                continue
        targets.append(p)
    by_mid = {}
    for p in targets:
        by_mid.setdefault(p["mid"], []).append(p)
    done = 0
    errors = []
    for mid, group in by_mid.items():
        if done >= BUDGET_PER_RUN:
            break
        aid_map = _aid_map(mid, group)
        for p in group:
            if done >= BUDGET_PER_RUN:
                break
            bvid = p.get("source_id")
            if not bvid or bvid not in aid_map:
                continue
            done += 1
            try:
                lines, _stats, samples = _sample_for_video(aid_map[bvid])
            except Exception as e:
                errors.append("%s 采样失败: %s" % (bvid, e))
                time.sleep(SLEEP_BETWEEN)
                continue
            if not lines:
                time.sleep(SLEEP_BETWEEN)
                continue
            raw = summarize.summarize_opinions(p.get("title") or "", "\n".join(lines))
            if not raw:
                errors.append("%s 观点聚类失败" % bvid)
            else:
                db.set_up_post_comments(bvid, json.dumps(raw, ensure_ascii=False),
                                        json.dumps(samples, ensure_ascii=False))
            time.sleep(SLEEP_BETWEEN)

    # 帖子页的 B站帖子（不限 UP）：按 BV 号搜索解析 aid，只补近 30 天的
    pcands = [p for p in db.list_posts()
              if (p.get("platform") or "") == "bilibili"
              and p.get("source_id")
              and now - _parse_ts(p.get("published_at")) <= POSTS_MAX_AGE_HOURS * 3600
              and (not p.get("comment_summary")
                   or now - _parse_ts(p.get("comment_at")) >= REFRESH_SECONDS)]
    pcands.sort(key=lambda p: p.get("published_at") or "", reverse=True)
    pdone = 0
    for p in pcands:
        if pdone >= POSTS_BUDGET:
            break
        bvid = p["source_id"]
        aid = _aid_by_bvid(bvid)
        if not aid:
            continue
        pdone += 1
        try:
            lines, _stats, samples = _sample_for_video(aid)
        except Exception as e:
            errors.append("%s 采样失败: %s" % (bvid, e))
            time.sleep(SLEEP_BETWEEN)
            continue
        if not lines:
            time.sleep(SLEEP_BETWEEN)
            continue
        raw = summarize.summarize_opinions(p.get("title") or "", "\n".join(lines))
        if not raw:
            errors.append("%s 观点聚类失败" % bvid)
        else:
            db.set_post_comments(bvid, json.dumps(raw, ensure_ascii=False),
                                 json.dumps(samples, ensure_ascii=False))
        time.sleep(SLEEP_BETWEEN)
    return {"checked": done + pdone, "backfilled": bf_done, "errors": errors}
