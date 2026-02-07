"""
Telegram notification service for sending alarm alerts
"""
import httpx
from datetime import datetime
from typing import Optional
from app.config import settings


class TelegramService:
    """Service for sending notifications to Telegram"""

    def __init__(self):
        self.enabled = settings.telegram_enabled
        self.bot_token = settings.telegram_bot_token
        self.chat_id = settings.telegram_chat_id
        self.api_url = f"https://api.telegram.org/bot{self.bot_token}"

    @property
    def is_configured(self) -> bool:
        """Check if Telegram is properly configured"""
        return self.enabled and bool(self.bot_token) and bool(self.chat_id)

    async def send_message(self, text: str, parse_mode: str = "HTML") -> bool:
        """Send a text message to the configured chat"""
        if not self.is_configured:
            return False

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{self.api_url}/sendMessage",
                    json={
                        "chat_id": self.chat_id,
                        "text": text,
                        "parse_mode": parse_mode,
                        "disable_web_page_preview": True
                    }
                )
                response.raise_for_status()
                return True
        except Exception as e:
            print(f"[Telegram] Failed to send message: {e}")
            return False

    async def send_photo(self, photo_url: str, caption: str = "", parse_mode: str = "HTML") -> bool:
        """Send a photo with optional caption to the configured chat"""
        if not self.is_configured:
            return False

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.api_url}/sendPhoto",
                    json={
                        "chat_id": self.chat_id,
                        "photo": photo_url,
                        "caption": caption,
                        "parse_mode": parse_mode
                    }
                )
                response.raise_for_status()
                return True
        except Exception as e:
            print(f"[Telegram] Failed to send photo: {e}")
            # Fallback to text message if photo fails
            return await self.send_message(caption)

    async def send_alarm_notification(
        self,
        alarm_type: str,
        alarm_name: str,
        camera_name: str,
        location: Optional[str],
        alarm_time: datetime,
        confidence: Optional[float] = None,
        image_url: Optional[str] = None
    ) -> bool:
        """Send a formatted alarm notification"""
        if not self.is_configured:
            return False

        # Determine severity emoji
        severity_map = {
            "No Helmet": ("🔴", "CRITICAL"),
            "No Safety Vest": ("🔴", "CRITICAL"),
            "No Goggles": ("🟠", "HIGH"),
            "No Gloves": ("🟠", "HIGH"),
            "No Mask": ("🟡", "MEDIUM"),
            "Intrusion": ("🔴", "CRITICAL"),
            "Fire": ("🔴", "CRITICAL"),
            "Smoke": ("🔴", "CRITICAL"),
        }

        emoji, severity = severity_map.get(alarm_type, ("🟡", "MEDIUM"))

        # Format time
        time_str = alarm_time.strftime("%d %b %Y, %H:%M:%S")

        # Build message
        message = f"""{emoji} <b>ALARM: {alarm_type}</b>

<b>Severity:</b> {severity}
<b>Camera:</b> {camera_name or 'Unknown'}
<b>Location:</b> {location or 'Not specified'}
<b>Time:</b> {time_str}"""

        if confidence:
            message += f"\n<b>Confidence:</b> {confidence * 100:.0f}%"

        if alarm_name and alarm_name != alarm_type:
            message += f"\n<b>Details:</b> {alarm_name}"

        message += "\n\n#HSEMonitoring #Alarm"

        # Send with photo if available
        if image_url:
            return await self.send_photo(image_url, message)
        else:
            return await self.send_message(message)


# Global instance
telegram = TelegramService()
