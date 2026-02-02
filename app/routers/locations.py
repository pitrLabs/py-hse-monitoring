"""
Router for camera locations and groups management
"""
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import CameraLocation, CameraGroup, User
from app.schemas import (
    CameraLocationCreate,
    CameraLocationUpdate,
    CameraLocationResponse,
    CameraGroupCreate,
    CameraGroupUpdate,
    CameraGroupResponse,
    SyncResult
)
from app.auth import get_current_user, get_current_superuser
from app.services.rtu_api import sync_locations_from_api, rtu_client

router = APIRouter(prefix="/locations", tags=["Camera Locations"])


# ============ Camera Locations - Static Routes First ============

@router.get("", response_model=List[CameraLocationResponse])
async def get_locations(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    source: Optional[str] = Query(None, description="Filter by source: keypoint, gps_tim_har, manual"),
    location_type: Optional[str] = Query(None, description="Filter by location type"),
    search: Optional[str] = Query(None, description="Search by name or address"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    db: Session = Depends(get_db)
):
    """Get all camera locations with optional filters"""
    query = db.query(CameraLocation)

    # Always filter out invalid coordinates (outside valid ranges)
    query = query.filter(
        CameraLocation.latitude >= -90,
        CameraLocation.latitude <= 90,
        CameraLocation.longitude >= -180,
        CameraLocation.longitude <= 180
    )

    if source:
        query = query.filter(CameraLocation.source == source)
    if location_type:
        query = query.filter(CameraLocation.location_type == location_type)
    if is_active is not None:
        query = query.filter(CameraLocation.is_active == is_active)
    if search:
        search_pattern = f"%{search}%"
        query = query.filter(
            (CameraLocation.name.ilike(search_pattern)) |
            (CameraLocation.address.ilike(search_pattern)) |
            (CameraLocation.description.ilike(search_pattern))
        )

    locations = query.order_by(CameraLocation.name).offset(skip).limit(limit).all()
    return locations


@router.get("/stats")
async def get_location_stats(db: Session = Depends(get_db)):
    """Get location statistics"""
    total = db.query(func.count(CameraLocation.id)).scalar()
    by_source = db.query(
        CameraLocation.source,
        func.count(CameraLocation.id)
    ).group_by(CameraLocation.source).all()

    by_type = db.query(
        CameraLocation.location_type,
        func.count(CameraLocation.id)
    ).group_by(CameraLocation.location_type).all()

    return {
        "total": total,
        "by_source": {s: c for s, c in by_source},
        "by_type": {t or "Unknown": c for t, c in by_type}
    }


@router.delete("/cleanup-invalid")
async def cleanup_invalid_coordinates(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser)
):
    """
    Delete all locations with invalid coordinates (superuser only).
    This cleans up data that was synced before validation was added.
    """
    invalid_locations = db.query(CameraLocation).filter(
        (CameraLocation.latitude < -90) |
        (CameraLocation.latitude > 90) |
        (CameraLocation.longitude < -180) |
        (CameraLocation.longitude > 180)
    ).all()

    count = len(invalid_locations)
    for loc in invalid_locations:
        db.delete(loc)

    db.commit()

    return {
        "message": f"Cleaned up {count} locations with invalid coordinates",
        "deleted": count
    }


