import pytest

from app.core.errors import QueryExecutionError
from app.db.connectors import ConnectionConfig, create_readonly_engine
from app.db.executor import execute_readonly


def test_health(client):
    assert client.get("/api/health").json()["status"] == "ok"


def test_demo_connection_lifecycle(client, headers):
    assert client.get("/api/connections/current", headers=headers).json()["connection"] is None

    resp = client.post("/api/connections", json={"type": "sqlite_demo"}, headers=headers)
    assert resp.status_code == 201
    tables = {t["name"] for t in resp.json()["schema"]["tables"]}
    assert {"countries", "economy_stats"} <= tables

    assert client.get("/api/connections/current", headers=headers).json()["connection"]["type"] == "sqlite_demo"
    assert client.delete("/api/connections/current", headers=headers).status_code == 204
    assert client.get("/api/connections/current", headers=headers).json()["connection"] is None


def test_chat_requires_connection(client, headers):
    resp = client.post("/api/chat", json={"message": "hi"}, headers=headers)
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "not_connected"


def test_session_header_required(client, auth_header):
    assert client.post("/api/connections", json={"type": "sqlite_demo"}, headers=auth_header).status_code == 400


def test_database_layer_rejects_writes_even_without_guard(client, settings):
    engine = create_readonly_engine(ConnectionConfig(type="sqlite_demo"), settings)
    result = execute_readonly(engine, "SELECT COUNT(*) AS n FROM countries", row_limit=10, timeout_seconds=5)
    assert result.rows == [[50]]
    with pytest.raises(QueryExecutionError):
        execute_readonly(engine, "DELETE FROM countries RETURNING country_id", row_limit=10, timeout_seconds=5)
    assert execute_readonly(engine, "SELECT COUNT(*) FROM countries", row_limit=10, timeout_seconds=5).rows == [[50]]
