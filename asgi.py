"""ASGI entry point.

Production: uvicorn asgi:app --host 0.0.0.0 --port $PORT
Local dev:  python asgi.py
"""

import os

import uvicorn

from app import create_app
from app.config import get_settings

app = create_app()

if __name__ == "__main__":
    uvicorn.run(
        "asgi:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "5000")),
        reload=not get_settings().is_production,
        reload_dirs=["app"],
    )
