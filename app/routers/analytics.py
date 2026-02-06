"""
Analytics Router
Provides REST endpoints for BM-APP analytics data (people count, zone occupancy, etc.)
Each entity has: GET list + POST sync from BM-APP
"""
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session

from app.auth import get_current_user, get_current_superuser
from app.database import get_db
from app.models import (
    User, PeopleCount, ZoneOccupancy, ZoneOccupancyAvg,
    StoreCount, StayDuration, Schedule, SensorDevice, SensorData
)
from app.schemas import (
    PeopleCountResponse, ZoneOccupancyResponse, ZoneOccupancyAvgResponse,
    StoreCountResponse, StayDurationResponse, ScheduleResponse,
    SensorDeviceResponse, SensorDataResponse, AnalyticsSyncResult
)
from app.config import settings

router = APIRouter(prefix="/analytics", tags=["analytics"])


# ============ People Count ============

@router.get("/people-count", response_model=List[PeopleCountResponse])
def list_people_count(
    camera_name: Optional[str] = None,
    task_session: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    limit: int = Query(default=100, le=1000),
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(PeopleCount)
    if camera_name:
        query = query.filter(PeopleCount.camera_name == camera_name)
    if task_session:
        query = query.filter(PeopleCount.task_session == task_session)
    if start_date:
        query = query.filter(PeopleCount.record_time >= start_date)
    if end_date:
        query = query.filter(PeopleCount.record_time <= end_date)
    return query.order_by(PeopleCount.record_time.desc()).offset(offset).limit(limit).all()


@router.post("/people-count/sync", response_model=AnalyticsSyncResult)
async def sync_people_count(
    session: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    """Sync people count data from BM-APP"""
    if not settings.bmapp_enabled:
        raise HTTPException(status_code=400, detail="BM-APP integration is disabled")

    from app.services.bmapp_client import get_bmapp_client
    client = get_bmapp_client()
    errors = []
    synced = 0

    try:
        records = await client.get_people_count(session)
        for record in records:
            try:
                entry = PeopleCount(
                    bmapp_id=str(record.get("Id", "")),
                    camera_name=record.get("MediaName", ""),
                    task_session=record.get("AlgTaskSession", ""),
                    count_in=record.get("In", 0),
                    count_out=record.get("Out", 0),
                    total=record.get("Total", 0),
                    record_time=_parse_bmapp_time(record.get("Time", "")),
                    extra_data=record,
                )
                db.add(entry)
                synced += 1
            except Exception as e:
                errors.append(str(e))
        db.commit()
    except Exception as e:
        errors.append(f"BM-APP fetch error: {e}")

    return AnalyticsSyncResult(entity="people_count", synced=synced, errors=errors)


# ============ Zone Occupancy ============

@router.get("/zone-occupancy", response_model=List[ZoneOccupancyResponse])
def list_zone_occupancy(
    camera_name: Optional[str] = None,
    task_session: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    limit: int = Query(default=100, le=1000),
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(ZoneOccupancy)
    if camera_name:
        query = query.filter(ZoneOccupancy.camera_name == camera_name)
    if task_session:
        query = query.filter(ZoneOccupancy.task_session == task_session)
    if start_date:
        query = query.filter(ZoneOccupancy.record_time >= start_date)
    if end_date:
        query = query.filter(ZoneOccupancy.record_time <= end_date)
    return query.order_by(ZoneOccupancy.record_time.desc()).offset(offset).limit(limit).all()


@router.post("/zone-occupancy/sync", response_model=AnalyticsSyncResult)
async def sync_zone_occupancy(
    session: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    if not settings.bmapp_enabled:
        raise HTTPException(status_code=400, detail="BM-APP integration is disabled")

    from app.services.bmapp_client import get_bmapp_client
    client = get_bmapp_client()
    errors = []
    synced = 0

    try:
        records = await client.get_zone_occupancy(session)
        for record in records:
            try:
                entry = ZoneOccupancy(
                    bmapp_id=str(record.get("Id", "")),
                    camera_name=record.get("MediaName", ""),
                    task_session=record.get("AlgTaskSession", ""),
                    zone_name=record.get("ZoneName", ""),
                    people_count=record.get("Count", 0),
                    record_time=_parse_bmapp_time(record.get("Time", "")),
                    extra_data=record,
                )
                db.add(entry)
                synced += 1
            except Exception as e:
                errors.append(str(e))
        db.commit()
    except Exception as e:
        errors.append(f"BM-APP fetch error: {e}")

    return AnalyticsSyncResult(entity="zone_occupancy", synced=synced, errors=errors)


# ============ Zone Occupancy Avg ============

@router.get("/zone-occupancy-avg", response_model=List[ZoneOccupancyAvgResponse])
def list_zone_occupancy_avg(
    camera_name: Optional[str] = None,
    limit: int = Query(default=100, le=1000),
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(ZoneOccupancyAvg)
    if camera_name:
        query = query.filter(ZoneOccupancyAvg.camera_name == camera_name)
    return query.order_by(ZoneOccupancyAvg.period_start.desc()).offset(offset).limit(limit).all()


@router.post("/zone-occupancy-avg/sync", response_model=AnalyticsSyncResult)
async def sync_zone_occupancy_avg(
    session: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    if not settings.bmapp_enabled:
        raise HTTPException(status_code=400, detail="BM-APP integration is disabled")

    from app.services.bmapp_client import get_bmapp_client
    client = get_bmapp_client()
    errors = []
    synced = 0

    try:
        records = await client.get_zone_occupancy_avg(session)
        for record in records:
            try:
                entry = ZoneOccupancyAvg(
                    bmapp_id=str(record.get("Id", "")),
                    camera_name=record.get("MediaName", ""),
                    task_session=record.get("AlgTaskSession", ""),
                    zone_name=record.get("ZoneName", ""),
                    avg_count=record.get("AvgCount", 0.0),
                    period_start=_parse_bmapp_time(record.get("StartTime", "")),
                    period_end=_parse_bmapp_time(record.get("EndTime", "")) if record.get("EndTime") else None,
                    extra_data=record,
                )
                db.add(entry)
                synced += 1
            except Exception as e:
                errors.append(str(e))
        db.commit()
    except Exception as e:
        errors.append(f"BM-APP fetch error: {e}")

    return AnalyticsSyncResult(entity="zone_occupancy_avg", synced=synced, errors=errors)


# ============ Store Count ============

@router.get("/store-count", response_model=List[StoreCountResponse])
def list_store_count(
    camera_name: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    limit: int = Query(default=100, le=1000),
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(StoreCount)
    if camera_name:
        query = query.filter(StoreCount.camera_name == camera_name)
    if start_date:
        query = query.filter(StoreCount.record_date >= start_date)
    if end_date:
        query = query.filter(StoreCount.record_date <= end_date)
    return query.order_by(StoreCount.record_date.desc()).offset(offset).limit(limit).all()


@router.post("/store-count/sync", response_model=AnalyticsSyncResult)
async def sync_store_count(
    session: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    if not settings.bmapp_enabled:
        raise HTTPException(status_code=400, detail="BM-APP integration is disabled")

    from app.services.bmapp_client import get_bmapp_client
    client = get_bmapp_client()
    errors = []
    synced = 0

    try:
        records = await client.get_store_count(session)
        for record in records:
            try:
                entry = StoreCount(
                    bmapp_id=str(record.get("Id", "")),
                    camera_name=record.get("MediaName", ""),
                    task_session=record.get("AlgTaskSession", ""),
                    entry_count=record.get("EntryCount", 0),
                    exit_count=record.get("ExitCount", 0),
                    record_date=_parse_bmapp_time(record.get("Date", "")),
                    extra_data=record,
                )
                db.add(entry)
                synced += 1
            except Exception as e:
                errors.append(str(e))
        db.commit()
    except Exception as e:
        errors.append(f"BM-APP fetch error: {e}")

    return AnalyticsSyncResult(entity="store_count", synced=synced, errors=errors)


# ============ Stay Duration ============

@router.get("/stay-duration", response_model=List[StayDurationResponse])
def list_stay_duration(
    camera_name: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    limit: int = Query(default=100, le=1000),
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(StayDuration)
    if camera_name:
        query = query.filter(StayDuration.camera_name == camera_name)
    if start_date:
        query = query.filter(StayDuration.record_time >= start_date)
    if end_date:
        query = query.filter(StayDuration.record_time <= end_date)
    return query.order_by(StayDuration.record_time.desc()).offset(offset).limit(limit).all()


@router.post("/stay-duration/sync", response_model=AnalyticsSyncResult)
async def sync_stay_duration(
    session: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    if not settings.bmapp_enabled:
        raise HTTPException(status_code=400, detail="BM-APP integration is disabled")

    from app.services.bmapp_client import get_bmapp_client
    client = get_bmapp_client()
    errors = []
    synced = 0

    try:
        records = await client.get_stay_duration(session)
        for record in records:
            try:
                entry = StayDuration(
                    bmapp_id=str(record.get("Id", "")),
                    camera_name=record.get("MediaName", ""),
                    task_session=record.get("AlgTaskSession", ""),
                    zone_name=record.get("ZoneName", ""),
                    avg_duration=record.get("AvgDuration", 0.0),
                    max_duration=record.get("MaxDuration", 0.0),
                    min_duration=record.get("MinDuration", 0.0),
                    sample_count=record.get("SampleCount", 0),
                    record_time=_parse_bmapp_time(record.get("Time", "")),
                    extra_data=record,
                )
                db.add(entry)
                synced += 1
            except Exception as e:
                errors.append(str(e))
        db.commit()
    except Exception as e:
        errors.append(f"BM-APP fetch error: {e}")

    return AnalyticsSyncResult(entity="stay_duration", synced=synced, errors=errors)


# ============ Schedules ============

@router.get("/schedules", response_model=List[ScheduleResponse])
def list_schedules(
    task_session: Optional[str] = None,
    limit: int = Query(default=100, le=1000),
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Schedule)
    if task_session:
        query = query.filter(Schedule.task_session == task_session)
    return query.offset(offset).limit(limit).all()


@router.post("/schedules/sync", response_model=AnalyticsSyncResult)
async def sync_schedules(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    if not settings.bmapp_enabled:
        raise HTTPException(status_code=400, detail="BM-APP integration is disabled")

    from app.services.bmapp_client import get_bmapp_client
    client = get_bmapp_client()
    errors = []
    synced = 0

    try:
        records = await client.get_schedules()
        for record in records:
            try:
                entry = Schedule(
                    bmapp_id=str(record.get("Id", "")),
                    task_session="",
                    schedule_name=record.get("Name", ""),
                    schedule_type=record.get("Summary", ""),
                    start_time=record.get("Value", ""),
                    end_time="",
                    days_of_week="",
                    is_enabled=True,
                    extra_data=record,
                )
                db.add(entry)
                synced += 1
            except Exception as e:
                errors.append(str(e))
        db.commit()
    except Exception as e:
        errors.append(f"BM-APP fetch error: {e}")

    return AnalyticsSyncResult(entity="schedules", synced=synced, errors=errors)


@router.get("/schedules/bmapp")
async def list_schedules_bmapp(
    current_user: User = Depends(get_current_user),
):
    """Get schedules directly from BM-APP (live data)"""
    if not settings.bmapp_enabled:
        raise HTTPException(status_code=400, detail="BM-APP integration is disabled")

    from app.services.bmapp_client import get_bmapp_client
    client = get_bmapp_client()
    try:
        schedules = await client.get_schedules()
        return {"schedules": schedules}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"BM-APP error: {e}")


@router.post("/schedules/create")
async def create_schedule(
    name: str,
    summary: str = "",
    value: str = "",
    current_user: User = Depends(get_current_superuser),
):
    """Create a new schedule in BM-APP"""
    if not settings.bmapp_enabled:
        raise HTTPException(status_code=400, detail="BM-APP integration is disabled")

    from app.services.bmapp_client import get_bmapp_client
    client = get_bmapp_client()
    try:
        result = await client.create_schedule(name, summary, value)
        return {"success": True, "schedule_id": result.get("id")}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/schedules/{schedule_id}")
async def delete_schedule(
    schedule_id: int,
    current_user: User = Depends(get_current_superuser),
):
    """Delete a schedule from BM-APP"""
    if not settings.bmapp_enabled:
        raise HTTPException(status_code=400, detail="BM-APP integration is disabled")

    if schedule_id == -1:
        raise HTTPException(status_code=400, detail="Cannot delete default schedule")

    from app.services.bmapp_client import get_bmapp_client
    client = get_bmapp_client()
    try:
        await client.delete_schedule(schedule_id)
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ============ Sensor Devices ============

@router.get("/sensor-devices", response_model=List[SensorDeviceResponse])
def list_sensor_devices(
    limit: int = Query(default=100, le=1000),
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return db.query(SensorDevice).offset(offset).limit(limit).all()


@router.post("/sensor-devices/sync", response_model=AnalyticsSyncResult)
async def sync_sensor_devices(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    if not settings.bmapp_enabled:
        raise HTTPException(status_code=400, detail="BM-APP integration is disabled")

    from app.services.bmapp_client import get_bmapp_client
    client = get_bmapp_client()
    errors = []
    synced = 0

    try:
        records = await client.get_sensor_devices()
        for record in records:
            try:
                bmapp_id = str(record.get("Id", ""))
                # Upsert: update if exists, create if not
                existing = db.query(SensorDevice).filter(SensorDevice.bmapp_id == bmapp_id).first()
                if existing:
                    existing.device_name = record.get("DeviceName", existing.device_name)
                    existing.device_type = record.get("DeviceType", existing.device_type)
                    existing.location = record.get("Location", existing.location)
                    existing.is_online = record.get("IsOnline", existing.is_online)
                    existing.extra_data = record
                    existing.synced_at = datetime.utcnow()
                else:
                    entry = SensorDevice(
                        bmapp_id=bmapp_id,
                        device_name=record.get("DeviceName", "Unknown"),
                        device_type=record.get("DeviceType", ""),
                        location=record.get("Location", ""),
                        is_online=record.get("IsOnline", False),
                        extra_data=record,
                    )
                    db.add(entry)
                synced += 1
            except Exception as e:
                errors.append(str(e))
        db.commit()
    except Exception as e:
        errors.append(f"BM-APP fetch error: {e}")

    return AnalyticsSyncResult(entity="sensor_devices", synced=synced, errors=errors)


@router.get("/sensor-devices/types")
async def get_sensor_device_types(
    current_user: User = Depends(get_current_user),
):
    """Get available sensor device types from BM-APP (LORA, Modbus, GPIO, etc.)"""
    if not settings.bmapp_enabled:
        raise HTTPException(status_code=400, detail="BM-APP integration is disabled")

    from app.services.bmapp_client import get_bmapp_client
    client = get_bmapp_client()
    try:
        types = await client.get_sensor_device_types()
        return {"types": types}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"BM-APP error: {e}")


@router.get("/sensor-devices/bmapp")
async def list_sensors_bmapp(
    current_user: User = Depends(get_current_user),
):
    """Get configured sensors directly from BM-APP (live data)"""
    if not settings.bmapp_enabled:
        raise HTTPException(status_code=400, detail="BM-APP integration is disabled")

    from app.services.bmapp_client import get_bmapp_client
    client = get_bmapp_client()
    try:
        sensors = await client.get_sensors()
        return {"sensors": sensors}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"BM-APP error: {e}")


@router.post("/sensor-devices/create")
async def create_sensor(
    name: str,
    sensor_type: int,
    unique: str = "",
    protocol: str = "HTTP",
    extra_params: Optional[List[dict]] = None,
    current_user: User = Depends(get_current_superuser),
):
    """Create a new sensor in BM-APP

    Args:
        name: Sensor name
        sensor_type: Type ID (1=HTTP, 3=GPIO, 4=Modbus, 5=RS232, 6=LORA)
        unique: Unique identifier (defaults to name)
        protocol: "HTTP" or "IO"
        extra_params: Additional configuration parameters
    """
    if not settings.bmapp_enabled:
        raise HTTPException(status_code=400, detail="BM-APP integration is disabled")

    from app.services.bmapp_client import get_bmapp_client
    client = get_bmapp_client()
    try:
        await client.create_sensor(name, sensor_type, unique, protocol, extra_params)
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/sensor-devices/{sensor_name}")
async def update_sensor(
    sensor_name: str,
    sensor_type: int,
    unique: str = "",
    protocol: str = "HTTP",
    extra_params: Optional[List[dict]] = None,
    current_user: User = Depends(get_current_superuser),
):
    """Update an existing sensor in BM-APP"""
    if not settings.bmapp_enabled:
        raise HTTPException(status_code=400, detail="BM-APP integration is disabled")

    from app.services.bmapp_client import get_bmapp_client
    client = get_bmapp_client()
    try:
        await client.update_sensor(sensor_name, sensor_type, unique, protocol, extra_params)
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/sensor-devices/{sensor_name}")
async def delete_sensor(
    sensor_name: str,
    current_user: User = Depends(get_current_superuser),
):
    """Delete a sensor from BM-APP"""
    if not settings.bmapp_enabled:
        raise HTTPException(status_code=400, detail="BM-APP integration is disabled")

    from app.services.bmapp_client import get_bmapp_client
    client = get_bmapp_client()
    try:
        await client.delete_sensor(sensor_name)
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/sensor-devices/{sensor_name}/clean-data")
async def clean_sensor_data_endpoint(
    sensor_name: str,
    current_user: User = Depends(get_current_superuser),
):
    """Clean all data for a specific sensor"""
    if not settings.bmapp_enabled:
        raise HTTPException(status_code=400, detail="BM-APP integration is disabled")

    from app.services.bmapp_client import get_bmapp_client
    client = get_bmapp_client()
    try:
        await client.clean_sensor_data(sensor_name)
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ============ Sensor Data ============

@router.get("/sensor-data", response_model=List[SensorDataResponse])
def list_sensor_data(
    sensor_bmapp_id: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    limit: int = Query(default=100, le=1000),
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(SensorData)
    if sensor_bmapp_id:
        query = query.filter(SensorData.sensor_bmapp_id == sensor_bmapp_id)
    if start_date:
        query = query.filter(SensorData.record_time >= start_date)
    if end_date:
        query = query.filter(SensorData.record_time <= end_date)
    return query.order_by(SensorData.record_time.desc()).offset(offset).limit(limit).all()


@router.post("/sensor-data/sync", response_model=AnalyticsSyncResult)
async def sync_sensor_data(
    sensor_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    if not settings.bmapp_enabled:
        raise HTTPException(status_code=400, detail="BM-APP integration is disabled")

    from app.services.bmapp_client import get_bmapp_client
    client = get_bmapp_client()
    errors = []
    synced = 0

    try:
        records = await client.get_sensor_data(sensor_id)
        for record in records:
            try:
                sensor_bmapp_id = str(record.get("SensorDeviceId", ""))
                # Try to find matching sensor device in our DB
                sensor_device = db.query(SensorDevice).filter(
                    SensorDevice.bmapp_id == sensor_bmapp_id
                ).first()

                entry = SensorData(
                    bmapp_id=str(record.get("Id", "")),
                    sensor_device_id=sensor_device.id if sensor_device else None,
                    sensor_bmapp_id=sensor_bmapp_id,
                    value=float(record.get("Value", 0)),
                    unit=record.get("Unit", ""),
                    record_time=_parse_bmapp_time(record.get("Time", "")),
                    extra_data=record,
                )
                db.add(entry)
                synced += 1
            except Exception as e:
                errors.append(str(e))
        db.commit()
    except Exception as e:
        errors.append(f"BM-APP fetch error: {e}")

    return AnalyticsSyncResult(entity="sensor_data", synced=synced, errors=errors)


# ============ Device Statistics (from BM-APP) ============

@router.get("/device-stats")
async def get_device_stats(
    current_user: User = Depends(get_current_user),
):
    """Get aggregated device statistics directly from BM-APP (algo_alarm, channel_alarm, media_status, task_status)"""
    if not settings.bmapp_enabled:
        raise HTTPException(status_code=400, detail="BM-APP integration is disabled")

    from app.services.bmapp_client import get_bmapp_client
    client = get_bmapp_client()
    try:
        result = await client.get_device_stats()
        return result.get("Content", {})
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"BM-APP error: {e}")


# ============ Helpers ============

def _parse_bmapp_time(time_str: str) -> datetime:
    """Parse BM-APP time string to datetime. Handles multiple formats."""
    if not time_str:
        return datetime.utcnow()

    for fmt in [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%d",
    ]:
        try:
            return datetime.strptime(time_str, fmt)
        except ValueError:
            continue

    # If it's a unix timestamp
    try:
        return datetime.utcfromtimestamp(float(time_str))
    except (ValueError, OSError):
        pass

    return datetime.utcnow()
