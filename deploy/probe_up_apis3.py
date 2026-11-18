"""探测空间视频列表的 -412 风控绕过方案。"""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

import bilibili  # noqa: E402
import requests

MID = 174570683


def j(url, params=None, referer="https://www.bilibili.com/"):
    return requests.get(url, params=params, headers={
        "User-Agent": bilibili.UA, "Referer": referer,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9",
    }, timeout=20)


# A. 老接口 x/space/arc/search（无 wbi）
try:
    r = j("https://api.bilibili.com/x/space/arc/search",
          {"mid": MID, "ps": 3, "pn": 1, "order": "pubdate"},
          referer=f"https://space.bilibili.com/{MID}/video")
    d = r.json()
    vids = ((d.get("data") or {}).get("list") or {}).get("vlist") or []
    print("A. 老接口 x/space/arc/search: code=%s 返回 %d 条" % (d.get("code"), len(vids)))
    for v in vids[:3]:
        print("   bvid=%s title=%s" % (v.get("bvid"), v.get("title")))
except Exception as e:
    print("A. 老接口失败:", e)

time.sleep(3)

# B. wbi 接口重试（等 10 秒后）
for attempt in range(3):
    try:
        params = bilibili._sign({"mid": MID, "ps": 3, "pn": 1, "order": "pubdate"})
        r = j("https://api.bilibili.com/x/space/wbi/arc/search", params,
              referer=f"https://space.bilibili.com/{MID}/video")
        d = r.json()
        vids = ((d.get("data") or {}).get("list") or {}).get("vlist") or []
        print(f"B. wbi 重试第 {attempt+1} 次: code={d.get('code')} 返回 {len(vids)} 条")
        if d.get("code") == 0:
            for v in vids[:3]:
                print("   bvid=%s title=%s" % (v.get("bvid"), v.get("title")))
            break
    except Exception as e:
        print(f"B. wbi 重试第 {attempt+1} 次失败: {e}")
    time.sleep(8)

# C. 动态接口（无需登录的版本）x/polymer/web-dynamic/v1/feed/space
try:
    r = j("https://api.bilibili.com/x/polymer/web-dynamic/v1/feed/space",
          {"host_mid": MID}, referer=f"https://space.bilibili.com/{MID}/dynamic")
    d = r.json()
    items = (d.get("data") or {}).get("items") or []
    print("C. 动态 feed/space: code=%s msg=%s 返回 %d 条" % (d.get("code"), d.get("message"), len(items)))
except Exception as e:
    print("C. 动态接口失败:", e)

# D. 移动端接口 app.bilibili.com/x/v2/space/arc/search
try:
    r = j("https://app.bilibili.com/x/v2/space/arc/search",
          {"mid": MID, "ps": 3, "pn": 1}, referer="https://app.bilibili.com/")
    d = r.json()
    vids = ((d.get("data") or {}).get("list") or {}).get("vlist") or []
    print("D. app 接口 arc/search: code=%s 返回 %d 条" % (d.get("code"), len(vids)))
    for v in vids[:3]:
        print("   bvid=%s title=%s" % (v.get("bvid"), v.get("title")))
except Exception as e:
    print("D. app 接口失败:", e)
