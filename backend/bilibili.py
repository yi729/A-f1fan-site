"""B站数据抓取：搜索、视频详情、热门评论，含 wbi 签名。

可选：把浏览器里的完整 Cookie 字符串粘到 data/bili_cookie.txt，
可显著降低风控概率（未登录时部分接口可能被限流）。
"""
import hashlib
import re
import time
import urllib.parse
from pathlib import Path

import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

_cookie = None


def load_cookie():
    global _cookie
    p = Path(__file__).resolve().parent.parent / "data" / "bili_cookie.txt"
    if p.exists():
        s = p.read_text(encoding="utf-8").strip()
        if s:
            _cookie = s


def _headers(referer="https://www.bilibili.com/"):
    h = {
        "User-Agent": UA,
        "Referer": referer,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9",
    }
    if _cookie:
        h["Cookie"] = _cookie
    return h


def _get_json(url, params=None, referer="https://www.bilibili.com/"):
    last = None
    for attempt in range(3):
        try:
            resp = requests.get(url, params=params, headers=_headers(referer), timeout=20)
            data = resp.json()
            if data.get("code") != 0:
                if data.get("code") == -412:  # 风控，重试无意义
                    raise RuntimeError(f"B站风控拦截 code=-412: {data.get('message')}")
                raise RuntimeError(f"B站接口错误 code={data.get('code')} msg={data.get('message')}")
            return data
        except requests.exceptions.RequestException as exc:
            last = exc
            time.sleep(1.0 * (attempt + 1))
    raise last


# ---------------- wbi 签名 ----------------
_MIXIN_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
    33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40,
    61, 26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11,
    36, 20, 34, 44, 52,
]

_wbi_keys = None


def _mixin_key(orig):
    return "".join(orig[i] for i in _MIXIN_TAB)[:32]


def _get_wbi_keys():
    global _wbi_keys
    if _wbi_keys:
        return _wbi_keys
    # nav 接口未登录时会返回 code=-101，但 wbi_img 密钥仍然存在，故直接取。
    resp = requests.get(
        "https://api.bilibili.com/x/web-interface/nav",
        headers=_headers(), timeout=20,
    )
    data = resp.json()
    wbi = data["data"]["wbi_img"]
    img = wbi["img_url"].rsplit("/", 1)[-1].split(".")[0]
    sub = wbi["sub_url"].rsplit("/", 1)[-1].split(".")[0]
    _wbi_keys = (img, sub)
    return _wbi_keys


def _sign(params):
    img, sub = _get_wbi_keys()
    mixin = _mixin_key(img + sub)
    params = dict(params)
    params["wts"] = int(time.time())
    params = dict(sorted(params.items()))
    params = {k: "".join(ch for ch in str(v) if ch not in "!'()*") for k, v in params.items()}
    query = urllib.parse.urlencode(params)
    params["w_rid"] = hashlib.md5((query + mixin).encode()).hexdigest()
    return params


# ---------------- 接口 ----------------
def search_videos(keyword, page=1, page_size=10):
    params = _sign({
        "search_type": "video",
        "keyword": keyword,
        "page": page,
        "page_size": page_size,
    })
    data = _get_json(
        "https://api.bilibili.com/x/web-interface/wbi/search/type",
        params, referer="https://search.bilibili.com/",
    )
    return data["data"].get("result") or []


def video_detail(bvid):
    data = _get_json(
        "https://api.bilibili.com/x/web-interface/view",
        {"bvid": bvid}, referer="https://www.bilibili.com/video/" + bvid,
    )
    return data["data"]


def hot_comments(oid):
    data = _get_json(
        "https://api.bilibili.com/x/v2/reply/main",
        {"oid": oid, "type": 1, "mode": 3, "next": 1},
        referer="https://www.bilibili.com/",
    )
    return data["data"]


def reply_main(oid, mode=3, page=1):
    """评论主列表分页：mode=3 热度 / mode=2 时间，page 为页码。"""
    data = _get_json(
        "https://api.bilibili.com/x/v2/reply/main",
        {"oid": oid, "type": 1, "mode": mode, "next": page},
        referer="https://www.bilibili.com/",
    )
    return data["data"]


def reply_newest(oid, ps=20):
    """时间排序最新评论（老接口需 wbi 签名；新接口 mode=2 首屏返回空不可用）。"""
    data = _get_json(
        "https://api.bilibili.com/x/v2/reply",
        _sign({"oid": oid, "type": 1, "sort": 0, "ps": ps, "pn": 1}),
        referer="https://www.bilibili.com/",
    )
    return (data.get("data") or {}).get("replies") or []


def reply_sub(oid, root_rpid, ps=5):
    """指定主评论的楼中楼回复。"""
    data = _get_json(
        "https://api.bilibili.com/x/v2/reply/reply",
        {"oid": oid, "type": 1, "root": root_rpid, "ps": ps},
        referer="https://www.bilibili.com/",
    )
    return (data.get("data") or {}).get("replies") or []


