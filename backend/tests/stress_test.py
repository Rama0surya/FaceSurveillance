"""
Comprehensive Backend API Stress Test
Tests all endpoints: health, cameras CRUD, detections, stats, alerts, settings, debug, websocket
"""
import requests
import time
import json
import statistics
import concurrent.futures
import asyncio
import sys
from datetime import datetime

BASE = "http://localhost:8000"
RESULTS = []
CREATED_IDS = {"cameras": [], "alert_rules": []}

def test_endpoint(method, path, name, expected_status=200, json_body=None, params=None, allow_statuses=None):
    """Test a single endpoint and record results."""
    url = f"{BASE}{path}"
    allowed = allow_statuses or [expected_status]
    try:
        start = time.perf_counter()
        if method == "GET":
            r = requests.get(url, params=params, timeout=15)
        elif method == "POST":
            r = requests.post(url, json=json_body, timeout=15)
        elif method == "PUT":
            r = requests.put(url, json=json_body, timeout=15)
        elif method == "DELETE":
            r = requests.delete(url, timeout=15)
        elapsed_ms = (time.perf_counter() - start) * 1000
        
        passed = r.status_code in allowed
        body = None
        try:
            body = r.json()
        except:
            body = r.text[:200] if r.text else None
        
        result = {
            "name": name,
            "method": method,
            "path": path,
            "status_code": r.status_code,
            "expected": expected_status,
            "passed": passed,
            "time_ms": round(elapsed_ms, 2),
            "response_preview": str(body)[:150] if body else "",
            "error": None if passed else f"Got {r.status_code}, expected {allowed}"
        }
    except Exception as e:
        result = {
            "name": name, "method": method, "path": path,
            "status_code": 0, "expected": expected_status,
            "passed": False, "time_ms": 0,
            "response_preview": "", "error": str(e)[:150]
        }
    RESULTS.append(result)
    status_icon = "PASS" if result["passed"] else "FAIL"
    print(f"  [{status_icon}] {name} ({method} {path}) -> {result['status_code']} ({result['time_ms']:.0f}ms)")
    return result


def stress_endpoint(method, path, name, n=50, json_body=None, params=None):
    """Hit an endpoint N times concurrently and measure latency distribution."""
    url = f"{BASE}{path}"
    times = []
    errors = 0
    
    def single_request(_):
        try:
            start = time.perf_counter()
            if method == "GET":
                r = requests.get(url, params=params, timeout=15)
            elif method == "POST":
                r = requests.post(url, json=json_body, timeout=15)
            elapsed = (time.perf_counter() - start) * 1000
            if r.status_code >= 500:
                return None, True
            return elapsed, False
        except:
            return None, True

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(single_request, range(n)))
    
    for elapsed, err in results:
        if err:
            errors += 1
        elif elapsed is not None:
            times.append(elapsed)
    
    stats = {}
    if times:
        stats = {
            "min_ms": round(min(times), 1),
            "max_ms": round(max(times), 1),
            "avg_ms": round(statistics.mean(times), 1),
            "median_ms": round(statistics.median(times), 1),
            "p95_ms": round(sorted(times)[int(len(times)*0.95)], 1) if len(times) > 1 else round(times[0], 1),
            "p99_ms": round(sorted(times)[int(len(times)*0.99)], 1) if len(times) > 1 else round(times[0], 1),
        }
    
    result = {
        "name": f"STRESS: {name}",
        "method": method,
        "path": path,
        "requests": n,
        "success": len(times),
        "errors": errors,
        "passed": errors == 0,
        **stats
    }
    print(f"  [{'PASS' if result['passed'] else 'FAIL'}] STRESS {name}: {n} reqs, {errors} errors, avg={stats.get('avg_ms','N/A')}ms, p95={stats.get('p95_ms','N/A')}ms")
    return result


