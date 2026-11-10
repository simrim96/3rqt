"""Adapter minimale per API OpenAI-compatibili (lista modelli + chat).

Pensato per il health check (scripts/check_nodes.py, `harness doctor`) e per
riuso nei fasi successive. Solo HTTP sincrono: l'async arriva con lo scheduler
(Fase 4). Il transport httpx e' iniettabile per i test.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from nodes.config import Node

DEFAULT_TIMEOUT = 30.0


@dataclass
class NodeStatus:
    name: str
    endpoint: str
    reachable: bool = False
    runtime: str = "unknown"
    version: str | None = None
    server_header: str | None = None
    models: list[dict[str, Any]] = field(default_factory=list)
    configured_model_present: bool | None = None
    chat_ok: bool = False
    chat_reply: str | None = None
    latency_s: float | None = None
    error: str | None = None


def _base(endpoint: str) -> str:
    return endpoint.rstrip("/")


def _headers(node: Node) -> dict[str, str]:
    key = node.api_key or "none"
    return {"Authorization": f"Bearer {key}"}


def list_models(
    node: Node, client: httpx.Client | None = None
) -> tuple[list[dict], httpx.Response]:
    """GET <endpoint>/models. Ritorna (modelli, risposta HTTP)."""
    own = client is None
    if own:
        client = httpx.Client(timeout=DEFAULT_TIMEOUT)
    try:
        resp = client.get(f"{_base(node.endpoint)}/models", headers=_headers(node))
        resp.raise_for_status()
        data = resp.json().get("data", [])
        return data, resp
    finally:
        if own:
            client.close()


def chat_completion(
    node: Node,
    prompt: str,
    *,
    model: str | None = None,
    max_tokens: int = 64,
    temperature: float = 0.0,
    client: httpx.Client | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """POST <endpoint>/chat/completions minimale. Ritorna la JSON del provider."""
    own = client is None
    if own:
        client = httpx.Client(timeout=timeout)
    payload = {
        "model": model or node.model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    try:
        resp = client.post(
            f"{_base(node.endpoint)}/chat/completions",
            json=payload,
            headers=_headers(node),
            timeout=timeout,
        )
        resp.raise_for_status()
        return resp.json()
    finally:
        if own:
            client.close()


def _extract_reply(data: dict[str, Any]) -> str:
    """Content del messaggio; fallback su campi reasoning dei runtime thinking."""
    try:
        msg = data["choices"][0]["message"]
    except (KeyError, IndexError, TypeError):
        return ""
    for key in ("content", "reasoning_content", "reasoning"):
        val = msg.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def _detect_runtime(
    node: Node, client: httpx.Client, models: list[dict], resp: httpx.Response
) -> tuple[str, str | None]:
    """Euristiche di fingerprinting del runtime: /v1/health, owned_by, header Server."""
    version: str | None = None
    engine: str | None = None
    for health_path in (
        f"{_base(node.endpoint)}/health",
        "/".join(_base(node.endpoint).split("/")[:-1]) + "/health",
    ):
        try:
            h = client.get(health_path, timeout=5.0)
            if h.status_code == 200:
                try:
                    hj = h.json()
                except ValueError:
                    hj = {}
                if isinstance(hj, dict):
                    engine = hj.get("engine") or hj.get("service") or engine
                    version = hj.get("version") or version
                    if engine or version:
                        break
        except httpx.HTTPError:
            continue

    server = resp.headers.get("server")
    if server:
        server = server.strip()
        if version is None and "/" in server:
            name, _, ver = server.partition("/")
            version = ver.split(" ")[0]

    owned = {m.get("owned_by") for m in models if isinstance(m, dict) and m.get("owned_by")}
    if engine:
        runtime = engine
    elif len(owned) == 1:
        runtime = next(iter(owned))
    elif server:
        runtime = server.partition("/")[0]
    else:
        runtime = "openai-compatible"
    return runtime, version


def probe_node(node: Node, *, name: str = "?", timeout: float = DEFAULT_TIMEOUT) -> NodeStatus:
    """Health check completo: modelli + runtime + chat-completion minimale."""
    st = NodeStatus(name=name, endpoint=node.endpoint)
    t0 = time.monotonic()
    try:
        with httpx.Client(timeout=timeout) as client:
            models, resp = list_models(node, client=client)
            st.models = models
            st.reachable = True
            st.server_header = resp.headers.get("server")
            st.runtime, st.version = _detect_runtime(node, client, models, resp)
            st.configured_model_present = any(m.get("id") == node.model for m in models)
            try:
                data = chat_completion(
                    node, "Reply with exactly: OK", max_tokens=16, client=client, timeout=timeout
                )
                reply = _extract_reply(data)
                st.chat_ok = bool(reply)
                st.chat_reply = reply or "(vuoto)"
            except (httpx.HTTPError, ValueError) as exc:
                st.error = f"chat: {type(exc).__name__}: {exc}"
    except (httpx.HTTPError, ValueError) as exc:
        st.error = f"{type(exc).__name__}: {exc}"
    st.latency_s = round(time.monotonic() - t0, 2)
    return st
