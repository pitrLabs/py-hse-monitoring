import asyncio
import json
from datetime import datetime
from typing import Callable, Optional, Set
import websockets
from websockets.exceptions import ConnectionClosed
from app.config import settings

# Connected WebSocket clients for broadcasting alarms
connected_clients: Set = set()


class BmAppAlarmListener:
    """Listens to BM-APP WebSocket for real-time alarms"""

    def __init__(self, on_alarm: Optional[Callable] = None):
        self.ws_url = settings.bmapp_alarm_ws_url
        self.on_alarm = on_alarm
        self.running = False
        self._connection = None

    async def connect(self):
        """Connect to BM-APP WebSocket and listen for alarms"""
        if not settings.bmapp_enabled:
            print("BM-APP integration is disabled")
            return

        self.running = True
        retry_delay = 5

        while self.running:
            try:
                print(f"Connecting to BM-APP alarm WebSocket: {self.ws_url}")
                async with websockets.connect(self.ws_url) as ws:
                    self._connection = ws
                    retry_delay = 5  # Reset retry delay on successful connection
                    print("Connected to BM-APP alarm WebSocket")

                    while self.running:
                        try:
                            message = await asyncio.wait_for(ws.recv(), timeout=30)
                            await self._process_message(message)
                        except asyncio.TimeoutError:
                            # Send ping to keep connection alive
                            await ws.ping()

            except ConnectionClosed as e:
                print(f"BM-APP WebSocket connection closed: {e}")
            except Exception as e:
                print(f"BM-APP WebSocket error: {e}")

            if self.running:
                print(f"Reconnecting in {retry_delay} seconds...")
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 60)  # Exponential backoff, max 60s

    async def _process_message(self, message: str):
        """Process incoming alarm message from BM-APP"""
        try:
            data = json.loads(message)

            # Debug: Log raw alarm data to understand BM-APP format
            print(f"[BM-APP] Raw alarm received: {json.dumps(data, indent=2, default=str)[:500]}...")

            alarm = self._parse_alarm(data)

            # Debug: Log parsed alarm
            print(f"[BM-APP] Parsed alarm: type={alarm.get('alarm_type')}, camera={alarm.get('camera_name')}, conf={alarm.get('confidence')}, image={alarm.get('image_url')[:50] if alarm.get('image_url') else None}...")

            if alarm and self.on_alarm:
                await self.on_alarm(alarm)

            # Broadcast to connected WebSocket clients
            await broadcast_alarm(alarm or data)

        except json.JSONDecodeError as e:
            print(f"Failed to parse BM-APP message: {e}")
        except Exception as e:
            print(f"Error processing BM-APP alarm: {e}")

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

        From user's BM-APP UI observation:
        - Alarm Type: No Helmet
        - Alarm ID: NoHelmet (this is Result.Type)
        - Video Source: H8C-1 - rtsp://...  (MediaDesc - MediaUrl)
        - Confidence: 0.683594 (might be at root or in Properties)
        """

        # Extract nested objects
        media = data.get("Media", {}) or {}
        result = data.get("Result", {}) or {}
        properties = result.get("Properties", []) or []

        # ===== CONFIDENCE EXTRACTION =====
        # Priority: 1) Root level 2) Result.Properties 3) Result direct
        confidence = 0.0

        # First check root level (user reported seeing confidence at root)
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
        # Priority: Result.Type > root AlarmType > root Type
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
        # MediaDesc contains camera name like "H8C-1"
        camera_id = str(
            media.get("MediaName") or
            data.get("cameraId") or
            data.get("CameraId") or
            data.get("channelId") or
            ""
        )

        camera_name = (
            media.get("MediaDesc") or
            media.get("MediaName") or  # BM-APP often has name in MediaName when MediaDesc is empty
            data.get("cameraName") or
            data.get("CameraName") or
            data.get("TaskDesc") or
            ""
        )

        # Location - use MediaDesc or TaskDesc
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

        # ===== VIDEO URL =====
        video_url = (
            data.get("VideoFile") or
            data.get("videoUrl") or
            data.get("VideoUrl") or
            ""
        )

        # ===== ALARM TIME =====
        alarm_time = data.get("Time", "")
        if not alarm_time:
            timestamp_us = data.get("TimeStamp", 0)
            if timestamp_us:
                try:
                    alarm_time = datetime.fromtimestamp(timestamp_us / 1_000_000).isoformat()
                except (ValueError, OSError):
                    alarm_time = datetime.utcnow().isoformat()
            else:
                alarm_time = datetime.utcnow().isoformat()

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
            "description": description,
            "alarm_time": alarm_time,
            "raw_data": json.dumps(data)
        }

    def stop(self):
        """Stop the listener"""
        self.running = False
        if self._connection:
            asyncio.create_task(self._connection.close())


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


# Global listener instance
_alarm_listener: Optional[BmAppAlarmListener] = None


async def start_alarm_listener(on_alarm: Optional[Callable] = None):
    """Start the BM-APP alarm listener"""
    global _alarm_listener
    if _alarm_listener is None:
        _alarm_listener = BmAppAlarmListener(on_alarm)
        asyncio.create_task(_alarm_listener.connect())


def stop_alarm_listener():
    """Stop the BM-APP alarm listener"""
    global _alarm_listener
    if _alarm_listener:
        _alarm_listener.stop()
        _alarm_listener = None
