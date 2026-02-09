"""
AI Box Router - Manage multiple AI boxes (BM-APP instances)
"""
from datetime import datetime
from typing import List, Optional
from uuid import UUID
import asyncio
import time

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
import httpx

from app.database import get_db
from app.models import AIBox, VideoSource, User
from app.auth import get_current_user
from app import schemas

router = APIRouter(prefix="/ai-boxes", tags=["AI Boxes"])


@router.get("/", response_model=List[schemas.AIBoxResponse])
def list_ai_boxes(
    is_active: Optional[bool] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List all AI boxes with camera count."""
    query = db.query(AIBox)

    if is_active is not None:
        query = query.filter(AIBox.is_active == is_active)

    ai_boxes = query.order_by(AIBox.name).all()

    # Add camera count for each AI box
    result = []
    for box in ai_boxes:
        box_dict = {
            "id": box.id,
            "name": box.name,
            "code": box.code,
            "api_url": box.api_url,
            "alarm_ws_url": box.alarm_ws_url,
            "stream_ws_url": box.stream_ws_url,
            "is_active": box.is_active,
            "is_online": box.is_online,
            "last_seen_at": box.last_seen_at,
            "last_error": box.last_error,
            "created_at": box.created_at,
            "updated_at": box.updated_at,
            "camera_count": db.query(func.count(VideoSource.id)).filter(
                VideoSource.aibox_id == box.id
            ).scalar() or 0
        }
        result.append(schemas.AIBoxResponse(**box_dict))

    return result


@router.get("/health", response_model=schemas.AIBoxHealthResponse)
async def get_ai_boxes_health(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Check health status of all active AI boxes."""
    ai_boxes = db.query(AIBox).filter(AIBox.is_active == True).all()

    async def check_box_health(box: AIBox) -> schemas.AIBoxStatus:
        start_time = time.time()
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{box.api_url}/status")
                latency_ms = int((time.time() - start_time) * 1000)

                if response.status_code == 200:
                    # Update database
                    box.is_online = True
                    box.last_seen_at = datetime.utcnow()
                    box.last_error = None
                    return schemas.AIBoxStatus(
                        id=box.id,
                        name=box.name,
                        code=box.code,
                        is_online=True,
                        last_seen_at=box.last_seen_at,
                        latency_ms=latency_ms
                    )
        except Exception as e:
            box.is_online = False
            box.last_error = str(e)[:500]

        return schemas.AIBoxStatus(
            id=box.id,
            name=box.name,
            code=box.code,
            is_online=False,
            last_seen_at=box.last_seen_at,
            last_error=box.last_error
        )

    # Check all boxes concurrently
    tasks = [check_box_health(box) for box in ai_boxes]
    results = await asyncio.gather(*tasks)

    db.commit()

    online_count = sum(1 for r in results if r.is_online)

    return schemas.AIBoxHealthResponse(
        total=len(results),
        online=online_count,
        offline=len(results) - online_count,
        boxes=results
    )


@router.get("/{aibox_id}", response_model=schemas.AIBoxResponse)
def get_ai_box(
    aibox_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a single AI box by ID."""
    ai_box = db.query(AIBox).filter(AIBox.id == aibox_id).first()
    if not ai_box:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="AI Box not found"
        )

    camera_count = db.query(func.count(VideoSource.id)).filter(
        VideoSource.aibox_id == ai_box.id
    ).scalar() or 0

    return schemas.AIBoxResponse(
        id=ai_box.id,
        name=ai_box.name,
        code=ai_box.code,
        api_url=ai_box.api_url,
        alarm_ws_url=ai_box.alarm_ws_url,
        stream_ws_url=ai_box.stream_ws_url,
        is_active=ai_box.is_active,
        is_online=ai_box.is_online,
        last_seen_at=ai_box.last_seen_at,
        last_error=ai_box.last_error,
        created_at=ai_box.created_at,
        updated_at=ai_box.updated_at,
        camera_count=camera_count
    )


@router.post("/", response_model=schemas.AIBoxResponse, status_code=status.HTTP_201_CREATED)
def create_ai_box(
    ai_box_data: schemas.AIBoxCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new AI box."""
    # Check for duplicate code
    existing = db.query(AIBox).filter(AIBox.code == ai_box_data.code).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"AI Box with code '{ai_box_data.code}' already exists"
        )

    ai_box = AIBox(
        name=ai_box_data.name,
        code=ai_box_data.code,
        api_url=ai_box_data.api_url,
        alarm_ws_url=ai_box_data.alarm_ws_url,
        stream_ws_url=ai_box_data.stream_ws_url,
        is_active=ai_box_data.is_active
    )

    db.add(ai_box)
    db.commit()
    db.refresh(ai_box)

    return schemas.AIBoxResponse(
        id=ai_box.id,
        name=ai_box.name,
        code=ai_box.code,
        api_url=ai_box.api_url,
        alarm_ws_url=ai_box.alarm_ws_url,
        stream_ws_url=ai_box.stream_ws_url,
        is_active=ai_box.is_active,
        is_online=ai_box.is_online,
        last_seen_at=ai_box.last_seen_at,
        last_error=ai_box.last_error,
        created_at=ai_box.created_at,
        updated_at=ai_box.updated_at,
        camera_count=0
    )


@router.put("/{aibox_id}", response_model=schemas.AIBoxResponse)
def update_ai_box(
    aibox_id: UUID,
    ai_box_data: schemas.AIBoxUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update an AI box."""
    ai_box = db.query(AIBox).filter(AIBox.id == aibox_id).first()
    if not ai_box:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="AI Box not found"
        )

    # Check for duplicate code if updating code
    if ai_box_data.code and ai_box_data.code != ai_box.code:
        existing = db.query(AIBox).filter(AIBox.code == ai_box_data.code).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"AI Box with code '{ai_box_data.code}' already exists"
            )

    update_data = ai_box_data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(ai_box, key, value)

    db.commit()
    db.refresh(ai_box)

    camera_count = db.query(func.count(VideoSource.id)).filter(
        VideoSource.aibox_id == ai_box.id
    ).scalar() or 0

    return schemas.AIBoxResponse(
        id=ai_box.id,
        name=ai_box.name,
        code=ai_box.code,
        api_url=ai_box.api_url,
        alarm_ws_url=ai_box.alarm_ws_url,
        stream_ws_url=ai_box.stream_ws_url,
        is_active=ai_box.is_active,
        is_online=ai_box.is_online,
        last_seen_at=ai_box.last_seen_at,
        last_error=ai_box.last_error,
        created_at=ai_box.created_at,
        updated_at=ai_box.updated_at,
        camera_count=camera_count
    )


@router.delete("/{aibox_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_ai_box(
    aibox_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete an AI box."""
    ai_box = db.query(AIBox).filter(AIBox.id == aibox_id).first()
    if not ai_box:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="AI Box not found"
        )

    # Check if any cameras are linked
    camera_count = db.query(func.count(VideoSource.id)).filter(
        VideoSource.aibox_id == ai_box.id
    ).scalar() or 0

    if camera_count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete AI Box with {camera_count} linked cameras. Unlink cameras first."
        )

    db.delete(ai_box)
    db.commit()


