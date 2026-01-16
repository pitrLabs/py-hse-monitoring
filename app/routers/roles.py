from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app import schemas
from app.auth import get_current_superuser, require_permission
from app.database import get_db
from app.models import User, Role, Permission
router = APIRouter(prefix="/roles", tags=["Role & Permission Management"])

@router.get("/permissions", response_model=List[schemas.PermissionResponse])
def list_permissions(skip: int = 0, limit: int = 100, db: Session = Depends(get_db),
                     _: User = Depends(require_permission("roles", "read"))):
    permissions = db.query(Permission).offset(skip).limit(limit).all()

    return permissions


@router.post("/permissions", response_model=schemas.PermissionResponse, status_code=status.HTTP_201_CREATED)
def create_permission(permission_data: schemas.PermissionCreate, db: Session = Depends(get_db),
                      _: User = Depends(get_current_superuser)):
    if db.query(Permission).filter(Permission.name == permission_data.name).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Permission already exists")
    
    db_permission = Permission(name=permission_data.name,
                               resource=permission_data.resource,
                               action=permission_data.action,
                               description=permission_data.description)
    
    db.add(db_permission)
    db.commit()
    db.refresh(db_permission)
    
    return db_permission


@router.delete("/permissions/{permission_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_permission(permission_id: int, db: Session = Depends(get_db),
                      _: User = Depends(get_current_superuser)):
    permission = db.query(Permission).filter(Permission.id == permission_id).first()

    if not permission:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Permission not found")
    
    db.delete(permission)
    db.commit()
    
    return None


@router.get("/", response_model=List[schemas.RoleResponse])
def list_roles(skip: int = 0, limit: int = 100, db: Session = Depends(get_db),
               _: User = Depends(require_permission("roles", "read"))):
    roles = db.query(Role).offset(skip).limit(limit).all()

    return roles


@router.get("/{role_id}", response_model=schemas.RoleResponse)
def get_role(role_id: int, db: Session = Depends(get_db),
             _: User = Depends(require_permission("roles", "read"))):
    role = db.query(Role).filter(Role.id == role_id).first()

    if not role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")

    return role


@router.post("/", response_model=schemas.RoleResponse, status_code=status.HTTP_201_CREATED)
def create_role(role_data: schemas.RoleCreate, db: Session = Depends(get_db),
                _: User = Depends(require_permission("roles", "create"))):
    if db.query(Role).filter(Role.name == role_data.name).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Role already exists")
    
    db_role = Role(name=role_data.name, description=role_data.description)

    if role_data.permission_ids:
        permissions = db.query(Permission).filter(Permission.id.in_(role_data.permission_ids)).all()
        db_role.permissions = permissions
    
    db.add(db_role)
    db.commit()
    db.refresh(db_role)
    
    return db_role


@router.put("/{role_id}", response_model=schemas.RoleResponse)
def update_role(role_id: int, role_update: schemas.RoleUpdate, db: Session = Depends(get_db),
                _: User = Depends(require_permission("roles", "update"))):
    role = db.query(Role).filter(Role.id == role_id).first()

    if not role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Role not found")
    
    if role_update.name is not None:
        existing_role = db.query(Role).filter(Role.name == role_update.name,
                                              Role.id != role_id).first()
        if existing_role:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="Role name already exists")

        role.name = role_update.name
    
    if role_update.description is not None:
        role.description = role_update.description
    
    if role_update.permission_ids is not None:
        permissions = db.query(Permission).filter(Permission.id.in_(role_update.permission_ids)).all()
        role.permissions = permissions
    
    db.commit()
    db.refresh(role)
    
    return role


@router.delete("/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_role(role_id: int, db: Session = Depends(get_db),
                _: User = Depends(require_permission("roles", "delete"))):
    role = db.query(Role).filter(Role.id == role_id).first()

    if not role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Role not found")
    
    db.delete(role)
    db.commit()
    
    return None
