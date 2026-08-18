@echo off
setlocal
cd /d "%~dp0"
title BAHR-GCS baslatiliyor...

if not exist ".venv\Scripts\python.exe" (
    echo Sanal ortam bulunamadi, kuruluyor. Bu birkac dakika surebilir...
    echo.
    call setup.bat
    if not exist ".venv\Scripts\python.exe" (
        echo.
        echo [HATA] Kurulum basarisiz oldu.
        pause
        exit /b 1
    )
)

echo Kontrol ediliyor...
".venv\Scripts\python.exe" -c "import gcs.app" 2> "%~dp0run_error.log"
if errorlevel 1 (
    echo.
    echo [HATA] Uygulama baslatilamadi. Hata detayi:
    echo.
    type "%~dp0run_error.log"
    echo.
    echo Bagimliliklari yeniden kurmak icin setup.bat calistirin.
    pause
    exit /b 1
)
del "%~dp0run_error.log" >nul 2>nul

start "" ".venv\Scripts\pythonw.exe" main.py
exit
