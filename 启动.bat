@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
where py >nul 2>nul
if not errorlevel 1 (
  for %%V in (3.13 3.12 3.14 3.11 3.10) do (
    py -%%V -c "import sys" >nul 2>nul
    if not errorlevel 1 (
      py -%%V bootstrap.py %*
      goto finished
    )
  )
)
where python >nul 2>nul
if not errorlevel 1 (
  python bootstrap.py %*
  goto finished
)
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" bootstrap.py %*
  goto finished
)
echo 请先安装64位 Python 3.10–3.14，建议3.12或3.13：https://www.python.org/downloads/
pause
exit /b 1
:finished
set "ONION_EXIT=%errorlevel%"
if not "%ONION_EXIT%"=="0" pause
exit /b %ONION_EXIT%
