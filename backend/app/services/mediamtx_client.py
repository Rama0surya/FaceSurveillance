"""
Client for MediaMTX REST API.

MediaMTX provides a management API (default port 9997) for querying
and configuring stream paths at runtime.

This client is used by the camera routes to:
  - Register camera RTSP sources as MediaMTX proxy paths
  - Check stream health and availability
  - Remove paths when streams are stopped

All methods are async and use httpx for HTTP calls.
"""

from __future__ import annotations

import logging
from typing import Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class MediaMTXClient:
    """Async client for the MediaMTX v3 REST API."""

    def __init__(self) -> None:
        self.base_url = getattr(settings, "MEDIAMTX_API_URL", "http://localhost:9997")

    # ------------------------------------------------------------------
    # Path queries
    # ------------------------------------------------------------------

    async def list_paths(self) -> list[dict]:
        """List all active paths/streams in MediaMTX."""
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{self.base_url}/v3/paths/list")
            r.raise_for_status()
            return r.json().get("items", [])

    async def get_path(self, name: str) -> Optional[dict]:
        """Get info for a single path.

        Returns ``None`` if the path does not exist.
        """
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{self.base_url}/v3/paths/get/{name}")
            if r.status_code == 200:
                return r.json()
            return None

    # ------------------------------------------------------------------
    # Path management
    # ------------------------------------------------------------------

    async def add_path(self, name: str, source: str) -> bool:
        """Upsert a path that proxies to an RTSP source.

        If the path already exists in MediaMTX (e.g. defined in the static
        config), the add is skipped gracefully — the existing stream keeps
        running untouched.

        Args:
            name: Path name (e.g. ``cam1``). Will be accessible at
                  ``rtsp://mediamtx:8554/<name>``.
            source: Original RTSP URL of the camera.

        Returns:
            ``True`` if the path is available (created or already existed).
        """
        async with httpx.AsyncClient(timeout=5) as client:
            # Check if path already exists (static config or previously added)
            check = await client.get(f"{self.base_url}/v3/config/paths/get/{name}")
            if check.status_code == 200:
                logger.info(
                    "MediaMTX path '%s' already exists, skipping add", name
                )
                return True

            # Path not found — create it dynamically
            r = await client.post(
                f"{self.base_url}/v3/config/paths/add/{name}",
                json={
                    "source": source,
                    "rtspTransport": "tcp",
                    "sourceOnDemand": False,
                },
            )
            if r.status_code == 200:
                logger.info("MediaMTX path '%s' added → source=%s", name, source)
                return True

            # 400 "path already exists" — race condition between check and add,
            # treat as success since the path is available.
            if r.status_code == 400 and "already exists" in r.text:
                logger.info(
                    "MediaMTX path '%s' already exists (race), skipping", name
                )
                return True

            logger.warning(
                "MediaMTX add_path '%s' failed: %s %s", name, r.status_code, r.text
            )
            return False

    async def edit_path(self, name: str, source: str) -> bool:
        """Update an existing path's source URL.

        Returns:
            ``True`` if the path was updated successfully.
        """
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.patch(
                f"{self.base_url}/v3/config/paths/edit/{name}",
                json={
                    "source": source,
                    "rtspTransport": "tcp",
                    "sourceOnDemand": False,
                },
            )
            if r.status_code == 200:
                logger.info("MediaMTX path '%s' updated → source=%s", name, source)
                return True
            logger.warning(
                "MediaMTX edit_path '%s' failed: %s %s", name, r.status_code, r.text
            )
            return False

    async def remove_path(self, name: str) -> bool:
        """Remove a dynamically-added path from MediaMTX.

        Paths defined in the static mediamtx.yml cannot be removed via the
        API — a 404 here is expected and logged at DEBUG level only.

        Returns:
            ``True`` if the path was removed, ``False`` if it did not exist
            or could not be removed.
        """
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.post(
                f"{self.base_url}/v3/config/paths/remove/{name}",
            )
            if r.status_code == 200:
                logger.info("MediaMTX path '%s' removed", name)
                return True

            if r.status_code == 404:
                # Path is defined in static config — nothing to remove dynamically
                logger.debug(
                    "MediaMTX path '%s' not in dynamic config, skipping remove", name
                )
                return False

            logger.warning(
                "MediaMTX remove_path '%s' failed: %s %s", name, r.status_code, r.text
            )
            return False

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    async def is_healthy(self) -> bool:
        """Check whether MediaMTX is running and responsive."""
        try:
            async with httpx.AsyncClient(timeout=3) as client:
                r = await client.get(f"{self.base_url}/v3/paths/list")
                return r.status_code == 200
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def get_proxied_rtsp_url(self, path_name: str) -> str:
        """Build the RTSP URL for reading a stream through MediaMTX.

        Example: ``rtsp://mediamtx:8554/cam_abc123``
        """
        rtsp_base = getattr(
            settings, "MEDIAMTX_RTSP_URL", "rtsp://localhost:8554"
        )
        return f"{rtsp_base}/{path_name}"


# Singleton instance
mediamtx_client = MediaMTXClient()