"""
Auto Recorder Service
Automatically records healthy AI camera streams to MinIO in 5-minute chunks.
Each chunk saved with unique filename (no overwrite).
"""
import asyncio
import subprocess
import os
import tempfile
from datetime import datetime
from typing import Optional, Dict, Set
from uuid import uuid4

from app.config import settings
from app.database import SessionLocal
from app.models import AIBox, Recording
from app.services.minio_storage import get_minio_storage


# Configuration
CHUNK_DURATION_SECONDS = 300  # 5 minutes per chunk
HEALTH_CHECK_INTERVAL = 30  # Check camera health every 30 seconds
RECORDING_BUCKET = "recordings"


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
        if self.is_recording:
            await self.stop_chunk()

        try:
            # Check if FFmpeg is available
            try:
                result = subprocess.run(
                    ["ffmpeg", "-version"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=5
                )
                if result.returncode != 0:
                    print("[AutoRecorder] FFmpeg not available or not working properly")
                    return False
            except FileNotFoundError:
                print("[AutoRecorder] FFmpeg not installed! Please install FFmpeg to enable auto-recording.")
                return False
            except subprocess.TimeoutExpired:
                print("[AutoRecorder] FFmpeg check timed out")
                return False

            # Generate unique filename
            filename = self._generate_filename()
            self.current_file = os.path.join(tempfile.gettempdir(), filename)
            self.recording_start = datetime.utcnow()

            # FFmpeg command to record RTSP stream
            # -t: duration in seconds
            # -c copy: copy codec without re-encoding (faster)
            # -y: overwrite output file
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

            print(f"[AutoRecorder] Starting recording: {self.camera_name} -> {filename}")
            print(f"[AutoRecorder] RTSP URL: {self.rtsp_url}")

            # Start FFmpeg process
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE
            )
            self.is_recording = True
            return True

        except Exception as e:
            print(f"[AutoRecorder] Failed to start recording {self.camera_name}: {e}")
            import traceback
            traceback.print_exc()
            self.is_recording = False
            return False

    async def stop_chunk(self) -> Optional[str]:
        """Stop current recording chunk and upload to MinIO."""
        if not self.is_recording or not self.process:
            return None

        try:
            # Read any FFmpeg stderr output for debugging
            stderr_output = ""
            if self.process.stderr:
                try:
                    stderr_output = self.process.stderr.read().decode('utf-8', errors='ignore')[-500:]
                except:
                    pass

            # Terminate FFmpeg process gracefully
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                print(f"[AutoRecorder] FFmpeg didn't terminate gracefully, killing: {self.camera_name}")
                self.process.kill()

            exit_code = self.process.returncode
            self.is_recording = False
            self.process = None

            # Log FFmpeg exit status
            if exit_code != 0 and exit_code is not None:
                print(f"[AutoRecorder] FFmpeg exited with code {exit_code} for {self.camera_name}")
                if stderr_output:
                    print(f"[AutoRecorder] FFmpeg stderr: {stderr_output}")

            # Check if file was created and has content
            if self.current_file and os.path.exists(self.current_file):
                file_size = os.path.getsize(self.current_file)
                print(f"[AutoRecorder] Recording file size: {file_size} bytes for {self.camera_name}")

                if file_size > 0:
                    # Upload to MinIO
                    minio_path = await self._upload_to_minio()
                    if minio_path:
                        # Save recording entry to database
                        await self._save_to_database(minio_path, file_size)
                        print(f"[AutoRecorder] Successfully saved recording: {minio_path}")
                    return minio_path
                else:
                    print(f"[AutoRecorder] Empty recording file: {self.current_file}")
                    if stderr_output:
                        print(f"[AutoRecorder] FFmpeg stderr: {stderr_output}")
            else:
                print(f"[AutoRecorder] Recording file not created: {self.current_file}")

            return None

        except Exception as e:
            print(f"[AutoRecorder] Error stopping recording {self.camera_name}: {e}")
            import traceback
            traceback.print_exc()
            return None
        finally:
            # Cleanup temp file
            if self.current_file and os.path.exists(self.current_file):
                try:
                    os.remove(self.current_file)
                except:
                    pass
            self.current_file = None

    async def _upload_to_minio(self) -> Optional[str]:
        """Upload recording file to MinIO."""
        if not self.current_file or not os.path.exists(self.current_file):
            print(f"[AutoRecorder] Upload skipped - file not found: {self.current_file}")
            return None

        file_size = os.path.getsize(self.current_file)
        print(f"[AutoRecorder] Preparing to upload: {self.current_file} ({file_size} bytes)")

        storage = get_minio_storage()
        if not storage.is_initialized:
            print("[AutoRecorder] MinIO not initialized, skipping upload")
            return None

        try:
            # Generate MinIO object path
            date_path = datetime.utcnow().strftime("%Y/%m/%d")
            filename = os.path.basename(self.current_file)
            object_name = f"{date_path}/{filename}"

            print(f"[AutoRecorder] Uploading to bucket: {settings.minio_bucket_recordings}, path: {object_name}")

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
                print(f"[AutoRecorder] Successfully uploaded to MinIO: {object_name}")
                return object_name
            else:
                print(f"[AutoRecorder] Upload returned None/False for: {object_name}")
                return None

        except Exception as e:
            print(f"[AutoRecorder] Failed to upload to MinIO: {e}")
            import traceback
            traceback.print_exc()
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
            print(f"[AutoRecorder] Saved recording to DB: {self.camera_name} ({duration}s)")
        except Exception as e:
            db.rollback()
            print(f"[AutoRecorder] Failed to save recording to DB: {e}")
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
            print("[AutoRecorder] MinIO disabled, auto-recorder not starting")
            return

        self.running = True
        self._task = asyncio.create_task(self._monitor_loop())
        print("[AutoRecorder] Service started")

    def stop(self):
        """Stop the auto-recorder service."""
        self.running = False

        # Cancel all recording tasks
        for task in self._chunk_tasks.values():
            task.cancel()
        self._chunk_tasks.clear()

        # Stop all recorders
        for recorder in self.recorders.values():
            if recorder.is_recording:
                asyncio.create_task(recorder.stop_chunk())
        self.recorders.clear()

        if self._task:
            self._task.cancel()
            self._task = None

        print("[AutoRecorder] Service stopped")

    async def _monitor_loop(self):
        """Main monitoring loop - checks camera health and manages recordings."""
        # Wait for other services to initialize
        print("[AutoRecorder] Waiting 30 seconds for services to initialize...")
        await asyncio.sleep(30)
        print("[AutoRecorder] Starting monitor loop...")

        while self.running:
            try:
                await self._update_recorders()
                print(f"[AutoRecorder] Active recorders: {len(self.recorders)}")
            except Exception as e:
                print(f"[AutoRecorder] Monitor loop error: {e}")
                import traceback
                traceback.print_exc()

            await asyncio.sleep(HEALTH_CHECK_INTERVAL)

    async def _update_recorders(self):
        """Update recorders based on current healthy cameras."""
        db = SessionLocal()
        try:
            # Get all active AI Boxes
            aiboxes = db.query(AIBox).filter(AIBox.is_active == True).all()

            if not aiboxes:
                print("[AutoRecorder] No active AI Boxes found in database")
                return

            print(f"[AutoRecorder] Checking {len(aiboxes)} AI Box(es) for healthy cameras...")

            healthy_cameras: Set[str] = set()

            for aibox in aiboxes:
                print(f"[AutoRecorder] Checking AI Box: {aibox.name} ({aibox.api_url})")
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
                        print(f"[AutoRecorder] Started recorder for: {camera['name']}")

            # Stop recorders for cameras that are no longer healthy
            cameras_to_remove = set(self.recorders.keys()) - healthy_cameras
            for camera_id in cameras_to_remove:
                if camera_id in self._chunk_tasks:
                    self._chunk_tasks[camera_id].cancel()
                    del self._chunk_tasks[camera_id]

                recorder = self.recorders.pop(camera_id, None)
                if recorder:
                    await recorder.stop_chunk()
                    print(f"[AutoRecorder] Stopped recorder for: {recorder.camera_name}")

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
                print(f"[AutoRecorder] Chunk recording error for {camera_id}: {e}")
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
            full_url = f"{api_url}/app_task_status"
            print(f"[AutoRecorder] Fetching task status from: {full_url}")

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(full_url)
                print(f"[AutoRecorder] Response status: {response.status_code}")

                if response.status_code == 200:
                    data = response.json()
                    tasks = data.get("TaskList", [])
                    print(f"[AutoRecorder] Found {len(tasks)} tasks from {aibox.name}")

                    for task in tasks:
                        # Check AlgTaskStatus.type - 4=Healthy means stream is active
                        alg_task_status = task.get("AlgTaskStatus", {})
                        status_type = alg_task_status.get("type", 0) if isinstance(alg_task_status, dict) else 0
                        task_name = task.get("AlgTaskSession", "unknown")
                        media = task.get("Media", {}) or {}
                        media_name = media.get("MediaName", "unknown")

                        print(f"[AutoRecorder] Task: {task_name}, Media: {media_name}, Status: {status_type}")

                        # Only record cameras with status 4 (Healthy)
                        if status_type == 4:
                            media = task.get("Media", {}) or {}
                            rtsp_url = media.get("MediaUrl", "")

                            if rtsp_url:
                                camera_info = {
                                    "id": task.get("AlgTaskSession", task.get("MediaName", "")),
                                    "name": media.get("MediaName", task.get("MediaName", "Unknown")),
                                    "rtsp_url": rtsp_url
                                }
                                cameras.append(camera_info)
                                print(f"[AutoRecorder] Found healthy camera: {camera_info['name']} (status={status_type})")

                    if cameras:
                        print(f"[AutoRecorder] Found {len(cameras)} healthy cameras from {aibox.name}")
                    else:
                        print(f"[AutoRecorder] No healthy cameras found from {aibox.name}")

        except Exception as e:
            print(f"[AutoRecorder] Failed to get cameras from {aibox.name}: {e}")

        return cameras


# Global instance
_service: Optional[AutoRecorderService] = None


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
