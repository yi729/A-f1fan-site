"""部署帖子时效分类：上传代码 → 重启（自动加 race 列）→ 回填 → 验证。

用法: py deploy_race.py <host> <root密码>
"""
import os
import sys

import paramiko

ROOT = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(ROOT)

BACKFILL = r"""
import sys, sqlite3
from collections import Counter
sys.path.insert(0, "/opt/f1-site/backend")
import race
conn = sqlite3.connect("/opt/f1-site/data/f1.db")
conn.row_factory = sqlite3.Row
rows = conn.execute("SELECT id, title, raw_text FROM posts WHERE race IS NULL OR race=''").fetchall()
print("待回填时效:", len(rows))
for r in rows:
    body = (r["raw_text"] or "").split("【热门评论】")[0]
    v = race.detect_race(r["title"], body)
    conn.execute("UPDATE posts SET race=? WHERE id=?", (v, r["id"]))
conn.commit()
c = Counter(x["race"] for x in conn.execute("SELECT race FROM posts").fetchall())
print("回填完成，分布:")
for k, v in sorted(c.items(), key=lambda kv: -kv[1]):
    print(f"  {k}: {v}")
"""


def main():
    host = sys.argv[1]
    password = sys.argv[2]

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print(f"连接 {host} ...")
    ssh.connect(host, username="root", password=password, timeout=20)
    sftp = ssh.open_sftp()

    def run(cmd, timeout=300):
        print(">>>", cmd[:120])
        _, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
        out = stdout.read().decode("utf-8", "replace")
        err = stderr.read().decode("utf-8", "replace")
        rc = stdout.channel.recv_exit_status()
        if rc != 0:
            print("!! rc=%d\n%s" % (rc, err[-2000:]))
            raise SystemExit(1)
        return out

    # 1. 上传改动文件
    files = [
        ("backend/race.py", "/opt/f1-site/backend/race.py"),
        ("backend/db.py", "/opt/f1-site/backend/db.py"),
        ("backend/pipeline.py", "/opt/f1-site/backend/pipeline.py"),
        ("frontend/app.js", "/opt/f1-site/frontend/app.js"),
        ("frontend/index.html", "/opt/f1-site/frontend/index.html"),
        ("frontend/style.css", "/opt/f1-site/frontend/style.css"),
    ]
    for local, remote in files:
        print("上传", local)
        sftp.put(os.path.join(PROJ, local), remote)

    # 2. 重启服务（db.init 自动 ALTER TABLE 加 race 列）
    run("systemctl restart f1-site")

    # 3. 回填已有帖子
    remote_script = "/opt/f1-site/deploy/backfill_race.py"
    with sftp.open(remote_script, "w") as fh:
        fh.write(BACKFILL)
    print(run(f"cd /opt/f1-site && python3 {remote_script}", timeout=300))

    # 4. 验证接口
    print(run("curl -s http://127.0.0.1:8000/api/posts | head -c 300"))

    sftp.close()
    ssh.close()
    print("==== 时效分类部署完成 ====")


if __name__ == "__main__":
    main()