def _msg_text(msg):
    if isinstance(msg, str):
        return msg
    if isinstance(msg, list):
        parts = []
        for m in msg:
            if isinstance(m, dict):
                parts.append(m.get("text", ""))
            else:
                parts.append(str(m))
        return "".join(parts)
    if isinstance(msg, dict):
        return msg.get("message", "") or ""
    return ""


def _hot_comments_text(oid, top=5):
    data = hot_comments(oid)
    replies = (data.get("replies") or [])[:top]
    lines = []
    for r in replies:
        msg = _msg_text(r.get("content", {}).get("message", ""))
        if msg:
            lines.append("· " + msg.strip())
    return "\n".join(lines)


def get_post_data(bvid):
    detail = video_detail(bvid)
    aid = detail.get("aid")
    title = detail.get("title", "")
    desc = detail.get("desc", "")
    raw = title + "\n" + desc
    comments = ""
    if aid:
        try:
            comments = _hot_comments_text(aid)
        except Exception:
            comments = ""
    if comments:
        raw = raw + "\n【热门评论】\n" + comments
    return {
        "source_id": bvid,
        "title": title,
        "author": (detail.get("owner") or {}).get("name", ""),
        "url": "https://www.bilibili.com/video/" + bvid,
        "published_at": time.strftime("%Y-%m-%d", time.localtime(detail.get("pubdate", 0))),
        "raw_text": raw,
    }


def _is_f1_related(it):
    text = " ".join(filter(None, [
        it.get("title", ""), it.get("description", ""), it.get("tag", ""),
    ])).lower()
    return any(k in text for k in ("f1", "一级方程式", "方程式", "formula 1", "formula1"))


def collect_posts(category, keywords, limit=8):
    """按关键词搜索并聚合帖子，去重、过滤无关结果、按播放量排序后补详情与评论。"""
    items, seen = [], set()
    for kw in keywords:
        try:
            batch = search_videos(kw, page=1, page_size=10)
        except Exception:
            time.sleep(1)
            continue
        for it in batch:
            bvid = it.get("bvid")
            if bvid and bvid not in seen:
                seen.add(bvid)
                items.append(it)
        time.sleep(1)

    items = [it for it in items if _is_f1_related(it)]
    items.sort(key=lambda x: x.get("play", 0), reverse=True)

    posts = []
    for it in items[:limit]:
        try:
            posts.append(get_post_data(it["bvid"]))
        except Exception:
            continue
        time.sleep(0.8)
    return posts


# ---------------- UP 主空间 ----------------
def search_users(keyword, page=1, page_size=10):
    """按关键词搜索 UP 主（bili_user），返回候选列表（含 mid/uname/fans）。"""
    params = _sign({"search_type": "bili_user", "keyword": keyword, "page": page})
    data = _get_json(
        "https://api.bilibili.com/x/web-interface/wbi/search/type",
        params, referer="https://search.bilibili.com/",
    )
    return (data.get("data") or {}).get("result") or []


def up_info(mid):
    """UP 主资料（name/face）。空间接口可能被风控，由调用方兜底。"""
    params = _sign({"mid": mid})
    data = _get_json(
        "https://api.bilibili.com/x/space/wbi/acc/info",
        params, referer="https://space.bilibili.com/%d" % mid,
    )
    return data.get("data") or {}


def up_videos(mid, ps=30, pn=1):
    """UP 主投稿视频列表（按发布时间倒序）。

    空间接口风控比搜索严（大号 UP 尤甚，-412/-352 轮着来），
    -412 耐心退避重试最多 6 轮，-352（风控校验失败）只短试 2 轮，
    仍失败则抛异常，由调用方走「按 UP 名搜索」兜底。
    """
    last = None
    for attempt in range(6):
        try:
            params = _sign({"mid": mid, "ps": ps, "pn": pn, "order": "pubdate"})
            resp = requests.get(
                "https://api.bilibili.com/x/space/wbi/arc/search",
                params=params,
                headers=_headers(referer="https://space.bilibili.com/%d/video" % mid),
                timeout=20,
            )
            data = resp.json()
            if data.get("code") == 0:
                return ((data.get("data") or {}).get("list") or {}).get("vlist") or []
            if data.get("code") == -412:
                time.sleep(5 + attempt * 5)
                last = RuntimeError("B站空间接口风控 -412（已重试 %d 次）" % (attempt + 1))
                continue
            if data.get("code") == -352:
                if attempt >= 1:
                    raise RuntimeError("B站空间接口风控 -352")
                time.sleep(3)
                last = RuntimeError("B站空间接口风控 -352（已重试 %d 次）" % (attempt + 1))
                continue
            raise RuntimeError("B站接口错误 code=%s msg=%s" % (data.get("code"), data.get("message")))
        except requests.exceptions.RequestException as exc:
            last = exc
            time.sleep(2 + attempt * 2)
    raise last


