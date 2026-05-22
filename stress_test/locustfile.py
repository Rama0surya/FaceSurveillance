"""
Locust load test for Face Surveillance API endpoints.

Simulates realistic dashboard user behavior — camera list refreshes,
detection polling, stats queries, and stream status checks.

Usage:
    pip install locust

    # Interactive mode (browser UI at http://localhost:8089)
    locust -f locustfile.py --host http://localhost:8000

    # Headless mode (CI/CD):
    locust -f locustfile.py \\
        --host http://localhost:8000 \\
        --users 100 --spawn-rate 10 --run-time 5m \\
        --headless --csv locust_report
"""

from locust import HttpUser, task, between


class SurveillanceAPIUser(HttpUser):
    """Simulates a dashboard user hitting various API endpoints.

    Task weights model realistic usage patterns:
      - Camera list:    checked frequently (sidebar refresh)
      - Detections:     polled regularly (main view)
      - Stats:          periodic updates (charts)
      - Alerts:         less frequent (notification panel)
      - System info:    rare (settings page)
    """

    wait_time = between(0.5, 2.0)  # Random wait between requests

    def on_start(self):
        """Cache camera IDs on start for stream status checks."""
        self._camera_ids = self._fetch_camera_ids()

    def _fetch_camera_ids(self) -> list:
        """Helper: fetch camera IDs from API."""
        try:
            with self.client.get(
                "/api/cameras", name="/api/cameras [helper]", catch_response=True
            ) as resp:
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, list):
                        return [c["id"] for c in data if "id" in c]
                resp.success()  # Don't count helper call as failure
        except Exception:
            pass
        return []

    # ---- High frequency tasks (weight=5) ----

    @task(5)
    def get_cameras(self):
        """Dashboard sidebar: camera list refresh."""
        self.client.get("/api/cameras", name="/api/cameras")

    # ---- Medium frequency tasks (weight=3) ----

    @task(3)
    def get_detections(self):
        """Main view: recent detections list."""
        self.client.get("/api/detections?limit=50", name="/api/detections")

    @task(3)
    def get_stats_today(self):
        """Dashboard: today's aggregate stats."""
        self.client.get("/api/stats/today", name="/api/stats/today")

    # ---- Lower frequency tasks (weight=2) ----

    @task(2)
    def get_stats_hourly(self):
        """Charts: hourly breakdown."""
        self.client.get("/api/stats/hourly", name="/api/stats/hourly")

    @task(2)
    def get_snapshots(self):
        """Gallery: recent face snapshots."""
        self.client.get(
            "/api/detections/snapshots?limit=20", name="/api/detections/snapshots"
        )

    # ---- Low frequency tasks (weight=1) ----

    @task(1)
    def get_alerts(self):
        """Notification panel: alert list."""
        self.client.get("/api/alerts", name="/api/alerts")

    @task(1)
    def get_alert_rules(self):
        """Settings: alert rules configuration."""
        self.client.get("/api/alerts/rules", name="/api/alerts/rules")

    @task(1)
    def health_check(self):
        """Periodic health ping."""
        self.client.get("/", name="/ [health]")

    @task(1)
    def get_system_info(self):
        """Settings page: system info (expensive endpoint)."""
        self.client.get(
            "/api/settings/system-info", name="/api/settings/system-info"
        )

    @task(1)
    def get_stream_status(self):
        """Stream health indicator: per-camera status."""
        if self._camera_ids:
            cam = self._camera_ids[0]
            self.client.get(
                f"/api/stream/status/{cam}",
                name="/api/stream/status/[id]",
            )

    @task(1)
    def get_pipeline_toggles(self):
        """Settings: read pipeline toggle state."""
        self.client.get(
            "/api/settings/pipeline-toggles",
            name="/api/settings/pipeline-toggles",
        )

    @task(1)
    def get_detection_config(self):
        """Settings: read detection configuration."""
        self.client.get(
            "/api/settings/detection-config",
            name="/api/settings/detection-config",
        )
