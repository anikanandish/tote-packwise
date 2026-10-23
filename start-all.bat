@echo off
REM Starts all five services in their own windows.
cd /d "%~dp0"
if exist cpp-packer-service\build\packer_service.exe (
  set PACKER=build\packer_service.exe
) else (
  set PACKER=prebuilt\packer_service.exe
)
start "PackWise C++ packer :8090" cmd /k "cd cpp-packer-service && %PACKER% 8090"
start "TOTE + PackWise API :8000" cmd /k "cd backend && .venv\Scripts\activate && uvicorn app.main:app --reload --port 8000"
start "TOTE store :5173" cmd /k "cd tote-frontend && npm run dev"
start "PackWise :5174" cmd /k "cd packwise-frontend && npm run dev"
start "Simulator website :5175" cmd /k "cd simulator-site && py -m http.server 5175"
echo.
echo Opening in a few seconds:
echo   TOTE store      http://localhost:5173
echo   PackWise        http://localhost:5174
echo   Admin console   http://localhost:5174/admin/login
echo   Simulator       http://localhost:5175
echo   API docs        http://localhost:8000/docs
timeout /t 6 >nul
start http://localhost:5173
start http://localhost:5174
start http://localhost:5175
