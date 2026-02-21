"""
Face Database Router
Manage face recognition albums and feature records per AI Box.
Supports sync from BM-APP via faceengine/album/list and faceengine/feature/list.
"""
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth import get_current_user, get_current_superuser
from app.database import get_db
from app.models import User, FaceAlbum, FaceFeatureRecord, AIBox
from app.schemas import (
    FaceAlbumCreate, FaceAlbumUpdate, FaceAlbumResponse,
    FaceFeatureRecordCreate, FaceFeatureRecordResponse, SyncResult
)
from app.config import settings

router = APIRouter(prefix="/face-database", tags=["face-database"])


# ============ Face Albums ============

@router.get("/albums", response_model=List[FaceAlbumResponse])
def list_albums(
    aibox_id: Optional[UUID] = None,
    limit: int = Query(default=100, le=500),
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(FaceAlbum)
    if aibox_id:
        query = query.filter(FaceAlbum.aibox_id == aibox_id)
    return query.order_by(FaceAlbum.name).offset(offset).limit(limit).all()


@router.post("/albums", response_model=FaceAlbumResponse)
def create_album(
    data: FaceAlbumCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    album = FaceAlbum(**data.model_dump())
    db.add(album)
    db.commit()
    db.refresh(album)
    return album


@router.put("/albums/{album_id}", response_model=FaceAlbumResponse)
def update_album(
    album_id: UUID,
    data: FaceAlbumUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    album = db.query(FaceAlbum).filter(FaceAlbum.id == album_id).first()
    if not album:
        raise HTTPException(status_code=404, detail="Album not found")
    for field, val in data.model_dump(exclude_unset=True).items():
        setattr(album, field, val)
    db.commit()
    db.refresh(album)
    return album


@router.delete("/albums/{album_id}")
def delete_album(
    album_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    album = db.query(FaceAlbum).filter(FaceAlbum.id == album_id).first()
    if not album:
        raise HTTPException(status_code=404, detail="Album not found")
    db.delete(album)
    db.commit()
    return {"detail": "Deleted"}


@router.post("/albums/sync/{aibox_id}", response_model=SyncResult)
async def sync_albums_from_bmapp(
    aibox_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    """Sync face albums FROM BM-APP"""
    if not settings.bmapp_enabled:
        raise HTTPException(status_code=400, detail="BM-APP integration is disabled")
    aibox = db.query(AIBox).filter(AIBox.id == aibox_id).first()
    if not aibox:
        raise HTTPException(status_code=404, detail="AI Box not found")

    from app.services.bmapp_client import get_face_albums_from_aibox
    result = await get_face_albums_from_aibox(aibox.api_url)

    if result.get("status") == "error":
        raise HTTPException(status_code=502, detail=result.get("message", "BM-APP error"))
    if result.get("status") == "unsupported":
        raise HTTPException(status_code=501, detail=f"Face database not supported by this AI Box: {result.get('message', '')}")

    synced = 0
    errors = []
    for item in result.get("content", []):
        try:
            bmapp_id = item.get("SuitId") or item.get("suit_id") or item.get("Id")
            name = item.get("SuitName") or item.get("suit_name") or item.get("Name", "")
            feature_count = item.get("FeatureCount") or item.get("feature_count", 0)
            album = db.query(FaceAlbum).filter(
                FaceAlbum.aibox_id == aibox_id,
                FaceAlbum.bmapp_id == bmapp_id
            ).first()
            if album:
                album.name = name
                album.feature_count = feature_count
                album.is_synced_bmapp = True
            else:
                album = FaceAlbum(
                    aibox_id=aibox_id,
                    bmapp_id=bmapp_id,
                    name=name,
                    feature_count=feature_count,
                    is_synced_bmapp=True,
                )
                db.add(album)
            synced += 1
        except Exception as e:
            errors.append(str(e))
    db.commit()
    return SyncResult(success=True, synced_count=synced, message=f"Synced {synced} albums", errors=errors)


# ============ Face Feature Records ============

@router.get("/albums/{album_id}/features", response_model=List[FaceFeatureRecordResponse])
def list_features(
    album_id: UUID,
    limit: int = Query(default=100, le=500),
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    album = db.query(FaceAlbum).filter(FaceAlbum.id == album_id).first()
    if not album:
        raise HTTPException(status_code=404, detail="Album not found")
    query = db.query(FaceFeatureRecord).filter(FaceFeatureRecord.album_id == album_id)
    return query.order_by(FaceFeatureRecord.created_at.desc()).offset(offset).limit(limit).all()


@router.post("/albums/{album_id}/features", response_model=FaceFeatureRecordResponse)
def create_feature(
    album_id: UUID,
    data: FaceFeatureRecordCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    album = db.query(FaceAlbum).filter(FaceAlbum.id == album_id).first()
    if not album:
        raise HTTPException(status_code=404, detail="Album not found")
    feature_data = data.model_dump()
    feature_data["album_id"] = album_id
    feature = FaceFeatureRecord(**feature_data)
    db.add(feature)
    # Update denormalized count
    album.feature_count = db.query(FaceFeatureRecord).filter(FaceFeatureRecord.album_id == album_id).count() + 1
    db.commit()
    db.refresh(feature)
    return feature


@router.delete("/features/{feature_id}")
def delete_feature(
    feature_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    feature = db.query(FaceFeatureRecord).filter(FaceFeatureRecord.id == feature_id).first()
    if not feature:
        raise HTTPException(status_code=404, detail="Feature record not found")
    album_id = feature.album_id
    db.delete(feature)
    # Update denormalized count
    album = db.query(FaceAlbum).filter(FaceAlbum.id == album_id).first()
    if album:
        album.feature_count = max(0, db.query(FaceFeatureRecord).filter(FaceFeatureRecord.album_id == album_id).count() - 1)
    db.commit()
    return {"detail": "Deleted"}


@router.post("/features/sync/{aibox_id}", response_model=SyncResult)
async def sync_features_from_bmapp(
    aibox_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    """Sync face features FROM BM-APP for all albums of this aibox"""
    if not settings.bmapp_enabled:
        raise HTTPException(status_code=400, detail="BM-APP integration is disabled")
    aibox = db.query(AIBox).filter(AIBox.id == aibox_id).first()
    if not aibox:
        raise HTTPException(status_code=404, detail="AI Box not found")

    albums = db.query(FaceAlbum).filter(
        FaceAlbum.aibox_id == aibox_id,
        FaceAlbum.bmapp_id != None
    ).all()

    from app.services.bmapp_client import get_face_features_from_aibox
    synced = 0
    errors = []
    for album in albums:
        try:
            result = await get_face_features_from_aibox(aibox.api_url, album.bmapp_id)
            if result.get("status") in ("error", "unsupported"):
                errors.append(f"Album {album.name}: {result.get('message', 'error')}")
                continue
            for item in result.get("content", []):
                bmapp_id = item.get("FeatureId") or item.get("feature_id") or item.get("Id")
                name = item.get("Name") or item.get("name")
                jpeg_path = item.get("JpegPath") or item.get("jpeg_path")
                feature = db.query(FaceFeatureRecord).filter(
                    FaceFeatureRecord.album_id == album.id,
                    FaceFeatureRecord.bmapp_id == bmapp_id
                ).first()
                if feature:
                    feature.name = name
                    feature.jpeg_path = jpeg_path
                    feature.is_synced_bmapp = True
                else:
                    feature = FaceFeatureRecord(
                        album_id=album.id,
                        aibox_id=aibox_id,
                        bmapp_id=bmapp_id,
                        name=name,
                        jpeg_path=jpeg_path,
                        extra_data=item,
                        is_synced_bmapp=True,
                    )
                    db.add(feature)
                synced += 1
            album.feature_count = db.query(FaceFeatureRecord).filter(FaceFeatureRecord.album_id == album.id).count()
        except Exception as e:
            errors.append(f"Album {album.name}: {str(e)}")
    db.commit()
    return SyncResult(success=True, synced_count=synced, message=f"Synced {synced} features", errors=errors)
