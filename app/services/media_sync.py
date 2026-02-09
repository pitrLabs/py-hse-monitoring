"""
Media Sync Service
Background service that syncs alarm images and recordings from BM-APP to MinIO.
"""
import asyncio
from datetime import datetime
from typing import Optional

from app.config import settings
from app.database import SessionLocal
from app.models import Alarm, Recording, AIBox
from app.services.minio_storage import get_minio_storage


# Sync configuration
SYNC_INTERVAL = 300  # 5 minutes
BATCH_ALARM_IMAGES = 50
BATCH_ALARM_VIDEOS = 20
BATCH_RECORDINGS = 10


def _get_extension_from_url(url: str) -> str:
    """Extract file extension from URL."""
    if not url:
        return "jpg"
    url_path = url.split("?")[0]  # Remove query string
    if "." in url_path:
        ext = url_path.rsplit(".", 1)[-1].lower()
        if ext in ["jpg", "jpeg", "png", "gif", "webp", "mp4", "avi", "mkv", "mov", "webm"]:
            return ext
    # Default extensions based on common patterns
    if any(x in url.lower() for x in ["video", "mp4", "recording"]):
        return "mp4"
    return "jpg"


def _get_content_type(extension: str) -> str:
    """Get MIME type from extension."""
    types = {
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "gif": "image/gif",
        "webp": "image/webp",
        "mp4": "video/mp4",
        "avi": "video/x-msvideo",
        "mkv": "video/x-matroska",
        "mov": "video/quicktime",
        "webm": "video/webm",
    }
    return types.get(extension, "application/octet-stream")


