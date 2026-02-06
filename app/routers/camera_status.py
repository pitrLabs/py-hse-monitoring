from typing import Dict
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from app.auth import get_current_user
from app.models import User
from app.services.camera_status import (
    get_all_statuses,
    add_client,
    remove_client,
    send_snapshot,
)

router = APIRouter(prefix="/camera-status", tags=["camera-status"])


@router.get("/", response_model=Dict[str, dict])
def get_camera_statuses(
    current_user: User = Depends(get_current_user),
):
    """Get current snapshot of all camera statuses"""
    return get_all_statuses()


@router.websocket("/ws")
async def camera_status_websocket(websocket: WebSocket):
    """WebSocket endpoint for real-time camera status updates.

    On connect: sends full status snapshot.
    After that: pushes only changes (diff-based).
    """
    await websocket.accept()
    add_client(websocket)

    try:
        # Send initial snapshot
        await send_snapshot(websocket)

        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        pass
    finally:
        remove_client(websocket)
