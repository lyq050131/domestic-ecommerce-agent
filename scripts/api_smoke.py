# -*- coding: utf-8 -*-
import subprocess, sys, time
import requests

PY = r"D:\domestic_ecommerce_agent_taobao\.venv\Scripts\python.exe"
BASE = r"D:\domestic_ecommerce_agent_taobao"
port = 8011
proc = subprocess.Popen(
    [PY, "-m", "uvicorn", "api.app:app", "--port", str(port)],
    cwd=BASE,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    encoding="utf-8",
)
try:
    health = None
    for _ in range(40):
        try:
            health = requests.get(f"http://127.0.0.1:{port}/health", timeout=2).json()
            break
        except Exception:
            time.sleep(0.5)
    if health is None:
        print("health timeout")
        out = proc.stdout.read() if proc.stdout else ""
        print(out[-3000:])
        sys.exit(1)
    print("health:", health)
    status = requests.get(f"http://127.0.0.1:{port}/api/v1/system/status", timeout=15).json()
    print("status:", status)
finally:
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except Exception:
        proc.kill()
    print("api stopped")