def search_videos_by_up(name, page_size=30):
    """兜底：按 UP 名称搜索视频（按发布倒序），只留作者名完全一致的。

    空间投稿接口对大号 UP 风控严时用这个替身，实测覆盖近全部近期投稿。
    """
    params = _sign({
        "search_type": "video", "keyword": name, "page": 1,
        "page_size": page_size, "order": "pubdate",
    })
    data = _get_json(
        "https://api.bilibili.com/x/web-interface/wbi/search/type",
        params, referer="https://search.bilibili.com/",
    )
    res = (data.get("data") or {}).get("result") or []
    return [it for it in res if (it.get("author") or "") == name]


def up_articles(mid, ps=12, pn=1):
    """UP 主专栏列表（按发布时间倒序）。"""
    data = _get_json(
        "https://api.bilibili.com/x/space/article",
        {"mid": mid, "pn": pn, "ps": ps, "sort": "publish_time"},
        referer="https://space.bilibili.com/%d/article" % mid,
    )
    return (data.get("data") or {}).get("articles") or []


def article_view(cvid):
    """专栏全文（content 为纯文本正文）。"""
    data = _get_json(
        "https://api.bilibili.com/x/article/view",
        {"id": cvid}, referer="https://www.bilibili.com/read/cv%d" % cvid,
    )
    return data.get("data") or {}


# ---------------- 字幕（AI 字幕 / CC 字幕） ----------------
def _pb_varint(data, pos):
    result = 0
    shift = 0
    while True:
        if pos >= len(data):
            raise ValueError("truncated varint")
        b = data[pos]
        pos += 1
        result |= (b & 0x7F) << shift
        if b < 0x80:
            return result, pos
        shift += 7
        if shift > 63:
            raise ValueError("varint too long")


def _pb_fields(data):
    """解析 protobuf 消息为 (字段号, wire_type, varint值, bytes值) 列表。"""
    fields = []
    pos = 0
    while pos < len(data):
        key, pos = _pb_varint(data, pos)
        no, wire = key >> 3, key & 7
        if wire == 0:
            value, pos = _pb_varint(data, pos)
            fields.append((no, wire, value, None))
        elif wire == 2:
            length, pos = _pb_varint(data, pos)
            if pos + length > len(data):
                raise ValueError("truncated field")
            fields.append((no, wire, None, data[pos:pos + length]))
            pos += length
        elif wire in (1, 5):
            length = 8 if wire == 1 else 4
            if pos + length > len(data):
                raise ValueError("truncated field")
            fields.append((no, wire, None, data[pos:pos + length]))
            pos += length
        else:
            raise ValueError("unsupported wire type %d" % wire)
    return fields


def _pb_text(fields, no):
    for f in fields:
        if f[0] == no and f[1] == 2 and f[3] is not None:
            return f[3].decode("utf-8", "replace")
    return ""


def _subtitle_proto_tracks(bvid, aid, cid):
    """新版字幕元数据接口 /x/v2/subtitle/web/view（2026.01 起 protobuf）。

    外层 field 1(bytes) -> data；data 内重复 field 3(bytes) -> 字幕轨；
    轨内 field 1=id、3=lan、4=lan_doc、5=subtitle_url。
    任何失败返回空列表。
    """
    if not aid or not cid:
        return []
    try:
        resp = requests.get(
            "https://api.bilibili.com/x/v2/subtitle/web/view",
            params={
                "oid": cid,
                "pid": aid,
                "type": 1,
                "context_ext": '{"video_type":1}',
                "cur_production_type": 0,
                "preferred_language": "ai-zh",
                "playlist_switch": 0,
            },
            headers=_headers("https://www.bilibili.com/video/" + bvid),
            timeout=20,
        )
    except requests.exceptions.RequestException:
        return []
    if resp.status_code != 200:
        return []
    payload = resp.content
    if payload[:1] == b"{":  # 出错时返回 JSON（code/message）
        return []
    try:
        data_bytes = None
        for f in _pb_fields(payload):
            if f[0] == 1 and f[1] == 2 and f[3] is not None:
                data_bytes = f[3]
        if data_bytes is None:
            return []
        tracks = []
        for f in _pb_fields(data_bytes):
            if f[0] != 3 or f[1] != 2 or f[3] is None:
                continue
            item = _pb_fields(f[3])
            lan = _pb_text(item, 3)
            url = _pb_text(item, 5)
            if lan and url:
                tracks.append({"lan": lan, "lan_doc": _pb_text(item, 4), "url": url})
        return tracks
    except ValueError:
        return []


