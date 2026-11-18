"""SQLite 存取：帖子与抓取日志。"""
import os
import sqlite3
import threading
import time

_conn = None
_lock = threading.Lock()


def init(db_path):
    global _conn
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    _conn = sqlite3.connect(db_path, check_same_thread=False)
    _conn.row_factory = sqlite3.Row
    with _lock:
        _conn.execute(
            """CREATE TABLE IF NOT EXISTS posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform TEXT NOT NULL,
                source_id TEXT NOT NULL,
                title TEXT,
                author TEXT,
                url TEXT,
                published_at TEXT,
                category TEXT,
                raw_text TEXT,
                summary TEXT,
                created_at TEXT
            )"""
        )
        _conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_posts_platform_source ON posts(platform, source_id)"
        )
        _conn.execute(
            """CREATE TABLE IF NOT EXISTS scrape_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TEXT,
                finished_at TEXT,
                total INTEGER,
                added INTEGER,
                error TEXT
            )"""
        )
        # 迁移：老库补 race 列（所属大奖赛 / 赛季整体）
        cols = [r[1] for r in _conn.execute("PRAGMA table_info(posts)").fetchall()]
        if "race" not in cols:
            _conn.execute("ALTER TABLE posts ADD COLUMN race TEXT")
        if "comment_summary" not in cols:
            _conn.execute("ALTER TABLE posts ADD COLUMN comment_summary TEXT")
        if "comment_at" not in cols:
            _conn.execute("ALTER TABLE posts ADD COLUMN comment_at TEXT")
        if "comment_samples" not in cols:
            _conn.execute("ALTER TABLE posts ADD COLUMN comment_samples TEXT")
        # UP 主订阅与内容汇总
        _conn.execute(
            """CREATE TABLE IF NOT EXISTS up_subscriptions (
                mid INTEGER PRIMARY KEY,
                name TEXT,
                avatar TEXT,
                enabled INTEGER DEFAULT 1,
                created_at TEXT
            )"""
        )
        _conn.execute(
            """CREATE TABLE IF NOT EXISTS up_posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mid INTEGER,
                source_type TEXT,
                source_id TEXT,
                title TEXT,
                author TEXT,
                url TEXT,
                cover TEXT,
                published_at TEXT,
                summary TEXT,
                summary_type TEXT,
                subtitle_text TEXT DEFAULT '',
                created_at TEXT
            )"""
        )
        _conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_up_posts_type_source ON up_posts(source_type, source_id)"
        )
        cols = [r[1] for r in _conn.execute("PRAGMA table_info(up_posts)").fetchall()]
        if "subtitle_text" not in cols:
            _conn.execute("ALTER TABLE up_posts ADD COLUMN subtitle_text TEXT DEFAULT ''")
        if "comment_summary" not in cols:
            _conn.execute("ALTER TABLE up_posts ADD COLUMN comment_summary TEXT")
        if "comment_at" not in cols:
            _conn.execute("ALTER TABLE up_posts ADD COLUMN comment_at TEXT")
        if "comment_samples" not in cols:
            _conn.execute("ALTER TABLE up_posts ADD COLUMN comment_samples TEXT")
        # 用户账号与个人订阅
        _conn.execute(
            """CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nickname TEXT UNIQUE NOT NULL,
                pass_hash TEXT NOT NULL,
                created_at TEXT
            )"""
        )
        _conn.execute(
            """CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY,
                user_id INTEGER,
                expires_at TEXT,
                created_at TEXT
            )"""
        )
        _conn.execute(
            """CREATE TABLE IF NOT EXISTS user_subs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                mid INTEGER,
                name TEXT,
                avatar TEXT,
                enabled INTEGER DEFAULT 1,
                created_at TEXT
            )"""
        )
        _conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_user_subs_user_mid ON user_subs(user_id, mid)"
        )
        _conn.execute(
            """CREATE TABLE IF NOT EXISTS user_favs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                item_type TEXT,
                item_id INTEGER,
                created_at TEXT
            )"""
        )
        _conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_user_favs ON user_favs(user_id, item_type, item_id)"
        )
        _conn.commit()


