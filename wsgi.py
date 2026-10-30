"""WSGI entry point.

Production: gunicorn -c gunicorn.conf.py wsgi:app
Local dev:  python wsgi.py
"""

import os

from app import create_app
from app.config import get_settings

app = create_app()

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", "5000")),
        debug=not get_settings().is_production,
        threaded=True,
    )
