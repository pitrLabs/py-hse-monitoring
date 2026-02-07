from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional


class Settings(BaseSettings):
    # Database
    database_url: str = Field(alias="DATABASE_URL")

    # Security
    secret_key: str = Field(alias="SECRET_KEY")
    algorithm: str = Field(default="HS256", alias="ALGORITHM")
    access_token_expire_minutes: int = Field(default=30, alias="ACCESS_TOKEN_EXPIRE_MINUTES")

    # Application
    app_name: str = Field(default="HSE Monitoring", alias="APP_NAME")
    app_version: str = Field(default="1.0.0", alias="APP_VERSION")
    debug: bool = Field(default=False, alias="DEBUG")

    # Server
    webrtc: str = Field(default="", alias="WEBRTC")
    mediamtx_api_url: str = Field(default="http://mediamtx:9997", alias="MEDIAMTX_API_URL")

    # BM-APP Integration
    bmapp_enabled: bool = Field(default=False, alias="BMAPP_ENABLED")
    bmapp_api_url: str = Field(default="http://103.75.84.183:2323/api", alias="BMAPP_API_URL")
    bmapp_alarm_ws_url: str = Field(default="ws://103.75.84.183:2323/alarm/", alias="BMAPP_ALARM_WS_URL")
    bmapp_webrtc_url: str = Field(default="http://103.75.84.183:2323/webrtc", alias="BMAPP_WEBRTC_URL")

    # Camera status polling
    camera_status_poll_interval: int = Field(default=10, alias="CAMERA_STATUS_POLL_INTERVAL")

    # External RTU API for camera locations
    rtu_api_key: str = Field(default="plnup2djateng@!145", alias="RTU_API_KEY")
    rtu_keypoint_url: str = Field(default="https://rtu.up2djty.com/api/keypoint_up2djty", alias="RTU_KEYPOINT_URL")
    rtu_gps_tim_har_url: str = Field(default="https://rtu.up2djty.com/api/gps_tim_har", alias="RTU_GPS_TIM_HAR_URL")

    # MinIO Object Storage
    minio_enabled: bool = Field(default=False, alias="MINIO_ENABLED")
    minio_endpoint: str = Field(default="localhost:9000", alias="MINIO_ENDPOINT")
    minio_access_key: str = Field(default="minioadmin", alias="MINIO_ACCESS_KEY")
    minio_secret_key: str = Field(default="minioadmin123", alias="MINIO_SECRET_KEY")
    minio_secure: bool = Field(default=False, alias="MINIO_SECURE")
    minio_bucket_alarm_images: str = Field(default="alarm-images", alias="MINIO_BUCKET_ALARM_IMAGES")
    minio_bucket_recordings: str = Field(default="recordings", alias="MINIO_BUCKET_RECORDINGS")
    minio_bucket_local_videos: str = Field(default="local-videos", alias="MINIO_BUCKET_LOCAL_VIDEOS")
    minio_presigned_url_expiry: int = Field(default=3600, alias="MINIO_PRESIGNED_URL_EXPIRY")

    # Telegram Notifications
    telegram_enabled: bool = Field(default=False, alias="TELEGRAM_ENABLED")
    telegram_bot_token: str = Field(default="", alias="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: str = Field(default="", alias="TELEGRAM_CHAT_ID")

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        "populate_by_name": True,
        "extra": "ignore",
    }


settings = Settings()
