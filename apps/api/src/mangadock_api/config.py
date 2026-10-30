from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://mangadock:mangadock@localhost:5432/mangadock"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