@router.post("/{aibox_id}/test", response_model=schemas.AIBoxStatus)
async def test_ai_box_connection(
    aibox_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Test connection to an AI box."""
    ai_box = db.query(AIBox).filter(AIBox.id == aibox_id).first()
    if not ai_box:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="AI Box not found"
        )

    start_time = time.time()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{ai_box.api_url}/status")
            latency_ms = int((time.time() - start_time) * 1000)

            if response.status_code == 200:
                ai_box.is_online = True
                ai_box.last_seen_at = datetime.utcnow()
                ai_box.last_error = None
                db.commit()

                return schemas.AIBoxStatus(
                    id=ai_box.id,
                    name=ai_box.name,
                    code=ai_box.code,
                    is_online=True,
                    last_seen_at=ai_box.last_seen_at,
                    latency_ms=latency_ms
                )
            else:
                raise Exception(f"HTTP {response.status_code}")
    except Exception as e:
        ai_box.is_online = False
        ai_box.last_error = str(e)[:500]
        db.commit()

        return schemas.AIBoxStatus(
            id=ai_box.id,
            name=ai_box.name,
            code=ai_box.code,
            is_online=False,
            last_seen_at=ai_box.last_seen_at,
            last_error=str(e)[:500]
        )


@router.get("/{aibox_id}/cameras", response_model=List[schemas.VideoSourceResponse])
def get_ai_box_cameras(
    aibox_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all cameras linked to an AI box."""
    ai_box = db.query(AIBox).filter(AIBox.id == aibox_id).first()
    if not ai_box:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="AI Box not found"
        )

    cameras = db.query(VideoSource).filter(
        VideoSource.aibox_id == aibox_id
    ).order_by(VideoSource.name).all()

    return cameras
