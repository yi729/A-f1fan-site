# F1 数据中心

一个 F1 赛事数据聚合站：F1 各赛季积分/每站结果 + B站 F1 相关帖子自动抓取与 AI 摘要 + 评论区观点聚类。纯练手项目（FastAPI + SQLite + 原生前端）。

线上地址：http://116.62.82.5:8000

## 功能

- **赛事数据**：1950 年起各赛季车手/车队积分榜（领奖台、杆位）、每站结果（正赛/排位/冲刺）、车手对比；数据来自 Jolpica（Ergast 维护分支），头像/队徽按赛季路由（官方 CDN 有就显示，没有回退车队色徽章）
- **帖子分析**：每 6 小时自动搜索 B站 F1 帖子（分站识别 + 时效分类），DeepSeek 生成中文摘要；分站/时间/立场筛选
- **评论区观点**：对近 30 天的 B站视频分层采样评论（热评翻页 + 最新评论 + 长评 + 高回复争论层 + 楼中楼），DeepSeek 观点聚类（立场/阵营/原文引语），弹窗内「观点 / 时间线」双页签
- **UP 订阅**：订阅 B站 UP 主（公共订阅 + 注册用户个人订阅），每 2 小时轮询新视频/专栏，优先用 AI 字幕做摘要（三级回退：AI 字幕 → UP 字幕 → 简介），字幕正文站内弹窗查看
- **账号体系**：昵称 + 密码注册登录，个人订阅上限 10 个，游客可看公共订阅内容

## 技术栈

- 后端：FastAPI + Uvicorn + SQLite + APScheduler + requests
- AI：DeepSeek（OpenAI 兼容接口），用于帖子摘要 / UP 内容摘要 / 评论区观点聚类
- 前端：原生 HTML/CSS/JS（手机端优先的响应式布局），由 FastAPI 静态托管

## 目录结构

```
backend/         后端（main.py 接口与调度、pipeline.py 帖子抓取、
                 upsub.py UP 抓取、comment.py 评论采样与观点聚类、
                 bilibili.py B站 API、summarize.py DeepSeek、db.py SQLite）
frontend/        前端（index.html / app.js / style.css / assets 队徽等静态资源）
data/            运行时数据（f1.db、密钥文件），不入库
deploy/          部署脚本与说明（incremental_deploy.py 为日常增量部署入口）
run.py           本地启动入口
```

## 本地运行

```bash
pip install -r requirements.txt
python run.py
```

浏览器打开 http://127.0.0.1:8000。

可选配置（环境变量或文件）：

| 配置 | 说明 |
| --- | --- |
| `DEEPSEEK_API_KEY` | 未配置时摘要回退为原文；也可写入 `data/deepseek_key.txt`（首行为 key） |
| `SCRAPE_TOKEN` | 设置后「手动抓取一次」和管理员接口需口令 |
| `SCRAPE_INTERVAL_HOURS` | 帖子抓取间隔（默认 6） |
| `UP_CHECK_INTERVAL_HOURS` | UP 内容轮询间隔（默认 2） |
| `data/bili_cookie.txt` | B站登录 Cookie（`SESSDATA=xxx`），用于 AI 字幕接口；无 Cookie 也能抓取 |
