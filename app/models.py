from datetime import datetime
from typing import List
import uuid

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Index, Integer, String, Table, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass

user_roles = Table("user_roles",
                   Base.metadata,
                   Column("user_id", UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
                   Column("role_id", UUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True))

role_permissions = Table("role_permissions",
                         Base.metadata,
                         Column("role_id", UUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
                         Column("permission_id", UUID(as_uuid=True), ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True))

# Many-to-many relationship for camera assignment to operators
user_video_sources = Table("user_video_sources",
                           Base.metadata,
                           Column("user_id", UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
                           Column("video_source_id", UUID(as_uuid=True), ForeignKey("video_sources.id", ondelete="CASCADE"), primary_key=True))

# Per-user camera-to-group assignments (each user has their own folder organization)
user_camera_group_assignments = Table("user_camera_group_assignments",
                                      Base.metadata,
                                      Column("user_id", UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
                                      Column("video_source_id", UUID(as_uuid=True), ForeignKey("video_sources.id", ondelete="CASCADE"), primary_key=True),
                                      Column("group_id", UUID(as_uuid=True), ForeignKey("camera_groups.id", ondelete="CASCADE"), nullable=False))


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    email: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    active_session_id: Mapped[str | None] = mapped_column(String(64))  # Current active session - only one allowed
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime)  # Track last login time
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    roles: Mapped[List["Role"]] = relationship("Role", secondary=user_roles, back_populates="users", lazy="selectin")
    # Assigned cameras for operators - only these cameras will be visible to the user
    assigned_video_sources: Mapped[List["VideoSource"]] = relationship("VideoSource", secondary=user_video_sources, back_populates="assigned_users", lazy="selectin")


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    users: Mapped[List["User"]] = relationship("User", secondary=user_roles, back_populates="roles", lazy="selectin")
    permissions: Mapped[List["Permission"]] = relationship("Permission", secondary=role_permissions, back_populates="roles", lazy="selectin")


class Permission(Base):
    __tablename__ = "permissions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    resource: Mapped[str] = mapped_column(String(50), nullable=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    roles: Mapped[List["Role"]] = relationship("Role", secondary=role_permissions, back_populates="permissions", lazy="selectin")


class AIBox(Base):
    """AI Box / BM-APP instance"""
    __tablename__ = "ai_boxes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)  # "Site Semarang", "Site Pekalongan"
    code: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)  # "SMG", "PKL"
    api_url: Mapped[str] = mapped_column(String(500), nullable=False)  # http://103.75.84.183:2323/api
    alarm_ws_url: Mapped[str] = mapped_column(String(500), nullable=False)  # ws://103.75.84.183:2323/alarm/
    stream_ws_url: Mapped[str] = mapped_column(String(500), nullable=False)  # ws://103.75.84.183:2323/ws (for video)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_online: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_error: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    video_sources: Mapped[List["VideoSource"]] = relationship("VideoSource", back_populates="aibox", lazy="selectin")


class VideoSource(Base):
    __tablename__ = "video_sources"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    stream_name: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)  # MediaMTX stream identifier
    source_type: Mapped[str] = mapped_column(String(20), default="rtsp", nullable=False)  # rtsp, http, file
    description: Mapped[str | None] = mapped_column(String(500))
    location: Mapped[str | None] = mapped_column(String(200))
    group_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("camera_groups.id", ondelete="SET NULL"))
    aibox_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("ai_boxes.id", ondelete="SET NULL"), index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sound_alert: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)  # Play sound when alarm detected
    is_synced_bmapp: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)  # Synced to BM-APP
    bmapp_sync_error: Mapped[str | None] = mapped_column(String(500))  # Last sync error message
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    created_by: Mapped["User | None"] = relationship("User", foreign_keys=[created_by_id], lazy="selectin")
    group: Mapped["CameraGroup | None"] = relationship("CameraGroup", lazy="selectin")
    aibox: Mapped["AIBox | None"] = relationship("AIBox", back_populates="video_sources", lazy="selectin")
    ai_tasks: Mapped[List["AITask"]] = relationship("AITask", back_populates="video_source", lazy="selectin", passive_deletes=True)
    # Users (operators) who have access to this camera
    assigned_users: Mapped[List["User"]] = relationship("User", secondary=user_video_sources, back_populates="assigned_video_sources", lazy="selectin", passive_deletes=True)

    @property
    def task_session(self) -> str | None:
        """Get the first AI task's session name"""
        if self.ai_tasks and len(self.ai_tasks) > 0:
            return self.ai_tasks[0].task_name
        return None