def test_websocket_connect(path, name):
    """Test WebSocket connection (basic connect/disconnect)."""
    try:
        import websocket
        ws_url = f"ws://localhost:8000{path}"
        start = time.perf_counter()
        ws = websocket.create_connection(ws_url, timeout=5)
        elapsed_ms = (time.perf_counter() - start) * 1000
        ws.close()
        result = {"name": name, "path": path, "passed": True, "time_ms": round(elapsed_ms, 2), "error": None}
        print(f"  [PASS] {name} ({elapsed_ms:.0f}ms)")
    except ImportError:
        result = {"name": name, "path": path, "passed": None, "time_ms": 0, "error": "websocket-client not installed (skipped)"}
        print(f"  [SKIP] {name} - websocket-client not installed")
    except Exception as e:
        result = {"name": name, "path": path, "passed": False, "time_ms": 0, "error": str(e)[:150]}
        print(f"  [FAIL] {name} - {str(e)[:80]}")
    RESULTS.append(result)
    return result


def run_tests():
    print("=" * 70)
    print("FACE SURVEILLANCE API — COMPREHENSIVE STRESS TEST")
    print(f"Target: {BASE}")
    print(f"Started: {datetime.now().isoformat()}")
    print("=" * 70)

    # ── 1. HEALTH CHECK ──
    print("\n── 1. Health Check ──")
    test_endpoint("GET", "/", "Root health check")
    test_endpoint("GET", "/api/settings/health", "Health endpoint")
    test_endpoint("GET", "/docs", "Swagger docs", allow_statuses=[200])

    # ── 2. SYSTEM INFO ──
    print("\n── 2. System Info ──")
    test_endpoint("GET", "/api/settings/system-info", "Full system info")
    test_endpoint("GET", "/api/settings/hardware", "Hardware info")
    test_endpoint("GET", "/api/settings/models", "AI model info")

    # ── 3. CAMERA CRUD ──
    print("\n── 3. Camera CRUD ──")
    # List cameras (baseline)
    test_endpoint("GET", "/api/cameras", "List cameras (initial)")
    
    # Create cameras
    for i in range(3):
        r = test_endpoint("POST", "/api/cameras", f"Create camera #{i+1}", expected_status=201,
                          json_body={"name": f"StressTest Cam {i+1}", "rtsp_url": f"rtsp://fake:554/stream{i}"})
        if r["passed"]:
            try:
                body = json.loads(r["response_preview"].replace("'", '"')) if "id" in r["response_preview"] else None
            except:
                body = None
            if body and "id" in body:
                CREATED_IDS["cameras"].append(body["id"])
            else:
                # Try direct request to get the ID
                resp = requests.post(f"{BASE}/api/cameras", json={"name": f"StressTest CamX {i}", "rtsp_url": f"rtsp://fake:554/x{i}"}, timeout=10)
                if resp.status_code == 201:
                    CREATED_IDS["cameras"].append(resp.json()["id"])
    
    # If we don't have IDs from response preview, fetch them
    if not CREATED_IDS["cameras"]:
        resp = requests.get(f"{BASE}/api/cameras", timeout=10)
        if resp.status_code == 200:
            cams = resp.json()
            CREATED_IDS["cameras"] = [c["id"] for c in cams if "StressTest" in c.get("name", "")]
    
    cam_id = CREATED_IDS["cameras"][0] if CREATED_IDS["cameras"] else "nonexistent"
    
    test_endpoint("GET", "/api/cameras", "List cameras (after create)")
    
    # Update camera
    if cam_id != "nonexistent":
        test_endpoint("PUT", f"/api/cameras/{cam_id}", "Update camera name",
                      json_body={"name": "StressTest Updated"})
    
    # Camera status
    if cam_id != "nonexistent":
        test_endpoint("GET", f"/api/cameras/{cam_id}/status", "Get camera status")
        test_endpoint("GET", f"/api/cameras/{cam_id}/mediamtx-status", "Get MediaMTX status")
    
    # 404 tests
    test_endpoint("GET", f"/api/cameras/nonexistent-uuid/status", "Camera status 404", expected_status=404)
    test_endpoint("PUT", f"/api/cameras/nonexistent-uuid", "Update camera 404", expected_status=404, json_body={"name": "x"})
    test_endpoint("DELETE", f"/api/cameras/nonexistent-uuid", "Delete camera 404", expected_status=404)
    
    # Validation tests
    test_endpoint("POST", "/api/cameras", "Create camera - missing fields", expected_status=422, json_body={})
    test_endpoint("POST", "/api/cameras", "Create camera - empty name", expected_status=422, json_body={"name": "", "rtsp_url": "rtsp://x"})

    # ── 4. STREAM CONTROL ──
    print("\n── 4. Stream Control ──")
    if cam_id != "nonexistent":
        test_endpoint("POST", f"/api/cameras/{cam_id}/start", "Start stream (fake RTSP)", allow_statuses=[200, 500])
        time.sleep(1)
        test_endpoint("GET", f"/api/cameras/{cam_id}/status", "Status after start")
        test_endpoint("POST", f"/api/cameras/{cam_id}/stop", "Stop stream")
        test_endpoint("GET", f"/api/cameras/{cam_id}/status", "Status after stop")
    test_endpoint("POST", f"/api/cameras/nonexistent-uuid/start", "Start stream 404", expected_status=404)

    # ── 5. MOCK DATA ──
    print("\n── 5. Mock Data Generation ──")
    test_endpoint("POST", "/api/debug/generate-mock", "Generate 50 mock detections", params={"count": 50})
    test_endpoint("POST", "/api/debug/generate-mock", "Generate 200 mock detections", params={"count": 200})

    # ── 6. DETECTIONS & SNAPSHOTS ──
    print("\n── 6. Detections & Snapshots ──")
    test_endpoint("GET", "/api/detections", "List detections (default)")
    test_endpoint("GET", "/api/detections", "Detections page 1, per_page 5", params={"page": 1, "per_page": 5})
    test_endpoint("GET", "/api/detections", "Detections page 2", params={"page": 2, "per_page": 10})
    if cam_id != "nonexistent":
        test_endpoint("GET", "/api/detections", "Detections by camera", params={"camera_id": cam_id})
    test_endpoint("GET", "/api/detections", "Detections by emotion", params={"emotion": "happy"})
    test_endpoint("GET", "/api/detections", "Detections by gender", params={"gender": "male"})
    test_endpoint("GET", "/api/detections", "Detections by date range", params={"date_from": "2026-01-01", "date_to": "2026-12-31"})
    
    test_endpoint("GET", "/api/snapshots", "List snapshots (default)")
    test_endpoint("GET", "/api/snapshots", "Snapshots with limit", params={"limit": 5, "offset": 0})
    test_endpoint("GET", "/api/snapshots", "Snapshots by emotion", params={"emotion": "neutral"})

    # ── 7. STATISTICS ──
    print("\n── 7. Statistics ──")
    test_endpoint("GET", "/api/stats/today", "Today stats (all cameras)")
    if cam_id != "nonexistent":
        test_endpoint("GET", "/api/stats/today", "Today stats (specific camera)", params={"camera_id": cam_id})
    test_endpoint("GET", "/api/stats/hourly", "Hourly stats (today)")
    test_endpoint("GET", "/api/stats/hourly", "Hourly stats (specific date)", params={"date": "2026-05-21"})
    test_endpoint("GET", "/api/stats/comparison", "Day-over-day comparison")

    # ── 8. ALERT RULES CRUD ──
    print("\n── 8. Alert Rules CRUD ──")
    test_endpoint("GET", "/api/alerts/rules", "List alert rules (initial)")
    
    rule_body = {
        "name": "StressTest Rule - Crowd",
        "rule_type": "crowd_count",
        "condition": {"threshold": 10, "operator": "gte"},
        "severity": "critical",
        "is_active": True,
        "cooldown_seconds": 30
    }
    r = test_endpoint("POST", "/api/alerts/rules", "Create alert rule", expected_status=201)
    # Get the rule directly
    resp = requests.post(f"{BASE}/api/alerts/rules", json=rule_body, timeout=10)
    rule_id = None
    if resp.status_code == 201:
        rule_id = resp.json().get("id")
        CREATED_IDS["alert_rules"].append(rule_id)
    
    # Create another rule
    rule_body2 = {
        "name": "StressTest Rule - Emotion",
        "rule_type": "emotion",
        "condition": {"emotion": "angry", "threshold": 3},
        "severity": "warning",
        "is_active": True,
        "cooldown_seconds": 60
    }
    resp2 = requests.post(f"{BASE}/api/alerts/rules", json=rule_body2, timeout=10)
    if resp2.status_code == 201:
        CREATED_IDS["alert_rules"].append(resp2.json().get("id"))
    
    test_endpoint("GET", "/api/alerts/rules", "List alert rules (after create)")
    
    if rule_id:
        test_endpoint("PUT", f"/api/alerts/rules/{rule_id}", "Update alert rule",
                      json_body={"name": "Updated StressTest Rule", "severity": "warning"})
    
    # 404 test
    test_endpoint("PUT", "/api/alerts/rules/nonexistent-uuid", "Update rule 404", expected_status=404,
                  json_body={"name": "x"})
    test_endpoint("DELETE", "/api/alerts/rules/nonexistent-uuid", "Delete rule 404", expected_status=404)

    # ── 9. ALERTS ──
    print("\n── 9. Alerts ──")
    test_endpoint("GET", "/api/alerts", "List alerts (default)")
    test_endpoint("GET", "/api/alerts", "Alerts with pagination", params={"limit": 10, "offset": 0})
    test_endpoint("GET", "/api/alerts", "Alerts by severity", params={"severity": "critical"})
    test_endpoint("GET", "/api/alerts", "Alerts unread only", params={"is_read": False})
    test_endpoint("GET", "/api/alerts/unread-count", "Unread alert count")
    test_endpoint("POST", "/api/alerts/mark-all-read", "Mark all alerts read", json_body={})
    test_endpoint("PUT", "/api/alerts/nonexistent/read", "Mark alert read 404", expected_status=404)
    test_endpoint("PUT", "/api/alerts/nonexistent/resolve", "Resolve alert 404", expected_status=404,
                  json_body={"resolved_by": "tester"})

    # ── 10. SETTINGS / CONFIG ──
    print("\n── 10. Settings & Config ──")
    test_endpoint("PUT", "/api/settings/detection-config", "Update detection config",
                  json_body={"yolo_confidence": 0.6, "frame_fps": 10})
    test_endpoint("PUT", "/api/settings/detection-config", "Invalid detector",
                  expected_status=400, json_body={"face_detector": "invalid_detector"})
    test_endpoint("PUT", "/api/settings/detection-config", "Invalid tracker",
                  expected_status=400, json_body={"face_tracker": "invalid_tracker"})
    # Reset config
    test_endpoint("PUT", "/api/settings/detection-config", "Reset config",
                  json_body={"yolo_confidence": 0.5, "frame_fps": 5})

    # ── 11. WEBSOCKET ──
    print("\n── 11. WebSocket Connectivity ──")
    test_websocket_connect("/ws/stats", "WS /ws/stats connect")
    if cam_id != "nonexistent":
        test_websocket_connect(f"/ws/stream/{cam_id}", f"WS /ws/stream/{cam_id} connect")
    test_websocket_connect("/ws/alerts", "WS /ws/alerts connect")

    # ── 12. STRESS TESTS ──
    print("\n── 12. Stress Tests (concurrent) ──")
    stress_results = []
    stress_results.append(stress_endpoint("GET", "/", "Root health", n=100))
    stress_results.append(stress_endpoint("GET", "/api/cameras", "List cameras", n=50))
    stress_results.append(stress_endpoint("GET", "/api/detections", "List detections", n=50, params={"per_page": 5}))
    stress_results.append(stress_endpoint("GET", "/api/stats/today", "Today stats", n=50))
    stress_results.append(stress_endpoint("GET", "/api/stats/hourly", "Hourly stats", n=50))
    stress_results.append(stress_endpoint("GET", "/api/stats/comparison", "Comparison stats", n=50))
    stress_results.append(stress_endpoint("GET", "/api/alerts", "List alerts", n=50))
    stress_results.append(stress_endpoint("GET", "/api/alerts/rules", "List rules", n=50))
    stress_results.append(stress_endpoint("GET", "/api/snapshots", "List snapshots", n=50))
    stress_results.append(stress_endpoint("GET", "/api/settings/system-info", "System info", n=30))
    stress_results.append(stress_endpoint("GET", "/api/settings/health", "Health check", n=50))

    # ── 13. CLEANUP ──
    print("\n── 13. Cleanup ──")
    for rid in CREATED_IDS["alert_rules"]:
        if rid:
            test_endpoint("DELETE", f"/api/alerts/rules/{rid}", f"Delete alert rule {rid[:8]}…")
    
    for cid in CREATED_IDS["cameras"]:
        if cid:
            test_endpoint("DELETE", f"/api/cameras/{cid}", f"Delete camera {cid[:8]}…", expected_status=204)
    
    # Also clean up extra cameras created during the direct requests
    resp = requests.get(f"{BASE}/api/cameras", timeout=10)
    if resp.status_code == 200:
        for c in resp.json():
            if "StressTest" in c.get("name", ""):
                requests.delete(f"{BASE}/api/cameras/{c['id']}", timeout=10)
    
    test_endpoint("DELETE", "/api/debug/clear-mock", "Clear mock data")

    # ── GENERATE REPORT ──
    print("\n" + "=" * 70)
    print("GENERATING REPORT...")
    
    passed = sum(1 for r in RESULTS if r.get("passed") == True)
    failed = sum(1 for r in RESULTS if r.get("passed") == False)
    skipped = sum(1 for r in RESULTS if r.get("passed") is None)
    total = len(RESULTS)
    
    report = {
        "timestamp": datetime.now().isoformat(),
        "base_url": BASE,
        "summary": {"total": total, "passed": passed, "failed": failed, "skipped": skipped},
        "functional_tests": [r for r in RESULTS if not r.get("name", "").startswith("STRESS")],
        "stress_tests": stress_results,
    }
    
    # Write JSON
    with open("stress_test_results.json", "w") as f:
        json.dump(report, f, indent=2, default=str)
    
    # Write Markdown
    md = generate_markdown(report, stress_results)
    # Write to project root
    result_path = r"c:\Users\ahmad\Downloads\face_surveillance\FaceSurveillance\result.md"
    with open(result_path, "w", encoding="utf-8") as f:
        f.write(md)
    
    print(f"\nResults written to: {result_path}")
    print(f"TOTAL: {total} | PASSED: {passed} | FAILED: {failed} | SKIPPED: {skipped}")
    print("=" * 70)


