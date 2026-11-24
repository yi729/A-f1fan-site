"""小红书抓取：Playwright 无头浏览器自动化。

小红书网页搜索强制登录，且接口带 x-s 签名（前端混淆 JS 实时计算），
裸 HTTP 请求会被网关拒绝（实测 code:-1 / 500）。本模块用 Playwright
打开搜索页/详情页，拦截页面自己发出的 API JSON 响应取数据
（签名与 Cookie 由页面环境自动处理）。

登录态：data/xhs_cookie.txt 存完整 Cookie 头原文（用户从浏览器
DevTools Network 面板复制任一 xiaohongshu.com 请求的 Cookie 行），
启动时注入浏览器。Cookie 约 30 天过期，失效时 search_notes 抛
「Cookie 已失效」错误，需用户重新导出。

内存控制：整个抓取任务共享一个浏览器实例，任务结束即关闭，不常驻。
"""
import time
from pathlib import Path
from urllib.parse import quote

SEARCH_API = "sns/web/v2/search/notes"

_COOKIE_PATH = Path(__file__).resolve().parent.parent / "data" / "xhs_cookie.txt"

_pw = None
_browser = None
_context = None
_page = None


def cookie_available():
    return _COOKIE_PATH.exists() and bool(_COOKIE_PATH.read_text(encoding="utf-8").strip())


def _parse_cookie(text):
    cookies = []
    for part in text.split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        name, _, value = part.partition("=")
        cookies.append({
            "name": name.strip(),
            "value": value.strip(),
            "domain": ".xiaohongshu.com",
            "path": "/",
        })
    return cookies


def launch():
    """启动无头 Chromium 并注入 Cookie；重复调用会先关掉旧实例。"""
    global _pw, _browser, _context, _page
    close()
    from playwright.sync_api import sync_playwright
    raw = _COOKIE_PATH.read_text(encoding="utf-8").strip()
    if not raw:
        raise RuntimeError("未配置小红书 Cookie（data/xhs_cookie.txt）")
    _pw = sync_playwright().start()
    try:
        _browser = _pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
        )
    except Exception:
        _pw.stop()
        _pw = None
        raise
    _context = _browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        ),
        viewport={"width": 1366, "height": 900},
        locale="zh-CN",
    )
    _context.add_cookies(_parse_cookie(raw))
    _page = _context.new_page()


def close():
    global _pw, _browser, _context, _page
    try:
        if _page is not None:
            _page.close()
    except Exception:
        pass
    try:
        if _context is not None:
            _context.close()
    except Exception:
        pass
    try:
        if _browser is not None:
            _browser.close()
    except Exception:
        pass
    try:
        if _pw is not None:
            _pw.stop()
    except Exception:
        pass
    _pw = _browser = _context = _page = None


def _wait_json(action, api_kw, timeout=25000):
    """执行 action（页面导航），拦截并返回 URL 含 api_kw 的 JSON 响应；无匹配返回 None。"""
    try:
        with _page.expect_response(
            lambda r: api_kw in r.url, timeout=timeout
        ) as ri:
            action()
        return ri.value.json()
    except Exception:
        return None


def _ensure_page():
    if _page is None or _browser is None:
        launch()


def search_notes(keyword):
    """搜索关键词，返回笔记条目列表；Cookie 失效抛 RuntimeError。"""
    _ensure_page()
    url = "https://www.xiaohongshu.com/search_result?keyword=" + quote(keyword)
    data = _wait_json(
        lambda: _page.goto(url, wait_until="domcontentloaded"), SEARCH_API
    )
    if data is None:
        try:
            html = _page.content() or ""
        except Exception:
            html = ""
        if "登录后查看搜索结果" in html:
            raise RuntimeError("小红书 Cookie 已失效，请重新导出（data/xhs_cookie.txt）")
        raise RuntimeError("搜索请求未返回（可能被风控）：" + keyword)
    if not data.get("success"):
        raise RuntimeError(
            "搜索失败 code=%s msg=%s" % (data.get("code"), data.get("msg"))
        )
    items = (data.get("data") or {}).get("items") or []
    out = []
    for it in items:
        card = it.get("note_card") or {}
        user = card.get("user") or {}
        interact = card.get("interact_info") or {}
        cover = card.get("cover") or {}
        out.append({
            "note_id": it.get("id") or it.get("note_id") or "",
            "xsec_token": it.get("xsec_token") or "",
            "title": card.get("display_title") or "",
            "author": user.get("nickname") or "",
            "likes": interact.get("liked_count") or 0,
            "cover": cover.get("url_default") or cover.get("url") or "",
            "is_video": card.get("type") == "video",
            "time": card.get("time") or 0,  # 毫秒时间戳
        })
    return out


def get_note(note_id, xsec_token=""):
    """打开笔记详情页，从 SSR 状态 __INITIAL_STATE__.note 取正文；失败返回 None。

    详情页不再发 feed 接口（已废弃），笔记数据由服务端直出到页面
    __INITIAL_STATE__.note.noteDetailMap[note_id].note。
    """
    _ensure_page()
    url = "https://www.xiaohongshu.com/explore/" + note_id
    if xsec_token:
        url += "?xsec_token=" + quote(xsec_token)
    try:
        _page.goto(url, wait_until="domcontentloaded")
    except Exception:
        return None
    for _ in range(10):
        detail = _page.evaluate(GET_NOTE_JS)
        if detail:
            return detail
        _page.wait_for_timeout(1000)
    return None


GET_NOTE_JS = """() => {
  const st = window.__INITIAL_STATE__;
  if (!st || !st.note) return null;
  const map = st.note.noteDetailMap || {};
  const k = Object.keys(map).find((x) => x.length > 5);
  if (!k) return null;
  const card = (map[k] || {}).note;
  if (!card) return null;
  return {
    title: card.title || card.displayTitle || "",
    author: (card.user || {}).nickname || "",
    desc: card.desc || "",
    time: card.time || 0,
  };
}"""


def ms_to_date(ms):
    if not ms:
        return ""
    try:
        return time.strftime("%Y-%m-%d", time.localtime(ms / 1000))
    except Exception:
        return ""


def note_url(note_id, xsec_token=""):
    url = "https://www.xiaohongshu.com/explore/" + note_id
    if xsec_token:
        url += "?xsec_token=" + quote(xsec_token)
    return url
