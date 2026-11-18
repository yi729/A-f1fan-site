# -*- coding: utf-8 -*-
"""一次性全量抓取：新搜索词「F1 XX大奖赛」逐站扫描，日志带时间戳。"""
import sys
import time

sys.path.insert(0, "/opt/f1-site/backend")

import db
import pipeline

db.init("/opt/f1-site/data/f1.db")
t0 = time.time()
res = pipeline.run(limit_per_category=12, race_budget=24)
print(f"[{time.strftime('%H:%M:%S')}] 耗时(秒): {int(time.time()-t0)}")
print(f"[{time.strftime('%H:%M:%S')}] 结果: {res}")