def add_post(platform, source_id, title, author, url, published_at, category, raw_text, summary, race):
    with _lock:
        cur = _conn.execute(
            """INSERT OR IGNORE INTO posts
               (platform, source_id, title, author, url, published_at, category, raw_text, summary, race, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (platform, source_id, title, author, url, published_at, category, raw_text, summary,
             race, time.strftime("%Y-%m-%d %H:%M:%S")),
        )
        _conn.commit()
        return cur.rowcount > 0


def post_exists(platform, source_id):
    with _lock:
        row = _conn.execute(
            "SELECT 1 FROM posts WHERE platform=? AND source_id=?", (platform, source_id)
        ).fetchone()
        return row is not None


def race_covered(race_name):
    """该分站是否已收录过帖子（决定是否继续搜索该站）。"""
    with _lock:
        row = _conn.execute(
            "SELECT COUNT(*) AS n FROM posts WHERE race=?", (race_name,)
        ).fetchone()
        return (row[0] if row else 0) > 0


def run_count():
    """抓取次数，用于逐站搜索的轮流起始位。"""
    with _lock:
        row = _conn.execute("SELECT COUNT(*) AS n FROM scrape_runs").fetchone()
        return row[0] if row else 0


def list_posts(platform=None):
    with _lock:
        if platform:
            rows = _conn.execute(
                "SELECT * FROM posts WHERE platform=? ORDER BY id DESC", (platform,)
            ).fetchall()
        else:
            rows = _conn.execute("SELECT * FROM posts ORDER BY id DESC").fetchall()
        return [dict(r) for r in rows]


def get_post(post_id):
    with _lock:
        row = _conn.execute("SELECT * FROM posts WHERE id=?", (post_id,)).fetchone()
        return dict(row) if row else None


def _like(q):
    return "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def search_posts(q, limit=20):
    """按关键词搜帖子：标题 > 摘要 > 正文，其余按发布时间倒序。"""
    like = _like(q)
    with _lock:
        rows = _conn.execute(
            """SELECT id, platform, title, summary, author, url, published_at, race
               FROM posts
               WHERE title LIKE ? ESCAPE '\\' OR summary LIKE ? ESCAPE '\\'
                  OR author LIKE ? ESCAPE '\\' OR raw_text LIKE ? ESCAPE '\\'
               ORDER BY CASE WHEN title LIKE ? ESCAPE '\\' THEN 0
                             WHEN summary LIKE ? ESCAPE '\\' THEN 1 ELSE 2 END,
                        published_at DESC
               LIMIT ?""",
            (like, like, like, like, like, like, limit),
        ).fetchall()
        return [dict(r) for r in rows]


def search_up_posts(q, limit=20):
    """按关键词搜 UP 内容：标题 > 摘要 > 正文（AI 字幕）> 作者。"""
    like = _like(q)
    with _lock:
        rows = _conn.execute(
            """SELECT id, mid, source_type, title, summary, author, url, published_at
               FROM up_posts
               WHERE title LIKE ? ESCAPE '\\' OR summary LIKE ? ESCAPE '\\'
                  OR author LIKE ? ESCAPE '\\' OR subtitle_text LIKE ? ESCAPE '\\'
               ORDER BY CASE WHEN title LIKE ? ESCAPE '\\' THEN 0
                             WHEN summary LIKE ? ESCAPE '\\' THEN 1 ELSE 2 END,
                        published_at DESC
               LIMIT ?""",
            (like, like, like, like, like, like, limit),
        ).fetchall()
        return [dict(r) for r in rows]


def log_run(total, added, error=None):
    with _lock:
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        _conn.execute(
            "INSERT INTO scrape_runs (started_at, finished_at, total, added, error) VALUES (?,?,?,?,?)",
            (now, now, total, added, error),
        )
        _conn.commit()


# ---------------- UP 主订阅 ----------------
def add_subscription(mid, name, avatar):
    """新增或恢复订阅（重复添加会更新资料并重新启用）。"""
    with _lock:
        _conn.execute(
            """INSERT INTO up_subscriptions (mid, name, avatar, enabled, created_at)
               VALUES (?,?,?,1,?)
               ON CONFLICT(mid) DO UPDATE SET name=excluded.name, avatar=excluded.avatar, enabled=1""",
            (mid, name, avatar, time.strftime("%Y-%m-%d %H:%M:%S")),
        )
        _conn.commit()


def list_subscriptions():
    with _lock:
        rows = _conn.execute(
            "SELECT * FROM up_subscriptions ORDER BY created_at, mid"
        ).fetchall()
        return [dict(r) for r in rows]


def set_subscription_enabled(mid, enabled):
    with _lock:
        _conn.execute(
            "UPDATE up_subscriptions SET enabled=? WHERE mid=?", (1 if enabled else 0, mid)
        )
        _conn.commit()


def delete_subscription(mid):
    """删除订阅（已生成的汇总保留）。"""
    with _lock:
        _conn.execute("DELETE FROM up_subscriptions WHERE mid=?", (mid,))
        _conn.commit()


def up_post_exists(source_type, source_id):
    with _lock:
        row = _conn.execute(
            "SELECT 1 FROM up_posts WHERE source_type=? AND source_id=?",
            (source_type, source_id),
        ).fetchone()
        return row is not None


def add_up_post(mid, source_type, source_id, title, author, url, cover,
                published_at, summary, summary_type, subtitle_text=""):
    with _lock:
        cur = _conn.execute(
            """INSERT OR IGNORE INTO up_posts
               (mid, source_type, source_id, title, author, url, cover,
                published_at, summary, summary_type, subtitle_text, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (mid, source_type, source_id, title, author, url, cover,
             published_at, summary, summary_type, subtitle_text,
             time.strftime("%Y-%m-%d %H:%M:%S")),
        )
        _conn.commit()
        return cur.rowcount > 0


def update_up_post_summary(source_type, source_id, summary, summary_type,
                           subtitle_text=None):
    with _lock:
        if subtitle_text is None:
            _conn.execute(
                "UPDATE up_posts SET summary=?, summary_type=? WHERE source_type=? AND source_id=?",
                (summary, summary_type, source_type, source_id),
            )
        else:
            _conn.execute(
                "UPDATE up_posts SET summary=?, summary_type=?, subtitle_text=? "
                "WHERE source_type=? AND source_id=?",
                (summary, summary_type, subtitle_text, source_type, source_id),
            )
        _conn.commit()


def set_up_post_comments(source_id, comment_summary, comment_samples=None):
    """写入评论区观点汇总（JSON 字符串）与时间线样本，并记录时间戳。"""
    with _lock:
        _conn.execute(
            "UPDATE up_posts SET comment_summary=?, comment_samples=?, comment_at=? "
            "WHERE source_type='video' AND source_id=?",
            (comment_summary, comment_samples, time.strftime("%Y-%m-%d %H:%M:%S"), source_id),
        )
        _conn.commit()


def set_post_comments(source_id, comment_summary, comment_samples=None):
    """帖子页（posts 表）B站帖子的评论区观点汇总与时间线样本。"""
    with _lock:
        _conn.execute(
            "UPDATE posts SET comment_summary=?, comment_samples=?, comment_at=? "
            "WHERE platform='bilibili' AND source_id=?",
            (comment_summary, comment_samples, time.strftime("%Y-%m-%d %H:%M:%S"), source_id),
        )
        _conn.commit()


def list_up_posts(limit=200):
    with _lock:
        rows = _conn.execute(
            "SELECT * FROM up_posts ORDER BY published_at DESC, id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def list_up_posts_for_mids(mids, limit=200):
    if not mids:
        return []
    marks = ",".join("?" * len(mids))
    with _lock:
        rows = _conn.execute(
            "SELECT * FROM up_posts WHERE mid IN (%s) ORDER BY published_at DESC, id DESC LIMIT ?"
            % marks,
            tuple(mids) + (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


# ---------------- 用户账号 ----------------
def create_user(nickname, pass_hash):
    """注册成功返回用户 id，昵称已存在返回 None。"""
    with _lock:
        try:
            cur = _conn.execute(
                "INSERT INTO users (nickname, pass_hash, created_at) VALUES (?,?,?)",
                (nickname, pass_hash, time.strftime("%Y-%m-%d %H:%M:%S")),
            )
            _conn.commit()
            return cur.lastrowid
        except sqlite3.IntegrityError:
            return None


def get_user_by_nickname(nickname):
    with _lock:
        row = _conn.execute("SELECT * FROM users WHERE nickname=?", (nickname,)).fetchone()
        return dict(row) if row else None


def get_user_by_id(user_id):
    with _lock:
        row = _conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        return dict(row) if row else None


def create_session(token_hash, user_id, expires_at):
    with _lock:
        _conn.execute(
            "INSERT INTO sessions (token_hash, user_id, expires_at, created_at) VALUES (?,?,?,?)",
            (token_hash, user_id, expires_at, time.strftime("%Y-%m-%d %H:%M:%S")),
        )
        _conn.commit()


def session_user(token_hash):
    """有效会话返回 user_id，过期/不存在返回 None。"""
    with _lock:
        row = _conn.execute(
            "SELECT user_id FROM sessions WHERE token_hash=? AND expires_at>?",
            (token_hash, time.strftime("%Y-%m-%d %H:%M:%S")),
        ).fetchone()
        return row[0] if row else None


def delete_session(token_hash):
    with _lock:
        _conn.execute("DELETE FROM sessions WHERE token_hash=?", (token_hash,))
        _conn.commit()


def update_user_password(user_id, pass_hash):
    with _lock:
        _conn.execute("UPDATE users SET pass_hash=? WHERE id=?", (pass_hash, user_id))
        _conn.commit()


def delete_user(user_id):
    """注销：删除账号、其全部会话与个人订阅（汇总内容保留）。"""
    with _lock:
        _conn.execute("DELETE FROM user_subs WHERE user_id=?", (user_id,))
        _conn.execute("DELETE FROM user_favs WHERE user_id=?", (user_id,))
        _conn.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
        _conn.execute("DELETE FROM users WHERE id=?", (user_id,))
        _conn.commit()


# ---------------- 个人订阅 ----------------
def add_user_sub(user_id, mid, name, avatar):
    with _lock:
        _conn.execute(
            """INSERT INTO user_subs (user_id, mid, name, avatar, enabled, created_at)
               VALUES (?,?,?,?,1,?)
               ON CONFLICT(user_id, mid) DO UPDATE SET name=excluded.name,
               avatar=excluded.avatar, enabled=1""",
            (user_id, mid, name, avatar, time.strftime("%Y-%m-%d %H:%M:%S")),
        )
        _conn.commit()


def list_user_subs(user_id):
    with _lock:
        rows = _conn.execute(
            "SELECT * FROM user_subs WHERE user_id=? ORDER BY created_at, mid",
            (user_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def set_user_sub_enabled(user_id, mid, enabled):
    with _lock:
        _conn.execute(
            "UPDATE user_subs SET enabled=? WHERE user_id=? AND mid=?",
            (1 if enabled else 0, user_id, mid),
        )
        _conn.commit()


def delete_user_sub(user_id, mid):
    with _lock:
        _conn.execute("DELETE FROM user_subs WHERE user_id=? AND mid=?", (user_id, mid))
        _conn.commit()


def user_sub_count(user_id):
    with _lock:
        row = _conn.execute(
            "SELECT COUNT(*) FROM user_subs WHERE user_id=?", (user_id,)
        ).fetchone()
        return row[0] if row else 0


def crawl_targets():
    """抓取目标：公共订阅 + 全部用户订阅的去重并集（仅启用中的）。"""
    with _lock:
        rows = _conn.execute(
            """SELECT mid, MAX(name), MAX(avatar) FROM (
                   SELECT mid, name, avatar FROM up_subscriptions WHERE enabled=1
                   UNION ALL
                   SELECT mid, name, avatar FROM user_subs WHERE enabled=1
               ) GROUP BY mid"""
        ).fetchall()
        return [{"mid": r[0], "name": r[1], "avatar": r[2]} for r in rows]


# ---------------- 我的收藏 ----------------
def add_fav(user_id, item_type, item_id):
    with _lock:
        try:
            _conn.execute(
                """INSERT INTO user_favs (user_id, item_type, item_id, created_at)
                   VALUES (?,?,?,?)""",
                (user_id, item_type, item_id, time.strftime("%Y-%m-%d %H:%M:%S")),
            )
            _conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False


def delete_fav(user_id, item_type, item_id):
    with _lock:
        _conn.execute(
            "DELETE FROM user_favs WHERE user_id=? AND item_type=? AND item_id=?",
            (user_id, item_type, item_id),
        )
        _conn.commit()


def fav_ids(user_id):
    with _lock:
        rows = _conn.execute(
            "SELECT item_type, item_id FROM user_favs WHERE user_id=?",
            (user_id,),
        ).fetchall()
    out = {"post": [], "up": []}
    for r in rows:
        out.setdefault(r["item_type"], []).append(r["item_id"])
    return out


def list_favs(user_id, limit=100):
    """收藏列表：帖子 + UP 内容合并，按收藏时间倒序。"""
    with _lock:
        posts = _conn.execute(
            """SELECT f.created_at AS fav_at, f.item_id AS id, p.platform, p.title,
                      p.summary, p.author, p.url, p.published_at, p.race
               FROM user_favs f JOIN posts p ON p.id = f.item_id
               WHERE f.user_id=? AND f.item_type='post'""",
            (user_id,),
        ).fetchall()
        ups = _conn.execute(
            """SELECT f.created_at AS fav_at, f.item_id AS id, u.source_type, u.title,
                      u.summary, u.author, u.url, u.published_at, u.cover
               FROM user_favs f JOIN up_posts u ON u.id = f.item_id
               WHERE f.user_id=? AND f.item_type='up'""",
            (user_id,),
        ).fetchall()
    items = []
    for r in posts:
        d = dict(r)
        d["item_type"] = "post"
        items.append(d)
    for r in ups:
        d = dict(r)
        d["item_type"] = "up"
        items.append(d)
    items.sort(key=lambda x: x.get("fav_at") or "", reverse=True)
    return items[:limit]
