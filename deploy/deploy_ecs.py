"""一次性部署脚本：把本地项目部署到阿里云 ECS（Ubuntu 24.04）。

用法: py deploy_ecs.py <host> <root密码> [抓取口令]
"""
import os
import random
import string
import sys
import time

import paramiko

ROOT = os.path.dirname(os.path.abspath(__file__))  # deploy/ 目录
PROJ = os.path.dirname(ROOT)                        # 项目根目录


def main():
    host = sys.argv[1]
    password = sys.argv[2]
    token = sys.argv[3] if len(sys.argv) > 3 else "".join(
        random.choices(string.ascii_letters + string.digits, k=12))

    print(f"连接 {host} ...")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host, username="root", password=password, timeout=20)
    sftp = ssh.open_sftp()

    def run(cmd, timeout=900):
        print(">>>", cmd)
        _, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
        out = stdout.read().decode("utf-8", "replace")
        err = stderr.read().decode("utf-8", "replace")
        rc = stdout.channel.recv_exit_status()
        if rc != 0:
            print("!! 命令失败 rc=%d\n%s" % (rc, err[-3000:]))
            raise SystemExit(1)
        return out

    def put(local, remote):
        print("upload:", local, "->", remote)
        sftp.put(local, remote)

    def put_dir(local, remote):
        run(f"mkdir -p {remote}")
        for name in sorted(os.listdir(local)):
            lp = os.path.join(local, name)
            rp = remote.rstrip("/") + "/" + name
            if os.path.isdir(lp):
                put_dir(lp, rp)
            else:
                put(lp, rp)

    # 1. 系统依赖
    run("apt-get update -qq")
    run("DEBIAN_FRONTEND=noninteractive apt-get install -y -qq python3-pip git nginx")

    # 2. 上传代码
    run("rm -rf /opt/f1-site && mkdir -p /opt/f1-site/data")
    put_dir(os.path.join(PROJ, "backend"), "/opt/f1-site/backend")
    put_dir(os.path.join(PROJ, "frontend"), "/opt/f1-site/frontend")
    put(os.path.join(PROJ, "run.py"), "/opt/f1-site/run.py")
    put(os.path.join(PROJ, "requirements.txt"), "/opt/f1-site/requirements.txt")
    put_dir(ROOT, "/opt/f1-site/deploy")

    # 3. 凭据（本地有就传）
    for f in ("bili_cookie.txt", "deepseek_key.txt"):
        lp = os.path.join(PROJ, "data", f)
        if os.path.exists(lp):
            put(lp, f"/opt/f1-site/data/{f}")
        else:
            print("本地无", f, "，跳过")

    # 4. Python 依赖
    run("pip3 install --break-system-packages -q -r /opt/f1-site/requirements.txt")

    # 5. systemd 常驻
    unit = f"""[Unit]
Description=F1 数据中心（FastAPI 后端 + 静态前端）
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/f1-site
ExecStart=/usr/bin/python3 run.py
Restart=always
RestartSec=5
Environment=F1_HOST=0.0.0.0
Environment=F1_PORT=8000
Environment=SCRAPE_INTERVAL_HOURS=6
Environment=SCRAPE_TOKEN={token}
Environment=TZ=Asia/Shanghai

[Install]
WantedBy=multi-user.target
"""
    with sftp.open("/etc/systemd/system/f1-site.service", "w") as fh:
        fh.write(unit)
    run("systemctl daemon-reload && systemctl enable f1-site && systemctl restart f1-site")
    time.sleep(4)
    print(run("systemctl is-active f1-site"))

    # 6. 服务器本地冒烟测试
    print(run("curl -s http://127.0.0.1:8000/api/scheduler/status"))
    print(run("curl -s -o /dev/null -w 'page=%{http_code}\\n' http://127.0.0.1:8000/"))

    sftp.close()
    ssh.close()
    print("==== 部署完成 ====")
    print("抓取口令(SCRAPE_TOKEN):", token)
    print("访问地址: http://" + host + ":8000 （需在云控制台安全组放行 8000 端口）")


if __name__ == "__main__":
    main()
