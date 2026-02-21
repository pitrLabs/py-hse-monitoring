"""
Preferences Router
Manage system preference key-value pairs per AI Box.
Sync FROM BM-APP: GET /alg_config_fetch  (returns {key, value, desc, group, type, options, profile})
Push TO BM-APP:   POST /alg_config_import (payload: {Config: [{key, value, desc}]})
"""
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth import get_current_user, get_current_superuser
from app.database import get_db
from app.models import User, SystemPreference, AIBox
from app.schemas import (
    SystemPreferenceCreate, SystemPreferenceUpdate, SystemPreferenceResponse,
    SystemPreferenceBulkUpdate, SyncResult
)
from app.config import settings

router = APIRouter(prefix="/preferences", tags=["preferences"])


@router.get("", response_model=List[SystemPreferenceResponse])
def list_preferences(
    aibox_id: Optional[UUID] = None,
    category: Optional[str] = None,
    limit: int = Query(default=200, le=1000),
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(SystemPreference)
    if aibox_id:
        query = query.filter(SystemPreference.aibox_id == aibox_id)
    if category:
        query = query.filter(SystemPreference.category == category)
    return query.order_by(SystemPreference.category, SystemPreference.key).offset(offset).limit(limit).all()


@router.post("", response_model=SystemPreferenceResponse)
def create_preference(
    data: SystemPreferenceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    pref = SystemPreference(**data.model_dump())
    db.add(pref)
    db.commit()
    db.refresh(pref)
    return pref


@router.put("/{pref_id}", response_model=SystemPreferenceResponse)
def update_preference(
    pref_id: UUID,
    data: SystemPreferenceUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    pref = db.query(SystemPreference).filter(SystemPreference.id == pref_id).first()
    if not pref:
        raise HTTPException(status_code=404, detail="Preference not found")
    for field, val in data.model_dump(exclude_unset=True).items():
        setattr(pref, field, val)
    db.commit()
    db.refresh(pref)
    return pref


@router.delete("/{pref_id}")
def delete_preference(
    pref_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    pref = db.query(SystemPreference).filter(SystemPreference.id == pref_id).first()
    if not pref:
        raise HTTPException(status_code=404, detail="Preference not found")
    db.delete(pref)
    db.commit()
    return {"detail": "Deleted"}


@router.patch("/bulk")
def bulk_update_preferences(
    data: SystemPreferenceBulkUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    updated = 0
    for item in data.preferences:
        key = item.get("key")
        value = item.get("value", "")
        if not key:
            continue
        pref = db.query(SystemPreference).filter(
            SystemPreference.aibox_id == data.aibox_id,
            SystemPreference.key == key
        ).first()
        if pref:
            pref.value = value
            pref.is_synced_bmapp = False
            updated += 1
        else:
            new_pref = SystemPreference(
                aibox_id=data.aibox_id,
                key=key,
                value=value,
            )
            db.add(new_pref)
            updated += 1
    db.commit()
    return {"updated": updated}


@router.get("/categories")
def list_categories(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from sqlalchemy import distinct
    cats = db.query(distinct(SystemPreference.category)).all()
    return [c[0] for c in cats if c[0]]


@router.get("/bmapp/{aibox_id}")
async def fetch_preferences_from_bmapp(
    aibox_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    """Fetch raw preferences from BM-APP (read-only view)"""
    if not settings.bmapp_enabled:
        raise HTTPException(status_code=400, detail="BM-APP integration is disabled")
    aibox = db.query(AIBox).filter(AIBox.id == aibox_id).first()
    if not aibox:
        raise HTTPException(status_code=404, detail="AI Box not found")

    from app.services.bmapp_client import get_preferences_from_aibox
    result = await get_preferences_from_aibox(aibox.api_url)
    return result


@router.post("/sync/{aibox_id}", response_model=SyncResult)
async def sync_preferences_from_bmapp(
    aibox_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    """Sync preferences FROM BM-APP into local database"""
    if not settings.bmapp_enabled:
        raise HTTPException(status_code=400, detail="BM-APP integration is disabled")
    aibox = db.query(AIBox).filter(AIBox.id == aibox_id).first()
    if not aibox:
        raise HTTPException(status_code=404, detail="AI Box not found")

    from app.services.bmapp_client import get_preferences_from_aibox
    result = await get_preferences_from_aibox(aibox.api_url)

    if result.get("status") == "error":
        raise HTTPException(status_code=502, detail=result.get("message", "BM-APP error"))

    synced = 0
    errors = []
    for item in result.get("content", []):
        try:
            # BM-APP alg_config_fetch returns lowercase fields:
            # key, value, desc, group, type, options, profile
            key = item.get("key", "")
            value = str(item.get("value", ""))
            # Use 'group' as category (BM-APP native field), fallback to 'system'
            category = item.get("group") or "system"
            description = item.get("profile") or item.get("desc") or ""
            if not key:
                continue
            # Upsert: match on (aibox_id, key) — prevents duplicates on repeated sync
            pref = db.query(SystemPreference).filter(
                SystemPreference.aibox_id == aibox_id,
                SystemPreference.key == key
            ).first()
            if pref:
                pref.value = value
                pref.category = category
                pref.description = description
                pref.is_synced_bmapp = True
            else:
                pref = SystemPreference(
                    aibox_id=aibox_id,
                    key=key,
                    value=value,
                    category=category,
                    description=description,
                    is_synced_bmapp=True,
                )
                db.add(pref)
            synced += 1
        except Exception as e:
            errors.append(str(e))
    db.commit()
    return SyncResult(success=True, synced_count=synced, message=f"Synced {synced} preferences", errors=errors)


@router.post("/apply/{aibox_id}", response_model=SyncResult)
async def apply_preferences_to_bmapp(
    aibox_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    """Push local preferences TO BM-APP"""
    if not settings.bmapp_enabled:
        raise HTTPException(status_code=400, detail="BM-APP integration is disabled")
    aibox = db.query(AIBox).filter(AIBox.id == aibox_id).first()
    if not aibox:
        raise HTTPException(status_code=404, detail="AI Box not found")

    prefs = db.query(SystemPreference).filter(SystemPreference.aibox_id == aibox_id).all()
    # alg_config_import expects: {Config: [{key, value, desc}]}
    payload = [{"key": p.key, "value": p.value, "desc": p.description or ""} for p in prefs]

    from app.services.bmapp_client import set_preferences_on_aibox
    result = await set_preferences_on_aibox(aibox.api_url, payload)

    if result.get("status") == "error":
        raise HTTPException(status_code=502, detail=result.get("message", "BM-APP error"))

    for p in prefs:
        p.is_synced_bmapp = True
    db.commit()
    return SyncResult(success=True, synced_count=len(payload), message=f"Applied {len(payload)} preferences to BM-APP")
