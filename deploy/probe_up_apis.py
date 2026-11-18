"""探测 B站 UP 空间相关接口的可用性与返回结构（本地运行）。"""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

import bilibili  # noqa: E402

UA = bilibili.UA


def j(url, params=None, referer="https://www.bilibili.com/"):
    import requests
    r = requests.get(url, params=params, headers={
        "User-Agent": UA, "Referer": referer,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9",
    }, timeout=20)
    return r


def show(label, data, keys=None, limit=2):
    print("=" * 20, label, "=" * 20)
    if isinstance(data, dict):
        print("code:", data.get("code"), "msg:", data.get("message"))
        d = data.get("data")
        if d is None:
            print("data: None")
            return
        if isinstance(d, list):
            print("data list len:", len(d))
            for it in d[:limit]:
                print(json.dumps(it, ensure_ascii=False)[:500])
        elif isinstance(d, dict):
            print("data keys:", list(d.keys()))
            print(json.dumps(d, ensure_ascii=False)[:800])
        else:
            print("data:", str(d)[:300])
    else:
        print(str(data)[:500])


# 1. 用户搜索，找 4 个 UP 的 mid
names = ["临渊_Aslinger", "F1赛事咨讯", "Chester117", "F1世界锦标赛"]
for name in names:
    try:
        params = bilibili._sign({"search_type": "bili_user", "keyword": name, "page": 1})
        r = j("https://api.bilibili.com/x/web-interface/wbi/search/type", params,
              referer="https://search.bilibili.com/")
        d = r.json()
        res = (d.get("data") or {}).get("result") or []
        print(f"--- 用户搜索 {name}: code={d.get('code')} 命中 {len(res)}")
        for it in res[:3]:
            print("   mid=%s uname=%s fans=%s" % (
                it.get("mid"), it.get("uname"), it.get("fans")))
    except Exception as e:
        print(f"--- 用户搜索 {name} 失败: {e}")
    time.sleep(1.5)

print()
# 2. 空间视频列表（wbi）
mid = 353380171  # 占位，先随便试一个已知 mid；拿到真实 mid 后再跑
try:
    params = bilibili._sign({"mid": mid, "ps": 5, "pn": 1, "order": "pubdate"})
    r = j("https://api.bilibili.com/x/space/wbi/arc/search", params,
          referer=f"https://space.bilibili.com/{mid}/video")
    d = r.json()
    vlist = (d.get("data") or {}).get("list") or {}
    vids = vlist.get("vlist") or []
    print("--- 空间视频列表: code=%s, 返回 %d 条" % (d.get("code"), len(vids)))
    for v in vids[:3]:
        print("   bvid=%s title=%s pic=%s pubdate=%s" % (
            v.get("bvid"), v.get("title"), v.get("pic"), v.get("created")))
except Exception as e:
    print("--- 空间视频列表失败:", e)
