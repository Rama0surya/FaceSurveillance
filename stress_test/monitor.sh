#!/bin/bash
# ============================================================
# monitor.sh — Unified system monitor during stress test
# ============================================================
# Records GPU, CPU, RAM, Python process, and API health metrics
# to CSV files for post-test analysis.
#
# Usage: ./monitor.sh [DURATION_SECONDS] [INTERVAL_SECONDS]
# Default: 600s (10 min), 5s interval

DURATION=${1:-600}
INTERVAL=${2:-5}
OUTPUT_DIR="monitor_logs"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKEND_URL=${3:-"http://localhost:8000"}

mkdir -p "$OUTPUT_DIR"

echo "============================================"
echo "  System Monitor"
echo "  Duration: ${DURATION}s"
echo "  Interval: ${INTERVAL}s"
echo "  Output: $OUTPUT_DIR/"
echo "  Backend: $BACKEND_URL"
echo "============================================"

PIDS=()

cleanup() {
    echo ""
    echo "[INFO] Stopping all monitors..."
    for pid in "${PIDS[@]}"; do
        kill "$pid" 2>/dev/null
    done
    wait 2>/dev/null
    echo "[DONE] Logs saved to $OUTPUT_DIR/"
    echo "  Files:"
    ls -la "$OUTPUT_DIR/"*"$TIMESTAMP"* 2>/dev/null
}

trap cleanup EXIT INT TERM

# ---- 1. GPU monitoring ----
if command -v nvidia-smi &>/dev/null; then
    nvidia-smi --query-gpu=timestamp,name,temperature.gpu,utilization.gpu,utilization.memory,memory.total,memory.used,memory.free,power.draw \
        --format=csv -l "$INTERVAL" \
        > "$OUTPUT_DIR/gpu_${TIMESTAMP}.csv" &
    PIDS+=($!)
    echo "[OK] GPU monitor started"

    # Per-process GPU memory
    nvidia-smi pmon -s m -d "$INTERVAL" \
        > "$OUTPUT_DIR/gpu_process_${TIMESTAMP}.txt" &
    PIDS+=($!)
    echo "[OK] GPU per-process monitor started"
else
    echo "[SKIP] nvidia-smi not found — GPU monitoring disabled"
fi

# ---- 2. CPU/RAM monitoring ----
(
    echo "timestamp,cpu_percent,ram_used_mb,ram_total_mb,ram_percent"
    END_TIME=$((SECONDS + DURATION))
    while [ $SECONDS -lt $END_TIME ]; do
        if [ -f /proc/stat ]; then
            # Linux
            CPU=$(grep 'cpu ' /proc/stat | awk '{usage=($2+$4)*100/($2+$4+$5)} END {printf "%.1f", usage}')
            RAM=$(free -m 2>/dev/null | awk 'NR==2{printf "%s,%s,%.1f", $3,$2,$3*100/$2}')
        else
            # macOS/Windows fallback
            CPU="0"
            RAM="0,0,0"
        fi
        echo "$(date +%T),$CPU,$RAM"
        sleep "$INTERVAL"
    done
) > "$OUTPUT_DIR/system_${TIMESTAMP}.csv" &
PIDS+=($!)
echo "[OK] System monitor started"

# ---- 3. Python process monitoring ----
(
    echo "timestamp,python_rss_mb,python_cpu_pct,thread_count,fd_count"
    END_TIME=$((SECONDS + DURATION))
    while [ $SECONDS -lt $END_TIME ]; do
        # Find the uvicorn/python process
        PY_PID=$(pgrep -f 'uvicorn' | head -1)
        if [ -n "$PY_PID" ]; then
            RSS_KB=$(ps -o rss= -p "$PY_PID" 2>/dev/null | tr -d ' ')
            CPU_PCT=$(ps -o %cpu= -p "$PY_PID" 2>/dev/null | tr -d ' ')
            THREADS=$(ls /proc/"$PY_PID"/task 2>/dev/null | wc -l || echo 0)
            FDS=$(ls /proc/"$PY_PID"/fd 2>/dev/null | wc -l || echo 0)
            RSS_MB=$(echo "scale=1; ${RSS_KB:-0}/1024" | bc 2>/dev/null || echo 0)
            echo "$(date +%T),${RSS_MB},${CPU_PCT:-0},${THREADS},${FDS}"
        else
            echo "$(date +%T),0,0,0,0"
        fi
        sleep "$INTERVAL"
    done
) > "$OUTPUT_DIR/python_${TIMESTAMP}.csv" &
PIDS+=($!)
echo "[OK] Python process monitor started"

# ---- 4. API health check ----
(
    echo "timestamp,http_code,response_time_ms"
    END_TIME=$((SECONDS + DURATION))
    while [ $SECONDS -lt $END_TIME ]; do
        RESULT=$(curl -s -o /dev/null -w "%{http_code},%{time_total}" \
            "$BACKEND_URL/" 2>/dev/null || echo "000,0")
        CODE=$(echo "$RESULT" | cut -d, -f1)
        TIME_S=$(echo "$RESULT" | cut -d, -f2)
        TIME_MS=$(echo "scale=1; $TIME_S * 1000" | bc 2>/dev/null || echo 0)
        echo "$(date +%T),$CODE,$TIME_MS"
        sleep "$INTERVAL"
    done
) > "$OUTPUT_DIR/health_${TIMESTAMP}.csv" &
PIDS+=($!)
echo "[OK] Health check monitor started"

# ---- 5. Network connection count ----
(
    echo "timestamp,established,time_wait,close_wait"
    END_TIME=$((SECONDS + DURATION))
    while [ $SECONDS -lt $END_TIME ]; do
        if command -v ss &>/dev/null; then
            EST=$(ss -tn state established 2>/dev/null | grep -c ':8000' || echo 0)
            TW=$(ss -tn state time-wait 2>/dev/null | grep -c ':8000' || echo 0)
            CW=$(ss -tn state close-wait 2>/dev/null | grep -c ':8000' || echo 0)
        else
            EST=0; TW=0; CW=0
        fi
        echo "$(date +%T),$EST,$TW,$CW"
        sleep "$INTERVAL"
    done
) > "$OUTPUT_DIR/network_${TIMESTAMP}.csv" &
PIDS+=($!)
echo "[OK] Network monitor started"

echo ""
echo "All monitors running. Recording for ${DURATION}s..."
echo "Press Ctrl+C to stop early."
echo ""

# Live status updates every 30s
ELAPSED=0
while [ $ELAPSED -lt $DURATION ]; do
    sleep 30
    ELAPSED=$((ELAPSED + 30))
    REMAINING=$((DURATION - ELAPSED))
    if [ $REMAINING -gt 0 ]; then
        echo "[$(date +%T)] ${ELAPSED}s elapsed, ${REMAINING}s remaining..."
    fi
done

echo ""
echo "[$(date +%T)] Monitoring duration complete."
