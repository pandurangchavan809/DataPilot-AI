"""The agent graph's routing and retry paths, with the LLM agents faked."""

import time
from types import SimpleNamespace as NS

import pytest

from app.agents import orchestrator as orch
from app.core.errors import QueryExecutionError, UnsafeQueryError

RESULT = NS(row_count=1, elapsed_ms=1, truncated=False, to_dict=lambda: {"rows": [[1]]})


class FakeSqlAgent:
    drafts: list = []

    def __init__(self, *_):
        self.queue = list(self.drafts)

    def draft(self):
        return self.queue.pop(0)

    def repair(self, _error):
        return self.queue.pop(0)


def draft(sql="SELECT 1", cannot_answer=None):
    return NS(sql=sql, explanation="", cannot_answer=cannot_answer)


@pytest.fixture()
def ctx(monkeypatch):
    monkeypatch.setattr(orch, "select_tables", lambda *_: ([], "all"))
    monkeypatch.setattr(orch, "render_tables", lambda _: "")
    monkeypatch.setattr(orch, "SqlAgent", FakeSqlAgent)
    monkeypatch.setattr(orch, "validate_readonly_sql", lambda sql, *_: sql)
    monkeypatch.setattr(orch, "execute_readonly", lambda *_, **__: RESULT)
    monkeypatch.setattr(orch, "stream_insight", lambda *_: iter(["An ", "insight"]))
    monkeypatch.setattr(orch, "build_chart_spec", lambda *_: {"type": "bar"})
    return NS(
        settings=NS(max_sql_retries=2, query_row_limit=10, query_timeout_seconds=1),
        connection=NS(config=NS(dialect="sqlite"), engine=None),
        models_used=set(),
    )


def decide(monkeypatch, intent="data", chart=False):
    decision = NS(intent=intent, question="q", needs_chart=chart, chart_type=None)
    monkeypatch.setattr(orch, "route", lambda _: decision)


def names(events):
    return [e for e, _ in events]


def tokens(events):
    return "".join(d["text"] for e, d in events if e == "token")


def test_data_question_with_chart(ctx, monkeypatch):
    decide(monkeypatch, chart=True)
    FakeSqlAgent.drafts = [draft()]
    events = list(orch.run(ctx))
    assert [e for e in names(events) if e != "step"] == ["sql", "result", "chart", "token", "token", "done"]
    assert tokens(events) == "An insight"


def test_write_request_is_refused_without_touching_sql(ctx, monkeypatch):
    decide(monkeypatch, intent="write")
    FakeSqlAgent.drafts = []
    events = list(orch.run(ctx))
    assert tokens(events) == orch.WRITE_REFUSAL
    assert "sql" not in names(events)


def test_failed_query_is_repaired_then_succeeds(ctx, monkeypatch):
    decide(monkeypatch)
    FakeSqlAgent.drafts = [draft("bad"), draft("good")]

    def execute(_engine, sql, **_):
        if sql == "bad":
            raise QueryExecutionError("no such column")
        return RESULT

    monkeypatch.setattr(orch, "execute_readonly", execute)
    events = list(orch.run(ctx))
    assert [d["attempt"] for e, d in events if e == "sql"] == [1, 2]
    assert "result" in names(events) and "error" not in names(events)


def test_gives_up_after_all_retries(ctx, monkeypatch):
    decide(monkeypatch)
    FakeSqlAgent.drafts = [draft("x"), draft("x"), draft("x")]

    def reject(*_):
        raise UnsafeQueryError("not read-only")

    monkeypatch.setattr(orch, "validate_readonly_sql", reject)
    events = list(orch.run(ctx))
    assert names(events)[-2:] == ["error", "done"]
    assert "3 attempts" in events[-2][1]["message"]
    assert "result" not in names(events)


def test_unanswerable_question_stops_the_graph(ctx, monkeypatch):
    decide(monkeypatch)
    FakeSqlAgent.drafts = [draft(sql=None, cannot_answer="no such data")]
    events = list(orch.run(ctx))
    assert "no such data" in tokens(events)
    assert "sql" not in names(events)


def test_tokens_stream_live_instead_of_arriving_when_the_node_ends(ctx, monkeypatch):
    decide(monkeypatch)
    FakeSqlAgent.drafts = [draft()]

    def slow_insight(*_):
        for text in ("a", "b", "c"):
            time.sleep(0.3)
            yield text

    monkeypatch.setattr(orch, "stream_insight", slow_insight)
    arrivals = [time.perf_counter() for event, _ in orch.run(ctx) if event == "token"]
    assert len(arrivals) == 3
    assert arrivals[1] - arrivals[0] > 0.2 and arrivals[2] - arrivals[1] > 0.2
