from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app import schemas
from app.auth import (
    get_password_hash,
    get_current_superuser,
    require_permission,
)
from app.database import get_db
from app.models import User, Role, VideoSource

router = APIRouter(prefix="/users", tags=["User Management"])

@router.get("/", response_model=List[schemas.UserWithAssignedCameras])
def list_users(skip: int = 0, limit: int = 100, db: Session = Depends(get_db),
               _: User = Depends(require_permission("users", "read"))):
    users = db.query(User).offset(skip).limit(limit).all()

    return users


@router.get("/{user_id}", response_model=schemas.UserWithAssignedCameras)
def get_user(user_id: UUID, db: Session = Depends(get_db),
             _: User = Depends(require_permission("users", "read"))):
    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    return user


@router.post("/", response_model=schemas.UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(user_data: schemas.UserCreate, db: Session = Depends(get_db),
                _: User = Depends(require_permission("users", "create"))):
    if db.query(User).filter(User.username == user_data.username).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username already registered")

    if db.query(User).filter(User.email == user_data.email).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

    db_user = User(username=user_data.username, email=user_data.email, full_name=user_data.full_name,
                   hashed_password=get_password_hash(user_data.password), user_level=user_data.user_level)

    if user_data.role_ids:
        roles = db.query(Role).filter(Role.id.in_(user_data.role_ids)).all()
        db_user.roles = roles
    
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    
    return db_user


@router.put("/{user_id}", response_model=schemas.UserResponse)
def update_user(user_id: UUID, user_update: schemas.UserUpdate, db: Session = Depends(get_db),
                _: User = Depends(require_permission("users", "update"))):
    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    
    if user_update.email is not None:
        existing_user = db.query(User).filter(User.email == user_update.email,
                                              User.id != user_id).first()
        if existing_user:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

        user.email = user_update.email
    
    if user_update.full_name is not None:
        user.full_name = user_update.full_name
    
    if user_update.password is not None:
        user.hashed_password = get_password_hash(user_update.password)
    
    if user_update.is_active is not None:
        user.is_active = user_update.is_active
    
    if user_update.user_level is not None:
        user.user_level = user_update.user_level
    
    if user_update.role_ids is not None:
        roles = db.query(Role).filter(Role.id.in_(user_update.role_ids)).all()
        user.roles = roles
    
    db.commit()
    db.refresh(user)
    
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: UUID, db: Session = Depends(get_db),
                _: User = Depends(require_permission("users", "delete"))):
    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    db.delete(user)
    db.commit()

    return None


# Camera Assignment Endpoints

@router.get("/{user_id}/cameras", response_model=schemas.UserWithAssignedCameras)
def get_user_cameras(user_id: UUID, db: Session = Depends(get_db),
                     _: User = Depends(require_permission("users", "read"))):
    """Get user with their assigned cameras"""
    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    return user


@router.put("/{user_id}/cameras", response_model=schemas.UserWithAssignedCameras)
def assign_cameras_to_user(user_id: UUID, assignment: schemas.UserCameraAssignment,
                           db: Session = Depends(get_db),
                           _: User = Depends(require_permission("users", "update"))):
    """Assign cameras to a user (replaces existing assignments)"""
    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # Get all video sources by IDs
    video_sources = db.query(VideoSource).filter(
        VideoSource.id.in_(assignment.video_source_ids)
    ).all()

    # Validate all IDs exist
    found_ids = {vs.id for vs in video_sources}
    missing_ids = set(assignment.video_source_ids) - found_ids
    if missing_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Video sources not found: {[str(id) for id in missing_ids]}"
        )

    # Assign cameras to user (replaces existing)
    user.assigned_video_sources = video_sources
    db.commit()
    db.refresh(user)

    return user


@router.post("/{user_id}/cameras/{video_source_id}", response_model=schemas.UserWithAssignedCameras)
def add_camera_to_user(user_id: UUID, video_source_id: UUID,
                       db: Session = Depends(get_db),
                       _: User = Depends(require_permission("users", "update"))):
    """Add a single camera to user's assignments"""
    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    video_source = db.query(VideoSource).filter(VideoSource.id == video_source_id).first()

    if not video_source:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video source not found")

    # Add if not already assigned
    if video_source not in user.assigned_video_sources:
        user.assigned_video_sources.append(video_source)
        db.commit()
        db.refresh(user)

    return user


@router.delete("/{user_id}/cameras/{video_source_id}", response_model=schemas.UserWithAssignedCameras)
def remove_camera_from_user(user_id: UUID, video_source_id: UUID,
                            db: Session = Depends(get_db),
                            _: User = Depends(require_permission("users", "update"))):
    """Remove a camera from user's assignments"""
    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    video_source = db.query(VideoSource).filter(VideoSource.id == video_source_id).first()

    if not video_source:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video source not found")

    # Remove if assigned
    if video_source in user.assigned_video_sources:
        user.assigned_video_sources.remove(video_source)
        db.commit()
        db.refresh(user)

    return user
