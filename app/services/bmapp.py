import asyncio
import json
from typing import Callable, Optional, Set, Dict, List
from uuid import UUID
import websockets
from websockets.exceptions import ConnectionClosed
from sqlalchemy.orm import Session
from app.config import settings
from app.database import SessionLocal
from app.models import AIBox
from app.utils.timezone import parse_bmapp_time, parse_bmapp_timestamp_us, now_utc

# Connected WebSocket clients for broadcasting alarms
connected_clients: Set = set()


class BmAppAlarmListener:
    """Listens to a single AI Box WebSocket for real-time alarms"""

    def __init__(
        self,
        ws_url: str,
        aibox_id: Optional[str] = None,
        aibox_name: Optional[str] = None,
        aibox_code: Optional[str] = None,
        on_alarm: Optional[Callable] = None
    ):
        self.ws_url = ws_url
        self.aibox_id = aibox_id
        self.aibox_name = aibox_name
        self.aibox_code = aibox_code
        self.on_alarm = on_alarm
        self.running = False
        self._connection = None

    async def connect(self):
        """Connect to AI Box WebSocket and listen for alarms"""
        self.running = True
        retry_delay = 5
        box_label = f"[{self.aibox_code or 'LEGACY'}]"

        while self.running:
            try:
                print(f"{box_label} Connecting to alarm WebSocket: {self.ws_url}")
                async with websockets.connect(self.ws_url) as ws:
                    self._connection = ws
                    retry_delay = 5  # Reset retry delay on successful connection
                    print(f"{box_label} Connected to alarm WebSocket")

                    while self.running:
                        try:
                            message = await asyncio.wait_for(ws.recv(), timeout=30)
                            await self._process_message(message)
                        except asyncio.TimeoutError:
                            # Send ping to keep connection alive
                            await ws.ping()

            except ConnectionClosed as e:
                print(f"{box_label} WebSocket connection closed: {e}")
            except Exception as e:
                print(f"{box_label} WebSocket error: {e}")

            if self.running:
                print(f"{box_label} Reconnecting in {retry_delay} seconds...")
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 60)  # Exponential backoff, max 60s

    async def _process_message(self, message: str):
        """Process incoming alarm message from AI Box"""
        box_label = f"[{self.aibox_code or 'LEGACY'}]"
        try:
            data = json.loads(message)

            # Debug: Log raw alarm data
            print(f"{box_label} Raw alarm received: {json.dumps(data, indent=2, default=str)[:500]}...")

            alarm = self._parse_alarm(data)

            # Debug: Log parsed alarm
            print(f"{box_label} Parsed alarm: type={alarm.get('alarm_type')}, camera={alarm.get('camera_name')}, conf={alarm.get('confidence')}")

            if alarm and self.on_alarm:
                await self.on_alarm(alarm)

            # Broadcast to connected WebSocket clients
            await broadcast_alarm(alarm or data)

        except json.JSONDecodeError as e:
            print(f"{box_label} Failed to parse message: {e}")
        except Exception as e:
            print(f"{box_label} Error processing alarm: {e}")

    def _parse_alarm(self, data: dict) -> dict:
        """Parse BM-APP alarm format to our format

        BM-APP sends alarm in this format (from documentation 02-http-reporting.md):
        {
          "BoardId": "RJ-BOX-XXX",
          "AlarmId": "uuid",
          "TaskSession": "task_001",
          "TaskDesc": "description",
          "Time": "YYYY-MM-DD HH:mm:ss",
          "TimeStamp": 1699426698084625,
          "VideoFile": "VideoId",
          "Media": {
            "MediaName": "1",
            "MediaUrl": "rtsp://...",
            "MediaDesc": "H8C-1",
            "MediaWidth": 1920,
            "MediaHeight": 1080
          },
          "Result": {
            "Type": "NoHelmet",
            "Description": "No helmet detected",
            "RelativeBox": [x,y,w,h],
            "Properties": [{"property": "confidence", "value": 0.68}]
          },
          "ImageData": "base64...",
          "ImageDataLabeled": "base64...",
          "Summary": "string"
        }
        """

        # Extract nested objects
        media = data.get("Media", {}) or {}
        result = data.get("Result", {}) or {}
        properties = result.get("Properties", []) or []

        # ===== CONFIDENCE EXTRACTION =====
        confidence = 0.0

        # First check root level
        if "Confidence" in data or "confidence" in data:
            try:
                confidence = float(data.get("Confidence", data.get("confidence", 0)) or 0)
            except (ValueError, TypeError):
                pass

        # Then check Result.Properties array
        if confidence == 0:
            for prop in properties:
                if isinstance(prop, dict):
                    key = prop.get("property", prop.get("Property", "")).lower()
                    if key in ("confidence", "score", "similarity", "prob"):
                        try:
                            confidence = float(prop.get("value", prop.get("Value", 0)) or 0)
                        except (ValueError, TypeError):
                            pass
                        break

        # Check other common fields
        if confidence == 0:
            for field in ["score", "Score", "probability", "Probability"]:
                if field in data:
                    try:
                        confidence = float(data.get(field, 0) or 0)
                        break
                    except (ValueError, TypeError):
                        pass

        # ===== ALARM TYPE EXTRACTION =====
        alarm_type = (
            result.get("Type") or
            result.get("type") or
            data.get("AlarmType") or
            data.get("alarmType") or
            data.get("Type") or
            data.get("type") or
            "Unknown"
        )

        # ===== ALARM NAME/DESCRIPTION =====
        alarm_name = (
            data.get("TaskDesc") or
            result.get("Description") or
            result.get("description") or
            data.get("alarmName") or
            data.get("AlarmName") or
            f"{alarm_type} Detected"
        )

        # ===== CAMERA INFO EXTRACTION =====
        camera_id = str(
            media.get("MediaName") or
            data.get("cameraId") or
            data.get("CameraId") or
            data.get("channelId") or
            ""
        )

        camera_name = (
            media.get("MediaDesc") or
            media.get("MediaName") or
            data.get("cameraName") or
            data.get("CameraName") or
            data.get("TaskDesc") or
            ""
        )

        # Location
        location = (
            data.get("location") or
            data.get("Location") or
            media.get("MediaDesc") or
            data.get("TaskDesc") or
            ""
        )

        # ===== IMAGE URL =====
        image_url = (
            data.get("imageUrl") or
            data.get("ImageUrl") or
            data.get("picUrl") or
            data.get("PicUrl") or
            data.get("LocalLabeledPath") or
            data.get("LocalRawPath") or
            ""
        )

        # ===== BASE64 IMAGE DATA (for direct storage to MinIO) =====
        image_data_base64 = data.get("ImageData") or data.get("imageData") or ""
        labeled_image_data_base64 = data.get("ImageDataLabeled") or data.get("imageDataLabeled") or ""

        # Debug logging for image data
        print(f"[BmApp] Alarm parsed - imageUrl: {image_url[:100] if image_url else 'NONE'}")
        print(f"[BmApp] ImageData: {len(image_data_base64)} chars, ImageDataLabeled: {len(labeled_image_data_base64)} chars")

        # ===== MEDIA URL (RTSP) =====
        media_url = (
            media.get("MediaUrl") or
            media.get("mediaUrl") or
            data.get("MediaUrl") or
            data.get("mediaUrl") or
            ""
        )

        # ===== VIDEO URL =====
        video_url = (
            data.get("VideoFile") or
            data.get("videoUrl") or
            data.get("VideoUrl") or
            ""
        )

        # ===== ALARM TIME =====
        # BM-APP sends time in China timezone (UTC+8), convert to UTC
        time_str = data.get("Time", "")
        timestamp_us = data.get("TimeStamp", 0)

        if time_str:
            alarm_time = parse_bmapp_time(time_str).isoformat()
        elif timestamp_us:
            alarm_time = parse_bmapp_timestamp_us(timestamp_us).isoformat()
        else:
            alarm_time = now_utc().isoformat()

        # ===== DESCRIPTION/SUMMARY =====
        description = (
            data.get("Summary") or
            result.get("Description") or
            result.get("description") or
            data.get("description") or
            ""
        )

        # ===== BMAPP ID =====
        bmapp_id = str(
            data.get("AlarmId") or
            data.get("alarmId") or
            data.get("id") or
            data.get("Id") or
            ""
        )

        return {
            "bmapp_id": bmapp_id,
            "alarm_type": alarm_type,
            "alarm_name": alarm_name,
            "camera_id": camera_id,
            "camera_name": camera_name,
            "location": location,
            "confidence": confidence,
            "image_url": image_url,
            "video_url": video_url,
            "media_url": media_url,  # RTSP URL for video source
            "description": description,
            "alarm_time": alarm_time,
            "raw_data": json.dumps(data),
            # Base64 image data for MinIO storage
            "image_data_base64": image_data_base64,
            "labeled_image_data_base64": labeled_image_data_base64,
            # AI Box info
            "aibox_id": self.aibox_id,
            "aibox_name": self.aibox_name,
        }

    def stop(self):
        """Stop the listener"""
        self.running = False
        if self._connection:
            asyncio.create_task(self._connection.close())


