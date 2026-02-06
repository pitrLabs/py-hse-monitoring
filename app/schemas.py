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
    permission_ids: List[UUID] = []


class RoleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    permission_ids: Optional[List[UUID]] = None


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
    role_ids: List[UUID] = []
    is_superuser: bool = False


class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    password: Optional[str] = Field(None, min_length=6)
    is_active: Optional[bool] = None
    is_superuser: Optional[bool] = None
    role_ids: Optional[List[UUID]] = None


class UserResponse(UserBase):
    id: UUID
    is_active: bool
    is_superuser: bool
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
    group_id: Optional[UUID] = None
    is_active: bool = True
    sound_alert: bool = False


class VideoSourceCreate(VideoSourceBase):
    pass


class VideoSourceUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    url: Optional[str] = Field(None, min_length=1, max_length=500)
    stream_name: Optional[str] = Field(None, min_length=1, max_length=100, pattern="^[a-zA-Z0-9_-]+$")
    source_type: Optional[str] = Field(None, pattern="^(rtsp|http|file)$")
    description: Optional[str] = None
    location: Optional[str] = None
    group_id: Optional[UUID] = None
    is_active: Optional[bool] = None
    sound_alert: Optional[bool] = None


class VideoSourceResponse(BaseModel):
    """Response schema - no pattern validation since data already exists in DB"""
    id: UUID
    name: str
    url: str
    stream_name: str  # No pattern validation for response
    source_type: str
    description: Optional[str] = None
    location: Optional[str] = None
    group_id: Optional[UUID] = None
    is_active: bool
    sound_alert: bool
    is_synced_bmapp: bool = False
    bmapp_sync_error: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    created_by_id: Optional[UUID] = None

    class Config:
        from_attributes = True


# AI Task Schemas
class AITaskBase(BaseModel):
    task_name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None


class AITaskCreate(BaseModel):
    video_source_id: UUID
    task_name: Optional[str] = None  # Auto-generated if not provided
    algorithms: List[int] = Field(default=[195, 5], description="Algorithm IDs, e.g. [195, 5] for helmet+person detection")
    description: Optional[str] = None
    auto_start: bool = True  # Automatically start the task after creation


class AITaskUpdate(BaseModel):
    algorithms: Optional[List[int]] = None
    description: Optional[str] = None
    status: Optional[str] = Field(None, pattern="^(pending|running|stopped|failed)$")


class AITaskResponse(AITaskBase):
    id: UUID
    video_source_id: UUID
    algorithms: Optional[List[int]] = None
    status: str
    is_synced_bmapp: bool = False
    bmapp_sync_error: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    started_at: Optional[datetime] = None
    stopped_at: Optional[datetime] = None
    created_by_id: Optional[UUID] = None
    # Include video source info
    video_source: Optional["VideoSourceResponse"] = None

    class Config:
        from_attributes = True


class AITaskControl(BaseModel):
    action: str = Field(..., pattern="^(start|stop|restart)$")


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


# Camera Location Schemas
class CameraLocationBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    location_type: Optional[str] = None
    description: Optional[str] = None
    address: Optional[str] = None


class CameraLocationCreate(CameraLocationBase):
    external_id: Optional[str] = None
    source: str = "manual"
    extra_data: Optional[dict] = None


class CameraLocationUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    location_type: Optional[str] = None
    description: Optional[str] = None
    address: Optional[str] = None
    is_active: Optional[bool] = None


class CameraLocationResponse(CameraLocationBase):
    id: UUID
    external_id: Optional[str] = None
    source: str
    extra_data: Optional[dict] = None
    is_active: bool
    last_synced_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Camera Group Schemas (for folder renaming)
class CameraGroupBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    display_name: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = None


class CameraGroupCreate(CameraGroupBase):
    pass


class CameraGroupUpdate(BaseModel):
    display_name: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = None
    is_active: Optional[bool] = None


class CameraGroupResponse(CameraGroupBase):
    id: UUID
    user_id: Optional[UUID] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    created_by_id: Optional[UUID] = None

    class Config:
        from_attributes = True


class CameraGroupAssignment(BaseModel):
    """Per-user camera-to-group assignment"""
    video_source_id: UUID
    group_id: UUID


class CameraGroupAssignmentsResponse(BaseModel):
    """Response for user's camera-group assignments"""
    assignments: dict  # {video_source_id: group_id}


class SyncResult(BaseModel):
    synced: int
    created: int
    updated: int
    errors: List[str] = []


# Recording Schemas
class RecordingBase(BaseModel):
    file_name: str = Field(..., min_length=1, max_length=300)
    file_url: Optional[str] = None
    file_size: Optional[int] = None
    duration: Optional[int] = None
    camera_id: Optional[str] = None
    camera_name: Optional[str] = None
    task_session: Optional[str] = None
    trigger_type: str = Field(default="alarm", pattern="^(alarm|manual|schedule)$")
    thumbnail_url: Optional[str] = None


