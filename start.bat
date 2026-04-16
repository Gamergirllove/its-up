@echo off
echo ================================
echo   POLY BOT - Local Server
echo ================================

:: Install deps if needed
pip install -r requirements.txt --quiet

:: Get local IP
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4"') do (
    set LOCAL_IP=%%a
    goto :found
)
:found
set LOCAL_IP=%LOCAL_IP: =%

echo.
echo  Server starting...
echo  Local:    http://localhost:5000
echo  Mobile:   http://%LOCAL_IP%:5000
echo.
echo  (must be on same WiFi for mobile)
echo  For external access, run: ngrok http 5000
echo.

python app.py
pause
