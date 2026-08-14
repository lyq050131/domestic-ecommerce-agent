@echo off
cd /d "%~dp0.."
".venv\Scripts\python.exe" scripts\stop_api_service.py
pause