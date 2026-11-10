"""Test del client OpenAI-compatibile con transport finto (niente rete)."""

from __future__ import annotations

import json

import httpx
import pytest

from nodes import client as client_mod
from nodes.client import _extract_reply, chat_completion, probe_node
from nodes.config import Node

MODELS_PAYLOAD = {
    "object": "list",
    "data": [{"id": "m-test", "object": "model", "owned_by": "tabbyAPI", "meta": {"n_ctx": 65536}}],
}


def _node(**kw) -> Node:
    base = {"endpoint": "http://fake.test/v1", "model": "m-test", "family": "test"}
    base.update(kw)
    return Node.model_validate(base)


def _patch_client(monkeypatch, handler) -> None:
    """probe_node costruisce un httpx.Client interno: iniettiamo il mock."""

    class Patched(httpx.Client):
        def __init__(self, *a, **kw):
            kw.setdefault("transport", httpx.MockTransport(handler))
            super().__init__(*a, **kw)

    monkeypatch.setattr(client_mod.httpx, "Client", Patched)


def test_chat_completion_url_e_payload():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": "OK"}}]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    out = chat_completion(_node(), "ciao", client=client)
    assert out["choices"][0]["message"]["content"] == "OK"
    assert seen["url"] == "http://fake.test/v1/chat/completions"
    assert seen["auth"] == "Bearer none"
    assert seen["body"]["model"] == "m-test"
    assert seen["body"]["messages"] == [{"role": "user", "content": "ciao"}]


def test_probe_node_ok_runtime_da_health(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/models":
            return httpx.Response(200, json=MODELS_PAYLOAD, headers={"server": "uvicorn"})
        if request.url.path == "/v1/health":
            return httpx.Response(
                200, json={"status": "ok", "engine": "exllamav3", "version": "0.5"}
            )
        if request.url.path == "/v1/chat/completions":
            return httpx.Response(200, json={"choices": [{"message": {"content": " OK "}}]})
        return httpx.Response(404)

    _patch_client(monkeypatch, handler)
    st = probe_node(_node(), name="mid", timeout=5)
    assert st.reachable
    assert st.chat_ok
    assert st.chat_reply == "OK"
    assert st.runtime == "exllamav3"  # health.engine vince su owned_by
    assert st.version == "0.5"
    assert st.configured_model_present is True
    assert st.models[0]["meta"]["n_ctx"] == 65536


def test_probe_node_runtime_da_owned_by_senza_health(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/models":
            return httpx.Response(200, json=MODELS_PAYLOAD, headers={"server": "TornadoServer/6.4"})
        if request.url.path == "/v1/chat/completions":
            return httpx.Response(200, json={"choices": [{"message": {"content": "OK"}}]})
        return httpx.Response(404)

    _patch_client(monkeypatch, handler)
    st = probe_node(_node(), name="mid", timeout=5)
    assert st.runtime == "tabbyAPI"
    assert st.version == "6.4"  # dal header Server


def test_probe_node_runtime_da_service_key(monkeypatch):
    """Runtime che si dichiarano via health.service (con /v1/health assente)."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/models":
            return httpx.Response(200, json=MODELS_PAYLOAD)
        if request.url.path == "/v1/health":
            return httpx.Response(404, json={"error": "not found"})
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok", "service": "x-runtime"})
        if request.url.path == "/v1/chat/completions":
            return httpx.Response(200, json={"choices": [{"message": {"content": "OK"}}]})
        return httpx.Response(404)

    _patch_client(monkeypatch, handler)
    st = probe_node(_node(), name="h", timeout=5)
    assert st.runtime == "x-runtime"


def test_probe_node_chat_fallita(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/models":
            return httpx.Response(200, json=MODELS_PAYLOAD)
        if "chat" in request.url.path:
            return httpx.Response(500, text="boom")
        return httpx.Response(404)

    _patch_client(monkeypatch, handler)
    st = probe_node(_node(), name="mid", timeout=5)
    assert st.reachable  # /models risponde
    assert not st.chat_ok
    assert "chat" in (st.error or "")


def test_probe_node_endpoint_giu(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    _patch_client(monkeypatch, handler)
    st = probe_node(_node(), name="mid", timeout=5)
    assert not st.reachable
    assert not st.chat_ok
    assert "ConnectError" in (st.error or "")


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"choices": [{"message": {"content": "ciao"}}]}, "ciao"),
        ({"choices": [{"message": {"content": "", "reasoning_content": "R"}}]}, "R"),
        ({"choices": [{"message": {}}]}, ""),
        ({}, ""),
    ],
)
def test_extract_reply(payload, expected):
    assert _extract_reply(payload) == expected
