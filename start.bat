@echo off
chcp 65001 >nul
cd /d %~dp0
echo ============================================
echo   国内电商店铺自动化运营智能体 v3.1
echo   首次运行请先配置 .env（参考 .env.example）
echo ============================================
"%~dp0.venv\Scripts\python.exe" main.py
pause
