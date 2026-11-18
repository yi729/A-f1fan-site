"""用大模型生成帖子摘要（默认 DeepSeek，OpenAI 兼容接口）。

API Key 二选一：
1. 环境变量 DEEPSEEK_API_KEY
2. 文件 data/deepseek_key.txt（内容为 key 本身）
未配置 key 时 summarize() 返回 None，由前端回退显示原文。
"""
import json
import os
from pathlib import Path

import requests

API_KEY = ""
API_URL = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-chat"


def load_config():
    global API_KEY
    API_KEY = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not API_KEY:
        p = Path(__file__).resolve().parent.parent / "data" / "deepseek_key.txt"
        if p.exists():
            API_KEY = p.read_text(encoding="utf-8").strip()


def _call_deepseek(prompt, max_tokens=500):
    resp = requests.post(
        API_URL,
        json={
            "model": MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
            "max_tokens": max_tokens,
            "stream": False,
        },
        headers={"Authorization": "Bearer " + API_KEY, "Content-Type": "application/json"},
        timeout=90,
    )
    data = resp.json()
    return data["choices"][0]["message"]["content"].strip()


def summarize(text, category, max_chars=2500):
    if not API_KEY:
        return None
    text = (text or "").strip()
    if not text:
        return None
    text = text[:max_chars]
    prompt = (
        "你是 F1 赛车分析编辑。阅读下面这则 B站帖子（标题+简介+热门评论），"
        "用 3~5 句话写一段中文摘要，突出比赛策略、赛前预判或赛后总结的要点。"
        "不要编造原文没有的内容，直接输出摘要正文。\n\n"
        f"帖子分类：{category}\n\n帖子内容：\n{text}"
    )
    try:
        return _call_deepseek(prompt)
    except Exception:
        return None


def summarize_up(text, kind, max_chars=6000):
    """UP 主视频/专栏的通用内容摘要。kind 为「视频」或「专栏」。"""
    if not API_KEY:
        return None
    text = (text or "").strip()
    if not text:
        return None
    text = text[:max_chars]
    prompt = (
        "你是内容编辑。阅读下面这则 B站%s（标题+简介或正文），"
        "用 3~5 句话写一段中文摘要，概括核心内容、主要观点或关键信息。"
        "不要编造原文没有的内容，直接输出摘要正文。\n\n"
        "内容：\n%s" % (kind, text)
    )
    try:
        return _call_deepseek(prompt)
    except Exception:
        return None


def summarize_opinions(title, comments_text, max_chars=8000):
    """评论区观点聚类：输出观点簇 JSON 数组，失败返回 None。"""
    if not API_KEY:
        return None
    text = (comments_text or "").strip()
    if not text:
        return None
    text = text[:max_chars]
    prompt = (
        "你是社区舆情分析师。下面是 B站视频《%s》的评论区采样"
        "（分层采集：热评+最新+长评+争论楼中楼，已打散、不按点赞排序）。\n"
        "把评论观点聚类成 3~6 个观点簇，只输出 JSON 数组，不要任何其他文字。格式：\n"
        '[{"label":"观点标签（简短）","stance":"支持/质疑/调侃/中立/争议","size":"规模描述（多数/不少/少数）","quotes":["原文引述1","原文引述2"]}]\n'
        "要求：\n"
        "1. 观点簇覆盖不同阵营：技术探讨、站队争论、玩梗吐槽都要单独成簇，"
        "不能被高赞评论淹没；\n"
        "2. quotes 逐字引用评论原文（可截短，每条不超过 40 字），每簇 1~2 条；\n"
        "3. size 依据该观点在采样中的出现频次与点赞量综合估计。\n\n"
        "评论采样（每行一条，格式：赞x 回y | 评论内容）：\n%s" % (title, text)
    )
    try:
        raw = _call_deepseek(prompt, max_tokens=1200)
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
            if raw.rstrip().endswith("```"):
                raw = raw.rstrip()[:-3]
        return json.loads(raw)
    except Exception:
        return None
