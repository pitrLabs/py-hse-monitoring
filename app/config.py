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
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


settings = Settings()
