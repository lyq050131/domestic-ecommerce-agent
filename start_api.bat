@echo off
chcp 65001 >nul
cd /d %~dp0
echo 启动 API 服务: http://127.0.0.1:8000/docs
"%~dp0.venv\Scripts\python.exe" -m uvicorn api.app:app --reload --port 8000
pause
