"""FastAPI 入口：F1 数据接口 + 帖子接口 + UP 订阅接口 + 静态前端。"""
import hashlib
import os
import re
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import BackgroundTasks, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import db
import f1
import pipeline
import upsub
import comment

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR.parent / "frontend"
DB_PATH = BASE_DIR.parent / "data" / "f1.db"

db.init(str(DB_PATH))

_scheduler = None

# 公网部署时建议设置，防止任何人触发抓取。
SCRAPE_TOKEN = os.environ.get("SCRAPE_TOKEN", "").strip()


def scrape_interval_hours():
    return float(os.environ.get("SCRAPE_INTERVAL_HOURS", "6"))


def up_check_interval_hours():
    return float(os.environ.get("UP_CHECK_INTERVAL_HOURS", "2"))


@asynccontextmanager
async def lifespan(_app):
    global _scheduler
    _scheduler = BackgroundScheduler()
    _scheduler.add_job(
        pipeline.run,
        "interval",
        hours=scrape_interval_hours(),
        id="auto-scrape",
        max_instances=1,
        coalesce=True,
    )
    # UP 主订阅检查：启动 10 秒后先跑一轮，之后每 2 小时
    _scheduler.add_job(
        upsub.run,
        "interval",
        hours=up_check_interval_hours(),
        id="auto-upcheck",
        max_instances=1,
        coalesce=True,
        next_run_time=datetime.now() + timedelta(seconds=10),
    )
    # 字幕复查：每周把近期「简介」视频再查一遍（B站 AI 字幕可能晚生成）
    _scheduler.add_job(
        upsub.recheck_subtitles,
        "interval",
        days=7,
        id="auto-subrecheck",
        max_instances=1,
        coalesce=True,
        next_run_time=datetime.now() + timedelta(minutes=30),
    )
    # 评论区观点汇总：启动 15 分钟后先跑一轮，之后每 6 小时
    _scheduler.add_job(
        comment.run,
        "interval",
        hours=6,
        id="auto-comments",
        max_instances=1,
        coalesce=True,
        next_run_time=datetime.now() + timedelta(minutes=15),
    )
    _scheduler.start()
    yield
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)


app = FastAPI(title="F1 数据中心", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------- F1 接口 ----------------
@app.get("/api/f1/seasons")
def api_seasons():
    return f1.get_seasons()


@app.get("/api/f1/standings/drivers")
def api_standings_drivers(season: int | None = None, round: int | None = None):
    return f1.get_driver_standings(season, round)


@app.get("/api/f1/standings/constructors")
def api_standings_constructors(season: int | None = None, round: int | None = None):
    return f1.get_constructor_standings(season, round)


@app.get("/api/f1/season/{season}/races")
def api_season_races(season: int):
    return f1.get_season_races(season)


@app.get("/api/f1/season/{season}/race/{round}/results")
def api_race_results(season: int, round: int):
    return f1.get_race_results(season, round)


@app.get("/api/f1/drivers")
def api_drivers():
    return f1.get_all_drivers()


@app.get("/api/f1/driver/{driver_id}/career")
def api_driver_career(driver_id: str):
    return f1.get_driver_career(driver_id)


@app.get("/api/f1/compare")
def api_compare(d1: str, d2: str):
    return f1.compare_drivers(d1, d2)


@app.get("/api/f1/trend")
def api_trend(season: int):
    try:
        return f1.get_points_trend(season)
    except Exception:
        raise HTTPException(status_code=503, detail="上游数据源繁忙或限流，请稍后重试")


@app.get("/api/f1/calendar/{year}")
def api_calendar(year: int):
    return f1.get_calendar(year)


# ---------------- 帖子接口 ----------------
@app.get("/api/posts")
def api_posts():
    return db.list_posts()


@app.get("/api/search")
def api_search(q: str = ""):
    q = (q or "").strip()
    if not q:
        return {"posts": [], "upPosts": []}
    return {"posts": db.search_posts(q), "upPosts": db.search_up_posts(q)}


def _require_token(token, x_scrape_token):
    if SCRAPE_TOKEN:
        supplied = token or x_scrape_token
        if supplied != SCRAPE_TOKEN:
            raise HTTPException(status_code=403, detail="token 无效")


@app.post("/api/scrape")
def api_scrape(
    background_tasks: BackgroundTasks,
    token: str | None = None,
    x_scrape_token: str | None = Header(default=None),
):
    _require_token(token, x_scrape_token)
    if pipeline.is_running():
        return {"started": False, "busy": True}
    background_tasks.add_task(pipeline.run)
    return {"started": True}


# ---------------- UP 订阅接口 ----------------
@app.get("/api/ups")
def api_ups():
    return db.list_subscriptions()


# ---------------- 用户账号 ----------------
SESSION_DAYS = 30
MAX_SUBS_PER_USER = 10
_NICK_RE = re.compile(r"^[\w\u4e00-\u9fa5-]{1,20}$")


def _hash_pw(password):
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), 100_000)
    return salt + ":" + dk.hex()


