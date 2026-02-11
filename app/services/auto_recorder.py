"""
Auto Recorder Service
Automatically records healthy AI camera streams to MinIO in 5-minute chunks.
Each chunk saved with unique filename (no overwrite).
"""
import asyncio
import subprocess
import os
import tempfile
import logging
from datetime import datetime
from typing import Optional, Dict, Set
from uuid import uuid4

from app.config import settings
from app.database import SessionLocal
from app.models import AIBox, Recording
from app.services.minio_storage import get_minio_storage


# Setup logger
logger = logging.getLogger("auto_recorder")

# Configuration
CHUNK_DURATION_SECONDS = 300  # 5 minutes per chunk
HEALTH_CHECK_INTERVAL = 60  # Check camera health every 60 seconds (was 30)
RECORDING_BUCKET = "recordings"

# Global FFmpeg availability flag - checked once at startup
_ffmpeg_available: Optional[bool] = None


def check_ffmpeg_available() -> bool:
    """Check if FFmpeg is available. Cached after first check."""
    global _ffmpeg_available
    if _ffmpeg_available is not None:
        return _ffmpeg_available

    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=5
        )
        _ffmpeg_available = result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        _ffmpeg_available = False

    return _ffmpeg_available


class CameraRecorder:
    """Handles recording for a single camera stream."""

    def __init__(
        self,
        camera_id: str,
        camera_name: str,
        rtsp_url: str,
        aibox_id: str,
        aibox_name: str
    ):
        self.camera_id = camera_id
        self.camera_name = camera_name
        self.rtsp_url = rtsp_url
        self.aibox_id = aibox_id
        self.aibox_name = aibox_name
        self.process: Optional[subprocess.Popen] = None
        self.current_file: Optional[str] = None
        self.recording_start: Optional[datetime] = None
        self.is_recording = False

    def _generate_filename(self) -> str:
        """Generate unique filename for recording chunk."""
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        unique_id = uuid4().hex[:8]
        safe_name = self.camera_name.replace(" ", "_").replace("/", "-")[:30]
        return f"ai_record_{safe_name}_{timestamp}_{unique_id}.mp4"

    async def start_chunk(self) -> bool:
        """Start recording a new 5-minute chunk."""
        # Kill any existing process first
        if self.process is not None:
            try:
                if self.process.poll() is None:  # Still running
                    self.process.terminate()
                    try:
                        self.process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        self.process.kill()
                        self.process.wait()
            except Exception:
                pass
            finally:
                self.process = None
                self.is_recording = False

        try:
            # Check if FFmpeg is available (uses cached result)
            if not check_ffmpeg_available():
                return False

            # Generate unique filename
            filename = self._generate_filename()
            self.current_file = os.path.join(tempfile.gettempdir(), filename)
            self.recording_start = datetime.utcnow()

            # FFmpeg command to record RTSP stream
            # -t: duration in seconds
            # -c copy: copy codec without re-encoding (faster)
            # -y: overwrite output file
            # Note: Timeout options vary by FFmpeg version, using basic options for compatibility
            cmd = [
                "ffmpeg",
                "-rtsp_transport", "tcp",  # Use TCP for more reliable streaming
                "-i", self.rtsp_url,
                "-t", str(CHUNK_DURATION_SECONDS),
                "-c", "copy",
                "-movflags", "+faststart",  # Enable fast start for web playback
                "-y",
                self.current_file
            ]

            logger.info(f"Starting recording: {self.camera_name} -> {filename}")

            # Start FFmpeg process
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE
            )
            self.is_recording = True
            return True

        except Exception as e:
            logger.error(f"Failed to start recording {self.camera_name}: {e}", exc_info=True)
            self.is_recording = False
            return False

    async def stop_chunk(self) -> Optional[str]:
        """Stop current recording chunk and upload to MinIO."""
        if not self.process:
            self.is_recording = False
            return None

        exit_code = None
        stderr_output = ""
        minio_path = None

        try:
            # Read any FFmpeg stderr output for debugging
            if self.process.stderr:
                try:
                    stderr_output = self.process.stderr.read().decode('utf-8', errors='ignore')[-500:]
                except:
                    pass

            # Check if process is still running
            if self.process.poll() is None:
                # Terminate FFmpeg process gracefully
                self.process.terminate()
                try:
                    self.process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    logger.warning(f"FFmpeg didn't terminate gracefully, killing: {self.camera_name}")
                    self.process.kill()

            # Always wait to reap the process (prevent zombie)
            try:
                self.process.wait()
                exit_code = self.process.returncode
            except:
                pass

        except Exception as e:
            logger.error(f"Error stopping FFmpeg process: {e}")
        finally:
            self.is_recording = False
            self.process = None

        # Log FFmpeg exit status only on error
        if exit_code != 0 and exit_code is not None:
            logger.warning(f"FFmpeg exited with code {exit_code} for {self.camera_name}: {stderr_output[:200] if stderr_output else 'no stderr'}")

        # Check if file was created and has content
        try:
            if self.current_file and os.path.exists(self.current_file):
                file_size = os.path.getsize(self.current_file)

                if file_size > 0:
                    # Upload to MinIO
                    minio_path = await self._upload_to_minio()
                    if minio_path:
                        # Save recording entry to database
                        await self._save_to_database(minio_path, file_size)
                        logger.info(f"Saved recording: {minio_path} ({file_size} bytes)")
                else:
                    logger.warning(f"Empty recording file for {self.camera_name}")
            else:
                logger.warning(f"Recording file not created for {self.camera_name}")
        except Exception as e:
            logger.error(f"Error processing recording file: {e}")
        finally:
            # Cleanup temp file
            if self.current_file and os.path.exists(self.current_file):
                try:
                    os.remove(self.current_file)
                except:
                    pass
            self.current_file = None

        return minio_path

    async def _upload_to_minio(self) -> Optional[str]:
        """Upload recording file to MinIO."""
        if not self.current_file or not os.path.exists(self.current_file):
            return None

        file_size = os.path.getsize(self.current_file)

        storage = get_minio_storage()
        if not storage.is_initialized:
            logger.debug("MinIO not initialized, skipping upload")
            return None

        try:
            # Generate MinIO object path
            date_path = datetime.utcnow().strftime("%Y/%m/%d")
            filename = os.path.basename(self.current_file)
            object_name = f"{date_path}/{filename}"

            # Upload file
            with open(self.current_file, "rb") as f:
                result = storage.upload_file(
                    settings.minio_bucket_recordings,
                    object_name,
                    f,
                    "video/mp4",
                    file_size
                )

            if result:
                return object_name
            return None

        except Exception as e:
            logger.error(f"Failed to upload to MinIO: {e}", exc_info=True)
            return None

    async def _save_to_database(self, minio_path: str, file_size: int):
        """Save recording entry to database."""
        db = SessionLocal()
        try:
            duration = CHUNK_DURATION_SECONDS
            if self.recording_start:
                actual_duration = (datetime.utcnow() - self.recording_start).total_seconds()
                duration = min(int(actual_duration), CHUNK_DURATION_SECONDS)

            recording = Recording(
                file_name=os.path.basename(minio_path),
                camera_name=self.camera_name,
                task_session=self.camera_id,
                start_time=self.recording_start or datetime.utcnow(),
                end_time=datetime.utcnow(),
                duration=duration,
                file_size=file_size,
                trigger_type="auto",
                minio_file_path=minio_path,
                minio_synced_at=datetime.utcnow(),
                is_available=True
            )
            db.add(recording)
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to save recording to DB: {e}")
        finally:
            db.close()

    def check_health(self) -> bool:
        """Check if FFmpeg process is still running."""
        if self.process and self.process.poll() is None:
            return True
        return False


