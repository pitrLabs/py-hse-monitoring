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

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


settings = Settings()
