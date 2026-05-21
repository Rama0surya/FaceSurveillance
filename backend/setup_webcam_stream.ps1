# =============================================================
# setup_webcam_stream.ps1
# Jalankan dari folder: face-surveillance\backend
# =============================================================

$ErrorActionPreference = "Stop"
Write-Host "=== Face Surveillance: Webcam Stream Setup ===" -ForegroundColor Cyan

if (-not (Test-Path ".\app\main.py")) {
    Write-Host "[ERROR] Jalankan dari folder backend" -ForegroundColor Red; exit 1
}

function Refresh-Path {
    $m = [System.Environment]::GetEnvironmentVariable("PATH","Machine")
    $u = [System.Environment]::GetEnvironmentVariable("PATH","User")
    $env:PATH = "$m;$u"
}

function Find-Ffmpeg {
    Refresh-Path
    $f = Get-Command ffmpeg -ErrorAction SilentlyContinue
    if ($f) { return $f.Source }
    $wingetBase = "$env:LOCALAPPDATA\Microsoft\WinGet\Packages"
    if (Test-Path $wingetBase) {
        $found = Get-ChildItem $wingetBase -Recurse -Filter "ffmpeg.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($found) { return $found.FullName }
    }
    $manual = "$env:LOCALAPPDATA\ffmpeg\bin\ffmpeg.exe"
    if (Test-Path $manual) { return $manual }
    return $null
}

# ------------------------------------------------------------------
# STEP 1 - Locate ffmpeg
# ------------------------------------------------------------------
Write-Host "`n[1/4] Checking ffmpeg..." -ForegroundColor Yellow

$ffmpegExe = Find-Ffmpeg

if (-not $ffmpegExe) {
    Write-Host "  Installing via winget..." -ForegroundColor DarkYellow
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget) {
        winget install --id Gyan.FFmpeg --silent --accept-package-agreements --accept-source-agreements 2>&1 | Out-Null
    }
    $ffmpegExe = Find-Ffmpeg

    if (-not $ffmpegExe) {
        Write-Host "  Downloading manually..." -ForegroundColor DarkYellow
        $ffmpegDir = "$env:LOCALAPPDATA\ffmpeg"
        $ffmpegBin = "$ffmpegDir\bin"
        if (-not (Test-Path "$ffmpegBin\ffmpeg.exe")) {
            $zipUrl = "https://github.com/GyanD/codexffmpeg/releases/download/7.1/ffmpeg-7.1-essentials_build.zip"
            $zipPath = "$env:TEMP\ffmpeg_dl.zip"
            $ProgressPreference = "SilentlyContinue"
            Invoke-WebRequest -Uri $zipUrl -OutFile $zipPath
            $ProgressPreference = "Continue"
            Expand-Archive -Path $zipPath -DestinationPath "$env:TEMP\ffmpeg_ex" -Force
            $extracted = Get-ChildItem "$env:TEMP\ffmpeg_ex" -Directory | Select-Object -First 1
            New-Item -ItemType Directory -Path $ffmpegDir -Force | Out-Null
            Copy-Item -Path "$($extracted.FullName)\*" -Destination $ffmpegDir -Recurse -Force
            Remove-Item $zipPath -Force -ErrorAction SilentlyContinue
            Remove-Item "$env:TEMP\ffmpeg_ex" -Recurse -Force -ErrorAction SilentlyContinue
        }
        $env:PATH = "$ffmpegBin;$env:PATH"
        $ffmpegExe = "$ffmpegBin\ffmpeg.exe"
    }

    if (-not (Test-Path $ffmpegExe)) {
        Write-Host "[ERROR] ffmpeg not found. Install manual: https://ffmpeg.org/download.html" -ForegroundColor Red
        exit 1
    }
}

Write-Host "  ffmpeg OK: $ffmpegExe" -ForegroundColor Green
$ffmpegDir2 = Split-Path $ffmpegExe -Parent
if ($env:PATH -notlike "*$ffmpegDir2*") { $env:PATH = "$ffmpegDir2;$env:PATH" }

# ------------------------------------------------------------------
# STEP 2 - Detect webcam via dshow (stderr redirect to temp file)
# ------------------------------------------------------------------
Write-Host "`n[2/4] Detecting webcam device name..." -ForegroundColor Yellow

$tmpErr = "$env:TEMP\ffmpeg_devices.txt"

# Jalankan via cmd /c supaya stderr bisa diredirect dengan benar
$cmdArgs = "/c `"`"$ffmpegExe`" -list_devices true -f dshow -i dummy`" 2>`"$tmpErr`""
Start-Process -FilePath "cmd.exe" -ArgumentList $cmdArgs -Wait -NoNewWindow 2>$null

