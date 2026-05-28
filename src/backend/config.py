import os

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    demo_sqlite_path: str = "src/data/top50_countries.db"

    gemini_api_key: str

    gemini_model_name: str = "gemini-2.5-flash"

    api_host: str = "0.0.0.0"

    api_port: int = 8000

    frontend_url: str = "http://localhost:8501"

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()