class RecordingCreate(RecordingBase):
    bmapp_id: Optional[str] = None
    start_time: datetime
    end_time: Optional[datetime] = None
    alarm_id: Optional[UUID] = None


class RecordingUpdate(BaseModel):
    file_url: Optional[str] = None
    file_size: Optional[int] = None
    duration: Optional[int] = None
    end_time: Optional[datetime] = None
    thumbnail_url: Optional[str] = None
    is_available: Optional[bool] = None


class RecordingResponse(RecordingBase):
    id: UUID
    bmapp_id: Optional[str] = None
    start_time: datetime
    end_time: Optional[datetime] = None
    alarm_id: Optional[UUID] = None
    is_available: bool
    created_at: datetime
    synced_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class RecordingFilter(BaseModel):
    camera_id: Optional[str] = None
    task_session: Optional[str] = None
    trigger_type: Optional[str] = None
    alarm_id: Optional[UUID] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    is_available: Optional[bool] = True


class RecordingCalendarDay(BaseModel):
    date: str  # YYYY-MM-DD format
    count: int
    has_recordings: bool


# User Camera Assignment Schemas
class UserCameraAssignment(BaseModel):
    """Schema for assigning cameras to a user"""
    video_source_ids: List[UUID] = Field(..., description="List of video source IDs to assign to the user")


class UserWithAssignedCameras(UserResponse):
    """Extended user response with assigned cameras"""
    assigned_video_sources: List[VideoSourceResponse] = []

    class Config:
        from_attributes = True


class VideoSourceWithAssignedUsers(VideoSourceResponse):
    """Extended video source response with assigned users (minimal user info)"""
    assigned_user_ids: List[UUID] = []

    class Config:
        from_attributes = True


# ============ Analytics Schemas (BM-APP Data Entities) ============

class PeopleCountResponse(BaseModel):
    id: UUID
    bmapp_id: Optional[str] = None
    camera_name: Optional[str] = None
    task_session: Optional[str] = None
    count_in: int
    count_out: int
    total: int
    record_time: datetime
    extra_data: Optional[dict] = None
    synced_at: datetime

    class Config:
        from_attributes = True


class ZoneOccupancyResponse(BaseModel):
    id: UUID
    bmapp_id: Optional[str] = None
    camera_name: Optional[str] = None
    task_session: Optional[str] = None
    zone_name: Optional[str] = None
    people_count: int
    record_time: datetime
    extra_data: Optional[dict] = None
    synced_at: datetime

    class Config:
        from_attributes = True


class ZoneOccupancyAvgResponse(BaseModel):
    id: UUID
    bmapp_id: Optional[str] = None
    camera_name: Optional[str] = None
    task_session: Optional[str] = None
    zone_name: Optional[str] = None
    avg_count: float
    period_start: datetime
    period_end: Optional[datetime] = None
    extra_data: Optional[dict] = None
    synced_at: datetime

    class Config:
        from_attributes = True


class StoreCountResponse(BaseModel):
    id: UUID
    bmapp_id: Optional[str] = None
    camera_name: Optional[str] = None
    task_session: Optional[str] = None
    entry_count: int
    exit_count: int
    record_date: datetime
    extra_data: Optional[dict] = None
    synced_at: datetime

    class Config:
        from_attributes = True


class StayDurationResponse(BaseModel):
    id: UUID
    bmapp_id: Optional[str] = None
    camera_name: Optional[str] = None
    task_session: Optional[str] = None
    zone_name: Optional[str] = None
    avg_duration: float
    max_duration: float
    min_duration: float
    sample_count: int
    record_time: datetime
    extra_data: Optional[dict] = None
    synced_at: datetime

    class Config:
        from_attributes = True


class ScheduleResponse(BaseModel):
    id: UUID
    bmapp_id: Optional[str] = None
    task_session: Optional[str] = None
    schedule_name: Optional[str] = None
    schedule_type: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    days_of_week: Optional[str] = None
    is_enabled: bool
    extra_data: Optional[dict] = None
    synced_at: datetime

    class Config:
        from_attributes = True


class SensorDeviceResponse(BaseModel):
    id: UUID
    bmapp_id: Optional[str] = None
    device_name: str
    device_type: Optional[str] = None
    location: Optional[str] = None
    is_online: bool
    extra_data: Optional[dict] = None
    synced_at: datetime

    class Config:
        from_attributes = True


class SensorDataResponse(BaseModel):
    id: UUID
    bmapp_id: Optional[str] = None
    sensor_device_id: Optional[UUID] = None
    sensor_bmapp_id: Optional[str] = None
    value: float
    unit: Optional[str] = None
    record_time: datetime
    extra_data: Optional[dict] = None
    synced_at: datetime

    class Config:
        from_attributes = True


class AnalyticsSyncResult(BaseModel):
    entity: str
    synced: int
    errors: List[str] = []
