"""
Recordings Router
Manages video recordings from BM-APP with playback support
"""
import asyncio
from datetime import datetime, timedelta
from typing import List, Optional, Dict
from uuid import UUID, uuid4
from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlalchemy import func, extract
from sqlalchemy.orm import Session
import httpx

from app import schemas
from app.auth import get_current_user
from app.database import get_db
from app.models import Recording, Alarm, User
from app.config import settings
from app.services.minio_storage import get_minio_storage

router = APIRouter(prefix="/recordings", tags=["Recordings"])

# In-memory tracking of active recordings
active_recordings: Dict[str, dict] = {}


@router.get("/", response_model=List[schemas.RecordingResponse])
def list_recordings(
    skip: int = 0,
    limit: int = 100,
    camera_id: Optional[str] = None,
    task_session: Optional[str] = None,
    trigger_type: Optional[str] = None,
    alarm_id: Optional[UUID] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    is_available: Optional[bool] = True,
    minio_only: Optional[bool] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List recordings with filtering options."""
    query = db.query(Recording)

    if camera_id:
        query = query.filter(Recording.camera_id == camera_id)

    if task_session:
        query = query.filter(Recording.task_session == task_session)

    if trigger_type:
        query = query.filter(Recording.trigger_type == trigger_type)

    if alarm_id:
        query = query.filter(Recording.alarm_id == alarm_id)

    if start_date:
        try:
            start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            query = query.filter(Recording.start_time >= start_dt)
        except ValueError:
            pass

    if end_date:
        try:
            end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
            query = query.filter(Recording.start_time <= end_dt)
        except ValueError:
            pass

    if is_available is not None:
        query = query.filter(Recording.is_available == is_available)

    # Filter for recordings stored in MinIO only (can be played/downloaded)
    if minio_only:
        query = query.filter(
            Recording.minio_file_path.isnot(None),
            Recording.minio_file_path != "",
            Recording.minio_file_path != "UNAVAILABLE"
        )

    recordings = query.order_by(Recording.start_time.desc()).offset(skip).limit(limit).all()
    return recordings


@router.get("/calendar", response_model=List[schemas.RecordingCalendarDay])
def get_calendar_data(
    year: int = Query(..., ge=2020, le=2100),
    month: int = Query(..., ge=1, le=12),
    camera_id: Optional[str] = None,
    minio_only: Optional[bool] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get calendar data showing which days have recordings."""
    # Build query for the specified month
    start_of_month = datetime(year, month, 1)
    if month == 12:
        end_of_month = datetime(year + 1, 1, 1)
    else:
        end_of_month = datetime(year, month + 1, 1)

    query = db.query(
        func.date(Recording.start_time).label('date'),
        func.count(Recording.id).label('count')
    ).filter(
        Recording.start_time >= start_of_month,
        Recording.start_time < end_of_month,
        Recording.is_available == True
    )

    if camera_id:
        query = query.filter(Recording.camera_id == camera_id)

    # Filter for recordings stored in MinIO only
    if minio_only:
        query = query.filter(
            Recording.minio_file_path.isnot(None),
            Recording.minio_file_path != "",
            Recording.minio_file_path != "UNAVAILABLE"
        )

    query = query.group_by(func.date(Recording.start_time))
    results = query.all()

    # Convert to response format
    calendar_days = []
    for result in results:
        calendar_days.append(schemas.RecordingCalendarDay(
            date=str(result.date),
            count=result.count,
            has_recordings=result.count > 0
        ))

    return calendar_days


@router.get("/by-date", response_model=List[schemas.RecordingResponse])
def get_recordings_by_date(
    date: str = Query(..., description="Date in YYYY-MM-DD format"),
    camera_id: Optional[str] = None,
    minio_only: Optional[bool] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all recordings for a specific date."""
    try:
        target_date = datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid date format. Use YYYY-MM-DD"
        )

    start_of_day = target_date
    end_of_day = target_date + timedelta(days=1)

    query = db.query(Recording).filter(
        Recording.start_time >= start_of_day,
        Recording.start_time < end_of_day,
        Recording.is_available == True
    )

    if camera_id:
        query = query.filter(Recording.camera_id == camera_id)

    # Filter for recordings stored in MinIO only
    if minio_only:
        query = query.filter(
            Recording.minio_file_path.isnot(None),
            Recording.minio_file_path != "",
            Recording.minio_file_path != "UNAVAILABLE"
        )

    recordings = query.order_by(Recording.start_time.desc()).all()
    return recordings


@router.get("/by-alarm/{alarm_id}", response_model=List[schemas.RecordingResponse])
def get_recordings_by_alarm(
    alarm_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all recordings associated with a specific alarm."""
    recordings = db.query(Recording).filter(
        Recording.alarm_id == alarm_id
    ).order_by(Recording.start_time.desc()).all()

    return recordings


@router.get("/active")
def get_active_recordings(
    current_user: User = Depends(get_current_user)
):
    """Get all currently active recordings."""
    return {
        "active_recordings": list(active_recordings.values()),
        "count": len(active_recordings)
    }


@router.get("/active/{stream_id}")
def get_active_recording_status(
    stream_id: str,
    current_user: User = Depends(get_current_user)
):
    """Check if a specific stream is being recorded."""
    if stream_id in active_recordings:
        info = active_recordings[stream_id]
        start_time = datetime.fromisoformat(info["start_time"])
        elapsed = int((datetime.utcnow() - start_time).total_seconds())
        return {
            "is_recording": True,
            "recording_id": info["id"],
            "started_by": info["started_by_name"],
            "start_time": info["start_time"],
            "elapsed_seconds": elapsed
        }
    return {
        "is_recording": False
    }


@router.get("/{recording_id}", response_model=schemas.RecordingResponse)
def get_recording(
    recording_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a specific recording by ID."""
    recording = db.query(Recording).filter(Recording.id == recording_id).first()

    if not recording:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recording not found"
        )

    return recording


@router.post("/", response_model=schemas.RecordingResponse, status_code=status.HTTP_201_CREATED)
def create_recording(
    recording_data: schemas.RecordingCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new recording entry."""
    # If alarm_id is provided, validate it exists
    if recording_data.alarm_id:
        alarm = db.query(Alarm).filter(Alarm.id == recording_data.alarm_id).first()
        if not alarm:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Associated alarm not found"
            )

    db_recording = Recording(
        bmapp_id=recording_data.bmapp_id,
        file_name=recording_data.file_name,
        file_url=recording_data.file_url,
        file_size=recording_data.file_size,
        duration=recording_data.duration,
        camera_id=recording_data.camera_id,
        camera_name=recording_data.camera_name,
        task_session=recording_data.task_session,
        start_time=recording_data.start_time,
        end_time=recording_data.end_time,
        trigger_type=recording_data.trigger_type,
        alarm_id=recording_data.alarm_id,
        thumbnail_url=recording_data.thumbnail_url
    )

    db.add(db_recording)
    db.commit()
    db.refresh(db_recording)

    return db_recording


@router.put("/{recording_id}", response_model=schemas.RecordingResponse)
def update_recording(
    recording_id: UUID,
    recording_update: schemas.RecordingUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update a recording entry."""
    recording = db.query(Recording).filter(Recording.id == recording_id).first()

    if not recording:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recording not found"
        )

    update_data = recording_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(recording, field, value)

    db.commit()
    db.refresh(recording)

    return recording


@router.delete("/{recording_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_recording(
    recording_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete a recording entry."""
    recording = db.query(Recording).filter(Recording.id == recording_id).first()

    if not recording:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recording not found"
        )

    db.delete(recording)
    db.commit()

    return None


@router.post("/sync-from-alarms", status_code=status.HTTP_200_OK)
async def sync_recordings_from_alarms(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Sync recordings from alarms that have video_url.
    This creates Recording entries from existing alarms with video recordings.
    """
    # Find alarms with video_url that don't have associated recordings
    alarms_with_video = db.query(Alarm).filter(
        Alarm.video_url.isnot(None),
        Alarm.video_url != ""
    ).all()

    created = 0
    skipped = 0
    errors = []

    for alarm in alarms_with_video:
        # Check if recording already exists for this alarm
        existing = db.query(Recording).filter(Recording.alarm_id == alarm.id).first()
        if existing:
            skipped += 1
            continue

        try:
            # Extract file info from video_url
            video_url = alarm.video_url
            file_name = video_url.split("/")[-1] if video_url else f"recording_{alarm.id}.mp4"

            db_recording = Recording(
                bmapp_id=None,
                file_name=file_name,
                file_url=video_url,
                camera_id=alarm.camera_id,
                camera_name=alarm.camera_name,
                start_time=alarm.alarm_time,
                trigger_type="alarm",
                alarm_id=alarm.id,
                synced_at=datetime.utcnow()
            )

            db.add(db_recording)
            db.commit()
            created += 1

        except Exception as e:
            db.rollback()
            errors.append(f"Failed to create recording for alarm {alarm.id}: {str(e)}")

    return {
        "message": "Sync completed",
        "created": created,
        "skipped": skipped,
        "total_alarms_with_video": len(alarms_with_video),
        "errors": errors if errors else None
    }


@router.get("/stream/{recording_id}")
async def stream_recording(
    recording_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Stream/proxy a recording video from BM-APP.
    This acts as a proxy to the BM-APP video server.
    """
    recording = db.query(Recording).filter(Recording.id == recording_id).first()

    if not recording:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recording not found"
        )

    if not recording.file_url:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recording has no video URL"
        )

    # Build full URL if relative
    video_url = recording.file_url
    if not video_url.startswith("http"):
        bmapp_url = settings.bmapp_api_url.replace("/api", "")
        if video_url.startswith("/"):
            video_url = f"{bmapp_url}{video_url}"
        else:
            video_url = f"{bmapp_url}/{video_url}"

    async def stream_video():
        async with httpx.AsyncClient() as client:
            async with client.stream("GET", video_url) as response:
                async for chunk in response.aiter_bytes():
                    yield chunk

    return StreamingResponse(
        stream_video(),
        media_type="video/mp4",
        headers={
            "Content-Disposition": f'inline; filename="{recording.file_name}"',
            "Accept-Ranges": "bytes"
        }
    )


@router.get("/video-url/{recording_id}")
def get_video_url(
    recording_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get the video URL for playback (for use with video player)."""
    recording = db.query(Recording).filter(Recording.id == recording_id).first()

    if not recording:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recording not found"
        )

    video_url = None

    # Priority 1: MinIO storage (new recordings from auto-recorder)
    if recording.minio_file_path and recording.minio_file_path != "UNAVAILABLE":
        storage = get_minio_storage()
        if storage and storage.is_initialized:
            video_url = storage.get_presigned_url(
                settings.minio_bucket_recordings,
                recording.minio_file_path,
                expires=3600  # 1 hour
            )

    # Priority 2: BM-APP URL (old recordings)
    if not video_url and recording.file_url:
        video_url = recording.file_url
        if not video_url.startswith("http"):
            bmapp_url = settings.bmapp_api_url.replace("/api", "")
            if video_url.startswith("/"):
                video_url = f"{bmapp_url}{video_url}"
            else:
                video_url = f"{bmapp_url}/{video_url}"

    if not video_url:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recording has no video URL"
        )

    return {
        "id": str(recording.id),
        "file_name": recording.file_name,
        "video_url": video_url,
        "duration": recording.duration,
        "start_time": recording.start_time.isoformat() if recording.start_time else None
    }


@router.get("/download/{recording_id}")
def get_download_url(
    recording_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a download URL for a recording."""
    recording = db.query(Recording).filter(Recording.id == recording_id).first()

    if not recording:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recording not found"
        )

    download_url = None

    # Priority 1: MinIO storage
    if recording.minio_file_path and recording.minio_file_path != "UNAVAILABLE":
        storage = get_minio_storage()
        if storage and storage.is_initialized:
            # Generate presigned URL with download headers
            download_url = storage.get_presigned_url(
                settings.minio_bucket_recordings,
                recording.minio_file_path,
                expires=3600,  # 1 hour
                response_headers={
                    "response-content-disposition": f'attachment; filename="{recording.file_name}"'
                }
            )

    # Priority 2: BM-APP URL (proxy through stream endpoint)
    if not download_url and recording.file_url:
        # Use the stream endpoint for download
        download_url = f"/api/recordings/stream/{recording_id}"

    if not download_url:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recording has no downloadable file"
        )

    return {
        "id": str(recording.id),
        "file_name": recording.file_name,
        "download_url": download_url,
        "file_size": recording.file_size
    }