def generate_markdown(report, stress_results):
    s = report["summary"]
    ts = report["timestamp"]
    pass_rate = (s["passed"] / s["total"] * 100) if s["total"] > 0 else 0
    
    md = f"""# 🧪 Face Surveillance API — Stress Test Results

> **Date:** {ts}
> **Target:** {report["base_url"]}

---

## 📊 Summary

| Metric | Value |
|--------|-------|
| **Total Tests** | {s["total"]} |
| **Passed** | ✅ {s["passed"]} |
| **Failed** | ❌ {s["failed"]} |
| **Skipped** | ⏭️ {s["skipped"]} |
| **Pass Rate** | **{pass_rate:.1f}%** |

---

## 🔬 Functional Test Results

| # | Test Name | Method | Path | Status | Time (ms) | Result |
|---|-----------|--------|------|--------|-----------|--------|
"""
    for i, t in enumerate(report["functional_tests"], 1):
        icon = "✅" if t.get("passed") else ("⏭️" if t.get("passed") is None else "❌")
        path = t.get("path", "")
        if len(path) > 40:
            path = path[:37] + "…"
        time_ms = t.get("time_ms", 0)
        md += f"| {i} | {t['name']} | `{t.get('method','')}` | `{path}` | {t.get('status_code','-')} | {time_ms} | {icon} |\n"

    # Failed tests detail
    failed_tests = [t for t in report["functional_tests"] if t.get("passed") == False]
    if failed_tests:
        md += f"""
---

## ❌ Failed Tests Detail

"""
        for t in failed_tests:
            md += f"""### {t['name']}
- **Endpoint:** `{t.get('method','')} {t.get('path','')}`
- **Expected:** {t.get('expected','')} | **Got:** {t.get('status_code','')}
- **Error:** {t.get('error','')}
- **Response:** `{t.get('response_preview','')[:200]}`

"""

    # Stress test results
    md += """
---

## 🏋️ Stress Test Results (Concurrent Load)

| Endpoint | Requests | Success | Errors | Avg (ms) | Median (ms) | P95 (ms) | P99 (ms) | Min (ms) | Max (ms) | Result |
|----------|----------|---------|--------|----------|-------------|----------|----------|----------|----------|--------|
"""
    for st in stress_results:
        icon = "✅" if st.get("passed") else "❌"
        md += (f"| `{st.get('path','')}` | {st.get('requests',0)} | {st.get('success',0)} | "
               f"{st.get('errors',0)} | {st.get('avg_ms','N/A')} | {st.get('median_ms','N/A')} | "
               f"{st.get('p95_ms','N/A')} | {st.get('p99_ms','N/A')} | {st.get('min_ms','N/A')} | "
               f"{st.get('max_ms','N/A')} | {icon} |\n")

    # Performance analysis
    all_times = [t.get("time_ms", 0) for t in report["functional_tests"] if t.get("time_ms", 0) > 0]
    if all_times:
        md += f"""
---

## ⚡ Performance Analysis

| Metric | Value |
|--------|-------|
| **Fastest Response** | {min(all_times):.1f} ms |
| **Slowest Response** | {max(all_times):.1f} ms |
| **Average Response** | {statistics.mean(all_times):.1f} ms |
| **Median Response** | {statistics.median(all_times):.1f} ms |

### Response Time Distribution (Functional Tests)

| Range | Count |
|-------|-------|
| < 50ms | {sum(1 for t in all_times if t < 50)} |
| 50-100ms | {sum(1 for t in all_times if 50 <= t < 100)} |
| 100-500ms | {sum(1 for t in all_times if 100 <= t < 500)} |
| 500ms-1s | {sum(1 for t in all_times if 500 <= t < 1000)} |
| > 1s | {sum(1 for t in all_times if t >= 1000)} |
"""

    md += """
---

## 📋 Test Categories Covered

| Category | Tests | Description |
|----------|-------|-------------|
| Health Check | 3 | Root, /settings/health, /docs |
| System Info | 3 | Full info, hardware, models |
| Camera CRUD | ~12 | Create, read, update, delete + validation |
| Stream Control | ~5 | Start/stop stream, status checks |
| Mock Data | 2 | Generate + clear mock data |
| Detections | ~7 | List, filter by camera/emotion/gender/date |
| Snapshots | 3 | List, filter, pagination |
| Statistics | 5 | Today, hourly, comparison, per-camera |
| Alert Rules | ~6 | CRUD + validation |
| Alerts | ~8 | List, filter, mark read, resolve |
| Settings | 4 | Update config, validation, reset |
| WebSocket | 3 | /ws/stats, /ws/stream, /ws/alerts |
| Stress (concurrent) | 11 | 30-100 concurrent requests per endpoint |
| Cleanup | ~8 | Remove test data |

---

*Generated by automated stress test suite*
"""
    return md


if __name__ == "__main__":
    run_tests()
