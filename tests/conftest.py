import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-pytest-only-0123456789")

import uuid

import pytest

from app import create_app
from app.config import Settings


@pytest.fixture()
def settings(tmp_path):
    return Settings(
        secret_key="test-secret-key-for-pytest-only-0123456789",
        demo_db_path=tmp_path / "demo.db",
        auth_db_path=tmp_path / "auth.db",
        auth_rate_limit="1000/minute",
    )


@pytest.fixture()
def client(settings):
    return create_app(settings).test_client()


@pytest.fixture()
def auth_header(client):
    """Logs in as the seeded demo user."""
    resp = client.post("/api/auth/login", json={"email": "user", "password": "User@1234"})
    return {"Authorization": f"Bearer {resp.json['access_token']}"}


@pytest.fixture()
def headers(auth_header):
    return {**auth_header, "X-Session-Id": str(uuid.uuid4())}