def _ok_subtitle_url(url):
    """只放行 B站 自有域名的字幕地址，拒绝含控制字节的混淆 URL。"""
    p = urllib.parse.urlparse(url)
    if p.scheme not in ("http", "https"):
        return False
    host = (p.hostname or "").lower()
    if not any(host == s or host.endswith("." + s)
               for s in ("hdslb.com", "bilibili.com", "biliapi.net")):
        return False
    for m in re.finditer(r"%([0-9a-fA-F]{2})", url):
        if int(m.group(1), 16) < 0x20:
            return False
    return True


# 播放器对字幕 URL 的混淆参数（从 player core JS 逆向）：
# 真实 path 逐字节与循环密钥（key+"bilibili"）异或后百分号编码，
# 域名伪装成 subtitle.bilibili.com，解密后以前缀开头、真实域名固定 aisubtitle.hdslb.com。
_SUBTITLE_OBFUSCATE = [
    ('nP](wOFRvU.+<fjS{jn-!$D|Dz&",zT`', '=CFxYRn{.y|uVyO$uh&sikph?N.ilF/`'),
    ('Bn"q~|albg@]Go~ACgyDvKnd+)_D}^&J?', "Cu~L!xs~f^&r@'vh=q]q{eeng*sEg^kp#J"),
]


def _deobfuscate_subtitle_url(url):
    m = re.search(r"//subtitle\.bilibili\.com/([^?]+)", url)
    if not m:
        return ""
    query = "?" + url.split("?", 1)[1] if "?" in url else ""
    enc = urllib.parse.unquote(m.group(1))
    for prefix, key in _SUBTITLE_OBFUSCATE:
        full_key = key + "bilibili"
        dec = "".join(
            chr(ord(c) ^ ord(full_key[i % len(full_key)]))
            for i, c in enumerate(enc)
        )
        if dec.startswith(prefix):
            return "https://aisubtitle.hdslb.com" + dec[len(prefix):] + query
    return ""


def _subtitle_body_text(url):
    """下载字幕 JSON 并把 body[].content 拼成全文；失败返回空串。"""
    if url.startswith("//"):
        url = "https:" + url
    if "subtitle.bilibili.com" in url:
        url = _deobfuscate_subtitle_url(url)
    if not _ok_subtitle_url(url):
        return ""
    try:
        resp = requests.get(url, headers=_headers(), timeout=20)
        body = (resp.json() or {}).get("body") or []
    except Exception:
        return ""
    return "\n".join(b.get("content", "") for b in body)


def _pick_lan(tracks, langs):
    """按 langs 顺序挑选轨道（数组顺序不稳定，固定优先级），无匹配返回 None。"""
    for lan in langs:
        for t in tracks:
            if (t.get("lan") or "") == lan:
                return t
    return None


def ai_subtitle_text(bvid, aid, cid, up_mid):
    """B站 AI 字幕全文（新版 protobuf 接口）；未登录/无 AI 轨道/失败返回空串。"""
    if not _cookie:
        return ""
    tracks = _subtitle_proto_tracks(bvid, aid, cid)
    target = _pick_lan(tracks, ("ai-zh", "ai-zh-Hans", "ai-en"))
    if target is None:
        target = next(
            (t for t in tracks if (t.get("lan") or "").startswith("ai-")), None
        )
    if not target:
        return ""
    return _subtitle_body_text(target.get("subtitle_url") or target.get("url") or "")


def video_subtitle_text(bvid, cid, aid=None):
    """视频 CC（人工上传）字幕全文。

    先试 wbi/v2（JSON 元数据），拿不到再试新版 protobuf 接口里的人工轨；
    无字幕或任何失败返回空串。
    """
    subs = []
    try:
        params = _sign({"bvid": bvid, "cid": cid})
        data = _get_json(
            "https://api.bilibili.com/x/player/wbi/v2",
            params, referer="https://www.bilibili.com/video/" + bvid,
        )
        subs = ((data.get("data") or {}).get("subtitle") or {}).get("subtitles") or []
    except Exception:
        pass
    target = _pick_lan(subs, ("zh-Hans", "zh-CN", "zh-Hant", "zh-TW"))
    if target is None:
        target = next((s for s in subs if "zh" in (s.get("lan") or "").lower()), None)
    if target is None:
        target = next((s for s in subs if not (s.get("lan") or "").lower().startswith("ai-")), None)
    if target is None and aid:
        proto = _subtitle_proto_tracks(bvid, aid, cid)
        target = _pick_lan(proto, ("zh-Hans", "zh-CN", "zh-Hant", "zh-TW"))
        if target is None:
            target = next((t for t in proto if not (t.get("lan") or "").startswith("ai-")), None)
    if not target:
        return ""
    return _subtitle_body_text(target.get("subtitle_url") or target.get("url") or "")
