from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session
from app import schemas
from app.auth import get_current_user, get_current_superuser
from app.database import get_db
from app.models import VideoSource, User
from app.services.mediamtx import add_stream_path, remove_stream_path, update_stream_path

router = APIRouter(prefix="/video-sources", tags=["Video Sources"])


@router.get("/", response_model=List[schemas.VideoSourceResponse])
def list_video_sources(
    skip: int = 0,
    limit: int = 100,
    is_active: bool = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List all video sources. Available for all authenticated users."""
    query = db.query(VideoSource)

    if is_active is not None:
        query = query.filter(VideoSource.is_active == is_active)

    video_sources = query.order_by(VideoSource.created_at.desc()).offset(skip).limit(limit).all()
    return video_sources


@router.get("/{video_source_id}", response_model=schemas.VideoSourceResponse)
def get_video_source(
    video_source_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a specific video source by ID."""
    video_source = db.query(VideoSource).filter(VideoSource.id == video_source_id).first()

    if not video_source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Video source not found"
        )

    return video_source


@router.post("/", response_model=schemas.VideoSourceResponse, status_code=status.HTTP_201_CREATED)
async def create_video_source(
    video_source_data: schemas.VideoSourceCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser)
):
    """Create a new video source. Only for superusers (admins)."""
    # Check if stream_name already exists
    existing = db.query(VideoSource).filter(VideoSource.stream_name == video_source_data.stream_name).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Stream name already exists"
        )

    db_video_source = VideoSource(
        name=video_source_data.name,
        url=video_source_data.url,
        stream_name=video_source_data.stream_name,
        source_type=video_source_data.source_type,
        description=video_source_data.description,
        location=video_source_data.location,
        is_active=video_source_data.is_active,
        created_by_id=current_user.id
    )

    db.add(db_video_source)
    db.commit()
    db.refresh(db_video_source)

    # Sync with MediaMTX in background
    if db_video_source.is_active:
        background_tasks.add_task(add_stream_path, db_video_source.stream_name, db_video_source.url)

    return db_video_source


@router.put("/{video_source_id}", response_model=schemas.VideoSourceResponse)
async def update_video_source(
    video_source_id: UUID,
    video_source_update: schemas.VideoSourceUpdate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser)
):
    """Update a video source. Only for superusers (admins)."""
    video_source = db.query(VideoSource).filter(VideoSource.id == video_source_id).first()

    if not video_source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Video source not found"
        )

    old_stream_name = video_source.stream_name
    old_url = video_source.url
    old_is_active = video_source.is_active

    if video_source_update.name is not None:
        video_source.name = video_source_update.name

    if video_source_update.url is not None:
        video_source.url = video_source_update.url

    if video_source_update.stream_name is not None:
        existing = db.query(VideoSource).filter(
            VideoSource.stream_name == video_source_update.stream_name,
            VideoSource.id != video_source_id
        ).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Stream name already exists"
            )
        video_source.stream_name = video_source_update.stream_name

    if video_source_update.source_type is not None:
        video_source.source_type = video_source_update.source_type

    if video_source_update.description is not None:
        video_source.description = video_source_update.description

    if video_source_update.location is not None:
        video_source.location = video_source_update.location

    if video_source_update.is_active is not None:
        video_source.is_active = video_source_update.is_active

    db.commit()
    db.refresh(video_source)

    # Sync with MediaMTX in background
    stream_name_changed = old_stream_name != video_source.stream_name
    url_changed = old_url != video_source.url
    status_changed = old_is_active != video_source.is_active

    if stream_name_changed:
        # Remove old path, add new path
        background_tasks.add_task(remove_stream_path, old_stream_name)
        if video_source.is_active:
            background_tasks.add_task(add_stream_path, video_source.stream_name, video_source.url)
    elif url_changed and video_source.is_active:
        # Update existing path
        background_tasks.add_task(update_stream_path, video_source.stream_name, video_source.url)
    elif status_changed:
        if video_source.is_active:
            background_tasks.add_task(add_stream_path, video_source.stream_name, video_source.url)
        else:
            background_tasks.add_task(remove_stream_path, video_source.stream_name)

    return video_source


@router.delete("/{video_source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_video_source(
    video_source_id: UUID,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser)
):
    """Delete a video source. Only for superusers (admins)."""
    video_source = db.query(VideoSource).filter(VideoSource.id == video_source_id).first()

    if not video_source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Video source not found"
        )

    stream_name = video_source.stream_name

    db.delete(video_source)
    db.commit()

    # Remove from MediaMTX in background
    background_tasks.add_task(remove_stream_path, stream_name)

    return None


@router.patch("/{video_source_id}/toggle", response_model=schemas.VideoSourceResponse)
async def toggle_video_source(
    video_source_id: UUID,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser)
):
    """Toggle the active status of a video source. Only for superusers (admins)."""
    video_source = db.query(VideoSource).filter(VideoSource.id == video_source_id).first()

    if not video_source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Video source not found"
        )

    video_source.is_active = not video_source.is_active
    db.commit()
    db.refresh(video_source)

    # Sync with MediaMTX in background
    if video_source.is_active:
        background_tasks.add_task(add_stream_path, video_source.stream_name, video_source.url)
    else:
        background_tasks.add_task(remove_stream_path, video_source.stream_name)

    return video_source


@router.post("/sync-mediamtx", status_code=status.HTTP_200_OK)
async def sync_mediamtx(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser)
):
    """Sync all active video sources to MediaMTX. Only for superusers (admins)."""
    video_sources = db.query(VideoSource).filter(VideoSource.is_active == True).all()

    for vs in video_sources:
        background_tasks.add_task(add_stream_path, vs.stream_name, vs.url)

    return {"message": f"Syncing {len(video_sources)} video sources to MediaMTX"}
