@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "ROOT=%~dp0"
set "EXT_DIR=%ROOT%frontend\dist-extension"
set "PY=%ROOT%.venv\Scripts\python.exe"
set "YOUTUBE=https://www.youtube.com/watch?v=jNQXAC9IVRw"

echo.
echo Veritas — YouTube tab-capture test
echo.

if not exist "%PY%" (
  echo The project virtual environment was not found:
  echo   %PY%
  echo Create it before running this test. The extension needs that backend.
  goto :fail
)

where npm >nul 2>&1
if errorlevel 1 (
  echo Node.js npm was not found on PATH. Install Node.js, then run this file again.
  goto :fail
)

if not exist "%ROOT%frontend\node_modules\" (
  echo Installing frontend packages...
  pushd "%ROOT%frontend"
  call npm install
  if errorlevel 1 (
    popd
    goto :fail
  )
  popd
)

echo Building the extension...
pushd "%ROOT%frontend"
call npm run build:extension
if errorlevel 1 (
  popd
  goto :fail
)
popd

if not exist "%EXT_DIR%\manifest.json" (
  echo The extension build did not produce:
  echo   %EXT_DIR%\manifest.json
  goto :fail
)

call :check_health
if not errorlevel 1 (
  echo The Veritas API is already answering on http://localhost:8000
  goto :open_browser
)

echo Starting the Veritas API in a new window. Leave that window open.
echo The first start loads DeepGuard and can take a minute.
start "Veritas API" /D "%ROOT%" cmd /k ""%PY%" -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000"

echo Waiting for http://localhost:8000/health ...
set "TRIES=0"

:wait_health
set /a TRIES+=1
if %TRIES% GTR 60 goto :health_timeout
call :check_health
if not errorlevel 1 goto :api_ready
ping -n 3 127.0.0.1 >nul
goto :wait_health

:health_timeout
echo.
echo The API window is open, but /health did not answer within two minutes.
echo Read the "Veritas API" window before clicking Analyse this video.
goto :open_browser

:api_ready
echo The Veritas API is ready.

:open_browser
powershell -NoProfile -Command "Set-Clipboard -Value '%EXT_DIR%'"

set "CHROME=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if not exist "%CHROME%" set "CHROME=%LocalAppData%\Google\Chrome\Application\chrome.exe"
if not exist "%CHROME%" set "CHROME=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"

if not exist "%CHROME%" (
  echo Chrome was not found. Open YouTube yourself, then load the extension from:
  echo   %EXT_DIR%
  goto :steps
)

start "" "%CHROME%" "%YOUTUBE%" "chrome://extensions"

:steps
echo.
echo In Chrome:
echo   1. On chrome://extensions, turn on Developer mode.
echo   2. Click Load unpacked. The folder path is already copied. Paste it:
echo      %EXT_DIR%
echo   3. If Veritas is already loaded, click its reload icon instead.
echo   4. On the YouTube tab, press play so the picture is moving.
echo   5. Open the Veritas popup and click "Analyse this video".
echo.
echo The popup records about 8 seconds of the visible tab and sends it to
echo http://localhost:8000/api/analyze/video. Leave the Veritas API window open.
echo This checks the rendered YouTube picture, not YouTube's original file.
echo.
exit /b 0

:check_health
powershell -NoProfile -Command "try { $r = Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/health -TimeoutSec 3; if ($r.StatusCode -eq 200) { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>&1
exit /b

:fail
echo.
echo Setup stopped. Fix the message above and run this file again.
exit /b 1
