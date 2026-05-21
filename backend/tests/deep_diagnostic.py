"""
Deep diagnostic: isolate the ~2s delay and measure real throughput.
"""
import requests, time, statistics, json, socket, concurrent.futures

BASE = "http://localhost:8000"
R = {}

def timed_get(url, label, n=10, **kw):
    times = []
    for _ in range(n):
        s = time.perf_counter()
        r = requests.get(url, timeout=15, **kw)
        times.append((time.perf_counter() - s) * 1000)
    R[label] = {
        "min": round(min(times),1), "max": round(max(times),1),
        "avg": round(statistics.mean(times),1),
        "median": round(statistics.median(times),1),
        "p95": round(sorted(times)[int(len(times)*0.95)],1) if len(times)>1 else round(times[0],1),
        "samples": times[:5],
    }
    print(f"  {label}: avg={R[label]['avg']}ms  min={R[label]['min']}ms  max={R[label]['max']}ms")
    return R[label]

# 1. Raw TCP connect time
print("== 1. RAW TCP CONNECT ==")
tcp_times = []
for _ in range(10):
    s = time.perf_counter()
    sock = socket.create_connection(("localhost", 8000), timeout=5)
    tcp_times.append((time.perf_counter() - s) * 1000)
    sock.close()
R["tcp_connect"] = {"avg": round(statistics.mean(tcp_times),2), "samples": [round(t,2) for t in tcp_times]}
print(f"  TCP connect: avg={R['tcp_connect']['avg']}ms  samples={R['tcp_connect']['samples'][:5]}")

# 2. HTTP keep-alive vs new connection
print("\n== 2. KEEP-ALIVE vs NEW CONN ==")
print("  -- With keep-alive (session) --")
sess = requests.Session()
ka_times = []
for _ in range(15):
    s = time.perf_counter()
    sess.get(f"{BASE}/", timeout=10)
    ka_times.append((time.perf_counter() - s) * 1000)
R["keepalive"] = {"avg": round(statistics.mean(ka_times),1), "min": round(min(ka_times),1), "max": round(max(ka_times),1), "samples": [round(t,1) for t in ka_times]}
print(f"  Keep-alive: avg={R['keepalive']['avg']}ms  min={R['keepalive']['min']}ms  samples={R['keepalive']['samples'][:8]}")
sess.close()

print("  -- Without keep-alive (new conn each) --")
nk_times = []
for _ in range(10):
    s = time.perf_counter()
    requests.get(f"{BASE}/", timeout=10, headers={"Connection": "close"})
    nk_times.append((time.perf_counter() - s) * 1000)
R["no_keepalive"] = {"avg": round(statistics.mean(nk_times),1), "min": round(min(nk_times),1), "samples": [round(t,1) for t in nk_times]}
print(f"  No keep-alive: avg={R['no_keepalive']['avg']}ms  min={R['no_keepalive']['min']}ms  samples={R['no_keepalive']['samples'][:8]}")

# 3. Rapid-fire sequential (detect if delay is per-request or batched)
print("\n== 3. RAPID-FIRE SEQUENTIAL (50 reqs) ==")
sess2 = requests.Session()
# warm up
sess2.get(f"{BASE}/", timeout=10)
rapid_times = []
for _ in range(50):
    s = time.perf_counter()
    sess2.get(f"{BASE}/", timeout=10)
    rapid_times.append((time.perf_counter() - s) * 1000)
R["rapid_sequential"] = {
    "avg": round(statistics.mean(rapid_times),1),
    "min": round(min(rapid_times),1),
    "max": round(max(rapid_times),1),
    "median": round(statistics.median(rapid_times),1),
    "p95": round(sorted(rapid_times)[int(len(rapid_times)*0.95)],1),
    "first_5": [round(t,1) for t in rapid_times[:5]],
    "last_5": [round(t,1) for t in rapid_times[-5:]],
}
print(f"  avg={R['rapid_sequential']['avg']}ms  min={R['rapid_sequential']['min']}ms  p95={R['rapid_sequential']['p95']}ms")
print(f"  first 5: {R['rapid_sequential']['first_5']}")
print(f"  last 5:  {R['rapid_sequential']['last_5']}")
sess2.close()