class AITask(Base):
    """AI detection task linked to a video source"""
    __tablename__ = "ai_tasks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    task_name: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)  # AlgTaskSession in BM-APP
    video_source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("video_sources.id", ondelete="CASCADE"), nullable=False)
    algorithms: Mapped[dict | None] = mapped_column(JSONB)  # List of algorithm IDs e.g. [195, 5]
    description: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)  # pending, running, stopped, failed
    is_synced_bmapp: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)  # Synced to BM-APP
    bmapp_sync_error: Mapped[str | None] = mapped_column(String(500))  # Last sync error message
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))

    # Relationships
    video_source: Mapped["VideoSource"] = relationship("VideoSource", back_populates="ai_tasks", lazy="selectin")
    created_by: Mapped["User | None"] = relationship("User", lazy="selectin")


class Alarm(Base):
    __tablename__ = "alarms"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    bmapp_id: Mapped[str | None] = mapped_column(String(100), index=True)  # Original ID from BM-APP
    aibox_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("ai_boxes.id", ondelete="SET NULL"), index=True)
    aibox_name: Mapped[str | None] = mapped_column(String(100))  # Denormalized for display
    alarm_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)  # e.g. "NoHelmet", "Intrusion"
    alarm_name: Mapped[str] = mapped_column(String(200), nullable=False)
    camera_id: Mapped[str | None] = mapped_column(String(100), index=True)
    camera_name: Mapped[str | None] = mapped_column(String(200))
    location: Mapped[str | None] = mapped_column(String(300))
    confidence: Mapped[float] = mapped_column(default=0.0, nullable=False)
    image_url: Mapped[str | None] = mapped_column(String(500))
    video_url: Mapped[str | None] = mapped_column(String(500))
    media_url: Mapped[str | None] = mapped_column(String(500))  # RTSP URL for video source
    description: Mapped[str | None] = mapped_column(String(1000))
    raw_data: Mapped[str | None] = mapped_column(String(5000))  # Original JSON from BM-APP
    status: Mapped[str] = mapped_column(String(20), default="new", nullable=False)  # new, acknowledged, resolved
    alarm_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime)
    acknowledged_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime)
    resolved_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    # MinIO storage fields
    minio_image_path: Mapped[str | None] = mapped_column(String(500))  # Path in MinIO bucket (raw image)
    minio_labeled_image_path: Mapped[str | None] = mapped_column(String(500))  # Path for labeled image (with detection boxes)
    minio_video_path: Mapped[str | None] = mapped_column(String(500))  # Path in MinIO bucket
    minio_synced_at: Mapped[datetime | None] = mapped_column(DateTime)  # When synced to MinIO

    # Relationships
    aibox: Mapped["AIBox | None"] = relationship("AIBox", lazy="selectin")


class CameraLocation(Base):
    """Camera/keypoint locations from external API (RTU UP2DJTY)"""
    __tablename__ = "camera_locations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    external_id: Mapped[str | None] = mapped_column(String(100), index=True)  # ID from external API
    source: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # 'keypoint' or 'gps_tim_har'
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    location_type: Mapped[str | None] = mapped_column(String(100))  # Type/category from API
    description: Mapped[str | None] = mapped_column(String(500))
    address: Mapped[str | None] = mapped_column(String(500))
    extra_data: Mapped[dict | None] = mapped_column(JSONB)  # Store extra fields from API
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class LocationHistory(Base):
    """Historical GPS positions for tracking device movement over time"""
    __tablename__ = "location_history"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    device_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)  # id_alat from RTU API
    device_name: Mapped[str | None] = mapped_column(String(200))  # nama_tim
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # ON/OFF
    is_online: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    extra_data: Mapped[dict | None] = mapped_column(JSONB)  # Store extra fields from API
    recorded_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)  # When this position was recorded
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class CameraGroup(Base):
    """Camera groups/folders for organizing cameras - per user"""
    __tablename__ = "camera_groups"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(100))  # Custom display name (renamed by user)
    description: Mapped[str | None] = mapped_column(String(500))
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)  # Owner user (NULL = global/legacy)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))


