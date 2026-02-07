"""
Storage Router
Health check and statistics for MinIO storage.
"""
from typing import List
from fastapi import APIRouter, Depends

from app import schemas
from app.auth import get_current_user
from app.models import User
from app.config import settings
from app.services.minio_storage import get_minio_storage

router = APIRouter(prefix="/storage", tags=["Storage"])


@router.get("/health", response_model=schemas.StorageHealthResponse)
def health_check(
    current_user: User = Depends(get_current_user)
):
    """Check MinIO storage health and connection."""
    storage = get_minio_storage()
    result = storage.health_check()
    return schemas.StorageHealthResponse(**result)


@router.get("/buckets", response_model=List[schemas.BucketStatsResponse])
def list_buckets(
    current_user: User = Depends(get_current_user)
):
    """List all buckets with statistics."""
    storage = get_minio_storage()
    if not storage.is_initialized:
        return []

    buckets = [
        settings.minio_bucket_alarm_images,
        settings.minio_bucket_recordings,
        settings.minio_bucket_local_videos,
    ]

    result = []
    for bucket in buckets:
        stats = storage.get_bucket_stats(bucket)
        result.append(schemas.BucketStatsResponse(
            bucket=bucket,
            object_count=stats["object_count"],
            total_size=stats["total_size"],
            total_size_formatted=stats["total_size_formatted"]
        ))

    return result
