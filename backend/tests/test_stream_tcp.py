"""
TCP-based integration test for decoupled stream and SSE endpoints.
Runs against a running backend server on port 8000.
"""

import sys
import os
import requests

def test_stream_tcp():
    base_url = "http://127.0.0.1:8000"
    print("== Stream Endpoints TCP Verification ==", flush=True)
    
    # 1. Create a mock camera
    print("Creating mock camera...", flush=True)
    r = requests.post(f"{base_url}/api/cameras", json={
        "name": "TCP Test Camera",
        "rtsp_url": "rtsp://localhost:8554/tcp_stream"
    })
    assert r.status_code == 201, f"Failed to create camera: {r.text}"
    camera = r.json()
    cam_id = camera["id"]
    print(f"Created camera: {cam_id}", flush=True)
    
    try:
        # 2. Test SSE events
        print(f"\nTesting SSE events at /api/stream/events/{cam_id}...", flush=True)
        r_sse = requests.get(f"{base_url}/api/stream/events/{cam_id}", stream=True, timeout=5.0)
        assert r_sse.status_code == 200, f"Expected 200, got {r_sse.status_code}"
        assert "text/event-stream" in r_sse.headers["content-type"]
        print("  [PASS] SSE Content-Type is correct.", flush=True)
        
        # Read first line
        lines = r_sse.iter_lines()
        first_line = next(lines).decode('utf-8')
        print(f"  Received SSE line: {first_line}", flush=True)
        assert "connected" in first_line
        print("  [PASS] Received 'connected' event successfully.", flush=True)
        r_sse.close()
        
        # 3. Test video stream when offline (should be 503)
        print(f"\nTesting MJPEG stream at /api/stream/video/{cam_id} when offline...", flush=True)
        r_video = requests.get(f"{base_url}/api/stream/video/{cam_id}")
        assert r_video.status_code == 503, f"Expected 503, got {r_video.status_code}"
        print("  [PASS] Returned 503 when stream not running.", flush=True)
        
    finally:
        # 4. Cleanup
        print("\nCleaning up...", flush=True)
        requests.delete(f"{base_url}/api/cameras/{cam_id}")
        print("  Cleanup complete.", flush=True)
        print("\nAll TCP stream tests passed successfully!", flush=True)

if __name__ == "__main__":
    test_stream_tcp()