class Recording(Base):
    """Video recordings from BM-APP"""
    __tablename__ = "recordings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    bmapp_id: Mapped[str | None] = mapped_column(String(100), index=True)  # VideoFile ID from BM-APP
    file_name: Mapped[str] = mapped_column(String(300), nullable=False)
    file_url: Mapped[str | None] = mapped_column(String(500))
    file_size: Mapped[int | None] = mapped_column()  # bytes
    duration: Mapped[int | None] = mapped_column()  # seconds
    camera_id: Mapped[str | None] = mapped_column(String(100), index=True)
    camera_name: Mapped[str | None] = mapped_column(String(200))
    task_session: Mapped[str | None] = mapped_column(String(100))
    start_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    end_time: Mapped[datetime | None] = mapped_column(DateTime)
    trigger_type: Mapped[str] = mapped_column(String(50), default="alarm", nullable=False)  # alarm, manual, schedule
    alarm_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("alarms.id", ondelete="SET NULL"), index=True)
    thumbnail_url: Mapped[str | None] = mapped_column(String(500))
    is_available: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    synced_at: Mapped[datetime | None] = mapped_column(DateTime)
    # MinIO storage fields
    minio_file_path: Mapped[str | None] = mapped_column(String(500))
    minio_thumbnail_path: Mapped[str | None] = mapped_column(String(500))
    minio_synced_at: Mapped[datetime | None] = mapped_column(DateTime)

    # Relationships
    alarm: Mapped["Alarm | None"] = relationship("Alarm", lazy="selectin")


# ============ BM-APP Analytics Data Models ============

class PeopleCount(Base):
    """People counting data from BM-APP (table_people_count)"""
    __tablename__ = "people_counts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    bmapp_id: Mapped[str | None] = mapped_column(String(100), index=True)
    camera_name: Mapped[str | None] = mapped_column(String(200), index=True)
    task_session: Mapped[str | None] = mapped_column(String(100), index=True)
    count_in: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    count_out: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    record_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    extra_data: Mapped[dict | None] = mapped_column(JSONB)
    synced_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class ZoneOccupancy(Base):
    """Zone occupancy data from BM-APP (table_remained)"""
    __tablename__ = "zone_occupancies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    bmapp_id: Mapped[str | None] = mapped_column(String(100), index=True)
    camera_name: Mapped[str | None] = mapped_column(String(200), index=True)
    task_session: Mapped[str | None] = mapped_column(String(100), index=True)
    zone_name: Mapped[str | None] = mapped_column(String(200))
    people_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    record_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    extra_data: Mapped[dict | None] = mapped_column(JSONB)
    synced_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class ZoneOccupancyAvg(Base):
    """Average zone occupancy from BM-APP (table_remained_avg)"""
    __tablename__ = "zone_occupancy_avgs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    bmapp_id: Mapped[str | None] = mapped_column(String(100), index=True)
    camera_name: Mapped[str | None] = mapped_column(String(200), index=True)
    task_session: Mapped[str | None] = mapped_column(String(100), index=True)
    zone_name: Mapped[str | None] = mapped_column(String(200))
    avg_count: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    period_start: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    period_end: Mapped[datetime | None] = mapped_column(DateTime)
    extra_data: Mapped[dict | None] = mapped_column(JSONB)
    synced_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class StoreCount(Base):
    """Store entry/exit counting from BM-APP (table_store_count)"""
    __tablename__ = "store_counts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    bmapp_id: Mapped[str | None] = mapped_column(String(100), index=True)
    camera_name: Mapped[str | None] = mapped_column(String(200), index=True)
    task_session: Mapped[str | None] = mapped_column(String(100), index=True)
    entry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    exit_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    record_date: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    extra_data: Mapped[dict | None] = mapped_column(JSONB)
    synced_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class StayDuration(Base):
    """Stay duration data from BM-APP (table_store_stay_duration)"""
    __tablename__ = "stay_durations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    bmapp_id: Mapped[str | None] = mapped_column(String(100), index=True)
    camera_name: Mapped[str | None] = mapped_column(String(200), index=True)
    task_session: Mapped[str | None] = mapped_column(String(100), index=True)
    zone_name: Mapped[str | None] = mapped_column(String(200))
    avg_duration: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)  # seconds
    max_duration: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    min_duration: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    sample_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    record_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    extra_data: Mapped[dict | None] = mapped_column(JSONB)
    synced_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class Schedule(Base):
    """AI task schedule from BM-APP (table_schedule)"""
    __tablename__ = "schedules"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    bmapp_id: Mapped[str | None] = mapped_column(String(100), index=True)
    task_session: Mapped[str | None] = mapped_column(String(100), index=True)
    schedule_name: Mapped[str | None] = mapped_column(String(200))
    schedule_type: Mapped[str | None] = mapped_column(String(50))  # daily, weekly, etc.
    start_time: Mapped[str | None] = mapped_column(String(20))  # HH:MM format
    end_time: Mapped[str | None] = mapped_column(String(20))
    days_of_week: Mapped[str | None] = mapped_column(String(50))  # e.g. "1,2,3,4,5"
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    extra_data: Mapped[dict | None] = mapped_column(JSONB)
    synced_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class SensorDevice(Base):
    """Sensor device definition from BM-APP (table_sensor_device)"""
    __tablename__ = "sensor_devices"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    bmapp_id: Mapped[str | None] = mapped_column(String(100), unique=True, index=True)
    device_name: Mapped[str] = mapped_column(String(200), nullable=False)
    device_type: Mapped[str | None] = mapped_column(String(100))  # temperature, humidity, etc.
    location: Mapped[str | None] = mapped_column(String(300))
    is_online: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    extra_data: Mapped[dict | None] = mapped_column(JSONB)
    synced_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class SensorData(Base):
    """Sensor reading data from BM-APP (table_sensor_device_data)"""
    __tablename__ = "sensor_data"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    bmapp_id: Mapped[str | None] = mapped_column(String(100), index=True)
    sensor_device_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("sensor_devices.id", ondelete="CASCADE"), index=True)
    sensor_bmapp_id: Mapped[str | None] = mapped_column(String(100), index=True)  # BM-APP sensor device ID
    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str | None] = mapped_column(String(50))
    record_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    extra_data: Mapped[dict | None] = mapped_column(JSONB)
    synced_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    sensor_device: Mapped["SensorDevice | None"] = relationship("SensorDevice", lazy="selectin")


