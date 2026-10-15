@echo off
echo ========================================================
echo  Starting NetChaos Simulator
echo ========================================================
echo.
echo Starting Backend on http://localhost:8001 ...
start "NetChaos Backend (FastAPI)" cmd /k "cd /d "%~dp0backend" && .venv\Scripts\python.exe -m uvicorn app.main:app --port 8001 --reload"

echo Starting Frontend on http://localhost:5173 ...
start "NetChaos Frontend (Vite)" cmd /k "cd /d "%~dp0frontend" && npm run dev"

echo.
echo Both servers have been launched in separate terminal windows.
echo - Frontend Dashboard: http://localhost:5173
echo - Backend API Docs:   http://localhost:8001/docs
echo ========================================================
pause
