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
            alarm = self._parse_alarm(data)

            if alarm and self.on_alarm:
                await self.on_alarm(alarm)

            # Broadcast to connected WebSocket clients
            await broadcast_alarm(alarm or data)

        except json.JSONDecodeError as e:
            print(f"Failed to parse BM-APP message: {e}")
        except Exception as e:
            print(f"Error processing BM-APP alarm: {e}")

    def _parse_alarm(self, data: dict) -> dict:
        """Parse BM-APP alarm format to our format"""
        # BM-APP alarm format may vary, adjust based on actual data
        return {
            "bmapp_id": str(data.get("id", "")),
            "alarm_type": data.get("alarmType", data.get("type", "Unknown")),
            "alarm_name": data.get("alarmName", data.get("name", "Detection Alert")),
            "camera_id": str(data.get("cameraId", data.get("channelId", ""))),
            "camera_name": data.get("cameraName", data.get("channelName", "")),
            "location": data.get("location", ""),
            "confidence": float(data.get("confidence", data.get("score", 0)) or 0),
            "image_url": data.get("imageUrl", data.get("picUrl", "")),
            "video_url": data.get("videoUrl", ""),
            "description": data.get("description", data.get("desc", "")),
            "alarm_time": data.get("alarmTime", data.get("time", datetime.utcnow().isoformat())),
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