class SystemPreference(Base):
    """System preference/configuration key-value store per AI Box"""
    __tablename__ = "system_preferences"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    aibox_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("ai_boxes.id", ondelete="CASCADE"), index=True)
    key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    value: Mapped[str] = mapped_column(String(1024), nullable=False, default="")
    description: Mapped[str | None] = mapped_column(String(512))
    category: Mapped[str] = mapped_column(String(50), nullable=False, default="system")  # basic, network, alarm, encoding, database, system
    value_type: Mapped[str] = mapped_column(String(20), nullable=False, default="string")  # string, int, bool, float
    is_synced_bmapp: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    aibox: Mapped["AIBox | None"] = relationship("AIBox", lazy="selectin")


class AlgorithmThreshold(Base):
    """Algorithm confidence threshold per AI Box"""
    __tablename__ = "algorithm_thresholds"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    aibox_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("ai_boxes.id", ondelete="CASCADE"), index=True)
    algorithm_index: Mapped[int] = mapped_column(Integer, nullable=False)  # index in table_threshold (1-88)
    algorithm_name: Mapped[str] = mapped_column(String(200), nullable=False)  # desc from table_threshold
    threshold_value: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    is_synced_bmapp: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    aibox: Mapped["AIBox | None"] = relationship("AIBox", lazy="selectin")


class FaceAlbum(Base):
    """Face recognition album (group of face features) per AI Box"""
    __tablename__ = "face_albums"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    aibox_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("ai_boxes.id", ondelete="CASCADE"), index=True)
    bmapp_id: Mapped[int | None] = mapped_column(Integer)  # suit_id from table_suit
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    feature_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # denormalized count
    is_synced_bmapp: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    aibox: Mapped["AIBox | None"] = relationship("AIBox", lazy="selectin")
    features: Mapped[List["FaceFeatureRecord"]] = relationship("FaceFeatureRecord", back_populates="album", lazy="select")


