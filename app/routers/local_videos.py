"""
Local Videos Router
Manages local video files for manual upload and analysis.
"""
from datetime import datetime
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File, Form
from sqlalchemy import func
from sqlalchemy.orm import Session

from app import schemas
from app.auth import get_current_user
from app.database import get_db
from app.models import LocalVideo, User
from app.config import settings
from app.services.minio_storage import get_minio_storage

router = APIRouter(prefix="/local-videos", tags=["Local Videos"])

MAX_DIRECT_UPLOAD_SIZE = 100 * 1024 * 1024  # 100MB


def _add_presigned_urls(video: LocalVideo) -> dict:
    """Add presigned URLs to video response."""
    data = {
        "id": video.id,
        "name": video.name,
        "description": video.description,
        "original_filename": video.original_filename,
        "minio_path": video.minio_path,
        "thumbnail_path": video.thumbnail_path,
        "file_size": video.file_size,
        "duration": video.duration,
        "resolution": video.resolution,
        "format": video.format,
        "status": video.status,
        "error_message": video.error_message,
        "uploaded_by_id": video.uploaded_by_id,
        "created_at": video.created_at,
        "updated_at": video.updated_at,
        "stream_url": None,
        "thumbnail_url": None,
    }

    storage = get_minio_storage()
    if storage.is_initialized and video.minio_path:
        data["stream_url"] = storage.get_presigned_url(
            settings.minio_bucket_local_videos,
            video.minio_path
        )
        if video.thumbnail_path:
            data["thumbnail_url"] = storage.get_presigned_url(
                settings.minio_bucket_local_videos,
                video.thumbnail_path
            )

    return data


@router.get("/", response_model=List[schemas.LocalVideoResponse])
def list_videos(
    skip: int = 0,
    limit: int = 100,
    status: Optional[str] = None,
    search: Optional[str] = None,
    format: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List local videos with optional filters."""
    query = db.query(LocalVideo)

    if status:
        query = query.filter(LocalVideo.status == status)

    if format:
        query = query.filter(LocalVideo.format.ilike(f"%{format}%"))

    if search:
        query = query.filter(
            LocalVideo.name.ilike(f"%{search}%") |
            LocalVideo.original_filename.ilike(f"%{search}%") |
            LocalVideo.description.ilike(f"%{search}%")
        )

    videos = query.order_by(LocalVideo.created_at.desc()).offset(skip).limit(limit).all()

    return [_add_presigned_urls(v) for v in videos]


@router.get("/stats/summary", response_model=schemas.LocalVideoStats)
def get_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get storage statistics for local videos."""
    # Total count and size
    total_videos = db.query(func.count(LocalVideo.id)).scalar() or 0
    total_size = db.query(func.sum(LocalVideo.file_size)).scalar() or 0

    # Group by status
    status_counts = db.query(
        LocalVideo.status,
        func.count(LocalVideo.id)
    ).group_by(LocalVideo.status).all()
    by_status = {s: c for s, c in status_counts}

    # Group by format
    format_counts = db.query(
        LocalVideo.format,
        func.count(LocalVideo.id)
    ).filter(LocalVideo.format.isnot(None)).group_by(LocalVideo.format).all()
    by_format = {f: c for f, c in format_counts if f}

    # Format size
    def format_size(size_bytes: int) -> str:
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.2f} PB"

    return schemas.LocalVideoStats(
        total_videos=total_videos,
        total_size=total_size,
        total_size_formatted=format_size(total_size),
        by_status=by_status,
        by_format=by_format
    )


@router.get("/{video_id}", response_model=schemas.LocalVideoResponse)
def get_video(
    video_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a single video by ID."""
    video = db.query(LocalVideo).filter(LocalVideo.id == video_id).first()
    if not video:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Video not found"
        )
    return _add_presigned_urls(video)


@router.get("/{video_id}/stream-url")
def get_stream_url(
    video_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get presigned URL for streaming video."""
    video = db.query(LocalVideo).filter(LocalVideo.id == video_id).first()
    if not video:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Video not found"
        )

    storage = get_minio_storage()
    if not storage.is_initialized:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Storage service unavailable"
        )

    url = storage.get_presigned_url(
        settings.minio_bucket_local_videos,
        video.minio_path
    )

    if not url:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate stream URL"
        )

    return {
        "video_id": str(video_id),
        "stream_url": url,
        "expires_in": settings.minio_presigned_url_expiry
    }


