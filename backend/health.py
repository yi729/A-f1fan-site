"""抓取健康状态：三个调度任务各自的连续失败计数（内存态，重启清零）。

调度任务完成后调用 report() 上报成功/失败，调度状态接口读出，
前端在连续失败 >=2 次时提示，避免抓取静默停摆无人知晓。
"""
import time

_SERVICES = {
    "bilibili": "B站抓取",
    "xiaohongshu": "小红书抓取",
    "upcheck": "UP 检查",
}

_state = {
    k: {"fails": 0, "last_ok": "", "last_fail": "", "detail": ""}
    for k in _SERVICES
}


def report(service, ok, detail=""):
    s = _state.get(service)
    if s is None:
        return
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    if ok:
        s["fails"] = 0
        s["last_ok"] = now
        s["detail"] = ""
    else:
        s["fails"] += 1
        s["last_fail"] = now
        s["detail"] = str(detail or "")[:200]


def get():
    out = {}
    for k, s in _state.items():
        out[k] = dict(s)
        out[k]["label"] = _SERVICES[k]
    return out
