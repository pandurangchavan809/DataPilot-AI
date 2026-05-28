import os
from pydantic import BaseSettings


class Settings(BaseSettings):
    demo_sqlite_path: str = "./data/top50_countries.db"
    gemini_model_name: str = "gemini-2.5-flash"
    gemini_api_key: str | None = None

    class Config:
        env_file = ".env"


settings = Settings()

if settings.gemini_api_key:
    os.environ["GOOGLE_API_KEY"] = settings.gemini_api_key
