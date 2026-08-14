# -*- coding: utf-8 -*-
import io, os, subprocess, sys, time, urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
BASE = r"D:\domestic_ecommerce_agent_taobao"
PY = os.path.join(BASE, ".venv", "Scripts", "python.exe")
out = open(os.path.join(BASE, "logs", "api_out.log"), "ab")
err = open(os.path.join(BASE, "logs", "api_err.log"), "ab")
flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | 0x08000000  # CREATE_NO_WINDOW
proc = subprocess.Popen(
    [PY, "-m", "uvicorn", "api.app:app", "--host", "127.0.0.1", "--port", "8000"],
    cwd=BASE, stdout=out, stderr=err, creationflags=flags,
)
print("started pid:", proc.pid)
with open(os.path.join(BASE, "logs", "api.pid"), "w") as f:
    f.write(str(proc.pid))

ok = False
for _ in range(40):
    try:
        with urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=2) as r:
            print("health:", r.read().decode("utf-8"))
            ok = True
            break
    except Exception:
        time.sleep(0.5)
if not ok:
    print("health timeout; api_err.log tail:")
    with open(os.path.join(BASE, "logs", "api_err.log"), "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    print("".join(lines[-25:]))
    sys.exit(1)