@router.post("/upload/init", response_model=schemas.LocalVideoUploadInitResponse)
def init_upload(
    upload_data: schemas.LocalVideoUploadInit,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Initialize a presigned upload for large files.
    Returns a presigned URL for direct browser upload to MinIO.
    """
    storage = get_minio_storage()
    if not storage.is_initialized:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Storage service unavailable"
        )

    # Extract extension from filename
    extension = "mp4"
    if "." in upload_data.filename:
        extension = upload_data.filename.rsplit(".", 1)[-1].lower()

    # Generate object path
    object_name = storage.generate_object_name("video", extension)

    # Generate presigned upload URL
    upload_url = storage.get_presigned_upload_url(
        settings.minio_bucket_local_videos,
        object_name
    )

    if not upload_url:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate upload URL"
        )

    # Create video record in processing state
    video = LocalVideo(
        name=upload_data.name,
        description=upload_data.description,
        original_filename=upload_data.filename,
        minio_path=object_name,
        file_size=upload_data.file_size,
        format=extension.upper(),
        status="processing",
        uploaded_by_id=current_user.id
    )
    db.add(video)
    db.commit()
    db.refresh(video)

    return schemas.LocalVideoUploadInitResponse(
        video_id=video.id,
        upload_url=upload_url,
        minio_path=object_name,
        expires_in=settings.minio_presigned_url_expiry
    )


@router.post("/upload/complete", response_model=schemas.LocalVideoResponse)
def complete_upload(
    complete_data: schemas.LocalVideoUploadComplete,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Mark an upload as complete and update video metadata."""
    video = db.query(LocalVideo).filter(LocalVideo.id == complete_data.video_id).first()
    if not video:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Video not found"
        )

    # Verify the file exists in MinIO
    storage = get_minio_storage()
    if storage.is_initialized:
        info = storage.get_object_info(settings.minio_bucket_local_videos, video.minio_path)
        if info:
            video.file_size = info.get("size", video.file_size)

    # Update metadata
    if complete_data.duration is not None:
        video.duration = complete_data.duration
    if complete_data.resolution:
        video.resolution = complete_data.resolution
    if complete_data.format:
        video.format = complete_data.format

    video.status = "ready"
    video.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(video)

    return _add_presigned_urls(video)


@router.post("/upload", response_model=schemas.LocalVideoResponse)
async def direct_upload(
    file: UploadFile = File(...),
    name: str = Form(...),
    description: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Direct upload for smaller files (< 100MB).
    For larger files, use the presigned upload flow.
    """
    storage = get_minio_storage()
    if not storage.is_initialized:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Storage service unavailable"
        )

    # Read file content
    content = await file.read()
    file_size = len(content)

    if file_size > MAX_DIRECT_UPLOAD_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large for direct upload. Max size: {MAX_DIRECT_UPLOAD_SIZE // (1024*1024)}MB. Use presigned upload for larger files."
        )

    # Extract extension
    extension = "mp4"
    if file.filename and "." in file.filename:
        extension = file.filename.rsplit(".", 1)[-1].lower()

    # Generate object path
    object_name = storage.generate_object_name("video", extension)

    # Upload to MinIO
    content_type = file.content_type or "video/mp4"
    result = storage.upload_bytes(
        settings.minio_bucket_local_videos,
        object_name,
        content,
        content_type
    )

    if not result:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to upload file"
        )

    # Create video record
    video = LocalVideo(
        name=name,
        description=description,
        original_filename=file.filename or "video.mp4",
        minio_path=object_name,
        file_size=file_size,
        format=extension.upper(),
        status="ready",
        uploaded_by_id=current_user.id
    )
    db.add(video)
    db.commit()
    db.refresh(video)

    return _add_presigned_urls(video)


@router.put("/{video_id}", response_model=schemas.LocalVideoResponse)
def update_video(
    video_id: UUID,
    update_data: schemas.LocalVideoUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update video metadata."""
    video = db.query(LocalVideo).filter(LocalVideo.id == video_id).first()
    if not video:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Video not found"
        )

    update_dict = update_data.model_dump(exclude_unset=True)
    for field, value in update_dict.items():
        setattr(video, field, value)

    video.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(video)

    return _add_presigned_urls(video)


@router.delete("/{video_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_video(
    video_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete a video and its file from storage."""
    video = db.query(LocalVideo).filter(LocalVideo.id == video_id).first()
    if not video:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Video not found"
        )

    # Delete from MinIO
    storage = get_minio_storage()
    if storage.is_initialized and video.minio_path:
        storage.delete_object(settings.minio_bucket_local_videos, video.minio_path)
        if video.thumbnail_path:
            storage.delete_object(settings.minio_bucket_local_videos, video.thumbnail_path)

    # Delete from database
    db.delete(video)
    db.commit()

    return None
