"""
BM-APP REST API Client
Handles communication with BM-APP for camera and AI task management
"""
import httpx
from typing import Optional, List, Dict, Any
from app.config import settings


class BmAppClient:
    """Client for BM-APP REST API"""

    def __init__(self):
        self.base_url = settings.bmapp_api_url.rstrip('/')
        self.timeout = 30.0

    async def _request(self, endpoint: str, data: dict = None) -> dict:
        """Make a POST request to BM-APP API"""
        url = f"{self.base_url}{endpoint}"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                url,
                json=data or {},
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()
            return response.json()

    # ==================== Media (Camera) APIs ====================

    async def get_media_list(self) -> List[dict]:
        """Fetch all media/cameras from BM-APP"""
        result = await self._request("/alg_media_fetch")
        if result.get("Result", {}).get("Code") == 0:
            return result.get("Content", [])
        raise Exception(result.get("Result", {}).get("Desc", "Failed to fetch media"))

    async def add_media(
        self,
        media_name: str,
        media_url: str,
        media_desc: str = "",
        rtsp_transport: bool = False
    ) -> dict:
        """Add a new media/camera to BM-APP"""
        data = {
            "MediaName": media_name,
            "MediaUrl": media_url,
            "MediaDesc": media_desc,
            "RtspTransport": rtsp_transport,
            "GBTransport": False,
            "Params": [
                {"Key": "GB28181ChannelId", "Name": "GB28181 Channel", "Type": "INPUT", "Value": ""},
                {"Key": "SipBChannelId", "Name": "STAT GRID SipB Channel", "Type": "INPUT", "Value": ""}
            ]
        }
        result = await self._request("/alg_media_config", data)
        if result.get("Result", {}).get("Code") == 0:
            return result
        raise Exception(result.get("Result", {}).get("Desc", "Failed to add media"))

    async def update_media(
        self,
        media_name: str,
        media_url: str,
        media_desc: str = "",
        rtsp_transport: bool = False
    ) -> dict:
        """Update an existing media/camera in BM-APP"""
        # In BM-APP, update is same as config - it updates if exists
        return await self.add_media(media_name, media_url, media_desc, rtsp_transport)

    async def delete_media(self, media_name: str) -> dict:
        """Delete a media/camera from BM-APP"""
        data = {"MediaName": media_name}
        result = await self._request("/alg_media_delete", data)
        if result.get("Result", {}).get("Code") == 0:
            return result
        raise Exception(result.get("Result", {}).get("Desc", "Failed to delete media"))

    async def probe_media(self, media_url: str) -> dict:
        """Probe a media URL to check if it's valid"""
        data = {"MediaUrl": media_url}
        result = await self._request("/alg_probe_media", data)
        return result

    # ==================== Task APIs ====================

    async def get_task_list(self) -> List[dict]:
        """Fetch all AI tasks from BM-APP"""
        result = await self._request("/alg_task_fetch")
        if result.get("Result", {}).get("Code") == 0:
            return result.get("Content", [])
        raise Exception(result.get("Result", {}).get("Desc", "Failed to fetch tasks"))

    async def create_task(
        self,
        task_session: str,
        media_name: str,
        alg_info: List[int],
        method_config: List[int],
        user_data: Optional[dict] = None,
        task_desc: str = "",
        restart: bool = True,
        enable_mp4_record: int = -1
    ) -> dict:
        """Create a new AI task in BM-APP"""
        data = {
            "AlgTaskSession": task_session,
            "MediaName": media_name,
            "AlgInfo": alg_info,
            "TaskDesc": task_desc,
            "Restart": restart,
            "EnableMp4Record": enable_mp4_record,
            "ScheduleId": -1,
            "ConditionId": 0,
            "AlarmBody": 0,
            "AlarmProtocol": 0,
            "Sensors": [],
            "MetadataUrl": "",
            "GB28181Channel": "",
            "SipBChannel": "",
            "UserData": {
                "MethodConfig": method_config,
                "enable_people_deep_mode": False,
                "helmet_det_threshold": 0.5,
                "helmet_v3_keep_no_sec": 5,
                "helmet_v3_repeat_sec": 0,
                "no_helmet_det_threshold": 0.7,
                "threshold_for_people": 0.5,
                **(user_data or {})
            }
        }
        result = await self._request("/alg_task_config", data)
        if result.get("Result", {}).get("Code") == 0:
            return result
        raise Exception(result.get("Result", {}).get("Desc", "Failed to create task"))

    async def update_task(
        self,
        task_session: str,
        media_name: str,
        alg_info: List[int],
        method_config: List[int],
        user_data: Optional[dict] = None,
        task_desc: str = "",
        restart: bool = True
    ) -> dict:
        """Update an existing AI task in BM-APP"""
        return await self.create_task(
            task_session, media_name, alg_info, method_config, user_data, task_desc, restart
        )

    async def delete_task(self, task_session: str) -> dict:
        """Delete an AI task from BM-APP"""
        data = {"AlgTaskSession": task_session}
        result = await self._request("/alg_task_delete", data)
        if result.get("Result", {}).get("Code") == 0:
            return result
        raise Exception(result.get("Result", {}).get("Desc", "Failed to delete task"))

    async def control_task(self, task_session: str, action: str) -> dict:
        """Start or stop an AI task

        Args:
            task_session: The task session name
            action: "start" or "stop"

        Note: BM-APP task control may require the task to be reconfigured
        rather than using the control endpoint directly.
        """
        # Try multiple parameter formats since BM-APP API is not well documented
        formats_to_try = [
            {"AlgTaskSession": task_session, "Ctrl": 1 if action == "start" else 0},
            {"Session": task_session, "Ctrl": 1 if action == "start" else 0},
            {"AlgTaskSession": task_session},
            {"TaskIdx": -1, "AlgTaskSession": task_session, "Ctrl": 1 if action == "start" else 0},
        ]

        last_error = None
        for data in formats_to_try:
            try:
                result = await self._request("/alg_task_control", data)
                if result.get("Result", {}).get("Code") == 0:
                    return result
                last_error = result.get("Result", {}).get("Desc", "Unknown error")
            except Exception as e:
                last_error = str(e)

        # If control doesn't work, try reconfiguring the task (which restarts it)
        if action == "start":
            try:
                # Get current task config
                tasks = await self.get_task_list()
                for task in tasks:
                    if task.get("AlgTaskSession") == task_session:
                        # Reconfigure the task with Restart=True to start it
                        task["Restart"] = True
                        result = await self._request("/alg_task_config", task)
                        if result.get("Result", {}).get("Code") == 0:
                            return {"Result": {"Code": 0, "Desc": "Task reconfigured to start"}}
            except Exception as e:
                pass

        raise Exception(f"Failed to {action} task: {last_error}")

    # ==================== AI Ability APIs ====================

    async def get_abilities(self) -> List[dict]:
        """Fetch all available AI abilities/algorithms from BM-APP"""
        result = await self._request("/alg_ability_fetch")
        if result.get("Result", {}).get("Code") == 0:
            return result.get("Ability", [])
        raise Exception(result.get("Result", {}).get("Desc", "Failed to fetch abilities"))

    async def get_ability_supported(self) -> dict:
        """Get supported abilities for the current device"""
        result = await self._request("/alg_ability_supported")
        return result

    # ==================== Other APIs ====================

    async def get_device_stats(self) -> dict:
        """Get device statistics from BM-APP"""
        result = await self._request("/alg_device_statics")
        return result

    async def get_version(self) -> dict:
        """Get BM-APP version info"""
        result = await self._request("/version")
        return result

    async def get_zlmediakit_streams(self) -> List[dict]:
        """Get available streams from ZLMediaKit"""
        # ZLMediaKit API is at /index/api/, not /api/
        base = self.base_url.replace('/api', '')
        url = f"{base}/index/api/getMediaList"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(url)
            response.raise_for_status()
            result = response.json()
            if result.get("code") == 0:
                return result.get("data", [])
            return []