class FaceFeatureRecord(Base):
    """Individual face feature record within an album"""
    __tablename__ = "face_feature_records"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    album_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("face_albums.id", ondelete="CASCADE"), nullable=False, index=True)
    aibox_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("ai_boxes.id", ondelete="SET NULL"), index=True)
    bmapp_id: Mapped[int | None] = mapped_column(Integer)  # feature_id from table_suit_feature
    jpeg_path: Mapped[str | None] = mapped_column(String(512))  # local path on bm-app
    minio_path: Mapped[str | None] = mapped_column(String(512))  # MinIO storage path
    name: Mapped[str | None] = mapped_column(String(256))  # person name/label
    extra_data: Mapped[dict | None] = mapped_column(JSONB)
    is_synced_bmapp: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    album: Mapped["FaceAlbum"] = relationship("FaceAlbum", back_populates="features", lazy="selectin")


class ModbusDevice(Base):
    """Modbus device configuration per AI Box"""
    __tablename__ = "modbus_devices"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    aibox_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("ai_boxes.id", ondelete="CASCADE"), index=True)
    bmapp_id: Mapped[int | None] = mapped_column(Integer)  # id from table_modbus
    description: Mapped[str] = mapped_column(String(256), nullable=False)
    alarm_url: Mapped[str | None] = mapped_column(String(512))
    port: Mapped[int] = mapped_column(Integer, default=502, nullable=False)
    poll_interval: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)  # seconds
    device_path: Mapped[str | None] = mapped_column(String(32))  # e.g. /dev/ttyUSB0
    slave_addr: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    start_reg_addr: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    end_reg_addr: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    start_data: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    end_data: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    device_type: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # 0=input, 1=output
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_synced_bmapp: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    aibox: Mapped["AIBox | None"] = relationship("AIBox", lazy="selectin")


class LocalVideo(Base):
    """Local video files uploaded manually for analysis"""
    __tablename__ = "local_videos"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000))
    original_filename: Mapped[str] = mapped_column(String(300), nullable=False)
    minio_path: Mapped[str] = mapped_column(String(500), nullable=False)  # e.g., "2024/01/28/video_xxx.mp4"
    thumbnail_path: Mapped[str | None] = mapped_column(String(500))
    file_size: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # bytes
    duration: Mapped[int | None] = mapped_column(Integer)  # seconds
    resolution: Mapped[str | None] = mapped_column(String(20))  # e.g., "1920x1080"
    format: Mapped[str | None] = mapped_column(String(20))  # e.g., "MP4"
    status: Mapped[str] = mapped_column(String(20), default="processing", nullable=False, index=True)  # processing, ready, error
    error_message: Mapped[str | None] = mapped_column(String(500))
    uploaded_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    uploaded_by: Mapped["User | None"] = relationship("User", lazy="selectin")


class AuditLog(Base):
    """Audit log for tracking all significant system actions"""
    __tablename__ = "audit_logs"

    # Primary Info
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # Actor (WHO)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True)
    username: Mapped[str] = mapped_column(String(50), nullable=False)  # Denormalized - for when user is deleted
    user_email: Mapped[str] = mapped_column(String(100), nullable=False)  # Denormalized

    # Action (WHAT)
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)  # "user.created", "alarm.deleted", etc
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # "user", "alarm", "video_source"
    resource_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))  # ID of affected resource
    resource_name: Mapped[str | None] = mapped_column(String(200))  # Denormalized name for display

    # Context (WHERE/HOW)
    ip_address: Mapped[str | None] = mapped_column(String(45))  # IPv6 max 45 chars
    user_agent: Mapped[str | None] = mapped_column(String(500))  # Browser/API client info
    endpoint: Mapped[str | None] = mapped_column(String(200))  # API endpoint called, e.g. "/video-sources/{id}"
    method: Mapped[str | None] = mapped_column(String(10))  # HTTP method: GET, POST, PUT, DELETE

    # Changes (BEFORE/AFTER)
    old_values: Mapped[dict | None] = mapped_column(JSONB)  # State before change
    new_values: Mapped[dict | None] = mapped_column(JSONB)  # State after change
    changes_summary: Mapped[str | None] = mapped_column(String(1000))  # Human-readable summary

    # Result
    status: Mapped[str] = mapped_column(String(20), default="success", nullable=False, index=True)  # "success" | "failed" | "partial"
    error_message: Mapped[str | None] = mapped_column(String(1000))  # If failed

    # Additional Context
    extra_metadata: Mapped[dict | None] = mapped_column(JSONB)  # Extra context (e.g., bulk operation count)

    # Relationships
    user: Mapped["User | None"] = relationship("User", lazy="selectin")
