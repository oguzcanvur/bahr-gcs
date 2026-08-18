@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (
    set "PY=py -3"
) else (
    where python >nul 2>nul
    if %errorlevel%==0 (
        set "PY=python"
    ) else (
        echo [HATA] Python bulunamadi.
        echo https://www.python.org/downloads/ adresinden Python kurun ve
        echo kurulum sirasinda "Add python.exe to PATH" secenegini isaretleyin.
        pause
        exit /b 1
    )
)

if exist .venv (
    echo Mevcut .venv siliniyor...
    rmdir /s /q .venv
)

echo Sanal ortam olusturuluyor...
%PY% -m venv .venv
if not exist .venv\Scripts\python.exe (
    echo [HATA] Sanal ortam olusturulamadi.
    pause
    exit /b 1
)

echo Bagimliliklar kuruluyor, bu birkac dakika surebilir...
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 (
    echo [HATA] Bagimlilik kurulumu basarisiz oldu.
    pause
    exit /b 1
)

echo.
echo ============================================
echo Kurulum tamamlandi.
echo.
echo Uygulamayi dogrudan calistirmak icin:
echo   .venv\Scripts\python.exe main.py
echo.
echo Qt Creator icin: Edit - Preferences - Python - Interpreters - Add
echo ve su yolu sec:
echo   %cd%\.venv\Scripts\python.exe
echo ============================================
pause