class MediaSyncService:
    """Background service that syncs BM-APP media to MinIO."""

    def __init__(self):
        self.interval = SYNC_INTERVAL
        self.running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self):
        """Start the background sync service."""
        self.running = True
        self._task = asyncio.create_task(self._sync_loop())
        print(f"[MediaSync] Started (interval={self.interval}s)")

    def stop(self):
        """Stop the background sync service."""
        self.running = False
        if self._task:
            self._task.cancel()
            self._task = None
        print("[MediaSync] Stopped")

    async def _sync_loop(self):
        """Main sync loop."""
        # Wait on startup to let other services initialize
        await asyncio.sleep(15)

        while self.running:
            try:
                await self._sync_all()
            except Exception as e:
                print(f"[MediaSync] Error: {e}")
            await asyncio.sleep(self.interval)

    async def _sync_all(self):
        """Run all sync tasks."""
        if not settings.minio_enabled:
            print("[MediaSync] MinIO is disabled (MINIO_ENABLED=false), skipping sync")
            return

        storage = get_minio_storage()
        if not storage.is_initialized:
            print("[MediaSync] MinIO not initialized, skipping sync")
            return

        print("[MediaSync] Running sync cycle...")
        db = SessionLocal()
        try:
            await self._sync_alarm_images(db, storage)
            await self._sync_alarm_videos(db, storage)
            await self._sync_recordings(db, storage)
            print("[MediaSync] Sync cycle complete")
        finally:
            db.close()

    async def _sync_alarm_images(self, db, storage):
        """Sync alarm images from BM-APP to MinIO."""
        # Find alarms with image_url but no minio_image_path (and not marked as unavailable)
        alarms = db.query(Alarm).filter(
            Alarm.image_url.isnot(None),
            Alarm.image_url != "",
            Alarm.minio_image_path.is_(None)
        ).limit(BATCH_ALARM_IMAGES).all()

        if not alarms:
            return

        print(f"[MediaSync] Syncing {len(alarms)} alarm images...")
        synced = 0
        skipped = 0
        failed = 0

        for alarm in alarms:
            try:
                # Get base URL for this alarm's AI Box
                bmapp_base = None
                if alarm.aibox_id:
                    aibox = db.query(AIBox).filter(AIBox.id == alarm.aibox_id).first()
                    if aibox and aibox.api_url:
                        bmapp_base = aibox.api_url.rsplit("/api", 1)[0]
                if not bmapp_base:
                    bmapp_base = settings.bmapp_api_url.replace("/api", "")

                # Try to get labeled image URL first (from raw_data if available)
                labeled_url = None
                raw_url = alarm.image_url

                if alarm.raw_data:
                    try:
                        import json
                        raw_data = json.loads(alarm.raw_data) if isinstance(alarm.raw_data, str) else alarm.raw_data
                        # BM-APP uses ImageDataLabeled for labeled images
                        labeled_path = raw_data.get("ImageDataLabeled") or raw_data.get("LocalLabeledPath")
                        if labeled_path:
                            if labeled_path.startswith("http"):
                                labeled_url = labeled_path
                            elif labeled_path.startswith("/"):
                                labeled_url = f"{bmapp_base}{labeled_path}"
                            else:
                                labeled_url = f"{bmapp_base}/{labeled_path}"
                    except:
                        pass

                # Build full raw URL
                if not raw_url.startswith("http"):
                    if raw_url.startswith("/"):
                        raw_url = f"{bmapp_base}{raw_url}"
                    else:
                        raw_url = f"{bmapp_base}/{raw_url}"

                # Try labeled image first, then raw image
                urls_to_try = []
                if labeled_url:
                    urls_to_try.append(("labeled", labeled_url))
                urls_to_try.append(("raw", raw_url))

                success = False
                for img_type, image_url in urls_to_try:
                    print(f"[MediaSync] Trying {img_type}: {image_url}")

                    extension = _get_extension_from_url(image_url)
                    object_name = storage.generate_object_name(f"alarm_{img_type}", extension)

                    result, status = await storage.upload_from_url(
                        settings.minio_bucket_alarm_images,
                        object_name,
                        image_url,
                        _get_content_type(extension)
                    )

                    if status == "success":
                        # Use labeled path field if we got labeled image
                        if img_type == "labeled":
                            alarm.minio_labeled_image_path = result
                        else:
                            alarm.minio_image_path = result
                        alarm.minio_synced_at = datetime.utcnow()
                        db.commit()
                        synced += 1
                        success = True
                        break
                    elif status == "not_found":
                        # Try next URL or mark as unavailable
                        continue
                    else:
                        # Other error - will retry next cycle
                        failed += 1
                        success = True  # Don't try more URLs on error
                        break

                if not success:
                    # All URLs returned 404 - mark as unavailable so we don't retry
                    alarm.minio_image_path = "UNAVAILABLE"
                    alarm.minio_synced_at = datetime.utcnow()
                    db.commit()
                    skipped += 1
                    print(f"[MediaSync] Alarm {alarm.id}: all image URLs unavailable (404)")

            except Exception as e:
                db.rollback()
                failed += 1
                print(f"[MediaSync] Failed to sync alarm image {alarm.id}: {e}")

        print(f"[MediaSync] Alarm images: synced={synced}, skipped={skipped}, failed={failed}")

    async def _sync_alarm_videos(self, db, storage):
        """Sync alarm videos from BM-APP to MinIO."""
        # Find alarms with video_url but no minio_video_path (and not marked unavailable)
        alarms = db.query(Alarm).filter(
            Alarm.video_url.isnot(None),
            Alarm.video_url != "",
            Alarm.minio_video_path.is_(None)
        ).limit(BATCH_ALARM_VIDEOS).all()

        if not alarms:
            return

        print(f"[MediaSync] Syncing {len(alarms)} alarm videos...")
        synced = 0
        skipped = 0
        failed = 0

        for alarm in alarms:
            try:
                # Build full URL if relative
                video_url = alarm.video_url
                if not video_url.startswith("http"):
                    # Get AI Box URL from database if aibox_id is available
                    bmapp_base = None
                    if alarm.aibox_id:
                        aibox = db.query(AIBox).filter(AIBox.id == alarm.aibox_id).first()
                        if aibox and aibox.api_url:
                            bmapp_base = aibox.api_url.rsplit("/api", 1)[0]
                    if not bmapp_base:
                        bmapp_base = settings.bmapp_api_url.replace("/api", "")

                    if video_url.startswith("/"):
                        video_url = f"{bmapp_base}{video_url}"
                    else:
                        video_url = f"{bmapp_base}/{video_url}"

                print(f"[MediaSync] Downloading video: {video_url}")

                extension = _get_extension_from_url(video_url)
                object_name = storage.generate_object_name("alarm_video", extension)

                result, status = await storage.upload_from_url(
                    settings.minio_bucket_alarm_images,
                    object_name,
                    video_url,
                    _get_content_type(extension)
                )

                if status == "success":
                    alarm.minio_video_path = result
                    alarm.minio_synced_at = datetime.utcnow()
                    db.commit()
                    synced += 1
                elif status == "not_found":
                    # Mark as unavailable so we don't retry
                    alarm.minio_video_path = "UNAVAILABLE"
                    alarm.minio_synced_at = datetime.utcnow()
                    db.commit()
                    skipped += 1
                    print(f"[MediaSync] Alarm {alarm.id}: video unavailable (404)")
                else:
                    failed += 1

            except Exception as e:
                db.rollback()
                failed += 1
                print(f"[MediaSync] Failed to sync alarm video {alarm.id}: {e}")

        print(f"[MediaSync] Alarm videos: synced={synced}, skipped={skipped}, failed={failed}")

    async def _sync_recordings(self, db, storage):
        """Sync recordings from BM-APP to MinIO."""
        # Find recordings with file_url but no minio_file_path (and not unavailable)
        recordings = db.query(Recording).filter(
            Recording.file_url.isnot(None),
            Recording.file_url != "",
            Recording.minio_file_path.is_(None)
        ).limit(BATCH_RECORDINGS).all()

        if not recordings:
            return

        print(f"[MediaSync] Syncing {len(recordings)} recordings...")
        synced = 0
        skipped = 0
        failed = 0

        for recording in recordings:
            try:
                file_url = recording.file_url
                if not file_url.startswith("http"):
                    bmapp_base = settings.bmapp_api_url.replace("/api", "")
                    if file_url.startswith("/"):
                        file_url = f"{bmapp_base}{file_url}"
                    else:
                        file_url = f"{bmapp_base}/{file_url}"

                print(f"[MediaSync] Downloading recording: {file_url}")

                extension = _get_extension_from_url(file_url)
                object_name = storage.generate_object_name("recording", extension)

                result, status = await storage.upload_from_url(
                    settings.minio_bucket_recordings,
                    object_name,
                    file_url,
                    _get_content_type(extension)
                )

                if status == "success":
                    recording.minio_file_path = result
                    recording.minio_synced_at = datetime.utcnow()
                    db.commit()
                    synced += 1
                elif status == "not_found":
                    recording.minio_file_path = "UNAVAILABLE"
                    recording.minio_synced_at = datetime.utcnow()
                    db.commit()
                    skipped += 1
                    print(f"[MediaSync] Recording {recording.id}: file unavailable (404)")
                else:
                    failed += 1

            except Exception as e:
                db.rollback()
                failed += 1
                print(f"[MediaSync] Failed to sync recording {recording.id}: {e}")

        print(f"[MediaSync] Recordings: synced={synced}, skipped={skipped}, failed={failed}")


# ============ Global Instance ============

_service: Optional[MediaSyncService] = None


async def start_media_sync():
    """Start the global media sync service."""
    global _service
    if _service is None:
        _service = MediaSyncService()
        await _service.start()


def stop_media_sync():
    """Stop the global media sync service."""
    global _service
    if _service:
        _service.stop()
        _service = None