# 4. Concurrent burst (max throughput)
print("\n== 4. CONCURRENT BURST (50 simultaneous) ==")
def single_req(_):
    s = time.perf_counter()
    requests.get(f"{BASE}/", timeout=15)
    return (time.perf_counter() - s) * 1000

wall_start = time.perf_counter()
with concurrent.futures.ThreadPoolExecutor(max_workers=50) as ex:
    burst_times = list(ex.map(single_req, range(50)))
wall_total = (time.perf_counter() - wall_start) * 1000
R["concurrent_burst"] = {
    "wall_time_ms": round(wall_total,1),
    "avg_per_req": round(statistics.mean(burst_times),1),
    "min": round(min(burst_times),1),
    "max": round(max(burst_times),1),
    "effective_rps": round(50 / (wall_total / 1000), 1),
}
print(f"  Wall time: {R['concurrent_burst']['wall_time_ms']}ms for 50 reqs")
print(f"  Effective RPS: {R['concurrent_burst']['effective_rps']}")
print(f"  Per-req avg: {R['concurrent_burst']['avg_per_req']}ms  min: {R['concurrent_burst']['min']}ms  max: {R['concurrent_burst']['max']}ms")

# 5. Endpoint-specific latency comparison (with keep-alive)
print("\n== 5. ENDPOINT LATENCY (keep-alive, 10 samples each) ==")
sess3 = requests.Session()
sess3.get(f"{BASE}/", timeout=10)  # warm
endpoints = [
    ("/", "root"),
    ("/api/cameras", "cameras_list"),
    ("/api/detections?per_page=5", "detections"),
    ("/api/stats/today", "stats_today"),
    ("/api/stats/hourly", "stats_hourly"),
    ("/api/stats/comparison", "stats_comparison"),
    ("/api/alerts", "alerts"),
    ("/api/alerts/rules", "alert_rules"),
    ("/api/snapshots?limit=5", "snapshots"),
    ("/api/settings/health", "health"),
    ("/api/settings/system-info", "system_info"),
]
for path, label in endpoints:
    times = []
    for _ in range(10):
        s = time.perf_counter()
        sess3.get(f"{BASE}{path}", timeout=15)
        times.append((time.perf_counter() - s) * 1000)
    R[f"ep_{label}"] = {"avg": round(statistics.mean(times),1), "min": round(min(times),1), "max": round(max(times),1)}
    print(f"  {label}: avg={R[f'ep_{label}']['avg']}ms  min={R[f'ep_{label}']['min']}ms  max={R[f'ep_{label}']['max']}ms")
sess3.close()

# 6. DB-heavy vs lightweight
print("\n== 6. DB ROUNDTRIP ISOLATION ==")
sess4 = requests.Session()
sess4.get(f"{BASE}/", timeout=10)
# Lightweight (no DB)
light_times = []
for _ in range(20):
    s = time.perf_counter()
    sess4.get(f"{BASE}/", timeout=10)
    light_times.append((time.perf_counter() - s) * 1000)
# DB-backed
db_times = []
for _ in range(20):
    s = time.perf_counter()
    sess4.get(f"{BASE}/api/cameras", timeout=10)
    db_times.append((time.perf_counter() - s) * 1000)
R["no_db_root"] = {"avg": round(statistics.mean(light_times),1), "min": round(min(light_times),1)}
R["with_db_cameras"] = {"avg": round(statistics.mean(db_times),1), "min": round(min(db_times),1)}
print(f"  No DB (root):     avg={R['no_db_root']['avg']}ms  min={R['no_db_root']['min']}ms")
print(f"  With DB (cameras): avg={R['with_db_cameras']['avg']}ms  min={R['with_db_cameras']['min']}ms")
print(f"  DB overhead estimate: ~{round(R['with_db_cameras']['avg'] - R['no_db_root']['avg'], 1)}ms")
sess4.close()

# Write JSON
with open("diagnostic_results.json", "w") as f:
    json.dump(R, f, indent=2, default=str)
print(f"\nResults saved to diagnostic_results.json")
