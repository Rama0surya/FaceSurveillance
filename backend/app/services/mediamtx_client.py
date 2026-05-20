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

    async def list_paths(self) -> list[dict]:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{self.base_url}/v3/paths/list")
            r.raise_for_status()
            return r.json().get("items", [])

    async def get_path(self, name: str) -> Optional[dict]:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{self.base_url}/v3/paths/get/{name}")
            if r.status_code == 200:
                return r.json()
            return None

    async def add_path(self, name: str, source: str) -> bool:
        async with httpx.AsyncClient(timeout=5) as client:
            # Check if path already exists
            check = await client.get(f"{self.base_url}/v3/config/paths/get/{name}")
            if check.status_code == 200:
                logger.info("MediaMTX path '%s' already exists, skipping add", name)
                return True

            # Create dynamically — POST /add, bukan DELETE /delete
            r = await client.post(
                f"{self.base_url}/v3/config/paths/add/{name}",
                json={
                    "source": source,
                    "sourceOnDemand": False,
                    "record": False,
                },
            )
            if r.status_code in (200, 201):
                logger.info("MediaMTX path '%s' added → source=%s", name, source)
                return True

            if r.status_code == 400 and "already exists" in r.text:
                logger.info("MediaMTX path '%s' already exists (race), skipping", name)
                return True

            logger.warning("MediaMTX add_path '%s' failed: %s %s", name, r.status_code, r.text)
            return False

    async def edit_path(self, name: str, source: str) -> bool:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.patch(
                f"{self.base_url}/v3/config/paths/edit/{name}",
                json={
                    "source": source,
                    "sourceOnDemand": False,
                    "record": False,
                },
            )
            if r.status_code == 200:
                logger.info("MediaMTX path '%s' updated → source=%s", name, source)
                return True
            logger.warning("MediaMTX edit_path '%s' failed: %s %s", name, r.status_code, r.text)
            return False

    async def remove_path(self, name: str) -> bool:
        # Fix: DELETE /delete bukan POST /remove
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.delete(
                f"{self.base_url}/v3/config/paths/delete/{name}",
            )
            if r.status_code in (200, 204):
                logger.info("MediaMTX path '%s' removed", name)
                return True

            if r.status_code == 404:
                logger.debug("MediaMTX path '%s' not in dynamic config, skipping remove", name)
                return False

            logger.warning("MediaMTX remove_path '%s' failed: %s %s", name, r.status_code, r.text)
            return False

    async def is_healthy(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=3) as client:
                r = await client.get(f"{self.base_url}/v3/paths/list")
                return r.status_code == 200
        except Exception:
            return False

    def get_proxied_rtsp_url(self, path_name: str) -> str:
        rtsp_base = getattr(settings, "MEDIAMTX_RTSP_URL", "rtsp://localhost:8554")
        return f"{rtsp_base}/{path_name}"

    def get_hls_url(self, path_name: str) -> str:
        """URL HLS untuk browser — pakai MEDIAMTX_HLS_URL dari env."""
        hls_base = getattr(settings, "MEDIAMTX_HLS_URL", "http://localhost:8888")
        return f"{hls_base}/{path_name}/index.m3u8"


mediamtx_client = MediaMTXClient()