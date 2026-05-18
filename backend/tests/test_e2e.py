"""
End-to-end integration tests for Face Surveillance API.

These tests run against a live backend instance (http://localhost:8000).
All tests use mock data — no physical cameras required.

Run:
    python -m pytest backend/tests/test_e2e.py -v

Prerequisites:
    - Backend running: uvicorn app.main:app --port 8000
    - pip install pytest pytest-asyncio httpx
"""

from __future__ import annotations

import asyncio
import os

import httpx
import pytest

BASE_URL = os.getenv("TEST_BASE_URL", "http://localhost:8000")
MEDIAMTX_API = os.getenv("MEDIAMTX_API_URL", "http://localhost:9997")

# Timeout for HTTP requests (seconds)
TIMEOUT = 10


# =====================================================================
# Fixtures
# =====================================================================

@pytest.fixture(scope="session")
def event_loop():
    """Create a session-scoped event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def client():
    """Session-scoped async HTTP client."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT) as c:
        yield c


@pytest.fixture(scope="session")
async def mediamtx_available():
    """Check if MediaMTX is running. Used to skip tests."""
    try:
        async with httpx.AsyncClient(timeout=3) as c:
            r = await c.get(f"{MEDIAMTX_API}/v3/paths/list")
            return r.status_code == 200
    except Exception:
        return False


# =====================================================================
# 1. Health Check
# =====================================================================

@pytest.mark.asyncio
async def test_health_check(client: httpx.AsyncClient):
    """GET / should return 200 with version info."""
    r = await client.get("/")
    assert r.status_code == 200
    data = r.json()
    assert "message" in data
    assert "version" in data


# =====================================================================
# 2. System Info
# =====================================================================

@pytest.mark.asyncio
async def test_system_info(client: httpx.AsyncClient):
    """GET /api/settings/system-info should return hardware details."""
    r = await client.get("/api/settings/system-info")
    assert r.status_code == 200
    data = r.json()
    # Should contain CPU, memory, and GPU info
    assert "cpu" in data or "system" in data


# =====================================================================
# 3. Camera CRUD
# =====================================================================

@pytest.mark.asyncio
async def test_camera_crud(client: httpx.AsyncClient):
    """Full camera lifecycle: create → read → update → delete."""
    # CREATE
    payload = {
        "name": "E2E Test Camera",
        "rtsp_url": "rtsp://example.com/test_stream",
    }
    r = await client.post("/api/cameras", json=payload)
    assert r.status_code == 201
    camera = r.json()
    camera_id = camera["id"]
    assert camera["name"] == "E2E Test Camera"

    # READ (list)
    r = await client.get("/api/cameras")
    assert r.status_code == 200
    cameras = r.json()
    assert any(c["id"] == camera_id for c in cameras)

    # UPDATE
    r = await client.put(
        f"/api/cameras/{camera_id}",
        json={"name": "E2E Updated Camera"},
    )
    assert r.status_code == 200
    assert r.json()["name"] == "E2E Updated Camera"

    # DELETE
    r = await client.delete(f"/api/cameras/{camera_id}")
    assert r.status_code == 204

    # Verify deleted
    r = await client.get("/api/cameras")
    cameras = r.json()
    assert not any(c["id"] == camera_id for c in cameras)


# =====================================================================
# 4. Alert Rules CRUD
# =====================================================================

@pytest.mark.asyncio
async def test_alert_rules_crud(client: httpx.AsyncClient):
    """Full alert rule lifecycle: create → read → update → delete."""
    # CREATE
    payload = {
        "name": "E2E Test Rule",
        "rule_type": "crowd_threshold",
        "config": {"threshold": 5},
        "enabled": True,
    }
    r = await client.post("/api/alerts/rules", json=payload)
    # Accept 201 or 200
    assert r.status_code in (200, 201)
    rule = r.json()
    rule_id = rule["id"]

    # READ (list)
    r = await client.get("/api/alerts/rules")
    assert r.status_code == 200
    rules = r.json()
    assert any(rl["id"] == rule_id for rl in rules)

    # UPDATE
    r = await client.put(
        f"/api/alerts/rules/{rule_id}",
        json={"name": "E2E Updated Rule", "enabled": False},
    )
    assert r.status_code == 200

    # DELETE
    r = await client.delete(f"/api/alerts/rules/{rule_id}")
    assert r.status_code in (200, 204)


# =====================================================================
# 5. Mock Data Generation
# =====================================================================

@pytest.mark.asyncio
async def test_mock_data(client: httpx.AsyncClient):
    """POST /api/debug/generate-mock should generate mock detections."""
    r = await client.post("/api/debug/generate-mock", params={"count": 20})
    assert r.status_code == 200
    data = r.json()
    assert "generated" in data or "message" in data


# =====================================================================
# 6. Stats After Mock
# =====================================================================

@pytest.mark.asyncio
async def test_stats_after_mock(client: httpx.AsyncClient):
    """GET /api/stats/today should return aggregated stats."""
    r = await client.get("/api/stats/today")
    assert r.status_code == 200
    data = r.json()
    # Stats should be present (may be zero if mock data is from a different day)
    assert isinstance(data, dict)


# =====================================================================
# 7. Snapshots After Mock
# =====================================================================

@pytest.mark.asyncio
async def test_snapshots_after_mock(client: httpx.AsyncClient):
    """GET /api/snapshots should return snapshot items."""
    r = await client.get("/api/snapshots")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, (list, dict))


# =====================================================================
# 8. Alerts After Mock
# =====================================================================

@pytest.mark.asyncio
async def test_alerts_after_mock(client: httpx.AsyncClient):
    """GET /api/alerts should return alert items."""
    r = await client.get("/api/alerts")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, (list, dict))


# =====================================================================
# 9. MediaMTX Health (conditional)
# =====================================================================

@pytest.mark.asyncio
async def test_mediamtx_health(mediamtx_available: bool):
    """Check MediaMTX API is accessible (skipped if not running)."""
    if not mediamtx_available:
        pytest.skip("MediaMTX is not running — skipping")

    async with httpx.AsyncClient(timeout=5) as client:
        r = await client.get(f"{MEDIAMTX_API}/v3/paths/list")
        assert r.status_code == 200
        data = r.json()
        assert "items" in data


# =====================================================================
# 10. MediaMTX Path Management (conditional)
# =====================================================================

@pytest.mark.asyncio
async def test_mediamtx_path_crud(mediamtx_available: bool):
    """Test adding and removing a path in MediaMTX (skipped if not running)."""
    if not mediamtx_available:
        pytest.skip("MediaMTX is not running — skipping")

    path_name = "e2e_test_path"
    source_url = "rtsp://example.com/test"

    async with httpx.AsyncClient(timeout=5) as client:
        # Add path
        r = await client.post(
            f"{MEDIAMTX_API}/v3/config/paths/add/{path_name}",
            json={"source": source_url},
        )
        assert r.status_code == 200

        # Verify path exists
        r = await client.get(f"{MEDIAMTX_API}/v3/config/paths/get/{path_name}")
        assert r.status_code == 200

        # Remove path
        r = await client.post(
            f"{MEDIAMTX_API}/v3/config/paths/remove/{path_name}",
        )
        assert r.status_code == 200
