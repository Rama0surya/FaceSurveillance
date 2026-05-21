@echo off
title ffmpeg - Webcam to RTSP (Auto Path)
echo Pushing webcam to rtsp://localhost:8554/webcam
echo Press Ctrl+C to stop
echo.

:: Cek apakah ffmpeg terdaftar di PATH System
where ffmpeg >nul 2>nul
if %errorlevel% equ 0 (
    set "FFMPEG_CMD=ffmpeg"
    goto :RUN_STREAM
)

:: Cek di jalur manual AppData Winget Ahmad
if exist "C:\Users\ahmad\AppData\Local\Microsoft\WinGet\Links\ffmpeg.exe" (
    set "FFMPEG_CMD=C:\Users\ahmad\AppData\Local\Microsoft\WinGet\Links\ffmpeg.exe"
    goto :RUN_STREAM
)

:: Cek di folder local AppData fallback dari script PowerShell sebelumnya
if exist "%LOCALAPPDATA%\ffmpeg\bin\ffmpeg.exe" (
    set "FFMPEG_CMD=%LOCALAPPDATA%\ffmpeg\bin\ffmpeg.exe"
    goto :RUN_STREAM
)

echo [ERROR] Aplikasi ffmpeg.exe tidak ditemukan di sistem kamu!
echo Silakan jalankan kembali .\setup_webcam_stream.ps1 dari PowerShell.
pause
exit

:RUN_STREAM
echo [OK] Menggunakan FFmpeg dari: %FFMPEG_CMD%
echo.

:: Jalankan stream (Ganti "NAMA_WEBCAM_ASLI_KAMU" dengan nama webcam aslimu!)
"%FFMPEG_CMD%" -f dshow -video_size 1280x720 -framerate 30 -i video="Integrated Camera" -vcodec libx264 -preset ultrafast -tune zerolatency -b:v 800k -maxrate 1000k -bufsize 1500k -pix_fmt yuv420p -g 30 -an -f rtsp -rtsp_transport tcp rtsp://localhost:8554/webcam

echo.
pause