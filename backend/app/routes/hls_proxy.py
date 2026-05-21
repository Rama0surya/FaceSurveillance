# app/routes/hls_proxy.py
import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/hls", tags=["hls"])

MEDIAMTX_HLS = "http://mediamtx:8888"

@router.get("/{path:path}")
async def proxy_hls(path: str):
    """
    Proxy HLS stream dari MediaMTX ke browser.
    Browser akses: GET /hls/{camera_path}/index.m3u8
    """
    url = f"{MEDIAMTX_HLS}/{path}"
    
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(url)
            if r.status_code != 200:
                raise HTTPException(status_code=r.status_code, detail="Stream not found")
            
            # Tentukan content-type berdasarkan file
            if path.endswith(".m3u8"):
                media_type = "application/vnd.apple.mpegurl"
            elif path.endswith(".ts"):
                media_type = "video/mp2t"
            else:
                media_type = "application/octet-stream"
            
            return StreamingResponse(
                iter([r.content]),
                media_type=media_type,
                headers={
                    "Cache-Control": "no-cache",
                    "Access-Control-Allow-Origin": "*",
                },
            )
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="MediaMTX not reachable")