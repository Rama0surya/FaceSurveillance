@echo off
title Face Surveillance - Webcam Test
echo ================================================
echo  Face Surveillance Webcam Launcher
echo  Pastikan backend dan frontend sudah running!
echo ================================================
echo.
pause
echo [1/2] Starting ffmpeg stream in new window...
start "ffmpeg Stream" cmd /k start_webcam_stream.bat
echo Waiting 5s for stream to stabilize...
timeout /t 5 /nobreak
echo [2/2] Starting detection engine...
python start_detection.py
echo.
echo Done! Buka http://localhost:5173
pause
