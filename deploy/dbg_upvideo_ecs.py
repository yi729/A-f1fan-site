# -*- coding: utf-8 -*-
"""ECS 上逐条追踪 F1赛事资讯 视频处理，定位不入库的原因。"""
import sys
import time
import traceback

sys.path.insert(0, "/opt/f1-site/backend")

import bilibili
import db
import summarize

db.init("/opt/f1-site/data/f1.db")
summarize.load_config()

vids = bilibili.search_videos_by_up("F1赛事资讯", 30)
print("fallback 拿到", len(vids), "条")
for n, v in enumerate(vids[:6], 1):
    bvid = v.get("bvid")
    print("--- 第", n, "条", bvid, "库中存在:", db.up_post_exists("video", bvid))
    try:
        detail = bilibili.video_detail(bvid)
        title = detail.get("title") or ""
        print("    detail OK:", title[:30], "cid=", detail.get("cid"), "desc=", len(detail.get("desc") or ""))
        if "直播回放" in title:
            print("    跳过: 直播回放")
            continue
        cid = detail.get("cid")
        sub = ""
        if cid:
            try:
                sub = bilibili.video_subtitle_text(bvid, cid)
            except Exception as e:
                print("    字幕异常:", str(e)[:60])
        print("    字幕长度:", len(sub))
        raw = "\n".join(filter(None, [title, detail.get("desc") or "", sub]))
        print("    raw 长度:", len(raw))
        t0 = time.time()
        summary = summarize.summarize_up(raw, "视频")
        print("    摘要耗时 %.1fs, 结果长度: %s" % (time.time() - t0, len(summary or "")))
    except Exception as e:
        print("    FAIL:", str(e)[:150])
        traceback.print_exc()
    time.sleep(1)
