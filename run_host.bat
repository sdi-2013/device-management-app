@echo off
echo ==========================================
echo      Device Management System
echo ==========================================
echo.

echo 1. Cleaning up old processes...
taskkill /F /IM streamlit.exe /T 2>nul
for /f "tokens=5" %%a in ('netstat -aon ^| find ":8501" ^| find "LISTENING"') do taskkill /f /pid %%a 2>nul

echo.
echo 2. Detecting Network IP...
python show_ip.py

echo.
echo 3. Starting Server...
echo [IMPORTANT] DO NOT CLOSE THIS WINDOW (Keep it open!)
echo.
.\.venv\Scripts\python.exe -m streamlit run app.py --server.address 0.0.0.0 --server.port 8501 --server.headless true
pause
