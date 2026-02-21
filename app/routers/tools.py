"""
Tools Router
Network diagnostics, ONVIF discovery, system info, and admin operations per AI Box.
"""
from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import get_current_user, get_current_superuser
from app.database import get_db
from app.models import User, AIBox
from app.schemas import PingRequest, PingResult, OnvifDevice, SystemInfo
from app.config import settings

router = APIRouter(prefix="/tools", tags=["tools"])


@router.post("/ping/{aibox_id}", response_model=PingResult)
async def ping_host(
    aibox_id: UUID,
    data: PingRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Ping a network address via the AI Box"""
    if not settings.bmapp_enabled:
        raise HTTPException(status_code=400, detail="BM-APP integration is disabled")
    aibox = db.query(AIBox).filter(AIBox.id == aibox_id).first()
    if not aibox:
        raise HTTPException(status_code=404, detail="AI Box not found")

    from app.services.bmapp_client import ping_on_aibox
    result = await ping_on_aibox(aibox.api_url, data.host, data.count)

    if result.get("status") == "error":
        return PingResult(host=data.host, success=False, error=result.get("message"))

    content = result.get("result", {}).get("Content", {})
    output = content.get("Output") or content.get("output") or str(result.get("result", ""))
    return PingResult(host=data.host, success=True, output=output)


@router.post("/discover-onvif/{aibox_id}", response_model=List[OnvifDevice])
async def discover_onvif(
    aibox_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Discover ONVIF cameras on the AI Box network"""
    if not settings.bmapp_enabled:
        raise HTTPException(status_code=400, detail="BM-APP integration is disabled")
    aibox = db.query(AIBox).filter(AIBox.id == aibox_id).first()
    if not aibox:
        raise HTTPException(status_code=404, detail="AI Box not found")

    from app.services.bmapp_client import discover_onvif_on_aibox
    result = await discover_onvif_on_aibox(aibox.api_url)

    if result.get("status") == "error":
        raise HTTPException(status_code=502, detail=result.get("message", "Discovery failed"))

    devices = []
    for item in result.get("devices", []):
        devices.append(OnvifDevice(
            ip=item.get("Ip") or item.get("ip", ""),
            port=item.get("Port") or item.get("port", 80),
            manufacturer=item.get("Manufacturer") or item.get("manufacturer"),
            model=item.get("Model") or item.get("model"),
            name=item.get("Name") or item.get("name"),
            profiles=item.get("Profiles") or item.get("profiles"),
            extra_data=item,
        ))
    return devices


@router.get("/system-info/{aibox_id}", response_model=SystemInfo)
async def get_system_info(
    aibox_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get system information from AI Box"""
    if not settings.bmapp_enabled:
        raise HTTPException(status_code=400, detail="BM-APP integration is disabled")
    aibox = db.query(AIBox).filter(AIBox.id == aibox_id).first()
    if not aibox:
        raise HTTPException(status_code=404, detail="AI Box not found")

    from app.services.bmapp_client import get_system_info_from_aibox
    result = await get_system_info_from_aibox(aibox.api_url)

    if result.get("status") == "error":
        raise HTTPException(status_code=502, detail=result.get("message", "Failed to get system info"))

    content = result.get("content", {})
    return SystemInfo(
        cpu_usage=content.get("CpuUsage") or content.get("cpu_usage"),
        memory_usage=content.get("MemUsage") or content.get("memory_usage"),
        disk_usage=content.get("DiskUsage") or content.get("disk_usage"),
        uptime=str(content.get("Uptime") or content.get("uptime") or ""),
        version=content.get("Version") or content.get("version"),
        extra_data=content,
    )


@router.post("/restart-service/{aibox_id}")
async def restart_service(
    aibox_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    """Restart the BM-APP service on AI Box"""
    if not settings.bmapp_enabled:
        raise HTTPException(status_code=400, detail="BM-APP integration is disabled")
    aibox = db.query(AIBox).filter(AIBox.id == aibox_id).first()
    if not aibox:
        raise HTTPException(status_code=404, detail="AI Box not found")

    from app.services.bmapp_client import BmAppClient
    client = BmAppClient()
    client.base_url = aibox.api_url.rstrip('/')
    try:
        result = await client._request("/app_restart_service")
        return {"success": True, "result": result}
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/reset-factory/{aibox_id}")
async def factory_reset(
    aibox_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    """Factory reset AI Box (superadmin only - DESTRUCTIVE)"""
    if not settings.bmapp_enabled:
        raise HTTPException(status_code=400, detail="BM-APP integration is disabled")
    aibox = db.query(AIBox).filter(AIBox.id == aibox_id).first()
    if not aibox:
        raise HTTPException(status_code=404, detail="AI Box not found")

    from app.services.bmapp_client import reset_aibox
    result = await reset_aibox(aibox.api_url)

    if result.get("status") == "error":
        raise HTTPException(status_code=502, detail=result.get("message", "Reset failed"))

    return {"success": True, "message": "Factory reset initiated", "result": result.get("result")}


@router.get("/logs/{aibox_id}")
async def get_logs(
    aibox_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    """Get recent logs from AI Box"""
    if not settings.bmapp_enabled:
        raise HTTPException(status_code=400, detail="BM-APP integration is disabled")
    aibox = db.query(AIBox).filter(AIBox.id == aibox_id).first()
    if not aibox:
        raise HTTPException(status_code=404, detail="AI Box not found")

    from app.services.bmapp_client import BmAppClient
    client = BmAppClient()
    client.base_url = aibox.api_url.rstrip('/')
    try:
        result = await client._request("/app_get_logs")
        content = result.get("Content", [])
        if isinstance(content, list):
            return {"logs": content}
        return {"logs": [str(content)]}
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
