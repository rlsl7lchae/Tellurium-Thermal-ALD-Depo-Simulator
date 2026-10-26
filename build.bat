@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] .venv not found. Run the setup steps in README.md first.
  exit /b 1
)

echo [1/3] Testing pipeline with sample Excel...
".venv\Scripts\python.exe" _selftest.py
if errorlevel 1 (
  echo [ERROR] Pipeline test failed. Stopping build.
  exit /b 1
)

if exist "build" rmdir /s /q "build"
if exist "dist\Te_ALD_Simulator" rmdir /s /q "dist\Te_ALD_Simulator"

echo [2/3] Running PyInstaller...
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean Te_ALD_Simulator.spec
if errorlevel 1 exit /b 1

echo [3/3] Done
echo.
echo EXE: dist\Te_ALD_Simulator\Te_ALD_Simulator.exe
echo Copy the whole dist\Te_ALD_Simulator folder to move it to another PC.
endlocal
