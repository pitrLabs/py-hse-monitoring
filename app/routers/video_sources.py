from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app import schemas
from app.auth import get_current_user, get_current_superuser
from app.database import get_db
from app.models import VideoSource, User

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
def create_video_source(
    video_source_data: schemas.VideoSourceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser)
):
    """Create a new video source. Only for superusers (admins)."""
    print(f"Received data: {video_source_data}")
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

    return db_video_source


@router.put("/{video_source_id}", response_model=schemas.VideoSourceResponse)
def update_video_source(
    video_source_id: UUID,
    video_source_update: schemas.VideoSourceUpdate,
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

    return video_source


@router.delete("/{video_source_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_video_source(
    video_source_id: UUID,
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

    db.delete(video_source)
    db.commit()

    return None


@router.patch("/{video_source_id}/toggle", response_model=schemas.VideoSourceResponse)
def toggle_video_source(
    video_source_id: UUID,
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

    return video_source
