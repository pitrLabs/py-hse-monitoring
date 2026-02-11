"""
GPS History Service
Fetches GPS data from RTU API every minute and stores it for historical tracking.
"""
import asyncio
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models import LocationHistory
from app.services.rtu_api import rtu_client, parse_coordinate_string


class GPSHistoryRecorder:
    """Records GPS positions from gps_tim_har API every minute"""

    def __init__(self, interval: int = 60):
        self.interval = interval  # seconds (default 1 minute)
        self.running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self):
        """Start the recording loop"""
        self.running = True
        self._task = asyncio.create_task(self._record_loop())
        print(f"[GPSHistory] Recording started (interval={self.interval}s)")

    def stop(self):
        """Stop the recording loop"""
        self.running = False
        if self._task:
            self._task.cancel()
            self._task = None
        print("[GPSHistory] Recording stopped")

    async def _record_loop(self):
        """Main recording loop"""
        while self.running:
            try:
                await self._record()
            except Exception as e:
                print(f"[GPSHistory] Record error: {e}")
            await asyncio.sleep(self.interval)

    async def _record(self):
        """Fetch GPS data and store in database"""
        try:
            # Fetch from gps_tim_har API (devices with GPS at HAR locations)
            data = await rtu_client.fetch_gps_tim_har()

            if not data:
                print("[GPSHistory] No data from gps_tim_har API")
                return

            now = datetime.utcnow()
            records_created = 0

            # Create a new database session
            db: Session = SessionLocal()
            try:
                for item in data:
                    # Parse GPS coordinates
                    lat, lng = 0.0, 0.0
                    gps_field = item.get("gps")
                    if gps_field and isinstance(gps_field, str) and gps_field.strip():
                        lat, lng = parse_coordinate_string(gps_field)

                    # Skip if no valid GPS
                    if lat == 0.0 and lng == 0.0:
                        continue

                    # Get device info
                    device_id = item.get("id_alat") or item.get("id") or ""
                    device_name = item.get("nama_tim") or f"Koper {device_id}"
                    status_str = str(item.get("status_perangkat", "")).upper()
                    is_online = status_str == "ON"

                    # Create history record
                    history = LocationHistory(
                        device_id=str(device_id),
                        device_name=device_name,
                        latitude=lat,
                        longitude=lng,
                        status=status_str or "UNKNOWN",
                        is_online=is_online,
                        extra_data={
                            "jenis_har": item.get("jenis_har"),
                            "keypoint_name": item.get("keypoint_name"),
                            "kondisi_jaringan": item.get("kondisi_jaringan"),
                        },
                        recorded_at=now
                    )
                    db.add(history)
                    records_created += 1

                db.commit()
                if records_created > 0:
                    print(f"[GPSHistory] Recorded {records_created} GPS positions at {now.isoformat()}")

            except Exception as e:
                db.rollback()
                print(f"[GPSHistory] Database error: {e}")
                raise
            finally:
                db.close()

        except Exception as e:
            print(f"[GPSHistory] Fetch error: {e}")


# ============ Global Recorder Instance ============

_recorder: Optional[GPSHistoryRecorder] = None


async def start_gps_history_recorder():
    """Start the GPS history recorder"""
    global _recorder
    if _recorder is None:
        _recorder = GPSHistoryRecorder(interval=settings.gps_history_interval)
        await _recorder.start()


def stop_gps_history_recorder():
    """Stop the GPS history recorder"""
    global _recorder
    if _recorder:
        _recorder.stop()
        _recorder = None


async def get_device_history(
    db: Session,
    device_id: str,
    from_time: Optional[datetime] = None,
    to_time: Optional[datetime] = None,
    limit: int = 1000
) -> list:
    """
    Get historical GPS positions for a device.

    Args:
        db: Database session
        device_id: Device ID (id_alat)
        from_time: Start time (optional)
        to_time: End time (optional)
        limit: Maximum number of records

    Returns:
        List of LocationHistory records
    """
    query = db.query(LocationHistory).filter(LocationHistory.device_id == device_id)

    if from_time:
        query = query.filter(LocationHistory.recorded_at >= from_time)
    if to_time:
        query = query.filter(LocationHistory.recorded_at <= to_time)

    return query.order_by(LocationHistory.recorded_at.asc()).limit(limit).all()


async def get_device_track(
    db: Session,
    device_id: str,
    from_time: Optional[datetime] = None,
    to_time: Optional[datetime] = None,
    limit: int = 1000
) -> list:
    """
    Get GPS track (coordinates only) for a device.
    Returns simplified list for map display.
    """
    history = await get_device_history(db, device_id, from_time, to_time, limit)

    return [
        {
            "lat": h.latitude,
            "lng": h.longitude,
            "status": h.status,
            "is_online": h.is_online,
            "recorded_at": h.recorded_at.isoformat()
        }
        for h in history
    ]
