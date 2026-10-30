from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://mangadock:mangadock@localhost:5432/mangadock"
    redis_url: str = "redis://localhost:6379/0"
    max_novel_chars: int = 120000

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
