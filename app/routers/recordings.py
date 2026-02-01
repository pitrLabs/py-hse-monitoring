"""
Recordings Router
Manages video recordings from BM-APP with playback support
"""
from datetime import datetime, timedelta
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, extract
from sqlalchemy.orm import Session
import httpx

from app import schemas
from app.auth import get_current_user
from app.database import get_db
from app.models import Recording, Alarm, User
from app.config import settings

router = APIRouter(prefix="/recordings", tags=["Recordings"])


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

    recordings = query.order_by(Recording.start_time.desc()).offset(skip).limit(limit).all()
    return recordings


@router.get("/calendar", response_model=List[schemas.RecordingCalendarDay])
def get_calendar_data(
    year: int = Query(..., ge=2020, le=2100),
    month: int = Query(..., ge=1, le=12),
    camera_id: Optional[str] = None,
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

    return {
        "id": str(recording.id),
        "file_name": recording.file_name,
        "video_url": video_url,
        "duration": recording.duration,
        "start_time": recording.start_time.isoformat() if recording.start_time else None
    }
