@echo off
REM Builds the PackWise packer service on Windows with MinGW-w64 g++ (MSYS2 UCRT64).
REM Output: build\packer_service.exe and build\test_core.exe
setlocal
cd /d "%~dp0"
if not exist build mkdir build

where g++ >nul 2>nul
if errorlevel 1 (
  echo [ERROR] g++ was not found on PATH.
  echo Install MSYS2 and the UCRT64 toolchain, then add C:\msys64\ucrt64\bin to PATH.
  echo See README.md, section "Install a C++ compiler".
  exit /b 1
)

echo Building packer_service.exe ...
g++ -std=c++17 -O2 -D_WIN32_WINNT=0x0A00 -Iinclude -Isrc src\main.cpp src\packer_core.cpp src\optimizer_core.cpp -o build\packer_service.exe -lws2_32 -lcrypt32 -static
if errorlevel 1 exit /b 1

echo Building test_core.exe ...
g++ -std=c++17 -O2 -Isrc tests\test_core.cpp src\packer_core.cpp src\optimizer_core.cpp -o build\test_core.exe -static
if errorlevel 1 exit /b 1

echo Running core tests ...
build\test_core.exe
if errorlevel 1 exit /b 1

echo.
echo Done. Start the service with:  build\packer_service.exe 8090
endlocal
