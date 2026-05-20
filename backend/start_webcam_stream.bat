@echo off
title ffmpeg - Webcam to RTSP
echo Pushing webcam to rtsp://localhost:8554/webcam
echo Press Ctrl+C to stop
echo.
"C:\Users\ahmad\AppData\Local\Microsoft\WinGet\Links\ffmpeg.exe" -f dshow -i video="Streaming Webcams" -vcodec libx264 -preset ultrafast -tune zerolatency -b:v 1500k -maxrate 1500k -bufsize 3000k -pix_fmt yuv420p -g 30 -an -f rtsp -rtsp_transport tcp rtsp://localhost:8554/webcam
echo.
pause