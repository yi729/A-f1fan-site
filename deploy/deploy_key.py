"""把 DeepSeek key 部署到服务器，并为已有帖子补 AI 摘要。

用法: py deploy_key.py <host> <root密码>
"""
import os
import sys

import paramiko

ROOT = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(ROOT)

BACKFILL = r"""
import os, sys, sqlite3, time
sys.path.insert(0, "/opt/f1-site/backend")
os.chdir("/opt/f1-site")
import summarize
summarize.load_config()
print("key loaded:", bool(summarize.API_KEY))
conn = sqlite3.connect("/opt/f1-site/data/f1.db")
conn.row_factory = sqlite3.Row
rows = conn.execute("SELECT id, title, category, raw_text FROM posts WHERE summary IS NULL OR summary=''").fetchall()
print("待补摘要:", len(rows))
ok = fail = 0
for r in rows:
    try:
        s = summarize.summarize(r["raw_text"] or r["title"], r["category"])
        if s:
            conn.execute("UPDATE posts SET summary=? WHERE id=?", (s, r["id"]))
            conn.commit()
            ok += 1
        else:
            fail += 1
            print("no summary:", r["id"])
    except Exception as e:
        fail += 1
        print("err", r["id"], e)
    time.sleep(0.5)
print(f"完成: 成功 {ok} 篇, 失败 {fail} 篇")
"""


def main():
    host = sys.argv[1]
    password = sys.argv[2]

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print(f"连接 {host} ...")
    ssh.connect(host, username="root", password=password, timeout=20)
    sftp = ssh.open_sftp()

    def run(cmd, timeout=900):
        print(">>>", cmd[:120])
        _, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
        out = stdout.read().decode("utf-8", "replace")
        err = stderr.read().decode("utf-8", "replace")
        rc = stdout.channel.recv_exit_status()
        if rc != 0:
            print("!! rc=%d\n%s" % (rc, err[-2000:]))
            raise SystemExit(1)
        return out

    # 1. 上传 key 文件（/opt/f1-site/data 已存在，数据库在其中）
    local_key = os.path.join(PROJ, "data", "deepseek_key.txt")
    print("上传 key ...")
    sftp.put(local_key, "/opt/f1-site/data/deepseek_key.txt")
    run("chmod 600 /opt/f1-site/data/deepseek_key.txt")

    # 2. 重启服务（让新抓取自动带摘要）
    run("systemctl restart f1-site")

    # 3. 上传并执行补摘要脚本
    remote_script = "/opt/f1-site/deploy/backfill_summaries.py"
    with sftp.open(remote_script, "w") as fh:
        fh.write(BACKFILL)
    print(run(f"cd /opt/f1-site && python3 {remote_script}", timeout=1200))

    sftp.close()
    ssh.close()
    print("==== key 部署完成 ====")


if __name__ == "__main__":
    main()
