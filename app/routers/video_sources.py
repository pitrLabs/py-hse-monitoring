from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session
from app import schemas
from app.auth import get_current_user, get_current_superuser
from app.database import get_db
from app.models import VideoSource, User
from app.services.mediamtx import add_stream_path, remove_stream_path, update_stream_path
from app.services.bmapp_client import (
    sync_media_to_bmapp,
    delete_media_from_bmapp,
    get_bmapp_client
)
from app.config import settings

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
        group_id=video_source_data.group_id,
        is_active=video_source_data.is_active,
        sound_alert=video_source_data.sound_alert,
        created_by_id=current_user.id
    )

    db.add(db_video_source)
    db.commit()
    db.refresh(db_video_source)

    # Sync with MediaMTX in background
    if db_video_source.is_active:
        background_tasks.add_task(add_stream_path, db_video_source.stream_name, db_video_source.url)

    # Sync with BM-APP in background
    if settings.bmapp_enabled:
        background_tasks.add_task(
            sync_media_to_bmapp,
            db_video_source.stream_name,
            db_video_source.url,
            db_video_source.description or ""
        )

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

    if video_source_update.group_id is not None:
        video_source.group_id = video_source_update.group_id

    if video_source_update.is_active is not None:
        video_source.is_active = video_source_update.is_active

    if video_source_update.sound_alert is not None:
        video_source.sound_alert = video_source_update.sound_alert

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
        # Sync with BM-APP - delete old, add new
        if settings.bmapp_enabled:
            background_tasks.add_task(delete_media_from_bmapp, old_stream_name)
            background_tasks.add_task(
                sync_media_to_bmapp,
                video_source.stream_name,
                video_source.url,
                video_source.description or ""
            )
    elif url_changed and video_source.is_active:
        # Update existing path
        background_tasks.add_task(update_stream_path, video_source.stream_name, video_source.url)
        # Sync with BM-APP
        if settings.bmapp_enabled:
            background_tasks.add_task(
                sync_media_to_bmapp,
                video_source.stream_name,
                video_source.url,
                video_source.description or ""
            )
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

    # Remove from BM-APP in background
    if settings.bmapp_enabled:
        background_tasks.add_task(delete_media_from_bmapp, stream_name)

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


@router.post("/sync-bmapp", status_code=status.HTTP_200_OK)
async def sync_bmapp(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser)
):
    """Sync all video sources to BM-APP. Only for superusers (admins)."""
    if not settings.bmapp_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="BM-APP integration is disabled"
        )

    video_sources = db.query(VideoSource).all()

    for vs in video_sources:
        background_tasks.add_task(
            sync_media_to_bmapp,
            vs.stream_name,
            vs.url,
            vs.description or ""
        )

    return {"message": f"Syncing {len(video_sources)} video sources to BM-APP"}


@router.get("/bmapp/media", status_code=status.HTTP_200_OK)
async def get_bmapp_media(
    current_user: User = Depends(get_current_user)
):
    """Get all media/cameras from BM-APP."""
    if not settings.bmapp_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="BM-APP integration is disabled"
        )

    try:
        client = get_bmapp_client()
        media_list = await client.get_media_list()
        return {"media": media_list}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/bmapp/tasks", status_code=status.HTTP_200_OK)
async def get_bmapp_tasks(
    current_user: User = Depends(get_current_user)
):
    """Get all AI tasks from BM-APP."""
    if not settings.bmapp_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="BM-APP integration is disabled"
        )

    try:
        client = get_bmapp_client()
        task_list = await client.get_task_list()
        return {"tasks": task_list}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/bmapp/abilities", status_code=status.HTTP_200_OK)
async def get_bmapp_abilities(
    current_user: User = Depends(get_current_user)
):
    """Get all available AI abilities from BM-APP."""
    if not settings.bmapp_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="BM-APP integration is disabled"
        )

    try:
        client = get_bmapp_client()
        abilities = await client.get_abilities()
        return {"abilities": abilities}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/import-from-bmapp", status_code=status.HTTP_200_OK)
async def import_from_bmapp(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser)
):
    """Import all media/cameras from BM-APP into our database.

    This will:
    1. Fetch all media from BM-APP
    2. Create VideoSource entries in database (skip if stream_name exists)
    3. Sync to MediaMTX for raw RTSP streaming

    Only for superusers (admins).
    """
    if not settings.bmapp_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="BM-APP integration is disabled"
        )

    try:
        client = get_bmapp_client()
        media_list = await client.get_media_list()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch media from BM-APP: {str(e)}"
        )

    imported = 0
    skipped = 0
    errors = []

    for media in media_list:
        media_name = media.get("MediaName", "")
        media_url = media.get("MediaUrl", "")
        media_desc = media.get("MediaDesc", "")

        if not media_name or not media_url:
            errors.append(f"Invalid media entry: {media}")
            continue

        # Check if already exists
        existing = db.query(VideoSource).filter(VideoSource.stream_name == media_name).first()
        if existing:
            skipped += 1
            continue

        # Determine source type from URL
        source_type = "rtsp"
        if media_url.startswith("http"):
            source_type = "http"
        elif media_url.startswith("file"):
            source_type = "file"

        # Create new video source
        try:
            db_video_source = VideoSource(
                name=media_name,
                url=media_url,
                stream_name=media_name,
                source_type=source_type,
                description=media_desc,
                is_active=True,
                is_synced_bmapp=True,
                created_by_id=current_user.id
            )
            db.add(db_video_source)
            db.commit()
            db.refresh(db_video_source)

            # Sync to MediaMTX in background
            background_tasks.add_task(add_stream_path, db_video_source.stream_name, db_video_source.url)

            imported += 1
        except Exception as e:
            db.rollback()
            errors.append(f"Failed to import {media_name}: {str(e)}")

    return {
        "message": f"Import completed",
        "imported": imported,
        "skipped": skipped,
        "total_from_bmapp": len(media_list),
        "errors": errors if errors else None
    }
