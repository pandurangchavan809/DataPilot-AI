import pytest

from app.agents.sql_agent import parse_sql_response
from app.core.errors import LLMError
from app.llm.gateway import ThinkFilter, clean_text, parse_json_object
from app.llm.registry import ModelRef


def test_think_filter_strips_leading_reasoning_across_chunks():
    f = ThinkFilter()
    chunks = ["<th", "ink>plan ", "the query</thi", "nk>\n\nHello", " world"]
    assert "".join(f.feed(c) for c in chunks) + f.flush() == "Hello world"


def test_think_filter_passes_plain_text():
    f = ThinkFilter()
    assert "".join(f.feed(c) for c in ["Hi", " there"]) + f.flush() == "Hi there"


def test_clean_text_and_json():
    assert clean_text("<think>x</think> ok") == "ok"
    assert parse_json_object('```json\n{"intent": "data"}\n```') == {"intent": "data"}
    with pytest.raises(LLMError):
        parse_json_object("no json here")


def test_parse_sql_response_fenced():
    draft = parse_sql_response("```sql\nSELECT 1;\n```\nExplanation: returns one")
    assert draft.sql == "SELECT 1"
    assert draft.explanation == "returns one"


def test_parse_sql_response_cannot_answer():
    draft = parse_sql_response("CANNOT_ANSWER: no sales table")
    assert draft.sql is None and draft.cannot_answer == "no sales table"


def test_model_ref_parsing_keeps_slashes():
    ref = ModelRef.parse("nebius:nvidia/Llama-3_3-Nemotron-Super-49B-v1_5")
    assert ref.provider == "nebius" and ref.name == "nvidia/Llama-3_3-Nemotron-Super-49B-v1_5"
    assert ref.label == "Llama-3_3-Nemotron-Super-49B-v1_5"