$dshowContent = ""
if (Test-Path $tmpErr) {
    $dshowContent = Get-Content $tmpErr -Raw -Encoding UTF8
    Remove-Item $tmpErr -Force -ErrorAction SilentlyContinue
}

$inVideo = $false
$devices = @()
foreach ($line in ($dshowContent -split "`n")) {
    if ($line -match "DirectShow video devices") { $inVideo = $true; continue }
    if ($line -match "DirectShow audio devices") { $inVideo = $false }
    if ($inVideo -and $line -match '"([^"]+)"' -and $line -notmatch "@device") {
        $devices += $Matches[1]
    }
}

if ($devices.Count -eq 0) {
    Write-Host "  Device name not detected, using index 0" -ForegroundColor DarkYellow
    $camDevice = "0"
    $useIndex  = $true
} else {
    Write-Host "  Found:" -ForegroundColor Green
    for ($i = 0; $i -lt $devices.Count; $i++) {
        Write-Host "    [$i] $($devices[$i])" -ForegroundColor White
    }
    $camDevice = $devices[0]
    $useIndex  = $false
    Write-Host "  Using: $camDevice" -ForegroundColor Green
}

# ------------------------------------------------------------------
# STEP 3 - Register camera in database
# ------------------------------------------------------------------
Write-Host "`n[3/4] Registering camera in database..." -ForegroundColor Yellow

$pyRegLines = @(
    "from app.core.db_client import get_db",
    "from sqlalchemy import text",
    "import uuid",
    "from datetime import datetime, timezone",
    "db = get_db()",
    "try:",
    "    row = db.execute(text(""SELECT id FROM cameras WHERE name = 'Webcam Test' LIMIT 1"")).mappings().first()",
    "    if row:",
    "        print('EXISTS:' + str(row['id']))",
    "    else:",
    "        cid = str(uuid.uuid4())",
    "        db.execute(text(""INSERT INTO cameras (id, name, rtsp_url, status, created_at) VALUES (:id, :n, :u, 'offline', :t)""),",
    "            {'id': cid, 'n': 'Webcam Test', 'u': 'rtsp://localhost:8554/webcam', 't': datetime.now(timezone.utc).isoformat()})",
    "        db.commit()",
    "        print('CREATED:' + cid)",
    "finally:",
    "    db.close()"
)
$pyRegLines | Out-File -FilePath ".\__reg.py" -Encoding UTF8
$regOut = (python .\__reg.py 2>&1) | Out-String
Remove-Item ".\__reg.py" -Force -ErrorAction SilentlyContinue

$camId = ""
if ($regOut -match "(CREATED|EXISTS):([a-f0-9\-]{36})") {
    $camStatus = $Matches[1]
    $camId     = $Matches[2].Trim()
    Write-Host "  Camera $camStatus - ID: $camId" -ForegroundColor Green
} else {
    Write-Host "[ERROR] Failed to register camera." -ForegroundColor Red
    Write-Host "Output: $regOut" -ForegroundColor DarkGray
    exit 1
}

# ------------------------------------------------------------------
# STEP 4 - Generate launcher files
# ------------------------------------------------------------------
Write-Host "`n[4/4] Generating launcher files..." -ForegroundColor Yellow

if ($useIndex) {
    $ffInput = "video=`"0`""
} else {
    $ffInput = "video=`"$camDevice`""
}

# start_webcam_stream.bat
# Update start_webcam_stream.bat dengan device name yang benar
# $ffmpegExe = "C:\Users\ahmad\AppData\Local\Microsoft\WinGet\Links\ffmpeg.exe"
# $camDevice = "Streaming Webcams"
# Ubah baris perintah FFmpeg di dalam variabel $b1 menjadi seperti ini:
$b1 += "`"$ffmpegExe`" -f dshow -i $ffInput -vcodec libx264 -preset ultrafast -tune zerolatency -b:v 1500k -maxrate 1500k -bufsize 3000k -pix_fmt yuv420p -g 30 -an -f rtsp -rtsp_transport tcp rtsp://localhost:8554/webcam`r`n"

$b1  = "@echo off`r`n"
$b1 += "title ffmpeg - Webcam to RTSP`r`n"
$b1 += "echo Pushing webcam to rtsp://localhost:8554/webcam`r`n"
$b1 += "echo Press Ctrl+C to stop`r`n"
$b1 += "echo.`r`n"
$b1 += "`"$ffmpegExe`" -f dshow -i video=`"$camDevice`" -vcodec libx264 -preset ultrafast -tune zerolatency -b:v 1500k -maxrate 1500k -bufsize 3000k -pix_fmt yuv420p -g 30 -an -f rtsp -rtsp_transport tcp rtsp://localhost:8554/webcam`r`n"
$b1 += "echo.`r`n"
$b1 += "pause`r`n"
[System.IO.File]::WriteAllText((Join-Path (Get-Location).Path "start_webcam_stream.bat"), $b1, [System.Text.Encoding]::ASCII)
Write-Host "Updated: start_webcam_stream.bat -> device: $camDevice" -ForegroundColor Green

