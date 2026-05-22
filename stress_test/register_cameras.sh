#!/bin/bash
# ============================================================
# register_cameras.sh — Register fake cameras in the backend API
# ============================================================
# Usage: ./register_cameras.sh [NUM_CAMERAS] [BACKEND_URL] [MEDIAMTX_HOST]
# Default: 10 cameras, http://localhost:8000, mediamtx

NUM_CAMERAS=${1:-10}
BACKEND_URL=${2:-"http://localhost:8000"}
MEDIAMTX_HOST=${3:-"mediamtx"}

echo "============================================"
echo "  Registering $NUM_CAMERAS fake cameras"
echo "  Backend: $BACKEND_URL"
echo "  RTSP host: $MEDIAMTX_HOST"
echo "============================================"

# Verify curl is available
if ! command -v curl &>/dev/null; then
    echo "[ERROR] curl not found. Install it first."
    exit 1
fi

REGISTERED=0
FAILED=0

for i in $(seq 1 "$NUM_CAMERAS"); do
    NAME="stress_cam_$(printf '%03d' $i)"
    RTSP_URL="rtsp://$MEDIAMTX_HOST:8554/$NAME"

    echo -n "[$(date +%T)] Registering camera: $NAME ... "

    RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$BACKEND_URL/api/cameras" \
        -H "Content-Type: application/json" \
        -d "{
            \"name\": \"$NAME\",
            \"rtsp_url\": \"$RTSP_URL\",
            \"status\": \"live\"
        }" 2>/dev/null)

    HTTP_CODE=$(echo "$RESPONSE" | tail -1)
    BODY=$(echo "$RESPONSE" | head -n -1)

    if [ "$HTTP_CODE" -ge 200 ] && [ "$HTTP_CODE" -lt 300 ]; then
        # Try to extract camera ID from response
        CAM_ID=$(echo "$BODY" | python3 -c "import sys,json; print(json.load(sys.stdin).get('id','ok'))" 2>/dev/null || echo "ok")
        echo "OK (id=$CAM_ID)"
        REGISTERED=$((REGISTERED + 1))
    else
        echo "FAILED (HTTP $HTTP_CODE)"
        FAILED=$((FAILED + 1))
    fi

    sleep 0.2
done

echo ""
echo "============================================"
echo "  Registration complete"
echo "  Registered: $REGISTERED / $NUM_CAMERAS"
echo "  Failed: $FAILED"
echo "============================================"

# Step 2: Start all streams via API
echo ""
echo "Starting camera streams..."
for i in $(seq 1 "$NUM_CAMERAS"); do
    NAME="stress_cam_$(printf '%03d' $i)"

    # Get camera ID by listing cameras and filtering by name
    CAM_ID=$(curl -s "$BACKEND_URL/api/cameras" | \
        python3 -c "import sys,json; cams=json.load(sys.stdin); print(next((c['id'] for c in cams if c['name']=='$NAME'), ''))" 2>/dev/null)

    if [ -n "$CAM_ID" ]; then
        echo -n "  Starting $NAME ($CAM_ID) ... "
        HTTP=$(curl -s -o /dev/null -w "%{http_code}" \
            -X POST "$BACKEND_URL/api/cameras/$CAM_ID/start")
        echo "HTTP $HTTP"
    fi
done

echo ""
echo "Done. All cameras registered and streams started."
