@echo off
REM One-time setup for TOTE + PackWise on Windows. Run from the project folder.
setlocal
cd /d "%~dp0"

echo === 1/4  Environment files ===
if not exist backend\.env copy backend\.env.example backend\.env >nul
if not exist tote-frontend\.env copy tote-frontend\.env.example tote-frontend\.env >nul
if not exist packwise-frontend\.env copy packwise-frontend\.env.example packwise-frontend\.env >nul

echo === 2/4  Python backend ===
cd backend
if not exist .venv python -m venv .venv
call .venv\Scripts\activate
python -m pip install --upgrade pip >nul
pip install -r requirements.txt || goto :fail
call deactivate
cd ..

echo === 3/4  Frontends ===
cd tote-frontend && call npm install || goto :fail
cd ..\packwise-frontend && call npm install || goto :fail
cd ..

echo === 4/4  C++ packing service ===
where g++ >nul 2>nul
if errorlevel 1 (
  echo g++ not found: the prebuilt cpp-packer-service\prebuilt\packer_service.exe will be used.
  echo Install MSYS2 later to build it yourself - see README.
) else (
  call cpp-packer-service\build.bat || goto :fail
)

echo.
echo Setup complete. Start everything with:  start-all.bat
exit /b 0
:fail
echo.
echo [ERROR] Setup stopped. Read the message above and see README "Troubleshooting".
exit /b 1
