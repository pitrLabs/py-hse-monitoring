"""
Analytics Auto-Sync Service
Periodically syncs analytics data from BM-APP to our database.
Runs as a background task alongside the camera status poller.
"""
import asyncio
from typing import Optional

from app.config import settings
from app.database import SessionLocal
from app.models import (
    PeopleCount, ZoneOccupancy, ZoneOccupancyAvg,
    StoreCount, StayDuration, Schedule, SensorDevice, SensorData
)
from app.utils.timezone import parse_bmapp_time, now_utc


# Default sync interval: 60 seconds
SYNC_INTERVAL = 60


def _parse_time(time_str: str):
    """Parse BM-APP time string to UTC datetime (BM-APP uses China timezone UTC+8)"""
    return parse_bmapp_time(time_str)


class AnalyticsSyncService:
    """Background service that auto-syncs BM-APP analytics data"""

    def __init__(self):
        self.interval = SYNC_INTERVAL
        self.running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self):
        self.running = True
        self._task = asyncio.create_task(self._sync_loop())
        print(f"[AnalyticsSync] Auto-sync started (interval={self.interval}s)")

    def stop(self):
        self.running = False
        if self._task:
            self._task.cancel()
            self._task = None
        print("[AnalyticsSync] Auto-sync stopped")

    async def _sync_loop(self):
        # Wait a bit on startup to let other services initialize
        await asyncio.sleep(10)

        while self.running:
            try:
                await self._sync_all()
            except Exception as e:
                print(f"[AnalyticsSync] Sync error: {e}")
            await asyncio.sleep(self.interval)

    async def _sync_all(self):
        """Sync all analytics entities from BM-APP"""
        if not settings.bmapp_enabled:
            return

        from app.services.bmapp_client import get_bmapp_client
        client = get_bmapp_client()
        db = SessionLocal()

        try:
            # Sync each entity, catching errors per entity so one failure doesn't block others
            await self._sync_people_count(client, db)
            await self._sync_zone_occupancy(client, db)
            await self._sync_zone_occupancy_avg(client, db)
            await self._sync_store_count(client, db)
            await self._sync_stay_duration(client, db)
            await self._sync_schedules(client, db)
            await self._sync_sensor_devices(client, db)
            await self._sync_sensor_data(client, db)
        finally:
            db.close()

    async def _sync_people_count(self, client, db):
        try:
            records = await client.get_people_count()
            if not records:
                return
            # Get existing bmapp_ids to avoid duplicates
            existing_ids = set(
                r[0] for r in db.query(PeopleCount.bmapp_id).filter(
                    PeopleCount.bmapp_id.isnot(None)
                ).all()
            )
            count = 0
            for record in records:
                bmapp_id = str(record.get("Id", ""))
                if bmapp_id in existing_ids:
                    continue
                db.add(PeopleCount(
                    bmapp_id=bmapp_id,
                    camera_name=record.get("MediaName", ""),
                    task_session=record.get("AlgTaskSession", ""),
                    count_in=record.get("In", 0),
                    count_out=record.get("Out", 0),
                    total=record.get("Total", 0),
                    record_time=_parse_time(record.get("Time", "")),
                    extra_data=record,
                ))
                count += 1
            if count > 0:
                db.commit()
                print(f"[AnalyticsSync] people_count: +{count} new records")
        except Exception as e:
            db.rollback()
            print(f"[AnalyticsSync] people_count error: {e}")

    async def _sync_zone_occupancy(self, client, db):
        try:
            records = await client.get_zone_occupancy()
            if not records:
                return
            existing_ids = set(
                r[0] for r in db.query(ZoneOccupancy.bmapp_id).filter(
                    ZoneOccupancy.bmapp_id.isnot(None)
                ).all()
            )
            count = 0
            for record in records:
                bmapp_id = str(record.get("Id", ""))
                if bmapp_id in existing_ids:
                    continue
                db.add(ZoneOccupancy(
                    bmapp_id=bmapp_id,
                    camera_name=record.get("MediaName", ""),
                    task_session=record.get("AlgTaskSession", ""),
                    zone_name=record.get("ZoneName", ""),
                    people_count=record.get("Count", 0),
                    record_time=_parse_time(record.get("Time", "")),
                    extra_data=record,
                ))
                count += 1
            if count > 0:
                db.commit()
                print(f"[AnalyticsSync] zone_occupancy: +{count} new records")
        except Exception as e:
            db.rollback()
            print(f"[AnalyticsSync] zone_occupancy error: {e}")

    async def _sync_zone_occupancy_avg(self, client, db):
        try:
            records = await client.get_zone_occupancy_avg()
            if not records:
                return
            existing_ids = set(
                r[0] for r in db.query(ZoneOccupancyAvg.bmapp_id).filter(
                    ZoneOccupancyAvg.bmapp_id.isnot(None)
                ).all()
            )
            count = 0
            for record in records:
                bmapp_id = str(record.get("Id", ""))
                if bmapp_id in existing_ids:
                    continue
                db.add(ZoneOccupancyAvg(
                    bmapp_id=bmapp_id,
                    camera_name=record.get("MediaName", ""),
                    task_session=record.get("AlgTaskSession", ""),
                    zone_name=record.get("ZoneName", ""),
                    avg_count=record.get("AvgCount", 0.0),
                    period_start=_parse_time(record.get("StartTime", "")),
                    period_end=_parse_time(record.get("EndTime", "")) if record.get("EndTime") else None,
                    extra_data=record,
                ))
                count += 1
            if count > 0:
                db.commit()
                print(f"[AnalyticsSync] zone_occupancy_avg: +{count} new records")
        except Exception as e:
            db.rollback()
            print(f"[AnalyticsSync] zone_occupancy_avg error: {e}")

    async def _sync_store_count(self, client, db):
        try:
            records = await client.get_store_count()
            if not records:
                return
            existing_ids = set(
                r[0] for r in db.query(StoreCount.bmapp_id).filter(
                    StoreCount.bmapp_id.isnot(None)
                ).all()
            )
            count = 0
            for record in records:
                bmapp_id = str(record.get("Id", ""))
                if bmapp_id in existing_ids:
                    continue
                db.add(StoreCount(
                    bmapp_id=bmapp_id,
                    camera_name=record.get("MediaName", ""),
                    task_session=record.get("AlgTaskSession", ""),
                    entry_count=record.get("EntryCount", 0),
                    exit_count=record.get("ExitCount", 0),
                    record_date=_parse_time(record.get("Date", "")),
                    extra_data=record,
                ))
                count += 1
            if count > 0:
                db.commit()
                print(f"[AnalyticsSync] store_count: +{count} new records")
        except Exception as e:
            db.rollback()
            print(f"[AnalyticsSync] store_count error: {e}")

    async def _sync_stay_duration(self, client, db):
        try:
            records = await client.get_stay_duration()
            if not records:
                return
            existing_ids = set(
                r[0] for r in db.query(StayDuration.bmapp_id).filter(
                    StayDuration.bmapp_id.isnot(None)
                ).all()
            )
            count = 0
            for record in records:
                bmapp_id = str(record.get("Id", ""))
                if bmapp_id in existing_ids:
                    continue
                db.add(StayDuration(
                    bmapp_id=bmapp_id,
                    camera_name=record.get("MediaName", ""),
                    task_session=record.get("AlgTaskSession", ""),
                    zone_name=record.get("ZoneName", ""),
                    avg_duration=record.get("AvgDuration", 0.0),
                    max_duration=record.get("MaxDuration", 0.0),
                    min_duration=record.get("MinDuration", 0.0),
                    sample_count=record.get("SampleCount", 0),
                    record_time=_parse_time(record.get("Time", "")),
                    extra_data=record,
                ))
                count += 1
            if count > 0:
                db.commit()
                print(f"[AnalyticsSync] stay_duration: +{count} new records")
        except Exception as e:
            db.rollback()
            print(f"[AnalyticsSync] stay_duration error: {e}")

    async def _sync_schedules(self, client, db):
        try:
            records = await client.get_schedules()
            if not records:
                return
            existing_ids = set(
                r[0] for r in db.query(Schedule.bmapp_id).filter(
                    Schedule.bmapp_id.isnot(None)
                ).all()
            )
            count = 0
            for record in records:
                bmapp_id = str(record.get("Id", ""))
                if bmapp_id in existing_ids:
                    continue
                db.add(Schedule(
                    bmapp_id=bmapp_id,
                    task_session="",
                    schedule_name=record.get("Name", ""),
                    schedule_type=record.get("Summary", ""),
                    start_time=record.get("Value", ""),
                    end_time="",
                    days_of_week="",
                    is_enabled=True,
                    extra_data=record,
                ))
                count += 1
            if count > 0:
                db.commit()
                print(f"[AnalyticsSync] schedules: +{count} new records")
        except Exception as e:
            db.rollback()
            print(f"[AnalyticsSync] schedules error: {e}")

    async def _sync_sensor_devices(self, client, db):
        try:
            records = await client.get_sensor_devices()
            if not records:
                return
            count = 0
            for record in records:
                bmapp_id = str(record.get("Id", ""))
                existing = db.query(SensorDevice).filter(SensorDevice.bmapp_id == bmapp_id).first()
                if existing:
                    existing.device_name = record.get("DeviceName", existing.device_name)
                    existing.device_type = record.get("DeviceType", existing.device_type)
                    existing.location = record.get("Location", existing.location)
                    existing.is_online = record.get("IsOnline", existing.is_online)
                    existing.extra_data = record
                    existing.synced_at = now_utc()
                else:
                    db.add(SensorDevice(
                        bmapp_id=bmapp_id,
                        device_name=record.get("DeviceName", "Unknown"),
                        device_type=record.get("DeviceType", ""),
                        location=record.get("Location", ""),
                        is_online=record.get("IsOnline", False),
                        extra_data=record,
                    ))
                count += 1
            if count > 0:
                db.commit()
                print(f"[AnalyticsSync] sensor_devices: {count} synced")
        except Exception as e:
            db.rollback()
            print(f"[AnalyticsSync] sensor_devices error: {e}")

    async def _sync_sensor_data(self, client, db):
        try:
            records = await client.get_sensor_data()
            if not records:
                return
            existing_ids = set(
                r[0] for r in db.query(SensorData.bmapp_id).filter(
                    SensorData.bmapp_id.isnot(None)
                ).all()
            )
            count = 0
            for record in records:
                bmapp_id = str(record.get("Id", ""))
                if bmapp_id in existing_ids:
                    continue
                sensor_bmapp_id = str(record.get("SensorDeviceId", ""))
                sensor_device = db.query(SensorDevice).filter(
                    SensorDevice.bmapp_id == sensor_bmapp_id
                ).first()
                db.add(SensorData(
                    bmapp_id=bmapp_id,
                    sensor_device_id=sensor_device.id if sensor_device else None,
                    sensor_bmapp_id=sensor_bmapp_id,
                    value=float(record.get("Value", 0)),
                    unit=record.get("Unit", ""),
                    record_time=_parse_time(record.get("Time", "")),
                    extra_data=record,
                ))
                count += 1
            if count > 0:
                db.commit()
                print(f"[AnalyticsSync] sensor_data: +{count} new records")
        except Exception as e:
            db.rollback()
            print(f"[AnalyticsSync] sensor_data error: {e}")


# ============ Global Instance ============

_service: Optional[AnalyticsSyncService] = None


async def start_analytics_sync():
    global _service
    if _service is None:
        _service = AnalyticsSyncService()
        await _service.start()


def stop_analytics_sync():
    global _service
    if _service:
        _service.stop()
        _service = None
