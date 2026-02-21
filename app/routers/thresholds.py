"""
Algorithm Thresholds Router
Manage AI algorithm confidence thresholds per AI Box.
Sync FROM BM-APP: GET /alg_threshold_fetch  (returns {Threshold: [{id, desc, value}]})
Push TO BM-APP:   POST /alg_threshold_config (payload: {Threshold: [{id, desc, value}]})
"""
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth import get_current_user, get_current_superuser
from app.database import get_db
from app.models import User, AlgorithmThreshold, AIBox
from app.schemas import (
    AlgorithmThresholdCreate, AlgorithmThresholdUpdate, AlgorithmThresholdResponse,
    AlgorithmThresholdBulkUpdate, SyncResult
)
from app.config import settings

router = APIRouter(prefix="/thresholds", tags=["thresholds"])


@router.get("", response_model=List[AlgorithmThresholdResponse])
def list_thresholds(
    aibox_id: Optional[UUID] = None,
    limit: int = Query(default=200, le=1000),
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(AlgorithmThreshold)
    if aibox_id:
        query = query.filter(AlgorithmThreshold.aibox_id == aibox_id)
    return query.order_by(AlgorithmThreshold.algorithm_index).offset(offset).limit(limit).all()


@router.post("", response_model=AlgorithmThresholdResponse)
def create_threshold(
    data: AlgorithmThresholdCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    threshold = AlgorithmThreshold(**data.model_dump())
    db.add(threshold)
    db.commit()
    db.refresh(threshold)
    return threshold


@router.put("/{threshold_id}", response_model=AlgorithmThresholdResponse)
def update_threshold(
    threshold_id: UUID,
    data: AlgorithmThresholdUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    threshold = db.query(AlgorithmThreshold).filter(AlgorithmThreshold.id == threshold_id).first()
    if not threshold:
        raise HTTPException(status_code=404, detail="Threshold not found")
    for field, val in data.model_dump(exclude_unset=True).items():
        setattr(threshold, field, val)
    threshold.is_synced_bmapp = False
    db.commit()
    db.refresh(threshold)
    return threshold


@router.delete("/{threshold_id}")
def delete_threshold(
    threshold_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    threshold = db.query(AlgorithmThreshold).filter(AlgorithmThreshold.id == threshold_id).first()
    if not threshold:
        raise HTTPException(status_code=404, detail="Threshold not found")
    db.delete(threshold)
    db.commit()
    return {"detail": "Deleted"}


@router.patch("/bulk")
def bulk_update_thresholds(
    data: AlgorithmThresholdBulkUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    updated = 0
    for item in data.updates:
        threshold_id = item.get("id")
        value = item.get("threshold_value")
        if threshold_id is None or value is None:
            continue
        threshold = db.query(AlgorithmThreshold).filter(
            AlgorithmThreshold.id == threshold_id,
            AlgorithmThreshold.aibox_id == data.aibox_id
        ).first()
        if threshold:
            threshold.threshold_value = float(value)
            threshold.is_synced_bmapp = False
            updated += 1
    db.commit()
    return {"updated": updated}


@router.get("/bmapp/{aibox_id}")
async def fetch_thresholds_from_bmapp(
    aibox_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    """Fetch raw thresholds from BM-APP (read-only view)"""
    if not settings.bmapp_enabled:
        raise HTTPException(status_code=400, detail="BM-APP integration is disabled")
    aibox = db.query(AIBox).filter(AIBox.id == aibox_id).first()
    if not aibox:
        raise HTTPException(status_code=404, detail="AI Box not found")

    from app.services.bmapp_client import get_thresholds_from_aibox
    result = await get_thresholds_from_aibox(aibox.api_url)
    return result


@router.post("/sync/{aibox_id}", response_model=SyncResult)
async def sync_thresholds_from_bmapp(
    aibox_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    """Sync algorithm thresholds FROM BM-APP"""
    if not settings.bmapp_enabled:
        raise HTTPException(status_code=400, detail="BM-APP integration is disabled")
    aibox = db.query(AIBox).filter(AIBox.id == aibox_id).first()
    if not aibox:
        raise HTTPException(status_code=404, detail="AI Box not found")

    from app.services.bmapp_client import get_thresholds_from_aibox
    result = await get_thresholds_from_aibox(aibox.api_url)

    if result.get("status") == "error":
        raise HTTPException(status_code=502, detail=result.get("message", "BM-APP error"))

    synced = 0
    errors = []
    for item in result.get("content", []):
        try:
            # BM-APP alg_threshold_fetch returns: {id, desc, value}
            idx = item.get("id", 0)
            name = item.get("desc") or f"Algorithm {idx}"
            value = float(item.get("value", 0.5))
            if not idx:
                continue
            # Upsert: match on (aibox_id, algorithm_index) — prevents duplicates on repeated sync
            threshold = db.query(AlgorithmThreshold).filter(
                AlgorithmThreshold.aibox_id == aibox_id,
                AlgorithmThreshold.algorithm_index == idx
            ).first()
            if threshold:
                threshold.algorithm_name = name
                threshold.threshold_value = value
                threshold.is_synced_bmapp = True
            else:
                threshold = AlgorithmThreshold(
                    aibox_id=aibox_id,
                    algorithm_index=idx,
                    algorithm_name=name,
                    threshold_value=value,
                    is_synced_bmapp=True,
                )
                db.add(threshold)
            synced += 1
        except Exception as e:
            errors.append(str(e))
    db.commit()
    return SyncResult(success=True, synced_count=synced, message=f"Synced {synced} thresholds", errors=errors)


@router.post("/apply/{aibox_id}", response_model=SyncResult)
async def apply_thresholds_to_bmapp(
    aibox_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    """Push local thresholds TO BM-APP"""
    if not settings.bmapp_enabled:
        raise HTTPException(status_code=400, detail="BM-APP integration is disabled")
    aibox = db.query(AIBox).filter(AIBox.id == aibox_id).first()
    if not aibox:
        raise HTTPException(status_code=404, detail="AI Box not found")

    thresholds = db.query(AlgorithmThreshold).filter(AlgorithmThreshold.aibox_id == aibox_id).all()
    # alg_threshold_config expects same format as fetch: {id, desc, value}
    payload = [
        {"id": t.algorithm_index, "desc": t.algorithm_name, "value": t.threshold_value}
        for t in thresholds
    ]

    from app.services.bmapp_client import set_thresholds_on_aibox
    result = await set_thresholds_on_aibox(aibox.api_url, payload)

    if result.get("status") == "error":
        raise HTTPException(status_code=502, detail=result.get("message", "BM-APP error"))

    for t in thresholds:
        t.is_synced_bmapp = True
    db.commit()
    return SyncResult(success=True, synced_count=len(payload), message=f"Applied {len(payload)} thresholds to BM-APP")