class MultiAIBoxAlarmManager:
    """Manages alarm listeners for multiple AI Boxes"""

    def __init__(self, on_alarm: Optional[Callable] = None):
        self.on_alarm = on_alarm
        self.listeners: Dict[str, BmAppAlarmListener] = {}
        self.running = False
        self._refresh_task: Optional[asyncio.Task] = None

    def _get_active_aiboxes(self) -> List[AIBox]:
        """Get active AI Boxes from database"""
        db: Session = SessionLocal()
        try:
            return db.query(AIBox).filter(AIBox.is_active == True).all()
        finally:
            db.close()

    async def start(self):
        """Start listening to all active AI Boxes"""
        self.running = True
        print("[MultiAIBoxAlarmManager] Starting...")

        # Initial load
        await self._refresh_listeners()

        # Start periodic refresh task (every 60 seconds)
        self._refresh_task = asyncio.create_task(self._periodic_refresh())

    async def _refresh_listeners(self):
        """Refresh listeners based on current AI Boxes in database"""
        aiboxes = self._get_active_aiboxes()
        current_ids = set(self.listeners.keys())
        new_ids = {str(box.id) for box in aiboxes}

        # Stop listeners for removed/deactivated AI Boxes
        for box_id in current_ids - new_ids:
            print(f"[MultiAIBoxAlarmManager] Stopping listener for removed AI Box: {box_id}")
            self.listeners[box_id].stop()
            del self.listeners[box_id]

        # Start listeners for new AI Boxes
        for box in aiboxes:
            box_id = str(box.id)
            if box_id not in self.listeners:
                print(f"[MultiAIBoxAlarmManager] Starting listener for AI Box: {box.name} ({box.code})")
                listener = BmAppAlarmListener(
                    ws_url=box.alarm_ws_url,
                    aibox_id=box_id,
                    aibox_name=box.name,
                    aibox_code=box.code,
                    on_alarm=self.on_alarm
                )
                self.listeners[box_id] = listener
                asyncio.create_task(listener.connect())

        if len(self.listeners) == 0:
            print("[MultiAIBoxAlarmManager] No active AI Boxes configured. Add AI Boxes via /admin/ai-boxes")
        else:
            print(f"[MultiAIBoxAlarmManager] Active listeners: {len(self.listeners)}")

    async def _periodic_refresh(self):
        """Periodically refresh AI Box listeners"""
        while self.running:
            await asyncio.sleep(60)  # Check every 60 seconds
            if self.running:
                await self._refresh_listeners()

    def stop(self):
        """Stop all listeners"""
        self.running = False
        if self._refresh_task:
            self._refresh_task.cancel()
        for listener in self.listeners.values():
            listener.stop()
        self.listeners.clear()
        print("[MultiAIBoxAlarmManager] Stopped all listeners")


