"""存量视频回填：字幕帖补存字幕正文；「简介」帖有字幕则升级为字幕摘要。

在 ECS 上运行（/opt/f1-site 下），上传后直接 python3 执行本文件即可。
已有字幕摘要的条目只补正文、不重算摘要（省 DeepSeek 配额）。
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, "/opt/f1-site/backend")

import requests

import bilibili
import db
import summarize
import upsub

db.init("/opt/f1-site/data/f1.db")
bilibili.load_cookie()
summarize.load_config()
if not bilibili._cookie:
    print("!! 未配置 Cookie（data/bili_cookie.txt），AI 字幕接口无法使用，退出")
    sys.exit(1)

SUBTEXT_LIMIT = 8000

rows = [
    r for r in db.list_up_posts(limit=1000)
    if r["source_type"] == "video"
]
print("视频总数:", len(rows))

_vids_cache = {}


def _up_videos_cached(mid):
    """空间投稿列表按 UP 缓存，避免每个视频都查一次（风控更敏感）。"""
    if mid not in _vids_cache:
        try:
            _vids_cache[mid] = bilibili.up_videos(mid, ps=30) or []
        except Exception:
            _vids_cache[mid] = []
    return _vids_cache[mid]


def _detail_fallback(bvid, row):
    """view 被风控时兜底：pagelist 拿 cid + 空间投稿列表拿 aid，标题简介用库里的。"""
    try:
        d = requests.get(
            "https://api.bilibili.com/x/player/pagelist",
            params={"bvid": bvid}, headers=bilibili._headers(), timeout=15,
        ).json()
        cid = d["data"][0]["cid"]
    except Exception:
        return None
    aid = None
    for v in _up_videos_cached(row["mid"]):
        if v.get("bvid") == bvid:
            aid = v.get("aid")
            break
    if not aid:
        return None
    return {"cid": cid, "aid": aid, "title": row.get("title") or "", "desc": ""}


upgraded = filled = 0
for i, r in enumerate(rows):
    bvid = r["source_id"]
    try:
        detail = bilibili.video_detail(bvid)  # 单次快速尝试，风控期直接走兜底
    except Exception:
        detail = _detail_fallback(bvid, r)
        if not detail:
            print(f"[{i+1}/{len(rows)}] {bvid} 详情失败，跳过")
            time.sleep(3)
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
    if not sub_text:
        print(f"[{i+1}/{len(rows)}] {bvid} 无字幕，跳过")
        time.sleep(2.5)
        continue
    sub_text = sub_text[:SUBTEXT_LIMIT]
    if (r.get("summary_type") or "") in ("AI字幕", "字幕"):
        db.update_up_post_summary("video", bvid, r.get("summary") or "",
                                  r["summary_type"], sub_text)
        filled += 1
        print(f"[{i+1}/{len(rows)}] {bvid} 补字幕正文 {len(sub_text)} 字")
    else:
        raw = "\n".join(filter(None, [
            detail.get("title") or "",
            detail.get("desc") or "",
            sub_text,
        ]))
        try:
            summary = summarize.summarize_up(raw, "视频")
        except Exception as exc:
            print(f"[{i+1}/{len(rows)}] {bvid} 摘要失败: {exc}")
            time.sleep(2.5)
            continue
        db.update_up_post_summary("video", bvid, summary, sub_kind, sub_text)
        upgraded += 1
        print(f"[{i+1}/{len(rows)}] {bvid} -> {sub_kind} 完成")
    time.sleep(2.5)

print(f"回填完成: 补正文 {filled}，升级 {upgraded} / 共 {len(rows)}")