def _check_pw(password, stored):
    try:
        salt, hex_dk = stored.split(":", 1)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), 100_000)
        return secrets.compare_digest(dk.hex(), hex_dk)
    except Exception:
        return False


def _token_hash(raw):
    return hashlib.sha256(raw.encode()).hexdigest()


def _issue_session(user_id):
    raw = secrets.token_hex(32)
    expires = (datetime.now() + timedelta(days=SESSION_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
    db.create_session(_token_hash(raw), user_id, expires)
    return raw


def _auth_user(authorization, x_user_token):
    raw = ""
    if authorization and authorization.lower().startswith("bearer "):
        raw = authorization[7:].strip()
    elif x_user_token:
        raw = x_user_token.strip()
    if not raw:
        return None
    return db.session_user(_token_hash(raw))


@app.post("/api/auth/register")
def api_auth_register(payload: dict):
    nickname = ((payload or {}).get("nickname") or "").strip()
    password = (payload or {}).get("password") or ""
    if not _NICK_RE.fullmatch(nickname):
        raise HTTPException(status_code=400, detail="昵称需为 1~20 位中英文/数字/下划线/连字符")
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="密码至少 6 位")
    user_id = db.create_user(nickname, _hash_pw(password))
    if not user_id:
        raise HTTPException(status_code=409, detail="昵称已被注册")
    return {"token": _issue_session(user_id), "nickname": nickname}


@app.post("/api/auth/login")
def api_auth_login(payload: dict):
    nickname = ((payload or {}).get("nickname") or "").strip()
    password = (payload or {}).get("password") or ""
    user = db.get_user_by_nickname(nickname)
    if not user or not _check_pw(password, user["pass_hash"]):
        raise HTTPException(status_code=401, detail="昵称或密码不正确")
    return {"token": _issue_session(user["id"]), "nickname": user["nickname"]}


@app.post("/api/auth/logout")
def api_auth_logout(
    authorization: str | None = Header(default=None),
    x_user_token: str | None = Header(default=None),
):
    raw = ""
    if authorization and authorization.lower().startswith("bearer "):
        raw = authorization[7:].strip()
    elif x_user_token:
        raw = x_user_token.strip()
    if raw:
        db.delete_session(_token_hash(raw))
    return {"ok": True}


@app.get("/api/auth/me")
def api_auth_me(
    authorization: str | None = Header(default=None),
    x_user_token: str | None = Header(default=None),
):
    user_id = _auth_user(authorization, x_user_token)
    if not user_id:
        raise HTTPException(status_code=401, detail="未登录")
    user = db.get_user_by_id(user_id)
    return {"nickname": (user or {}).get("nickname") or ""}


@app.post("/api/auth/password")
def api_auth_password(
    payload: dict,
    authorization: str | None = Header(default=None),
    x_user_token: str | None = Header(default=None),
):
    user_id = _auth_user(authorization, x_user_token)
    if not user_id:
        raise HTTPException(status_code=401, detail="请先登录")
    user = db.get_user_by_id(user_id)
    if not user or not _check_pw((payload or {}).get("old_password") or "", user["pass_hash"]):
        raise HTTPException(status_code=401, detail="当前密码不正确")
    new_pw = (payload or {}).get("new_password") or ""
    if len(new_pw) < 6:
        raise HTTPException(status_code=400, detail="新密码至少 6 位")
    db.update_user_password(user_id, _hash_pw(new_pw))
    return {"ok": True}


@app.post("/api/auth/delete")
def api_auth_delete(
    authorization: str | None = Header(default=None),
    x_user_token: str | None = Header(default=None),
):
    user_id = _auth_user(authorization, x_user_token)
    if not user_id:
        raise HTTPException(status_code=401, detail="请先登录")
    db.delete_user(user_id)
    return {"ok": True}


@app.get("/api/ups/mine")
def api_ups_mine(
    authorization: str | None = Header(default=None),
    x_user_token: str | None = Header(default=None),
):
    user_id = _auth_user(authorization, x_user_token)
    if not user_id:
        raise HTTPException(status_code=401, detail="请先登录")
    return db.list_user_subs(user_id)


@app.post("/api/ups/mine")
def api_ups_mine_add(
    payload: dict,
    authorization: str | None = Header(default=None),
    x_user_token: str | None = Header(default=None),
):
    user_id = _auth_user(authorization, x_user_token)
    if not user_id:
        raise HTTPException(status_code=401, detail="请先登录")
    if db.user_sub_count(user_id) >= MAX_SUBS_PER_USER:
        raise HTTPException(status_code=400, detail="最多订阅 %d 个 UP" % MAX_SUBS_PER_USER)
    text = (payload or {}).get("text") or ""
    up = upsub.resolve_up(text)
    if not up:
        raise HTTPException(status_code=404, detail="未找到该 UP 主，请检查链接或名称")
    db.add_user_sub(user_id, up["mid"], up["name"], up["avatar"])
    upsub.check_up_mid(up["mid"], up["name"])
    return {"ok": True, "subscription": {"mid": up["mid"], "name": up["name"], "avatar": up["avatar"]}}


@app.post("/api/ups/mine/{mid}/toggle")
def api_ups_mine_toggle(
    mid: int,
    authorization: str | None = Header(default=None),
    x_user_token: str | None = Header(default=None),
):
    user_id = _auth_user(authorization, x_user_token)
    if not user_id:
        raise HTTPException(status_code=401, detail="请先登录")
    sub = next((s for s in db.list_user_subs(user_id) if s["mid"] == mid), None)
    if not sub:
        raise HTTPException(status_code=404, detail="订阅不存在")
    enabled = not sub["enabled"]
    db.set_user_sub_enabled(user_id, mid, enabled)
    return {"ok": True, "enabled": enabled}


@app.delete("/api/ups/mine/{mid}")
def api_ups_mine_delete(
    mid: int,
    authorization: str | None = Header(default=None),
    x_user_token: str | None = Header(default=None),
):
    user_id = _auth_user(authorization, x_user_token)
    if not user_id:
        raise HTTPException(status_code=401, detail="请先登录")
    db.delete_user_sub(user_id, mid)
    return {"ok": True}


@app.post("/api/ups")
def api_ups_add(
    payload: dict,
    token: str | None = None,
    x_scrape_token: str | None = Header(default=None),
):
    """添加订阅：payload 为 {"text": "空间链接 / mid / UP 名称"}。"""
    _require_token(token, x_scrape_token)
    text = (payload or {}).get("text") or ""
    up = upsub.resolve_up(text)
    if not up:
        raise HTTPException(status_code=404, detail="未找到该 UP 主，请检查链接或名称")
    db.add_subscription(up["mid"], up["name"], up["avatar"])
    return {"ok": True, "subscription": {"mid": up["mid"], "name": up["name"], "avatar": up["avatar"]}}


@app.post("/api/ups/{mid}/toggle")
def api_ups_toggle(
    mid: int,
    token: str | None = None,
    x_scrape_token: str | None = Header(default=None),
):
    _require_token(token, x_scrape_token)
    sub = next((s for s in db.list_subscriptions() if s["mid"] == mid), None)
    if not sub:
        raise HTTPException(status_code=404, detail="订阅不存在")
    enabled = not sub["enabled"]
    db.set_subscription_enabled(mid, enabled)
    return {"ok": True, "enabled": enabled}


@app.delete("/api/ups/{mid}")
def api_ups_delete(
    mid: int,
    token: str | None = None,
    x_scrape_token: str | None = Header(default=None),
):
    _require_token(token, x_scrape_token)
    db.delete_subscription(mid)
    return {"ok": True}


@app.get("/api/ups/posts")
def api_ups_posts(
    authorization: str | None = Header(default=None),
    x_user_token: str | None = Header(default=None),
):
    """登录用户看「公共 + 我的」合并内容，游客只看公共订阅。"""
    mids = [s["mid"] for s in db.list_subscriptions()]
    user_id = _auth_user(authorization, x_user_token)
    if user_id:
        mids = list(dict.fromkeys(mids + [s["mid"] for s in db.list_user_subs(user_id)]))
    return db.list_up_posts_for_mids(mids)


@app.post("/api/ups/check")
def api_ups_check(
    background_tasks: BackgroundTasks,
    token: str | None = None,
    x_scrape_token: str | None = Header(default=None),
):
    _require_token(token, x_scrape_token)
    if upsub.is_running():
        return {"started": False, "busy": True}
    background_tasks.add_task(upsub.run)
    return {"started": True}


@app.get("/api/scheduler/status")
def api_scheduler_status():
    job = _scheduler.get_job("auto-scrape") if _scheduler is not None else None
    up_job = _scheduler.get_job("auto-upcheck") if _scheduler is not None else None
    return {
        "running": bool(_scheduler is not None and _scheduler.running),
        "intervalHours": scrape_interval_hours(),
        "nextRun": str(job.next_run_time) if job is not None and job.next_run_time else None,
        "upIntervalHours": up_check_interval_hours(),
        "upNextRun": str(up_job.next_run_time) if up_job is not None and up_job.next_run_time else None,
    }


app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="static")
