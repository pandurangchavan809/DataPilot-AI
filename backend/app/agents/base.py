"""Shared agent context types."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..config import Settings
from ..db.manager import ActiveConnection
from ..llm.gateway import LLMGateway
from ..llm.registry import ModelRef


@dataclass
class Turn:
    role: str  # "user" | "assistant"
    content: str
    sql: str | None = None


@dataclass
class AgentContext:
    question: str
    history: list[Turn]
    connection: ActiveConnection
    llm: LLMGateway
    settings: Settings
    model_override: ModelRef | None = None
    models_used: set[str] = field(default_factory=set)

    def history_messages(self, max_chars: int = 1500) -> list[dict[str, str]]:
        messages = []
        for turn in self.history[-self.settings.chat_history_turns * 2 :]:
            content = turn.content[:max_chars]
            if turn.role == "assistant" and turn.sql:
                content = f"{content}\n\n[SQL used]\n{turn.sql}"
            messages.append({"role": "assistant" if turn.role == "assistant" else "user", "content": content})
        return messages