async def broadcast_alarm(alarm: dict):
    """Broadcast alarm to all connected WebSocket clients"""
    if not connected_clients:
        return

    message = json.dumps({
        "type": "alarm",
        "data": alarm
    })

    disconnected = set()
    for client in connected_clients:
        try:
            await client.send_text(message)
        except Exception:
            disconnected.add(client)

    # Remove disconnected clients
    for client in disconnected:
        connected_clients.discard(client)


def add_client(websocket):
    """Add a WebSocket client to broadcast list"""
    connected_clients.add(websocket)


def remove_client(websocket):
    """Remove a WebSocket client from broadcast list"""
    connected_clients.discard(websocket)


# Global manager instance
_alarm_manager: Optional[MultiAIBoxAlarmManager] = None


async def start_alarm_listener(on_alarm: Optional[Callable] = None):
    """Start the alarm listeners for all AI Boxes from database"""
    global _alarm_manager

    if not settings.bmapp_enabled:
        print("[AlarmListener] BM-APP integration is disabled")
        return

    # Use multi AI Box manager (reads from database)
    if _alarm_manager is None:
        _alarm_manager = MultiAIBoxAlarmManager(on_alarm)
        asyncio.create_task(_alarm_manager.start())


def stop_alarm_listener():
    """Stop all alarm listeners"""
    global _alarm_manager

    if _alarm_manager:
        _alarm_manager.stop()
        _alarm_manager = None