# ============================================================================
# MANUAL RECORDING ENDPOINTS
# ============================================================================

@router.post("/start")
async def start_recording(
    stream_id: str = Query(..., description="Stream/task ID (e.g., 'task/session_id')"),
    camera_name: str = Query(..., description="Camera display name"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Start a manual recording for a stream.
    Only Operator role and above can start recordings.
    """
    # Check user role (P3 cannot record, only operator and above)
    if current_user.role not in ['operator', 'admin', 'superadmin']:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to start recordings"
        )

    # Check if already recording this stream
    if stream_id in active_recordings:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This stream is already being recorded"
        )

    # Generate recording ID
    recording_id = str(uuid4())
    start_time = datetime.utcnow()

    # Store active recording info
    active_recordings[stream_id] = {
        "id": recording_id,
        "stream_id": stream_id,
        "camera_name": camera_name,
        "started_by": str(current_user.id),
        "started_by_name": current_user.full_name or current_user.username,
        "start_time": start_time.isoformat(),
        "status": "recording"
    }

    # Create recording entry in database (status: recording)
    db_recording = Recording(
        id=UUID(recording_id),
        file_name=f"manual_{camera_name}_{start_time.strftime('%Y%m%d_%H%M%S')}.mp4",
        camera_name=camera_name,
        task_session=stream_id.replace("task/", ""),
        start_time=start_time,
        trigger_type="manual",
        is_available=False  # Not available until recording completes
    )
    db.add(db_recording)
    db.commit()

    return {
        "message": "Recording started",
        "recording_id": recording_id,
        "stream_id": stream_id,
        "camera_name": camera_name,
        "start_time": start_time.isoformat()
    }


@router.post("/stop")
async def stop_recording(
    stream_id: str = Query(..., description="Stream/task ID"),
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Stop a manual recording for a stream.
    """
    # Check user role
    if current_user.role not in ['operator', 'admin', 'superadmin']:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to stop recordings"
        )

    # Check if recording exists
    if stream_id not in active_recordings:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active recording found for this stream"
        )

    recording_info = active_recordings.pop(stream_id)
    recording_id = recording_info["id"]
    end_time = datetime.utcnow()
    start_time = datetime.fromisoformat(recording_info["start_time"])
    duration = int((end_time - start_time).total_seconds())

    # Update recording in database
    db_recording = db.query(Recording).filter(Recording.id == UUID(recording_id)).first()
    if db_recording:
        db_recording.end_time = end_time
        db_recording.duration = duration
        db_recording.is_available = True  # Now available for playback
        db.commit()
        db.refresh(db_recording)

    return {
        "message": "Recording stopped",
        "recording_id": recording_id,
        "stream_id": stream_id,
        "duration": duration,
        "start_time": start_time.isoformat(),
        "end_time": end_time.isoformat()
    }
