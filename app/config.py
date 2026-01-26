from pydantic_settings import BaseSettings
from decouple import config


class Settings(BaseSettings):
    database_url: str = config("DATABASE_URL")
    secret_key: str = config("SECRET_KEY")
    algorithm: str = config("ALGORITHM")
    access_token_expire_minutes: int = config("ACCESS_TOKEN_EXPIRE_MINUTES", cast=int)
    app_name: str = config("APP_NAME")
    app_version: str = config("APP_VERSION")
    debug: bool = config("DEBUG", cast=bool)
    webrtc: str = config("WEBRTC", default="")
    mediamtx_api_url: str = config("MEDIAMTX_API_URL", default="http://mediamtx:9997")

    # BM-APP Integration
    bmapp_enabled: bool = config("BMAPP_ENABLED", default=False, cast=bool)
    bmapp_api_url: str = config("BMAPP_API_URL", default="http://103.75.84.183:2323/api")
    bmapp_alarm_ws_url: str = config("BMAPP_ALARM_WS_URL", default="ws://103.75.84.183:2323/alarm/")
    bmapp_webrtc_url: str = config("BMAPP_WEBRTC_URL", default="http://103.75.84.183:2323/webrtc")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


settings = Settings()