class AutoRecorderService:
    """
    Service that automatically records all healthy AI camera streams.
    Records in 5-minute chunks, each saved with unique filename to MinIO.
    """

    def __init__(self):
        self.recorders: Dict[str, CameraRecorder] = {}
        self.running = False
        self._task: Optional[asyncio.Task] = None
        self._chunk_tasks: Dict[str, asyncio.Task] = {}

    async def start(self):
        """Start the auto-recorder service."""
        if not settings.minio_enabled:
            logger.info("MinIO disabled, auto-recorder not starting")
            return

        if not settings.auto_recorder_enabled:
            logger.info("Auto-recorder disabled by configuration")
            return

        # Check FFmpeg availability once at startup
        if not check_ffmpeg_available():
            logger.warning("FFmpeg not installed, auto-recorder disabled")
            return

        self.running = True
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info("Auto-recorder service started")

    def is_running(self) -> bool:
        """Check if auto-recorder is currently running."""
        return self.running and self._task is not None and not self._task.done()

    def get_status(self) -> dict:
        """Get current status of auto-recorder."""
        return {
            "enabled": settings.auto_recorder_enabled,
            "minio_enabled": settings.minio_enabled,
            "ffmpeg_available": check_ffmpeg_available(),
            "running": self.is_running(),
            "active_recorders": len(self.recorders),
            "cameras": [
                {
                    "camera_id": r.camera_id,
                    "camera_name": r.camera_name,
                    "is_recording": r.is_recording,
                    "aibox_name": r.aibox_name
                }
                for r in self.recorders.values()
            ]
        }

    def stop(self):
        """Stop the auto-recorder service."""
        self.running = False

        # Cancel all recording tasks
        for task in self._chunk_tasks.values():
            task.cancel()
        self._chunk_tasks.clear()

        # Stop all recorders and kill any FFmpeg processes
        for recorder in self.recorders.values():
            if recorder.process is not None:
                try:
                    if recorder.process.poll() is None:
                        recorder.process.kill()
                        recorder.process.wait()
                except Exception:
                    pass
        self.recorders.clear()

        if self._task:
            self._task.cancel()
            self._task = None

        logger.info("Auto-recorder service stopped")

    async def _monitor_loop(self):
        """Main monitoring loop - checks camera health and manages recordings."""
        # Wait for other services to initialize
        await asyncio.sleep(30)
        logger.info("Monitor loop started")

        while self.running:
            try:
                await self._update_recorders()
                # Only log if there are active recorders
                if self.recorders:
                    logger.debug(f"Active recorders: {len(self.recorders)}")
            except Exception as e:
                logger.error(f"Monitor loop error: {e}", exc_info=True)

            await asyncio.sleep(HEALTH_CHECK_INTERVAL)

    async def _update_recorders(self):
        """Update recorders based on current healthy cameras."""
        db = SessionLocal()
        try:
            # Get all active AI Boxes
            aiboxes = db.query(AIBox).filter(AIBox.is_active == True).all()

            if not aiboxes:
                return

            healthy_cameras: Set[str] = set()

            for aibox in aiboxes:
                # Fetch camera status from BM-APP
                cameras = await self._get_healthy_cameras(aibox)

                for camera in cameras:
                    camera_id = f"{aibox.id}_{camera['id']}"
                    healthy_cameras.add(camera_id)

                    # Start recording if not already recording
                    if camera_id not in self.recorders:
                        recorder = CameraRecorder(
                            camera_id=camera_id,
                            camera_name=camera['name'],
                            rtsp_url=camera['rtsp_url'],
                            aibox_id=str(aibox.id),
                            aibox_name=aibox.name
                        )
                        self.recorders[camera_id] = recorder
                        # Start chunk recording loop
                        self._chunk_tasks[camera_id] = asyncio.create_task(
                            self._chunk_recording_loop(camera_id)
                        )
                        logger.info(f"Started recorder for: {camera['name']}")

            # Stop recorders for cameras that are no longer healthy
            cameras_to_remove = set(self.recorders.keys()) - healthy_cameras
            for camera_id in cameras_to_remove:
                if camera_id in self._chunk_tasks:
                    self._chunk_tasks[camera_id].cancel()
                    del self._chunk_tasks[camera_id]

                recorder = self.recorders.pop(camera_id, None)
                if recorder:
                    await recorder.stop_chunk()
                    logger.info(f"Stopped recorder for: {recorder.camera_name}")

        finally:
            db.close()

    async def _chunk_recording_loop(self, camera_id: str):
        """Recording loop for a single camera - records in 5-minute chunks."""
        while self.running and camera_id in self.recorders:
            recorder = self.recorders.get(camera_id)
            if not recorder:
                break

            try:
                # Start a new chunk
                success = await recorder.start_chunk()
                if not success:
                    # Wait before retrying
                    await asyncio.sleep(60)
                    continue

                # Wait for chunk duration
                await asyncio.sleep(CHUNK_DURATION_SECONDS)

                # Stop and upload chunk
                await recorder.stop_chunk()

            except asyncio.CancelledError:
                # Gracefully stop on cancellation
                await recorder.stop_chunk()
                break
            except Exception as e:
                logger.error(f"Chunk recording error for {camera_id}: {e}")
                await asyncio.sleep(30)

    async def _get_healthy_cameras(self, aibox: AIBox) -> list:
        """
        Get list of healthy cameras from BM-APP.
        Returns list of dicts with: id, name, rtsp_url

        BM-APP AlgTaskStatus.type values:
        - 4 = Healthy (stream is active and working) <- Only this is used for recording
        - 1 = Connecting
        - 0 = Stopped
        """
        import httpx

        cameras = []

        try:
            # Fetch tasks from BM-APP API
            api_url = aibox.api_url.rstrip("/")
            full_url = f"{api_url}/alg_task_fetch"

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(full_url, json={})

                if response.status_code == 200:
                    data = response.json()
                    result_code = data.get("Result", {}).get("Code", -1)
                    if result_code != 0:
                        return cameras

                    raw_tasks = data.get("Content", [])
                    import json as json_lib

                    for raw_task in raw_tasks:
                        try:
                            # Parse "json" field if it's a string
                            task_config = {}
                            if "json" in raw_task:
                                task_json = raw_task.get("json", "{}")
                                if isinstance(task_json, str):
                                    try:
                                        task_config = json_lib.loads(task_json)
                                    except:
                                        task_config = {}
                                elif isinstance(task_json, dict):
                                    task_config = task_json

                            task_session = (
                                task_config.get("AlgTaskSession") or
                                raw_task.get("AlgTaskSession") or
                                raw_task.get("session") or
                                raw_task.get("name") or
                                ""
                            )

                            media_name = (
                                task_config.get("MediaName") or
                                raw_task.get("MediaName") or
                                raw_task.get("mediaName") or
                                task_session or
                                ""
                            )

                            # Status - check multiple locations
                            alg_task_status = (
                                raw_task.get("AlgTaskStatus") or
                                task_config.get("AlgTaskStatus") or
                                {}
                            )
                            if isinstance(alg_task_status, dict):
                                status_type = alg_task_status.get("type", 0)
                            else:
                                status_type = 0

                            # Only record cameras with status 4 (Healthy)
                            if status_type == 4:
                                rtsp_url = await self._get_media_url(aibox, media_name)
                                if rtsp_url:
                                    cameras.append({
                                        "id": task_session or media_name,
                                        "name": media_name,
                                        "rtsp_url": rtsp_url
                                    })

                        except Exception as e:
                            logger.debug(f"Error parsing task: {e}")
                            continue

        except Exception as e:
            logger.error(f"Failed to get cameras from {aibox.name}: {e}")

        return cameras

    async def _get_media_url(self, aibox: AIBox, media_name: str) -> Optional[str]:
        """
        Get RTSP URL for a media/camera from BM-APP.
        Uses /alg_media_fetch endpoint to get all configured media sources.
        """
        import httpx

        try:
            api_url = aibox.api_url.rstrip("/")
            full_url = f"{api_url}/alg_media_fetch"

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(full_url, json={})

                if response.status_code == 200:
                    data = response.json()
                    result_code = data.get("Result", {}).get("Code", -1)
                    if result_code != 0:
                        return None

                    media_list = data.get("Content", [])
                    import json as json_lib

                    for media in media_list:
                        if isinstance(media.get("json"), str):
                            try:
                                media_config = json_lib.loads(media.get("json", "{}"))
                            except:
                                media_config = media
                        else:
                            media_config = media

                        current_media_name = media_config.get("MediaName") or media.get("MediaName", "")

                        if current_media_name == media_name:
                            rtsp_url = media_config.get("MediaUrl") or media.get("MediaUrl", "")
                            if rtsp_url:
                                return rtsp_url

        except Exception as e:
            logger.debug(f"Failed to fetch media URL for {media_name}: {e}")

        return None


# Global instance
_service: Optional[AutoRecorderService] = None


def get_auto_recorder_service() -> Optional[AutoRecorderService]:
    """Get the global auto-recorder service instance."""
    return _service


async def start_auto_recorder():
    """Start the global auto-recorder service."""
    global _service
    if _service is None:
        _service = AutoRecorderService()
        await _service.start()


def stop_auto_recorder():
    """Stop the global auto-recorder service."""
    global _service
    if _service:
        _service.stop()
        _service = None
