import httpx
from app.config import settings

MEDIAMTX_API_URL = settings.mediamtx_api_url


async def add_stream_path(stream_name: str, rtsp_url: str) -> bool:
    """Add a new stream path to MediaMTX"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{MEDIAMTX_API_URL}/v3/config/paths/add/{stream_name}",
                json={
                    "source": rtsp_url,
                    "sourceProtocol": "tcp",
                    "sourceOnDemand": True,
                    "sourceOnDemandStartTimeout": "10s",
                    "sourceOnDemandCloseAfter": "10s"
                },
                timeout=10.0
            )
            return response.status_code in [200, 201]
    except Exception as e:
        print(f"Failed to add stream path {stream_name}: {e}")
        return False


async def update_stream_path(stream_name: str, rtsp_url: str) -> bool:
    """Update an existing stream path in MediaMTX"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.patch(
                f"{MEDIAMTX_API_URL}/v3/config/paths/patch/{stream_name}",
                json={
                    "source": rtsp_url,
                    "sourceProtocol": "tcp"
                },
                timeout=10.0
            )
            return response.status_code == 200
    except Exception as e:
        print(f"Failed to update stream path {stream_name}: {e}")
        return False


async def remove_stream_path(stream_name: str) -> bool:
    """Remove a stream path from MediaMTX"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.delete(
                f"{MEDIAMTX_API_URL}/v3/config/paths/delete/{stream_name}",
                timeout=10.0
            )
            return response.status_code in [200, 204]
    except Exception as e:
        print(f"Failed to remove stream path {stream_name}: {e}")
        return False


async def sync_all_paths(video_sources: list) -> dict:
    """Sync all video sources to MediaMTX"""
    results = {"added": 0, "failed": 0}
    for source in video_sources:
        if source.is_active:
            success = await add_stream_path(source.stream_name, source.url)
            if success:
                results["added"] += 1
            else:
                results["failed"] += 1
    return results
