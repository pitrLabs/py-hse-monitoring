"""
Camera Status Polling Service
Polls MediaMTX and BM-APP for real-time camera online/offline status.
Broadcasts changes to connected WebSocket clients.
"""
import asyncio
import json
from typing import Dict, Optional, Set
import httpx
from app.config import settings


# Status types
STATUS_ONLINE = "online"
STATUS_OFFLINE = "offline"
STATUS_CONNECTING = "connecting"
STATUS_ERROR = "error"

# In-memory status store: { stream_name: { status, source, updated_at } }
_statuses: Dict[str, dict] = {}

# Connected WebSocket clients
connected_clients: Set = set()


class CameraStatusPoller:
    """Polls MediaMTX and BM-APP for camera status every N seconds"""

    def __init__(self):
        self.interval = settings.camera_status_poll_interval
        self.running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self):
        """Start the polling loop"""
        self.running = True
        self._task = asyncio.create_task(self._poll_loop())
        print(f"[CameraStatus] Polling started (interval={self.interval}s)")

    def stop(self):
        """Stop the polling loop"""
        self.running = False
        if self._task:
            self._task.cancel()
            self._task = None
        print("[CameraStatus] Polling stopped")

    async def _poll_loop(self):
        """Main polling loop"""
        while self.running:
            try:
                await self._poll()
            except Exception as e:
                print(f"[CameraStatus] Poll error: {e}")
            await asyncio.sleep(self.interval)

    async def _poll(self):
        """Poll all sources and broadcast changes"""
        new_statuses: Dict[str, dict] = {}

        # Poll MediaMTX
        mediamtx_statuses = await self._poll_mediamtx()
        new_statuses.update(mediamtx_statuses)

        # Poll BM-APP tasks
        if settings.bmapp_enabled:
            bmapp_statuses = await self._poll_bmapp()
            new_statuses.update(bmapp_statuses)

        # Detect changes and broadcast
        changes = self._diff_statuses(new_statuses)
        _statuses.clear()
        _statuses.update(new_statuses)

        if changes:
            await broadcast_status_update(changes)

    async def _poll_mediamtx(self) -> Dict[str, dict]:
        """Poll MediaMTX /v3/paths/list for stream status"""
        statuses = {}
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(
                    f"{settings.mediamtx_api_url}/v3/paths/list"
                )
                if response.status_code == 200:
                    data = response.json()
                    items = data.get("items", [])
                    for item in items:
                        name = item.get("name", "")
                        ready = item.get("ready", False)
                        source = item.get("source")
                        bytes_received = item.get("bytesReceived", 0)

                        if ready and source:
                            status = STATUS_ONLINE
                        elif source and not ready:
                            status = STATUS_CONNECTING
                        else:
                            status = STATUS_OFFLINE

                        statuses[name] = {
                            "status": status,
                            "source": "mediamtx",
                            "ready": ready,
                            "bytesReceived": bytes_received,
                        }
        except Exception as e:
            print(f"[CameraStatus] MediaMTX poll error: {e}")
        return statuses

    async def _poll_bmapp(self) -> Dict[str, dict]:
        """Poll all active AI Boxes for AI task status"""
        statuses = {}
        try:
            from app.database import SessionLocal
            from app.models import AIBox
            db = SessionLocal()
            try:
                aiboxes = db.query(AIBox).filter(AIBox.is_active == True).all()
                aibox_data = [(str(b.id), b.name, b.api_url) for b in aiboxes]
            finally:
                db.close()

            for aibox_id, aibox_name, api_url in aibox_data:
                try:
                    await self._poll_single_aibox(statuses, aibox_id, aibox_name, api_url)
                except Exception as e:
                    print(f"[CameraStatus] BM-APP poll error for {aibox_name}: {e}")
        except Exception as e:
            print(f"[CameraStatus] BM-APP poll error: {e}")
        return statuses

    async def _poll_single_aibox(self, statuses: Dict[str, dict], aibox_id: str, aibox_name: str, api_url: str):
        """Poll a single AI Box for task statuses"""
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(
                f"{api_url.rstrip('/')}/alg_task_fetch",
                json={}
            )
            if response.status_code != 200:
                return

            data = response.json()
            if data.get("Result", {}).get("Code", -1) != 0:
                return

            tasks = data.get("Content", [])

        for task in tasks:
            session = task.get("AlgTaskSession", "").strip()
            if not session:
                continue

            # AlgTaskStatus.type: 4=Healthy, 1=Connecting, 0=Stopped, 2=Error
            task_status = task.get("AlgTaskStatus", {})
            status_type = task_status.get("type", 0) if isinstance(task_status, dict) else 0

            if status_type == 4:
                status = STATUS_ONLINE
            elif status_type == 1:
                status = STATUS_CONNECTING
            elif status_type == 2:
                status = STATUS_ERROR
            else:
                status = STATUS_OFFLINE

            media_name = task.get("MediaName", "").strip()
            status_entry = {
                "status": status,
                "source": "bmapp",
                "aibox": aibox_name,
                "taskSession": session,
                "mediaName": media_name,
            }

            # Store by session key for BM-APP lookups
            key = f"bmapp:{session}"
            statuses[key] = status_entry

            # Also store by MediaName (which matches stream_name) for Video Sources lookup
            if media_name:
                statuses[media_name] = status_entry

    def _diff_statuses(self, new_statuses: Dict[str, dict]) -> Dict[str, dict]:
        """Return only statuses that changed"""
        changes = {}
        all_keys = set(list(_statuses.keys()) + list(new_statuses.keys()))

        for key in all_keys:
            old = _statuses.get(key, {}).get("status")
            new = new_statuses.get(key, {}).get("status")

            if old != new:
                if key in new_statuses:
                    changes[key] = new_statuses[key]
                else:
                    # Stream was removed
                    changes[key] = {"status": STATUS_OFFLINE, "source": "removed"}

        return changes


def get_all_statuses() -> Dict[str, dict]:
    """Get current snapshot of all camera statuses"""
    return dict(_statuses)


def get_status(stream_name: str) -> str:
    """Get status for a specific stream"""
    entry = _statuses.get(stream_name)
    return entry["status"] if entry else STATUS_OFFLINE


# ============ WebSocket Client Management ============

def add_client(websocket):
    """Add a WebSocket client to broadcast list"""
    connected_clients.add(websocket)


def remove_client(websocket):
    """Remove a WebSocket client from broadcast list"""
    connected_clients.discard(websocket)


async def broadcast_status_update(changes: Dict[str, dict]):
    """Broadcast status changes to all connected WebSocket clients"""
    if not connected_clients:
        return

    message = json.dumps({
        "type": "status_update",
        "data": changes
    })

    disconnected = set()
    for client in connected_clients:
        try:
            await client.send_text(message)
        except Exception:
            disconnected.add(client)

    for client in disconnected:
        connected_clients.discard(client)


async def send_snapshot(websocket):
    """Send current status snapshot to a single client"""
    message = json.dumps({
        "type": "status_snapshot",
        "data": _statuses
    })
    await websocket.send_text(message)


# ============ Global Poller Instance ============

_poller: Optional[CameraStatusPoller] = None


async def start_camera_status_poller():
    """Start the camera status poller"""
    global _poller
    if _poller is None:
        _poller = CameraStatusPoller()
        await _poller.start()


def stop_camera_status_poller():
    """Stop the camera status poller"""
    global _poller
    if _poller:
        _poller.stop()
        _poller = None