# Global client instance
_client: Optional[BmAppClient] = None


def get_bmapp_client() -> BmAppClient:
    """Get the global BM-APP client instance"""
    global _client
    if _client is None:
        _client = BmAppClient()
    return _client


# Convenience functions for common operations
async def sync_media_to_bmapp(
    name: str,
    url: str,
    description: str = "",
    use_tcp: bool = False
) -> dict:
    """Sync a video source to BM-APP as media"""
    if not settings.bmapp_enabled:
        return {"status": "disabled", "message": "BM-APP integration is disabled"}

    client = get_bmapp_client()
    try:
        result = await client.add_media(name, url, description, use_tcp)
        return {"status": "success", "result": result}
    except Exception as e:
        return {"status": "error", "message": str(e)}


async def delete_media_from_bmapp(name: str) -> dict:
    """Delete a media from BM-APP"""
    if not settings.bmapp_enabled:
        return {"status": "disabled", "message": "BM-APP integration is disabled"}

    client = get_bmapp_client()
    try:
        result = await client.delete_media(name)
        return {"status": "success", "result": result}
    except Exception as e:
        return {"status": "error", "message": str(e)}


async def create_ai_task(
    name: str,
    media_name: str,
    algorithms: List[int]
) -> dict:
    """Create an AI task in BM-APP"""
    if not settings.bmapp_enabled:
        return {"status": "disabled", "message": "BM-APP integration is disabled"}

    client = get_bmapp_client()
    try:
        # AlgInfo is the major category, MethodConfig is the specific algorithm
        # Most common: AlgInfo=[1] for person-related detection
        result = await client.create_task(
            task_session=name,
            media_name=media_name,
            alg_info=[1],  # Person detection category
            method_config=algorithms
        )
        return {"status": "success", "result": result}
    except Exception as e:
        return {"status": "error", "message": str(e)}
