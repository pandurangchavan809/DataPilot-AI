"""The gateway's fallback and streaming rules, with the OpenAI SDK client stubbed."""

from types import SimpleNamespace as NS

import pytest

from app.core.errors import LLMError
from app.llm.gateway import LLMGateway
from app.llm.registry import ModelRef

PRIMARY = ModelRef("nebius", "main")
SECONDARY = ModelRef("gemini", "backup")


def chunk(text):
    return NS(choices=[NS(delta=NS(content=text))])


class StubClient:
    def __init__(self, reply=None, chunks=(), fail_after=None):
        self.reply, self.chunks, self.fail_after = reply, chunks, fail_after
        self.chat = NS(completions=NS(create=self.create))
        self.temperature = None

    def create(self, *, temperature, stream, **_):
        self.temperature = temperature
        if stream:
            return self._stream()
        if self.reply is None:
            raise RuntimeError("provider down")
        return NS(choices=[NS(message=NS(content=self.reply))])

    def _stream(self):
        for i, text in enumerate(self.chunks):
            if self.fail_after == i:
                raise RuntimeError("connection lost")
            yield chunk(text)
        if self.fail_after == len(self.chunks):
            raise RuntimeError("provider down")


class StubRegistry:
    def __init__(self, primary, secondary):
        self.clients = {PRIMARY.provider: primary, SECONDARY.provider: secondary}

    def roles(self):
        return {"primary": PRIMARY, "secondary": SECONDARY}

    def is_enabled(self, _ref):
        return True

    def client(self, provider):
        return self.clients[provider]


def gateway(primary, secondary):
    return LLMGateway(NS(llm_temperature=0.1, llm_max_tokens=100), StubRegistry(primary, secondary))


def test_complete_falls_back_and_strips_reasoning():
    result = gateway(StubClient(), StubClient(reply="<think>plan</think> Hello")).complete([])
    assert result.text == "Hello"
    assert result.model == SECONDARY


def test_complete_uses_the_default_temperature_unless_given():
    client = StubClient(reply="ok")
    gw = gateway(client, StubClient())
    gw.complete([])
    assert client.temperature == 0.1
    gw.complete([], temperature=0)
    assert client.temperature == 0


def test_complete_raises_when_every_provider_fails():
    with pytest.raises(LLMError):
        gateway(StubClient(), StubClient()).complete([])


def test_stream_filters_think_across_chunks_and_reports_the_model():
    seen = []
    chunks = ["<th", "ink>x</thi", "nk>Hi", " there"]
    out = "".join(gateway(StubClient(chunks=chunks), StubClient()).stream([], on_model=seen.append))
    assert out == "Hi there"
    assert seen == [PRIMARY]


def test_stream_falls_back_before_the_first_output():
    seen = []
    gw = gateway(StubClient(fail_after=0), StubClient(chunks=["from backup"]))
    assert "".join(gw.stream([], on_model=seen.append)) == "from backup"
    assert seen == [SECONDARY]


def test_stream_does_not_restart_on_another_model_after_output():
    gw = gateway(StubClient(chunks=["partial"], fail_after=1), StubClient(chunks=["backup"]))
    stream = gw.stream([])
    assert next(stream) == "partial"
    with pytest.raises(LLMError, match="Stream interrupted"):
        next(stream)
