"""本地联调：解析 4 个 UP → 订阅入库 → 小预算跑一轮 → 检查汇总结果。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

import db
import upsub

db.init(str(ROOT / "data" / "f1.db"))

# 1. 解析 4 个 UP
for name in ["临渊_Aslinger", "F1赛事资讯", "Chester117", "F1世界锦标赛"]:
    try:
        up = upsub.resolve_up(name)
        print("resolve %s -> %s" % (name, up))
        if up:
            db.add_subscription(up["mid"], up["name"], up["avatar"])
    except Exception as e:
        print("resolve %s 失败: %s" % (name, e))

print("订阅表:", db.list_subscriptions())

# 2. 小预算跑一轮（每 UP 最多 3 条，验证摘要素材与入库）
upsub.PER_UP_BUDGET = 3
result = upsub.run()
print("轮询结果:", result)

posts = db.list_up_posts()
print("汇总条数:", len(posts))
for p in posts[:10]:
    print("- [%s|%s] %s | %s | 摘要: %s" % (
        p["source_type"], p["summary_type"], p["title"][:30],
        p["published_at"], (p["summary"] or "")[:60],
    ))
