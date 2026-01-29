"""
AI Tasks Router
Manages AI detection tasks in BM-APP
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from app.auth import get_current_user, get_current_superuser
from app.models import User
from app.config import settings
from app.services.bmapp_client import get_bmapp_client

router = APIRouter(prefix="/ai-tasks", tags=["AI Tasks"])


class AITaskCreate(BaseModel):
    """Create AI task request"""
    task_name: str
    media_name: str
    algorithms: List[int]  # List of algorithm IDs (e.g., [195, 5] for helmet + vest)
    description: Optional[str] = ""


class AITaskControl(BaseModel):
    """Control AI task request"""
    action: str  # "start" or "stop"


@router.get("/")
async def list_ai_tasks(
    current_user: User = Depends(get_current_user)
):
    """Get all AI tasks from BM-APP."""
    if not settings.bmapp_enabled:
        return {"tasks": [], "bmapp_disabled": True}

    try:
        client = get_bmapp_client()
        tasks = await client.get_task_list()
        return {"tasks": tasks}
    except Exception as e:
        print(f"Failed to get AI tasks: {e}")
        return {"tasks": [], "error": str(e)}


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_ai_task(
    task_data: AITaskCreate,
    current_user: User = Depends(get_current_superuser)
):
    """Create a new AI task in BM-APP. Only for superusers."""
    if not settings.bmapp_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="BM-APP integration is disabled"
        )

    try:
        client = get_bmapp_client()
        result = await client.create_task(
            task_session=task_data.task_name,
            media_name=task_data.media_name,
            alg_info=[1],  # Person detection category (most common)
            method_config=task_data.algorithms,
            task_desc=task_data.description or ""
        )
        return {"message": "Task created successfully", "result": result}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.delete("/{task_name}")
async def delete_ai_task(
    task_name: str,
    current_user: User = Depends(get_current_superuser)
):
    """Delete an AI task from BM-APP. Only for superusers."""
    if not settings.bmapp_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="BM-APP integration is disabled"
        )

    try:
        client = get_bmapp_client()
        result = await client.delete_task(task_name)
        return {"message": "Task deleted successfully", "result": result}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/{task_name}/control")
async def control_ai_task(
    task_name: str,
    control: AITaskControl,
    current_user: User = Depends(get_current_superuser)
):
    """Start or stop an AI task. Only for superusers."""
    if not settings.bmapp_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="BM-APP integration is disabled"
        )

    if control.action not in ["start", "stop"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Action must be 'start' or 'stop'"
        )

    try:
        client = get_bmapp_client()
        result = await client.control_task(task_name, control.action)
        return {"message": f"Task {control.action}ed successfully", "result": result}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/abilities")
async def get_ai_abilities(
    current_user: User = Depends(get_current_user)
):
    """Get all available AI detection algorithms."""
    if not settings.bmapp_enabled:
        return {"abilities": []}

    try:
        client = get_bmapp_client()
        abilities = await client.get_abilities()

        # Simplify the response for frontend
        simplified = []
        for ability in abilities:
            simplified.append({
                "id": ability.get("item"),
                "code": ability.get("code"),
                "name": ability.get("name"),
                "description": ability.get("desc", ability.get("detail", "")),
                "parameters": ability.get("parameters", [])
            })

        return {"abilities": simplified}
    except Exception as e:
        print(f"Failed to get abilities: {e}")
        return {"abilities": []}


@router.get("/media")
async def get_bmapp_media(
    current_user: User = Depends(get_current_user)
):
    """Get all media/cameras from BM-APP with their status."""
    if not settings.bmapp_enabled:
        return {"media": []}

    try:
        client = get_bmapp_client()
        media_list = await client.get_media_list()

        # Simplify the response
        simplified = []
        for media in media_list:
            status_info = media.get("MediaStatus", {})
            simplified.append({
                "name": media.get("MediaName"),
                "url": media.get("MediaUrl"),
                "description": media.get("MediaDesc", ""),
                "status": status_info.get("label", "Unknown"),
                "status_type": status_info.get("type", 0),
                "status_style": status_info.get("style", ""),
                "resolution": status_info.get("size", {})
            })

        return {"media": simplified}
    except Exception as e:
        print(f"Failed to get media: {e}")
        return {"media": []}


@router.get("/streams")
async def get_available_streams(
    current_user: User = Depends(get_current_user)
):
    """Get all available WebRTC streams from ZLMediaKit.
    This helps debug which streams are actually available for playback."""
    if not settings.bmapp_enabled:
        # Return empty list instead of error for graceful degradation
        return {"streams": []}

    try:
        client = get_bmapp_client()
        streams = await client.get_zlmediakit_streams()

        # Simplify the response
        simplified = []
        for stream in streams:
            simplified.append({
                "app": stream.get("app"),
                "stream": stream.get("stream"),
                "schema": stream.get("schema"),
                "vhost": stream.get("vhost", "__defaultVhost__"),
                "tracks": stream.get("tracks", []),
                "readers": stream.get("readerCount", 0)
            })

        return {"streams": simplified}
    except Exception as e:
        # Return empty list on error for graceful degradation
        print(f"Failed to get streams: {e}")
        return {"streams": []}


@router.get("/preview-channels")
async def get_preview_channels(
    current_user: User = Depends(get_current_user)
):
    """Get preview channels from BM-APP for video streaming.
    Returns ChnGroup (channel groups) and TaskGroup (task groups).
    This is the raw data used by BM-APP native UI for video preview."""
    if not settings.bmapp_enabled:
        return {"channels": {}}

    try:
        client = get_bmapp_client()
        channels = await client.get_preview_channels()
        return {"channels": channels}
    except Exception as e:
        print(f"Failed to get preview channels: {e}")
        return {"channels": {}, "error": str(e)}
