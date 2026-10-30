"""Request payload models."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from ..db.connectors import ConnectionConfig


class HistoryTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(default="", max_length=20000)
    sql: str | None = Field(default=None, max_length=20000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    history: list[HistoryTurn] = Field(default_factory=list, max_length=50)
    model: str | None = None


class ConnectRequest(ConnectionConfig):
    pass