# start_detection.py
$p1 = @(
    "import requests, time, sys",
    "CAM_ID = '$camId'",
    "BASE = 'http://localhost:8000'",
    "print('Starting detection for Webcam Test...')",
    "print('Waiting 4s for stream to stabilize...')",
    "time.sleep(4)",
    "try:",
    "    r = requests.post(f'{BASE}/api/cameras/{CAM_ID}/start', timeout=10)",
    "    r.raise_for_status()",
    "    d = r.json()",
    "    print('[OK] Detection started!')",
    "    print('     Stream  : ' + str(d.get('stream_url')))",
    "    print('     MediaMTX: ' + str(d.get('via_mediamtx')))",
    "    print('')",
    "    print('Buka: http://localhost:5173')",
    "    print('Face Capture akan terisi dalam beberapa detik.')",
    "except requests.exceptions.ConnectionError:",
    "    print('[ERROR] Backend tidak jalan. Jalankan: uvicorn app.main:app --reload')",
    "    sys.exit(1)",
    "except Exception as e:",
    "    print('[ERROR] ' + str(e))",
    "    sys.exit(1)"
)
$p1 | Out-File -FilePath ".\start_detection.py" -Encoding UTF8
Write-Host "  Created: start_detection.py" -ForegroundColor Green

# stop_detection.py
$p2 = @(
    "import requests",
    "CAM_ID = '$camId'",
    "BASE = 'http://localhost:8000'",
    "try:",
    "    r = requests.post(f'{BASE}/api/cameras/{CAM_ID}/stop', timeout=10)",
    "    r.raise_for_status()",
    "    print('[OK] Detection stopped')",
    "except Exception as e:",
    "    print('[ERROR] ' + str(e))"
)
$p2 | Out-File -FilePath ".\stop_detection.py" -Encoding UTF8
Write-Host "  Created: stop_detection.py" -ForegroundColor Green

# launch_webcam_test.bat (master launcher)
$b2  = "@echo off`r`n"
$b2 += "title Face Surveillance - Webcam Test`r`n"
$b2 += "echo ================================================`r`n"
$b2 += "echo  Face Surveillance Webcam Launcher`r`n"
$b2 += "echo  Pastikan backend dan frontend sudah running!`r`n"
$b2 += "echo ================================================`r`n"
$b2 += "echo.`r`n"
$b2 += "pause`r`n"
$b2 += "echo [1/2] Starting ffmpeg stream in new window...`r`n"
$b2 += "start `"ffmpeg Stream`" cmd /k start_webcam_stream.bat`r`n"
$b2 += "echo Waiting 5s for stream to stabilize...`r`n"
$b2 += "timeout /t 5 /nobreak`r`n"
$b2 += "echo [2/2] Starting detection engine...`r`n"
$b2 += "python start_detection.py`r`n"
$b2 += "echo.`r`n"
$b2 += "echo Done! Buka http://localhost:5173`r`n"
$b2 += "pause`r`n"
[System.IO.File]::WriteAllText((Join-Path (Get-Location).Path "launch_webcam_test.bat"), $b2, [System.Text.Encoding]::ASCII)
Write-Host "  Created: launch_webcam_test.bat" -ForegroundColor Green

# ------------------------------------------------------------------
# Summary
# ------------------------------------------------------------------
Write-Host ""
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host " Setup selesai!" -ForegroundColor Cyan
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host " Camera   : Webcam Test" -ForegroundColor White
Write-Host " ID       : $camId" -ForegroundColor White
Write-Host " Device   : $camDevice" -ForegroundColor White
Write-Host " RTSP URL : rtsp://localhost:8554/webcam" -ForegroundColor White
Write-Host " ffmpeg   : $ffmpegExe" -ForegroundColor White
Write-Host ""
Write-Host " Cara running:" -ForegroundColor Yellow
Write-Host "   Terminal 1 : uvicorn app.main:app --reload" -ForegroundColor DarkGray
Write-Host "   Terminal 2 : cd ..\frontend && npm run dev" -ForegroundColor DarkGray
Write-Host "   Terminal 3 : .\launch_webcam_test.bat" -ForegroundColor Cyan
Write-Host ""
Write-Host " Atau manual step-by-step:" -ForegroundColor Yellow
Write-Host "   Step 1 : .\start_webcam_stream.bat  (buka di terminal baru)" -ForegroundColor DarkGray
Write-Host "   Step 2 : python start_detection.py" -ForegroundColor DarkGray
Write-Host "   Stop   : python stop_detection.py" -ForegroundColor DarkGray
Write-Host ""