@router.post("/sync", response_model=SyncResult)
async def sync_locations(
    source: str = Query("gps_tim_har", description="Source to sync: 'gps_tim_har' or 'all'"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Sync camera locations from external RTU API.
    This will fetch latest data and update the database.
    """
    if source not in ["gps_tim_har", "all"]:
        raise HTTPException(status_code=400, detail="Invalid source. Use 'gps_tim_har' or 'all'")

    total, created, updated, errors = await sync_locations_from_api(db, source)

    return SyncResult(
        synced=total,
        created=created,
        updated=updated,
        errors=errors
    )


@router.get("/external/preview")
async def preview_external_data(
    source: str = Query("gps_tim_har", description="Source to preview: 'gps_tim_har'"),
    current_user: User = Depends(get_current_user)
):
    """
    Preview data from external API without saving to database.
    Useful for checking what data will be synced.
    """
    try:
        if source == "keypoint":
            data = await rtu_client.fetch_keypoints()
            return {
                "source": "keypoint",
                "count": len(data),
                "sample": data[:10] if data else [],
                "message": f"Found {len(data)} keypoints"
            }
        elif source == "gps_tim_har":
            data = await rtu_client.fetch_gps_tim_har()
            return {
                "source": "gps_tim_har",
                "count": len(data),
                "sample": data[:10] if data else [],
                "message": f"Found {len(data)} GPS records"
            }
        else:
            raise HTTPException(status_code=400, detail="Invalid source. Use 'keypoint' or 'gps_tim_har'")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch external data: {str(e)}")


# ============ Camera Groups - Before dynamic routes ============

@router.get("/groups", response_model=List[CameraGroupResponse])
async def get_groups(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db)
):
    """Get all camera groups"""
    groups = db.query(CameraGroup).order_by(CameraGroup.name).offset(skip).limit(limit).all()
    return groups


@router.post("/groups", response_model=CameraGroupResponse)
async def create_group(
    group: CameraGroupCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new camera group"""
    existing = db.query(CameraGroup).filter(CameraGroup.name == group.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Group with this name already exists")

    new_group = CameraGroup(
        name=group.name,
        display_name=group.display_name or group.name,
        description=group.description,
        created_by_id=current_user.id
    )
    db.add(new_group)
    db.commit()
    db.refresh(new_group)
    return new_group


@router.post("/groups/upsert", response_model=CameraGroupResponse)
async def upsert_group(
    name: str = Query(..., description="Group name (original folder name)"),
    display_name: Optional[str] = Query(None, description="Custom display name"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Create or update a camera group.
    If group with same name exists, update it. Otherwise create new.
    Useful for frontend to ensure groups exist.
    """
    is_manager = current_user.is_superuser or any(
        role.name.lower() in ["superadmin", "manager", "admin"]
        for role in current_user.roles
    )
    if not is_manager:
        raise HTTPException(
            status_code=403,
            detail="Only superadmin and manager can manage groups"
        )

    existing = db.query(CameraGroup).filter(CameraGroup.name == name).first()

    if existing:
        if display_name:
            existing.display_name = display_name
        db.commit()
        db.refresh(existing)
        return existing
    else:
        new_group = CameraGroup(
            name=name,
            display_name=display_name or name,
            created_by_id=current_user.id
        )
        db.add(new_group)
        db.commit()
        db.refresh(new_group)
        return new_group


@router.get("/groups/{group_id}", response_model=CameraGroupResponse)
async def get_group(
    group_id: UUID,
    db: Session = Depends(get_db)
):
    """Get a specific camera group"""
    group = db.query(CameraGroup).filter(CameraGroup.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    return group


@router.patch("/groups/{group_id}", response_model=CameraGroupResponse)
async def update_group(
    group_id: UUID,
    group_update: CameraGroupUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Update a camera group (rename display name).
    Only superadmin and manager can update groups.
    """
    is_manager = current_user.is_superuser or any(
        role.name.lower() in ["superadmin", "manager", "admin"]
        for role in current_user.roles
    )
    if not is_manager:
        raise HTTPException(
            status_code=403,
            detail="Only superadmin and manager can rename groups"
        )

    group = db.query(CameraGroup).filter(CameraGroup.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    update_data = group_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(group, key, value)

    db.commit()
    db.refresh(group)
    return group


@router.delete("/groups/{group_id}")
async def delete_group(
    group_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser)
):
    """Delete a camera group (superuser only)"""
    group = db.query(CameraGroup).filter(CameraGroup.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    db.delete(group)
    db.commit()
    return {"message": "Group deleted"}


# ============ Camera Locations - Dynamic Routes Last ============

@router.get("/{location_id}", response_model=CameraLocationResponse)
async def get_location(
    location_id: UUID,
    db: Session = Depends(get_db)
):
    """Get a specific camera location"""
    location = db.query(CameraLocation).filter(CameraLocation.id == location_id).first()
    if not location:
        raise HTTPException(status_code=404, detail="Location not found")
    return location


@router.post("", response_model=CameraLocationResponse)
async def create_location(
    location: CameraLocationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new camera location manually"""
    new_location = CameraLocation(
        external_id=location.external_id,
        source=location.source or "manual",
        name=location.name,
        latitude=location.latitude,
        longitude=location.longitude,
        location_type=location.location_type,
        description=location.description,
        address=location.address,
        extra_data=location.extra_data
    )
    db.add(new_location)
    db.commit()
    db.refresh(new_location)
    return new_location


@router.patch("/{location_id}", response_model=CameraLocationResponse)
async def update_location(
    location_id: UUID,
    location_update: CameraLocationUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update a camera location"""
    location = db.query(CameraLocation).filter(CameraLocation.id == location_id).first()
    if not location:
        raise HTTPException(status_code=404, detail="Location not found")

    update_data = location_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(location, key, value)

    db.commit()
    db.refresh(location)
    return location


@router.delete("/{location_id}")
async def delete_location(
    location_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser)
):
    """Delete a camera location (superuser only)"""
    location = db.query(CameraLocation).filter(CameraLocation.id == location_id).first()
    if not location:
        raise HTTPException(status_code=404, detail="Location not found")

    db.delete(location)
    db.commit()
    return {"message": "Location deleted"}
