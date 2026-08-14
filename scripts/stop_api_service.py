# -*- coding: utf-8 -*-
import os, subprocess, sys

BASE = r"D:\domestic_ecommerce_agent_taobao"
pid_file = os.path.join(BASE, "logs", "api.pid")
if os.path.exists(pid_file):
    with open(pid_file) as f:
        pid = int(f.read().strip())
    r = subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, text=True)
    print(r.stdout.strip() or r.stderr.strip())
    os.remove(pid_file)
    print("API 已停止")
else:
    print("未找到运行中的 API（无 pid 文件）")