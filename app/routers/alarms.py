import json
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, Request
from sqlalchemy import desc, and_
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Alarm, User
from app.schemas import AlarmCreate, AlarmResponse, AlarmUpdate
from app.auth import get_current_user
from app.services.bmapp import add_client, remove_client, broadcast_alarm, BmAppAlarmListener

router = APIRouter(prefix="/alarms", tags=["alarms"])


@router.get("/", response_model=List[AlarmResponse])
def get_alarms(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    alarm_type: Optional[str] = None,
    camera_id: Optional[str] = None,
    status: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all alarms with optional filters"""
    query = db.query(Alarm)

    filters = []
    if alarm_type:
        filters.append(Alarm.alarm_type == alarm_type)
    if camera_id:
        filters.append(Alarm.camera_id == camera_id)
    if status:
        filters.append(Alarm.status == status)
    if start_date:
        filters.append(Alarm.alarm_time >= start_date)
    if end_date:
        filters.append(Alarm.alarm_time <= end_date)

    if filters:
        query = query.filter(and_(*filters))

    alarms = query.order_by(desc(Alarm.alarm_time)).offset(skip).limit(limit).all()
    return alarms


@router.get("/stats")
def get_alarm_stats(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get alarm statistics"""
    query = db.query(Alarm)

    if start_date:
        query = query.filter(Alarm.alarm_time >= start_date)
    if end_date:
        query = query.filter(Alarm.alarm_time <= end_date)

    total = query.count()
    new_count = query.filter(Alarm.status == "new").count()
    acknowledged_count = query.filter(Alarm.status == "acknowledged").count()
    resolved_count = query.filter(Alarm.status == "resolved").count()

    # Get count by type
    from sqlalchemy import func
    type_stats = db.query(
        Alarm.alarm_type,
        func.count(Alarm.id).label("count")
    ).group_by(Alarm.alarm_type).all()

    return {
        "total": total,
        "new": new_count,
        "acknowledged": acknowledged_count,
        "resolved": resolved_count,
        "by_type": {t.alarm_type: t.count for t in type_stats}
    }


@router.get("/{alarm_id}", response_model=AlarmResponse)
def get_alarm(
    alarm_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a specific alarm by ID"""
    alarm = db.query(Alarm).filter(Alarm.id == alarm_id).first()
    if not alarm:
        raise HTTPException(status_code=404, detail="Alarm not found")
    return alarm


@router.patch("/{alarm_id}/acknowledge", response_model=AlarmResponse)
def acknowledge_alarm(
    alarm_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Acknowledge an alarm"""
    alarm = db.query(Alarm).filter(Alarm.id == alarm_id).first()
    if not alarm:
        raise HTTPException(status_code=404, detail="Alarm not found")

    alarm.status = "acknowledged"
    alarm.acknowledged_at = datetime.utcnow()
    alarm.acknowledged_by_id = current_user.id
    db.commit()
    db.refresh(alarm)
    return alarm


@router.patch("/{alarm_id}/resolve", response_model=AlarmResponse)
def resolve_alarm(
    alarm_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Resolve an alarm"""
    alarm = db.query(Alarm).filter(Alarm.id == alarm_id).first()
    if not alarm:
        raise HTTPException(status_code=404, detail="Alarm not found")

    alarm.status = "resolved"
    alarm.resolved_at = datetime.utcnow()
    alarm.resolved_by_id = current_user.id
    db.commit()
    db.refresh(alarm)
    return alarm


@router.delete("/{alarm_id}")
def delete_alarm(
    alarm_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete an alarm"""
    alarm = db.query(Alarm).filter(Alarm.id == alarm_id).first()
    if not alarm:
        raise HTTPException(status_code=404, detail="Alarm not found")

    db.delete(alarm)
    db.commit()
    return {"message": "Alarm deleted"}


@router.post("/bulk-acknowledge")
def bulk_acknowledge(
    alarm_ids: List[UUID],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Acknowledge multiple alarms"""
    now = datetime.utcnow()
    updated = db.query(Alarm).filter(Alarm.id.in_(alarm_ids)).update({
        "status": "acknowledged",
        "acknowledged_at": now,
        "acknowledged_by_id": current_user.id
    }, synchronize_session=False)
    db.commit()
    return {"acknowledged": updated}


@router.post("/bulk-resolve")
def bulk_resolve(
    alarm_ids: List[UUID],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Resolve multiple alarms"""
    now = datetime.utcnow()
    updated = db.query(Alarm).filter(Alarm.id.in_(alarm_ids)).update({
        "status": "resolved",
        "resolved_at": now,
        "resolved_by_id": current_user.id
    }, synchronize_session=False)
    db.commit()
    return {"resolved": updated}


@router.websocket("/ws")
async def alarm_websocket(websocket: WebSocket):
    """WebSocket endpoint for real-time alarm updates"""
    await websocket.accept()
    add_client(websocket)

    try:
        while True:
            # Keep connection alive, receive any client messages
            data = await websocket.receive_text()
            # Client can send ping or commands
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        pass
    finally:
        remove_client(websocket)


# Internal function to save alarm from BM-APP
async def save_alarm_from_bmapp(alarm_data: dict, db: Session):
    """Save an alarm received from BM-APP to database"""
    from dateutil.parser import parse as parse_datetime

    alarm_time = alarm_data.get("alarm_time")
    if isinstance(alarm_time, str):
        try:
            alarm_time = parse_datetime(alarm_time)
        except:
            alarm_time = datetime.utcnow()

    alarm = Alarm(
        bmapp_id=alarm_data.get("bmapp_id"),
        alarm_type=alarm_data.get("alarm_type", "Unknown"),
        alarm_name=alarm_data.get("alarm_name", "Detection Alert"),
        camera_id=alarm_data.get("camera_id"),
        camera_name=alarm_data.get("camera_name"),
        location=alarm_data.get("location"),
        confidence=float(alarm_data.get("confidence", 0) or 0),
        image_url=alarm_data.get("image_url"),
        video_url=alarm_data.get("video_url"),
        description=alarm_data.get("description"),
        raw_data=alarm_data.get("raw_data"),
        alarm_time=alarm_time,
        status="new"
    )
    db.add(alarm)
    db.commit()
    return alarm


@router.post("/test", response_model=AlarmResponse)
async def create_test_alarm(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a test alarm to verify the system is working"""
    import uuid

    test_alarm_data = {
        "bmapp_id": str(uuid.uuid4()),
        "alarm_type": "NoHelmet",
        "alarm_name": "No Helmet Detected",
        "camera_id": "cam_01",
        "camera_name": "Front Gate Camera",
        "location": "Main Entrance - Zone A",
        "confidence": 0.92,
        "image_url": "",
        "video_url": "",
        "description": "Worker detected without safety helmet in restricted area",
        "alarm_time": datetime.utcnow().isoformat()
    }

    alarm = await save_alarm_from_bmapp(test_alarm_data, db)
    return alarm


@router.post("/simulate-bmapp")
async def simulate_bmapp_alarm(
    raw_data: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Simulate receiving an alarm from BM-APP to test parsing.

    Send BM-APP format:
    {
        "AlarmId": "uuid",
        "TaskSession": "task_001",
        "TaskDesc": "Helmet Detection",
        "Time": "2024-01-15 10:30:00",
        "Media": {
            "MediaName": "1",
            "MediaDesc": "Front Gate"
        },
        "Result": {
            "Type": "NoHelmet",
            "Description": "No helmet detected"
        }
    }
    """
    # Use the same parsing logic as the listener
    listener = BmAppAlarmListener()
    parsed = listener._parse_alarm(raw_data)

    # Save to database
    alarm = await save_alarm_from_bmapp(parsed, db)

    return {
        "message": "Alarm simulated successfully",
        "raw_input": raw_data,
        "parsed_output": parsed,
        "saved_alarm_id": str(alarm.id)
    }


# ============================================================================
# BM-APP HTTP REPORTING ENDPOINT (NO AUTH - Called directly by BM-APP device)
# ============================================================================

@router.post("/receive")
async def receive_bmapp_alarm(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Receive alarm from BM-APP via HTTP POST.

    This endpoint is called by BM-APP when MetadataUrl is configured.
    NO AUTHENTICATION required because BM-APP device cannot login.

    Configure in BM-APP task:
        MetadataUrl: "http://YOUR_BACKEND_IP:PORT/api/alarms/receive"

    Expected BM-APP format:
    {
        "BoardId": "RJ-BOX-XXX",
        "AlarmId": "uuid",
        "TaskSession": "task_001",
        "TaskDesc": "Helmet Detection",
        "Time": "2025-01-15 10:30:00",
        "TimeStamp": 1699426698084625,
        "Media": {
            "MediaName": "1",
            "MediaUrl": "rtsp://...",
            "MediaDesc": "H8C-1"
        },
        "Result": {
            "Type": "NoHelmet",
            "Description": "No helmet detected",
            "Properties": [
                {"property": "confidence", "value": 0.683594}
            ]
        },
        "ImageData": "base64...",
        "ImageDataLabeled": "base64..."
    }
    """
    try:
        raw_data = await request.json()

        # Log raw alarm for debugging
        print(f"[BM-APP HTTP] Received alarm: {json.dumps(raw_data, indent=2, default=str)[:1000]}...")

        # Parse using BmAppAlarmListener
        listener = BmAppAlarmListener()
        parsed = listener._parse_alarm(raw_data)

        print(f"[BM-APP HTTP] Parsed: type={parsed.get('alarm_type')}, camera={parsed.get('camera_name')}, conf={parsed.get('confidence')}")

        # Save to database
        alarm = await save_alarm_from_bmapp(parsed, db)

        # Broadcast to WebSocket clients for real-time updates
        await broadcast_alarm({
            "id": str(alarm.id),
            "bmapp_id": alarm.bmapp_id,
            "alarm_type": alarm.alarm_type,
            "alarm_name": alarm.alarm_name,
            "camera_id": alarm.camera_id,
            "camera_name": alarm.camera_name,
            "location": alarm.location,
            "confidence": alarm.confidence,
            "image_url": alarm.image_url,
            "video_url": alarm.video_url,
            "description": alarm.description,
            "alarm_time": alarm.alarm_time.isoformat() if alarm.alarm_time else None,
            "status": alarm.status
        })

        print(f"[BM-APP HTTP] Alarm saved with ID: {alarm.id}")

        # Return response in BM-APP expected format
        return {
            "Result": {
                "Code": 0,
                "Desc": "Alarm received successfully"
            },
            "AlarmId": str(alarm.id)
        }

    except json.JSONDecodeError as e:
        print(f"[BM-APP HTTP] JSON parse error: {e}")
        return {
            "Result": {
                "Code": 1,
                "Desc": f"Invalid JSON: {str(e)}"
            }
        }
    except Exception as e:
        print(f"[BM-APP HTTP] Error processing alarm: {e}")
        return {
            "Result": {
                "Code": 2,
                "Desc": f"Error: {str(e)}"
            }
        }
