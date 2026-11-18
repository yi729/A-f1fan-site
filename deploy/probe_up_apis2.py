"""第二轮探测：找第 4 个 UP、空间视频/专栏列表、文章全文、视频字幕。"""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

import bilibili  # noqa: E402


def j(url, params=None, referer="https://www.bilibili.com/"):
    import requests
    return requests.get(url, params=params, headers={
        "User-Agent": bilibili.UA, "Referer": referer,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9",
    }, timeout=20)


def search_user(name):
    params = bilibili._sign({"search_type": "bili_user", "keyword": name, "page": 1})
    r = j("https://api.bilibili.com/x/web-interface/wbi/search/type", params,
          referer="https://search.bilibili.com/")
    d = r.json()
    res = (d.get("data") or {}).get("result") or []
    print(f"--- 用户搜索 {name}: code={d.get('code')} 命中 {len(res)}")
    for it in res[:4]:
        print("   mid=%s uname=%s fans=%s" % (it.get("mid"), it.get("uname"), it.get("fans")))


# 1. 第 4 个 UP 的名称变体
for name in ["F1赛事资讯", "F1赛事", "F1 赛事资讯", "F1赛事咨讯"]:
    search_user(name)
    time.sleep(1.5)

print()
# 2. 空间视频列表（临渊）
MID = 174570683
try:
    params = bilibili._sign({"mid": MID, "ps": 5, "pn": 1, "order": "pubdate"})
    r = j("https://api.bilibili.com/x/space/wbi/arc/search", params,
          referer=f"https://space.bilibili.com/{MID}/video")
    d = r.json()
    print("--- 空间视频列表 code=%s msg=%s" % (d.get("code"), d.get("message")))
    vlist = (d.get("data") or {}).get("list") or {}
    vids = vlist.get("vlist") or []
    for v in vids[:3]:
        print("   bvid=%s title=%s created=%s" % (v.get("bvid"), v.get("title"), v.get("created")))
except Exception as e:
    print("--- 空间视频列表失败:", e)

print()
# 3. 空间专栏列表
try:
    r = j("https://api.bilibili.com/x/space/article",
          {"mid": MID, "pn": 1, "ps": 5, "sort": "publish_time"},
          referer=f"https://space.bilibili.com/{MID}/article")
    d = r.json()
    print("--- 空间专栏列表 code=%s msg=%s" % (d.get("code"), d.get("message")))
    arts = (d.get("data") or {}).get("articles") or []
    for a in arts[:3]:
        print("   cvid=%s title=%s publish=%s" % (a.get("id"), a.get("title"), a.get("publish_time")))
except Exception as e:
    print("--- 空间专栏列表失败:", e)

print()
# 4. 文章全文（拿第一个 cvid 试）
cv = None
try:
    r = j("https://api.bilibili.com/x/space/article",
          {"mid": MID, "pn": 1, "ps": 1, "sort": "publish_time"})
    arts = (r.json().get("data") or {}).get("articles") or []
    if arts:
        cv = arts[0]["id"]
except Exception:
    pass
if cv:
    try:
        r = j("https://api.bilibili.com/x/article/view", {"id": cv},
              referer=f"https://www.bilibili.com/read/cv{cv}")
        d = r.json()
        data = d.get("data") or {}
        print("--- 文章全文 code=%s, 字段: %s" % (d.get("code"), list(data.keys())))
        print("   title:", data.get("title"))
        print("   content 长度:", len(data.get("content") or ""))
        print("   content 前 200 字:", (data.get("content") or "")[:200])
    except Exception as e:
        print("--- 文章全文失败:", e)

print()
# 5. 视频字幕（拿临渊最新视频试）
bvid = None
try:
    params = bilibili._sign({"mid": MID, "ps": 1, "pn": 1, "order": "pubdate"})
    r = j("https://api.bilibili.com/x/space/wbi/arc/search", params)
    vids = ((r.json().get("data") or {}).get("list") or {}).get("vlist") or []
    if vids:
        bvid = vids[0]["bvid"]
except Exception:
    pass
if bvid:
    try:
        detail = bilibili.video_detail(bvid)
        cid = detail.get("cid")
        aid = detail.get("aid")
        print("--- 视频 %s title=%s aid=%s cid=%s" % (bvid, detail.get("title"), aid, cid))
        params = bilibili._sign({"bvid": bvid, "cid": cid})
        r = j("https://api.bilibili.com/x/player/wbi/v2", params,
              referer="https://www.bilibili.com/video/" + bvid)
        d = r.json()
        sub = ((d.get("data") or {}).get("subtitle") or {}).get("subtitles") or []
        print("--- player v2 code=%s, 字幕列表 %d 条" % (d.get("code"), len(sub)))
        for s in sub[:5]:
            print("   lan=%s url=%s" % (s.get("lan"), s.get("subtitle_url")))
        if sub:
            u = sub[0]["subtitle_url"]
            if u.startswith("//"):
                u = "https:" + u
            r2 = j(u)
            body = r2.json().get("body") or []
            print("--- 字幕内容 %d 句, 前 3 句:" % len(body))
            for b in body[:3]:
                print("   ", b.get("from"), "-", b.get("to"), b.get("content"))
    except Exception as e:
        import traceback
        traceback.print_exc()
        print("--- 字幕探测失败:", e)
