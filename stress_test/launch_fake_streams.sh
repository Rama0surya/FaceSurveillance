#!/bin/bash
# ============================================================
# launch_fake_streams.sh — Spawn N fake RTSP streams to MediaMTX
# ============================================================
# Usage: ./launch_fake_streams.sh [NUM_STREAMS] [VIDEO_FILE] [MEDIAMTX_HOST] [RTSP_PORT]
# Default: 10 streams, test_stream.mp4, localhost:8554
#
# Prerequisites:
#   - ffmpeg installed
#   - MediaMTX running and accepting RTSP publish
#   - A test video file (see below for how to generate one)
#
# Generate a test video with synthetic pattern:
#   ffmpeg -f lavfi -i testsrc=size=1920x1080:rate=30 -t 600 \
#          -c:v libx264 -pix_fmt yuv420p test_stream.mp4

NUM_STREAMS=${1:-10}
VIDEO_FILE=${2:-"test_stream.mp4"}
MEDIAMTX_HOST=${3:-"localhost"}
MEDIAMTX_RTSP_PORT=${4:-8554}

echo "============================================"
echo "  STRESS TEST: Launching $NUM_STREAMS fake RTSP streams"
echo "  Video source: $VIDEO_FILE"
echo "  Target: rtsp://$MEDIAMTX_HOST:$MEDIAMTX_RTSP_PORT"
echo "============================================"

# Verify video file exists
if [ ! -f "$VIDEO_FILE" ]; then
    echo ""
    echo "[ERROR] Video file not found: $VIDEO_FILE"
    echo ""
    echo "Generate a test video first:"
    echo "  ffmpeg -f lavfi -i testsrc=size=1920x1080:rate=30 -t 600 \\"
    echo "         -c:v libx264 -pix_fmt yuv420p $VIDEO_FILE"
    echo ""
    echo "Or use an existing video with faces for realistic testing."
    exit 1
fi

# Verify ffmpeg is available
if ! command -v ffmpeg &>/dev/null; then
    echo "[ERROR] ffmpeg not found. Install it first."
    exit 1
fi

PIDS=()

cleanup() {
    echo ""
    echo "[INFO] Stopping all ffmpeg processes..."
    for pid in "${PIDS[@]}"; do
        kill "$pid" 2>/dev/null
    done
    wait 2>/dev/null
    echo "[INFO] All $NUM_STREAMS streams stopped."
}

trap cleanup EXIT INT TERM

for i in $(seq 1 "$NUM_STREAMS"); do
    STREAM_NAME="stress_cam_$(printf '%03d' $i)"
    RTSP_URL="rtsp://$MEDIAMTX_HOST:$MEDIAMTX_RTSP_PORT/$STREAM_NAME"

    echo "[$(date +%T)] Starting stream $i/$NUM_STREAMS → $RTSP_URL"

    ffmpeg -re -stream_loop -1 \
        -i "$VIDEO_FILE" \
        -c:v libx264 -preset ultrafast -tune zerolatency \
        -b:v 2M -maxrate 2M -bufsize 4M \
        -g 30 -keyint_min 30 \
        -f rtsp -rtsp_transport tcp \
        "$RTSP_URL" \
        -loglevel warning \
        &

    PIDS+=($!)

    # Stagger launches to avoid thundering herd on MediaMTX
    sleep 0.5
done

echo ""
echo "============================================"
echo "  ALL $NUM_STREAMS STREAMS RUNNING"
echo "  Stream names: stress_cam_001 .. stress_cam_$(printf '%03d' $NUM_STREAMS)"
echo "  Press Ctrl+C to stop all streams"
echo "============================================"

# Wait for all background processes
wait
