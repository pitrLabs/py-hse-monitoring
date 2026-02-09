"""
Storage Router
Health check and statistics for MinIO storage.
"""
from typing import List
from uuid import uuid4
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import schemas
from app.auth import get_current_user
from app.models import User, Alarm, AIBox
from app.config import settings
from app.database import get_db
from app.services.minio_storage import get_minio_storage
from app.services.auto_recorder import get_auto_recorder_service

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


@router.get("/debug")
async def storage_debug(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Comprehensive debug endpoint for MinIO and auto-recorder issues."""
    import subprocess
    import httpx

    debug_info = {
        "minio": {},
        "ffmpeg": {},
        "auto_recorder": {},
        "aiboxes": []
    }

    # 1. Check MinIO configuration
    debug_info["minio"]["enabled"] = settings.minio_enabled
    debug_info["minio"]["endpoint"] = settings.minio_endpoint
    debug_info["minio"]["access_key"] = settings.minio_access_key[:3] + "***"  # Masked
    debug_info["minio"]["secret_key_length"] = len(settings.minio_secret_key)
    debug_info["minio"]["buckets_config"] = {
        "alarm_images": settings.minio_bucket_alarm_images,
        "recordings": settings.minio_bucket_recordings,
        "local_videos": settings.minio_bucket_local_videos
    }

    # 2. Test MinIO connection
    storage = get_minio_storage()
    debug_info["minio"]["initialized"] = storage.is_initialized

    if storage.is_initialized:
        try:
            health = storage.health_check()
            debug_info["minio"]["health"] = health

            # List bucket contents
            for bucket_name in [settings.minio_bucket_recordings, settings.minio_bucket_alarm_images]:
                try:
                    objects = storage.list_objects(bucket_name)
                    debug_info["minio"][f"bucket_{bucket_name}"] = {
                        "object_count": len(objects),
                        "objects": objects[:5] if objects else []  # First 5 objects
                    }
                except Exception as e:
                    debug_info["minio"][f"bucket_{bucket_name}"] = {"error": str(e)}
        except Exception as e:
            debug_info["minio"]["health_error"] = str(e)
    else:
        # Try to initialize and capture error
        try:
            storage.initialize()
            debug_info["minio"]["init_retry"] = "success"
        except Exception as e:
            debug_info["minio"]["init_error"] = str(e)
            import traceback
            debug_info["minio"]["init_traceback"] = traceback.format_exc()

    # 3. Check FFmpeg
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=5
        )
        debug_info["ffmpeg"]["available"] = result.returncode == 0
        debug_info["ffmpeg"]["version"] = result.stdout.decode()[:200] if result.returncode == 0 else None
    except FileNotFoundError:
        debug_info["ffmpeg"]["available"] = False
        debug_info["ffmpeg"]["error"] = "FFmpeg not found in PATH"
    except Exception as e:
        debug_info["ffmpeg"]["available"] = False
        debug_info["ffmpeg"]["error"] = str(e)

    # 4. Check auto-recorder service
    auto_recorder_svc = get_auto_recorder_service()
    if auto_recorder_svc:
        debug_info["auto_recorder"]["service_exists"] = True
        debug_info["auto_recorder"]["running"] = auto_recorder_svc.running
        debug_info["auto_recorder"]["active_recorders"] = len(auto_recorder_svc.recorders)
        debug_info["auto_recorder"]["recorder_details"] = []

        for camera_id, recorder in auto_recorder_svc.recorders.items():
            debug_info["auto_recorder"]["recorder_details"].append({
                "camera_id": camera_id,
                "camera_name": recorder.camera_name,
                "rtsp_url": recorder.rtsp_url[:50] + "..." if recorder.rtsp_url else None,
                "is_recording": recorder.is_recording,
                "current_file": recorder.current_file
            })
    else:
        debug_info["auto_recorder"]["service_exists"] = False
        debug_info["auto_recorder"]["error"] = "Auto-recorder service not started"

    # 5. Check AI Boxes and their cameras
    aiboxes = db.query(AIBox).filter(AIBox.is_active == True).all()
    debug_info["aiboxes_count"] = len(aiboxes)

    for aibox in aiboxes[:2]:  # Check first 2 boxes
        box_debug = {
            "id": str(aibox.id),
            "name": aibox.name,
            "api_url": aibox.api_url,
            "cameras": []
        }

        try:
            api_url = aibox.api_url.rstrip("/")

            async with httpx.AsyncClient(timeout=10.0) as client:
                # Fetch tasks
                task_resp = await client.post(f"{api_url}/alg_task_fetch", json={})
                if task_resp.status_code == 200:
                    task_data = task_resp.json()
                    if task_data.get("Result", {}).get("Code") == 0:
                        tasks = task_data.get("Content", [])
                        box_debug["task_count"] = len(tasks)

                        # Check for healthy cameras
                        healthy_count = 0
                        for task in tasks:
                            import json as json_lib
                            try:
                                task_json = task.get("json", "{}")
                                if isinstance(task_json, str):
                                    task_config = json_lib.loads(task_json)
                                else:
                                    task_config = task_json
                            except:
                                task_config = {}

                            status = task.get("AlgTaskStatus", {})
                            status_type = status.get("type", 0) if isinstance(status, dict) else 0
                            media_name = task_config.get("MediaName", "")

                            if status_type == 4:
                                healthy_count += 1
                                box_debug["cameras"].append({
                                    "name": media_name,
                                    "status": "Healthy",
                                    "status_type": status_type
                                })

                        box_debug["healthy_cameras"] = healthy_count

                # Fetch media list to get RTSP URLs
                media_resp = await client.post(f"{api_url}/alg_media_fetch", json={})
                if media_resp.status_code == 200:
                    media_data = media_resp.json()
                    if media_data.get("Result", {}).get("Code") == 0:
                        media_list = media_data.get("Content", [])
                        box_debug["media_count"] = len(media_list)

                        # Get first RTSP URL for testing
                        if media_list:
                            first_media = media_list[0]
                            import json as json_lib
                            try:
                                if isinstance(first_media.get("json"), str):
                                    media_config = json_lib.loads(first_media.get("json", "{}"))
                                else:
                                    media_config = first_media
                            except:
                                media_config = first_media

                            rtsp_url = media_config.get("MediaUrl", "")
                            box_debug["sample_rtsp_url"] = rtsp_url[:60] + "..." if rtsp_url else None

        except Exception as e:
            box_debug["error"] = str(e)

        debug_info["aiboxes"].append(box_debug)

    return debug_info


@router.post("/test-record")
async def test_record(
    rtsp_url: str,
    duration_seconds: int = 5,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Test recording from an RTSP URL for a short duration.
    This helps debug FFmpeg and RTSP connectivity issues.
    """
    import subprocess
    import tempfile
    import os

    result = {
        "rtsp_url": rtsp_url[:50] + "..." if len(rtsp_url) > 50 else rtsp_url,
        "duration_seconds": duration_seconds,
        "success": False
    }

    # Limit duration for safety
    duration_seconds = min(duration_seconds, 10)

    try:
        # Generate temp file
        filename = f"test_record_{uuid4().hex[:8]}.mp4"
        filepath = os.path.join(tempfile.gettempdir(), filename)

        # FFmpeg command
        cmd = [
            "ffmpeg",
            "-rtsp_transport", "tcp",
            "-i", rtsp_url,
            "-t", str(duration_seconds),
            "-c", "copy",
            "-y",
            filepath
        ]

        result["ffmpeg_cmd"] = " ".join(cmd[:6]) + " ..."  # Truncated for security

        # Run FFmpeg
        process = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=duration_seconds + 30
        )

        result["ffmpeg_returncode"] = process.returncode
        result["ffmpeg_stderr"] = process.stderr.decode('utf-8', errors='ignore')[-500:]

        # Check if file was created
        if os.path.exists(filepath):
            file_size = os.path.getsize(filepath)
            result["file_created"] = True
            result["file_size"] = file_size
            result["success"] = file_size > 0

            # Upload to MinIO if successful
            if result["success"]:
                storage = get_minio_storage()
                if storage.is_initialized:
                    object_name = f"test/{filename}"
                    with open(filepath, "rb") as f:
                        upload_result = storage.upload_file(
                            settings.minio_bucket_recordings,
                            object_name,
                            f,
                            "video/mp4",
                            file_size
                        )
                    result["minio_upload"] = upload_result is not None
                    result["minio_path"] = object_name if upload_result else None
                else:
                    result["minio_upload"] = False
                    result["minio_error"] = "MinIO not initialized"

            # Cleanup
            os.remove(filepath)
        else:
            result["file_created"] = False

    except subprocess.TimeoutExpired:
        result["error"] = "FFmpeg timed out"
    except Exception as e:
        result["error"] = str(e)
        import traceback
        result["traceback"] = traceback.format_exc()

    return result


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

        # Fetch task status from BM-APP using POST /alg_task_fetch
        try:
            import json as json_lib
            api_url = aibox.api_url.rstrip("/")
            full_url = f"{api_url}/alg_task_fetch"
            box_data["api_url_full"] = full_url

            async with httpx.AsyncClient(timeout=10.0) as client:
                # BM-APP requires POST request
                response = await client.post(full_url, json={})
                box_data["api_status_code"] = response.status_code

                if response.status_code == 200:
                    data = response.json()
                    # Check if request was successful (Code=0)
                    result_code = data.get("Result", {}).get("Code", -1)
                    box_data["api_result_code"] = result_code

                    if result_code != 0:
                        box_data["error"] = data.get("Result", {}).get("Desc", "Unknown API error")
                        continue

                    raw_tasks = data.get("Content", [])
                    box_data["task_count"] = len(raw_tasks)

                    for raw_task in raw_tasks:
                        # Parse JSON config from task
                        try:
                            task_json = raw_task.get("json", "{}")
                            if isinstance(task_json, str):
                                task_config = json_lib.loads(task_json)
                            else:
                                task_config = task_json
                        except:
                            task_config = {}

                        # Status is in raw task data
                        alg_task_status = raw_task.get("AlgTaskStatus", task_config.get("AlgTaskStatus", {}))
                        status_type = alg_task_status.get("type", 0) if isinstance(alg_task_status, dict) else 0

                        # Media info might be in task config or parsed separately
                        media_name = task_config.get("MediaName", raw_task.get("name", ""))
                        task_session = task_config.get("AlgTaskSession", raw_task.get("session", ""))

                        box_data["cameras"].append({
                            "task_session": task_session,
                            "media_name": media_name,
                            "media_url": task_config.get("MediaUrl", ""),
                            "status_type": status_type,
                            "status_name": {0: "Stopped", 1: "Connecting", 4: "Healthy"}.get(status_type, f"Unknown({status_type})"),
                            "is_recordable": status_type == 4
                        })
                else:
                    box_data["error"] = f"API returned status {response.status_code}"
                    box_data["response_text"] = response.text[:500] if response.text else ""
        except Exception as e:
            box_data["error"] = str(e)
            import traceback
            box_data["traceback"] = traceback.format_exc()

        aibox_info.append(box_data)

    # Get auto-recorder service status
    service_status = {
        "running": False,
        "active_recorders": 0,
        "recorder_details": []
    }

    auto_recorder_svc = get_auto_recorder_service()
    if auto_recorder_svc:
        service_status["running"] = auto_recorder_svc.running
        service_status["active_recorders"] = len(auto_recorder_svc.recorders)

        for camera_id, recorder in auto_recorder_svc.recorders.items():
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
