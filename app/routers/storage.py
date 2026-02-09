"""
Storage Router
Health check and statistics for MinIO storage.
"""
from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import schemas
from app.auth import get_current_user
from app.models import User, Alarm, AIBox
from app.config import settings
from app.database import get_db
from app.services.minio_storage import get_minio_storage
from app.services.auto_recorder import _service as auto_recorder_service

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


@router.get("/diagnostic")
def storage_diagnostic(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Diagnostic endpoint to check storage sync status."""
    storage = get_minio_storage()

    # Count alarms with/without MinIO paths
    total_alarms = db.query(Alarm).count()
    alarms_with_image_url = db.query(Alarm).filter(
        Alarm.image_url.isnot(None),
        Alarm.image_url != ""
    ).count()
    alarms_with_minio_path = db.query(Alarm).filter(
        Alarm.minio_image_path.isnot(None)
    ).count()
    alarms_with_minio_labeled = db.query(Alarm).filter(
        Alarm.minio_labeled_image_path.isnot(None)
    ).count()
    alarms_pending_sync = db.query(Alarm).filter(
        Alarm.image_url.isnot(None),
        Alarm.image_url != "",
        Alarm.minio_image_path.is_(None)
    ).count()

    # Get sample pending alarm for debugging
    sample_pending = db.query(Alarm).filter(
        Alarm.image_url.isnot(None),
        Alarm.image_url != "",
        Alarm.minio_image_path.is_(None)
    ).first()

    sample_info = None
    if sample_pending:
        sample_info = {
            "id": str(sample_pending.id),
            "image_url": sample_pending.image_url,
            "aibox_id": str(sample_pending.aibox_id) if sample_pending.aibox_id else None,
            "aibox_name": sample_pending.aibox_name,
            "created_at": sample_pending.created_at.isoformat() if sample_pending.created_at else None
        }

    return {
        "minio_enabled": settings.minio_enabled,
        "minio_initialized": storage.is_initialized,
        "minio_endpoint": settings.minio_endpoint,
        "total_alarms": total_alarms,
        "alarms_with_image_url": alarms_with_image_url,
        "alarms_with_minio_path": alarms_with_minio_path,
        "alarms_with_minio_labeled": alarms_with_minio_labeled,
        "alarms_pending_sync": alarms_pending_sync,
        "sample_pending_alarm": sample_info
    }


@router.get("/auto-recorder/status")
async def auto_recorder_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Check auto-recorder service status and debug info."""
    import httpx

    # Get AI Boxes from database
    aiboxes = db.query(AIBox).filter(AIBox.is_active == True).all()
    aibox_info = []

    for aibox in aiboxes:
        box_data = {
            "id": str(aibox.id),
            "name": aibox.name,
            "api_url": aibox.api_url,
            "is_active": aibox.is_active,
            "cameras": []
        }

        # Try to fetch task status from BM-APP
        try:
            api_url = aibox.api_url.rstrip("/")
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{api_url}/app_task_status")
                if response.status_code == 200:
                    data = response.json()
                    tasks = data.get("TaskList", [])

                    for task in tasks:
                        alg_task_status = task.get("AlgTaskStatus", {})
                        status_type = alg_task_status.get("type", 0) if isinstance(alg_task_status, dict) else 0
                        media = task.get("Media", {}) or {}

                        box_data["cameras"].append({
                            "task_session": task.get("AlgTaskSession", ""),
                            "media_name": media.get("MediaName", ""),
                            "media_url": media.get("MediaUrl", ""),
                            "status_type": status_type,
                            "status_name": {0: "Stopped", 1: "Connecting", 4: "Healthy"}.get(status_type, f"Unknown({status_type})"),
                            "is_recordable": status_type == 4
                        })
                else:
                    box_data["error"] = f"API returned status {response.status_code}"
        except Exception as e:
            box_data["error"] = str(e)

        aibox_info.append(box_data)

    # Get auto-recorder service status
    service_status = {
        "running": False,
        "active_recorders": 0,
        "recorder_details": []
    }

    if auto_recorder_service:
        service_status["running"] = auto_recorder_service.running
        service_status["active_recorders"] = len(auto_recorder_service.recorders)

        for camera_id, recorder in auto_recorder_service.recorders.items():
            service_status["recorder_details"].append({
                "camera_id": camera_id,
                "camera_name": recorder.camera_name,
                "rtsp_url": recorder.rtsp_url,
                "is_recording": recorder.is_recording,
                "current_file": recorder.current_file
            })

    return {
        "minio_enabled": settings.minio_enabled,
        "minio_initialized": get_minio_storage().is_initialized,
        "aiboxes": aibox_info,
        "auto_recorder": service_status
    }
