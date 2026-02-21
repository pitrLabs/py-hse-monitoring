"""
Modbus Router
Manage Modbus device configurations per AI Box.
Supports sync from/to BM-APP.
"""
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth import get_current_user, get_current_superuser
from app.database import get_db
from app.models import User, ModbusDevice, AIBox
from app.schemas import (
    ModbusDeviceCreate, ModbusDeviceUpdate, ModbusDeviceResponse, SyncResult
)
from app.config import settings

router = APIRouter(prefix="/modbus", tags=["modbus"])


@router.get("", response_model=List[ModbusDeviceResponse])
def list_devices(
    aibox_id: Optional[UUID] = None,
    limit: int = Query(default=100, le=500),
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(ModbusDevice)
    if aibox_id:
        query = query.filter(ModbusDevice.aibox_id == aibox_id)
    return query.order_by(ModbusDevice.description).offset(offset).limit(limit).all()


@router.post("", response_model=ModbusDeviceResponse)
def create_device(
    data: ModbusDeviceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    device = ModbusDevice(**data.model_dump())
    db.add(device)
    db.commit()
    db.refresh(device)
    return device


@router.put("/{device_id}", response_model=ModbusDeviceResponse)
def update_device(
    device_id: UUID,
    data: ModbusDeviceUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    device = db.query(ModbusDevice).filter(ModbusDevice.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Modbus device not found")
    for field, val in data.model_dump(exclude_unset=True).items():
        setattr(device, field, val)
    device.is_synced_bmapp = False
    db.commit()
    db.refresh(device)
    return device


@router.delete("/{device_id}")
def delete_device(
    device_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    device = db.query(ModbusDevice).filter(ModbusDevice.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Modbus device not found")
    db.delete(device)
    db.commit()
    return {"detail": "Deleted"}


@router.patch("/{device_id}/toggle", response_model=ModbusDeviceResponse)
def toggle_device(
    device_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    device = db.query(ModbusDevice).filter(ModbusDevice.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Modbus device not found")
    device.is_active = not device.is_active
    device.is_synced_bmapp = False
    db.commit()
    db.refresh(device)
    return device


@router.post("/sync/{aibox_id}", response_model=SyncResult)
async def sync_devices_from_bmapp(
    aibox_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    """Sync Modbus devices FROM BM-APP"""
    if not settings.bmapp_enabled:
        raise HTTPException(status_code=400, detail="BM-APP integration is disabled")
    aibox = db.query(AIBox).filter(AIBox.id == aibox_id).first()
    if not aibox:
        raise HTTPException(status_code=404, detail="AI Box not found")

    from app.services.bmapp_client import get_modbus_devices_from_aibox
    result = await get_modbus_devices_from_aibox(aibox.api_url)

    if result.get("status") == "error":
        raise HTTPException(status_code=502, detail=result.get("message", "BM-APP error"))

    synced = 0
    errors = []
    for item in result.get("content", []):
        try:
            bmapp_id = item.get("Id") or item.get("id")
            description = item.get("Desc") or item.get("desc") or item.get("description", "")
            device = db.query(ModbusDevice).filter(
                ModbusDevice.aibox_id == aibox_id,
                ModbusDevice.bmapp_id == bmapp_id
            ).first()
            if device:
                device.description = description
                device.alarm_url = item.get("AlarmUrl") or item.get("alarm_url")
                device.port = item.get("Port") or item.get("port", 502)
                device.poll_interval = float(item.get("PollInterval") or item.get("poll_interval", 1.0))
                device.device_path = item.get("DevicePath") or item.get("device_path")
                device.slave_addr = item.get("SlaveAddr") or item.get("slave_addr", 1)
                device.start_reg_addr = item.get("StartRegAddr") or item.get("start_reg_addr", 0)
                device.end_reg_addr = item.get("EndRegAddr") or item.get("end_reg_addr", 0)
                device.start_data = item.get("StartData") or item.get("start_data", 0)
                device.end_data = item.get("EndData") or item.get("end_data", 0)
                device.device_type = item.get("DeviceType") or item.get("device_type", 0)
                device.is_synced_bmapp = True
            else:
                device = ModbusDevice(
                    aibox_id=aibox_id,
                    bmapp_id=bmapp_id,
                    description=description,
                    alarm_url=item.get("AlarmUrl") or item.get("alarm_url"),
                    port=item.get("Port") or item.get("port", 502),
                    poll_interval=float(item.get("PollInterval") or item.get("poll_interval", 1.0)),
                    device_path=item.get("DevicePath") or item.get("device_path"),
                    slave_addr=item.get("SlaveAddr") or item.get("slave_addr", 1),
                    start_reg_addr=item.get("StartRegAddr") or item.get("start_reg_addr", 0),
                    end_reg_addr=item.get("EndRegAddr") or item.get("end_reg_addr", 0),
                    start_data=item.get("StartData") or item.get("start_data", 0),
                    end_data=item.get("EndData") or item.get("end_data", 0),
                    device_type=item.get("DeviceType") or item.get("device_type", 0),
                    is_synced_bmapp=True,
                )
                db.add(device)
            synced += 1
        except Exception as e:
            errors.append(str(e))
    db.commit()
    return SyncResult(success=True, synced_count=synced, message=f"Synced {synced} Modbus devices", errors=errors)


@router.post("/apply/{aibox_id}", response_model=SyncResult)
async def apply_devices_to_bmapp(
    aibox_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    """Push local Modbus device config TO BM-APP"""
    if not settings.bmapp_enabled:
        raise HTTPException(status_code=400, detail="BM-APP integration is disabled")
    aibox = db.query(AIBox).filter(AIBox.id == aibox_id).first()
    if not aibox:
        raise HTTPException(status_code=404, detail="AI Box not found")

    devices = db.query(ModbusDevice).filter(ModbusDevice.aibox_id == aibox_id).all()
    payload = [
        {
            "Id": d.bmapp_id,
            "Desc": d.description,
            "AlarmUrl": d.alarm_url or "",
            "Port": d.port,
            "PollInterval": d.poll_interval,
            "DevicePath": d.device_path or "",
            "SlaveAddr": d.slave_addr,
            "StartRegAddr": d.start_reg_addr,
            "EndRegAddr": d.end_reg_addr,
            "StartData": d.start_data,
            "EndData": d.end_data,
            "DeviceType": d.device_type,
        }
        for d in devices
    ]

    from app.services.bmapp_client import set_modbus_devices_on_aibox
    result = await set_modbus_devices_on_aibox(aibox.api_url, payload)

    if result.get("status") == "error":
        raise HTTPException(status_code=502, detail=result.get("message", "BM-APP error"))

    for d in devices:
        d.is_synced_bmapp = True
    db.commit()
    return SyncResult(success=True, synced_count=len(payload), message=f"Applied {len(payload)} Modbus devices to BM-APP")
