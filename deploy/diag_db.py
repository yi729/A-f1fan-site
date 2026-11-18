# -*- coding: utf-8 -*-
"""上传到服务器执行的诊断：DB 覆盖率 + 日志。"""
import sqlite3

db = sqlite3.connect("/opt/f1-site/data/f1.db")
total = db.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
print("帖子总数:", total)
rows = db.execute(
    "SELECT COALESCE(race,'(空)') r, COUNT(*) c FROM posts GROUP BY r ORDER BY c DESC"
).fetchall()
print("分站分布:")
for r, cn in rows:
    print(f"  {r}: {cn}")
runs = db.execute(
    "SELECT id, started_at, total, added, error FROM scrape_runs ORDER BY id DESC LIMIT 6"
).fetchall()
print("最近抓取记录:")
for r in runs:
    print("  ", r)
