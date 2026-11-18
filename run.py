"""启动脚本：python run.py 即可启动后端并托管前端。

本机开发默认监听 127.0.0.1:8000；
云服务器上用环境变量改为对外监听：
    F1_HOST=0.0.0.0 F1_PORT=8000 python run.py
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "backend"))

import uvicorn  # noqa: E402

host = os.environ.get("F1_HOST", "127.0.0.1")
port = int(os.environ.get("F1_PORT", "8000"))
uvicorn.run("main:app", host=host, port=port)
