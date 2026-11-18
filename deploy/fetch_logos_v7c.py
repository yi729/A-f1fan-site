# 一次性脚本：在 ECS 上运行（python3）
# v7c：对 7 个 commons 文件的 wsrv 耐心重试（429 是 wikimedia 限流，多试有机会）
import concurrent.futures
import hashlib
import os
import time
import urllib.parse
import urllib.request

OUT = "/tmp/oldlogos8"
os.makedirs(OUT, exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

FILES = {
    "surtees": "Surteeslogo.png",
    "march": "March_Engineering.png",
    "osella": "Osella_emblem.png",
    "tyrrell": "Tyrrell.svg",
    "dallara": "Dallara_logo.svg",
    "simtek": "Simtek_logo.svg",
    "penske": "Team_Penske_logo.svg",
}
TRIES = 30


def is_img(data):
    if not data:
        return False
    return len(data) > 600 and (
        data[:4] == b"\x89PNG" or data[:3] == b"\xff\xd8\xff"
        or data[:6] in (b"GIF87a", b"GIF89a"))


def md5dirs(fn):
    h = hashlib.md5(fn.encode("utf-8")).hexdigest()
    return h[0], h[:2]


def worker(cid, fn):
    d1, d2 = md5dirs(fn)
    qf = urllib.parse.quote(fn)
    base = f"https://upload.wikimedia.org/wikipedia/commons/{d1}/{d2}/{qf}"
    u = "https://wsrv.nl/?url=" + urllib.parse.quote(base, safe="") + "&output=png&w=600"
    for i in range(TRIES):
        try:
            req = urllib.request.Request(u, headers=UA)
            with urllib.request.urlopen(req, timeout=60) as r:
                data = r.read()
            if is_img(data):
                path = os.path.join(OUT, f"{cid}_wsrv.png")
                with open(path, "wb") as f:
                    f.write(data)
                print(f"OK  {cid} try{i+1} [{len(data)}B]", flush=True)
                return
        except Exception:
            pass
        time.sleep(10 + (i % 5) * 5)
    print(f"FAIL {cid} after {TRIES} tries", flush=True)


with concurrent.futures.ThreadPoolExecutor(max_workers=7) as ex:
    list(ex.map(lambda kv: worker(kv[0], kv[1]), FILES.items()))

print("=== DONE ===", flush=True)
for f in sorted(os.listdir(OUT)):
    print(f, os.path.getsize(os.path.join(OUT, f)), flush=True)
