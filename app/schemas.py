from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, EmailStr, Field
from uuid import UUID


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: Optional[str] = None


class PermissionBase(BaseModel):
    name: str
    resource: str
    action: str
    description: Optional[str] = None


class PermissionCreate(PermissionBase):
    pass


class PermissionResponse(PermissionBase):
    id: UUID
    created_at: datetime

    class Config:
        from_attributes = True


class RoleBase(BaseModel):
    name: str
    description: Optional[str] = None


class RoleCreate(RoleBase):
    permission_ids: List[int] = []


class RoleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    permission_ids: Optional[List[int]] = None


class RoleResponse(RoleBase):
    id: UUID
    created_at: datetime
    permissions: List[PermissionResponse] = []

    class Config:
        from_attributes = True


class UserBase(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    full_name: Optional[str] = None


class UserCreate(UserBase):
    password: str = Field(..., min_length=6)
    user_level: int = Field(default=1, ge=1, le=10)
    role_ids: List[int] = []


class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    password: Optional[str] = Field(None, min_length=6)
    is_active: Optional[bool] = None
    user_level: Optional[int] = Field(None, ge=1, le=10)
    role_ids: Optional[List[int]] = None


class UserResponse(UserBase):
    id: UUID
    is_active: bool
    is_superuser: bool
    user_level: int
    created_at: datetime
    updated_at: datetime
    roles: List[RoleResponse] = []

    class Config:
        from_attributes = True


class UserLogin(BaseModel):
    username: str
    password: str


class VideoSourceBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    url: str = Field(..., min_length=1, max_length=500)
    stream_name: str = Field(..., min_length=1, max_length=100, pattern="^[a-zA-Z0-9_-]+$")
    source_type: str = Field(default="rtsp", pattern="^(rtsp|http|file)$")
    description: Optional[str] = None
    location: Optional[str] = None
    is_active: bool = True


class VideoSourceCreate(VideoSourceBase):
    pass


class VideoSourceUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    url: Optional[str] = Field(None, min_length=1, max_length=500)
    stream_name: Optional[str] = Field(None, min_length=1, max_length=100, pattern="^[a-zA-Z0-9_-]+$")
    source_type: Optional[str] = Field(None, pattern="^(rtsp|http|file)$")
    description: Optional[str] = None
    location: Optional[str] = None
    is_active: Optional[bool] = None


class VideoSourceResponse(VideoSourceBase):
    id: UUID
    created_at: datetime
    updated_at: datetime
    created_by_id: Optional[UUID] = None

    class Config:
        from_attributes = True


# Alarm Schemas
class AlarmBase(BaseModel):
    alarm_type: str
    alarm_name: str
    camera_id: Optional[str] = None
    camera_name: Optional[str] = None
    location: Optional[str] = None
    confidence: float = 0.0
    image_url: Optional[str] = None
    video_url: Optional[str] = None
    description: Optional[str] = None


class AlarmCreate(AlarmBase):
    bmapp_id: Optional[str] = None
    raw_data: Optional[str] = None
    alarm_time: datetime


class AlarmResponse(AlarmBase):
    id: UUID
    bmapp_id: Optional[str] = None
    status: str
    alarm_time: datetime
    created_at: datetime
    acknowledged_at: Optional[datetime] = None
    acknowledged_by_id: Optional[UUID] = None
    resolved_at: Optional[datetime] = None
    resolved_by_id: Optional[UUID] = None

    class Config:
        from_attributes = True


class AlarmUpdate(BaseModel):
    status: Optional[str] = Field(None, pattern="^(new|acknowledged|resolved)$")


class AlarmFilter(BaseModel):
    alarm_type: Optional[str] = None
    camera_id: Optional[str] = None
    status: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
