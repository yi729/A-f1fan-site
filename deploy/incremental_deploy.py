"""增量部署：只上传头像/队徽/排位赛冲刺赛相关改动，不触碰数据目录。

用法: py incremental_deploy.py <host> <root密码>
"""
import os
import sys
import time

import paramiko

ROOT = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(ROOT)

FILES = [
    ("backend/images.py", "/opt/f1-site/backend/images.py"),
    ("backend/f1.py", "/opt/f1-site/backend/f1.py"),
    ("backend/headshots_static.json", "/opt/f1-site/backend/headshots_static.json"),
    ("backend/bilibili.py", "/opt/f1-site/backend/bilibili.py"),
    ("backend/summarize.py", "/opt/f1-site/backend/summarize.py"),
    ("backend/db.py", "/opt/f1-site/backend/db.py"),
    ("backend/upsub.py", "/opt/f1-site/backend/upsub.py"),
    ("backend/comment.py", "/opt/f1-site/backend/comment.py"),
    ("backend/main.py", "/opt/f1-site/backend/main.py"),
    ("backend/pipeline.py", "/opt/f1-site/backend/pipeline.py"),
    ("backend/xhs.py", "/opt/f1-site/backend/xhs.py"),
    ("deploy/refill_ai_subs.py", "/opt/f1-site/deploy/refill_ai_subs.py"),
    ("frontend/index.html", "/opt/f1-site/frontend/index.html"),
    ("frontend/app.js", "/opt/f1-site/frontend/app.js"),
    ("frontend/style.css", "/opt/f1-site/frontend/style.css"),
]
LOGOS_LOCAL = os.path.join(PROJ, "frontend", "assets", "team-logos")
LOGOS_REMOTE = "/opt/f1-site/frontend/assets/team-logos"


def main():
    host, password = sys.argv[1], sys.argv[2]
    print(f"连接 {host} ...")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host, username="root", password=password, timeout=20)
    sftp = ssh.open_sftp()

    def run(cmd, timeout=600):
        print(">>>", cmd)
        _, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
        out = stdout.read().decode("utf-8", "replace")
        err = stderr.read().decode("utf-8", "replace")
        rc = stdout.channel.recv_exit_status()
        if rc != 0:
            print("!! 命令失败 rc=%d\n%s" % (rc, err[-3000:]))
            raise SystemExit(1)
        return out

    # 1. 上传改动文件
    for lp, rp in FILES:
        print("upload:", lp, "->", rp)
        sftp.put(os.path.join(PROJ, lp), rp)

    # 2. 上传车队队徽（11 个 png），并清理旧的单色 avif
    run(f"rm -f {LOGOS_REMOTE}/*.avif")
    run(f"mkdir -p {LOGOS_REMOTE}")
    for name in sorted(os.listdir(LOGOS_LOCAL)):
        lp = os.path.join(LOGOS_LOCAL, name)
        if os.path.isfile(lp):
            print("upload:", lp, "->", LOGOS_REMOTE + "/" + name)
            sftp.put(lp, LOGOS_REMOTE + "/" + name)

    # 3. 重启服务
    run("systemctl restart f1-site")
    time.sleep(5)
    print(run("systemctl is-active f1-site"))

    # 4. 冒烟测试
    print("---- 队徽静态资源 ----")
    print(run("curl -s -o /dev/null -w 'Mercedes.avif=%{http_code}\\n' http://127.0.0.1:8000/assets/team-logos/Mercedes.avif"))
    print("---- 2026 车手积分榜（应含 headshot / teamLogo）----")
    print(run("curl -s 'http://127.0.0.1:8000/api/f1/standings/drivers?season=2026' | head -c 800"))
    print()
    print("---- 2025 R2 结果（正赛+排位+冲刺条数）----")
    print(run(
        "curl -s 'http://127.0.0.1:8000/api/f1/season/2025/race/2/results' | "
        "python3 -c \"import json,sys; d=json.load(sys.stdin); "
        "x=lambda k: ((d.get(k) or {}).get('results') or []) if isinstance(d.get(k),dict) else (d.get(k) or []); "
        "print('race=%d qualifying=%d sprint=%d' % (len(x('results')), len(x('qualifying')), len(x('sprint'))))\""
    ))
    print("---- UP 订阅接口与调度状态 ----")
    print(run("curl -s http://127.0.0.1:8000/api/ups"))
    print(run("curl -s http://127.0.0.1:8000/api/scheduler/status"))
    print(run("curl -s 'http://127.0.0.1:8000/api/ups/posts' | head -c 300"))
    print("---- ECS 访问 OpenF1 连通性 ----")
    print(run("curl -s -o /dev/null -w 'openf1=%{http_code}\\n' --max-time 15 'https://api.openf1.org/v1/sessions?year=2026&session_type=Race'"))
    print("---- 首页 ----")
    print(run("curl -s -o /dev/null -w 'page=%{http_code}\\n' http://127.0.0.1:8000/"))

    sftp.close()
    ssh.close()
    print("==== 增量部署完成 ====")


if __name__ == "__main__":
    main()
