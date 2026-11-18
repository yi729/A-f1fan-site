"""部署后手动验证：UP 订阅接口、调度状态、老断言检查、添加 4 个订阅。"""
import sys

import paramiko

host, password = sys.argv[1], sys.argv[2]
token = sys.argv[3] if len(sys.argv) > 3 else ""

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(host, username="root", password=password, timeout=20)


def run(cmd, timeout=120):
    print(">>>", cmd)
    _, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode("utf-8", "replace")
    err = stderr.read().decode("utf-8", "replace")
    rc = stdout.channel.recv_exit_status()
    print(out[:1500])
    if err.strip():
        print("[stderr]", err[:500])
    return rc, out


# 0. 2025 R2 老断言排查：看接口实际返回什么
run("curl -s 'http://127.0.0.1:8000/api/f1/season/2025/race/2/results' | head -c 300")

# 1. 调度状态（确认 auto-upcheck 已注册）
run("curl -s http://127.0.0.1:8000/api/scheduler/status")

# 2. 当前订阅列表（应为空）
run("curl -s http://127.0.0.1:8000/api/ups")

# 3. 添加 4 个订阅（token 鉴权）
for name in ["临渊_Aslinger", "F1赛事资讯", "Chester117", "F1世界锦标赛"]:
    run("curl -s -X POST http://127.0.0.1:8000/api/ups "
        "-H 'Content-Type: application/json' -H 'X-Scrape-Token: %s' "
        "-d '{\"text\": \"%s\"}'" % (token, name))
    import time
    time.sleep(2)

# 4. 订阅列表确认
run("curl -s http://127.0.0.1:8000/api/ups")

ssh.close()
print("==== 验证完成 ====")
