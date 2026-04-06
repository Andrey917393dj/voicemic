@echo off
title VoiceMic USB Setup
echo ============================================
echo   VoiceMic - USB Connection Setup (ADB)
echo ============================================
echo.

where adb >nul 2>nul
if %errorlevel% neq 0 (
    echo ERROR: ADB not found in PATH.
    echo Install Android Platform Tools:
    echo https://developer.android.com/tools/releases/platform-tools
    echo.
    echo After installing, add the folder to your system PATH.
    pause
    exit /b 1
)

echo Checking connected devices...
adb devices
echo.

set /p PORT="Enter port (default 8125): "
if "%PORT%"=="" set PORT=8125

echo Setting up port forwarding: tcp:%PORT% -^> tcp:%PORT%
adb forward tcp:%PORT% tcp:%PORT%

if %errorlevel% equ 0 (
    echo.
    echo SUCCESS! USB forwarding active.
    echo.
    echo On your phone app, connect to:
    echo   IP:   127.0.0.1
    echo   Port: %PORT%
    echo.
) else (
    echo.
    echo FAILED. Make sure:
    echo   1. USB Debugging is enabled on your phone
    echo   2. Phone is connected via USB
    echo   3. You authorized the PC on the phone
    echo.
)

pause
