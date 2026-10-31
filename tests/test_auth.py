import sqlite3
import time

import jwt

DEMO = {"email": "user", "password": "User@1234"}


def bearer(tokens):
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def test_demo_user_is_seeded_and_can_log_in(client):
    resp = client.post("/api/auth/login", json=DEMO)
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "Bearer"
    assert body["user"]["email"] == "user"
    assert "password_hash" not in body["user"]


def test_signup_then_me(client):
    resp = client.post("/api/auth/signup", json={"email": "Pandurang809@Gmail.com", "password": "Secret123"})
    assert resp.status_code == 201
    me = client.get("/api/auth/me", headers=bearer(resp.json()))
    assert me.json()["user"]["email"] == "pandurang809@gmail.com"  # emails are lower-cased


def test_signup_rejects_duplicates_and_weak_passwords(client):
    client.post("/api/auth/signup", json={"email": "a@b.co", "password": "Secret123"})
    assert client.post("/api/auth/signup", json={"email": "a@b.co", "password": "Secret123"}).status_code == 409
    assert client.post("/api/auth/signup", json={"email": "c@d.co", "password": "short1"}).status_code == 400
    assert client.post("/api/auth/signup", json={"email": "c@d.co", "password": "nodigitshere"}).status_code == 400
    assert client.post("/api/auth/signup", json={"email": "not-an-email", "password": "Secret123"}).status_code == 400


def test_wrong_password_is_rejected_and_logged(client, settings):
    resp = client.post("/api/auth/login", json={"email": "user", "password": "wrong"})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "invalid_credentials"
    client.post("/api/auth/login", json=DEMO)
    with sqlite3.connect(settings.auth_db_path) as db:
        events = db.execute("SELECT success FROM login_events ORDER BY id").fetchall()
        count = db.execute("SELECT login_count FROM users WHERE email = 'user'").fetchone()[0]
    assert events == [(0,), (1,)]
    assert count == 1


def test_protected_routes_need_a_token(client):
    assert client.get("/api/health").status_code == 200  # public
    assert client.get("/api/config").status_code == 401
    assert client.get("/api/config", headers={"Authorization": "Bearer garbage"}).status_code == 401
    tokens = client.post("/api/auth/login", json=DEMO).json()
    assert client.get("/api/config", headers=bearer(tokens)).status_code == 200


def test_refresh_token_cannot_be_used_as_access_token(client):
    tokens = client.post("/api/auth/login", json=DEMO).json()
    resp = client.get("/api/config", headers={"Authorization": f"Bearer {tokens['refresh_token']}"})
    assert resp.status_code == 401


def test_expired_access_token(client, settings):
    token = jwt.encode(
        {"sub": "1", "email": "user", "type": "access", "jti": "x", "exp": int(time.time()) - 5},
        settings.jwt_secret,
        algorithm="HS256",
    )
    resp = client.get("/api/config", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "token_expired"


def test_refresh_rotates_and_detects_reuse(client):
    first = client.post("/api/auth/login", json=DEMO).json()
    second = client.post("/api/auth/refresh", json={"refresh_token": first["refresh_token"]})
    assert second.status_code == 200
    assert client.get("/api/config", headers=bearer(second.json())).status_code == 200

    # Re-using the old (rotated) token is treated as theft: every session is revoked.
    assert client.post("/api/auth/refresh", json={"refresh_token": first["refresh_token"]}).status_code == 401
    assert client.post("/api/auth/refresh", json={"refresh_token": second.json()["refresh_token"]}).status_code == 401


def test_logout_revokes_refresh_token(client):
    tokens = client.post("/api/auth/login", json=DEMO).json()
    assert client.post("/api/auth/logout", json={"refresh_token": tokens["refresh_token"]}).status_code == 204
    assert client.post("/api/auth/refresh", json={"refresh_token": tokens["refresh_token"]}).status_code == 401


def test_db_sessions_are_scoped_per_user(client):
    sid = {"X-Session-Id": "shared-session-id-123456"}
    demo = bearer(client.post("/api/auth/login", json=DEMO).json())
    other = bearer(client.post("/api/auth/signup", json={"email": "x@y.co", "password": "Secret123"}).json())
    assert client.post("/api/connections", json={"type": "sqlite_demo"}, headers={**demo, **sid}).status_code == 201
    # Same session id, different user: must not see the demo user's connection.
    assert client.get("/api/connections/current", headers={**other, **sid}).json()["connection"] is None
