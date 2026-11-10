"""Adapter async unico per API OpenAI-compatibili (PLAN §3 Fase 1).

Copre: chat, streaming SSE, annullamento, timeout, retry con backoff
esponenziale, conteggio token (usage del server; fallback stima locale).

Regola chiave (PLAN §0.2): il comportamento non dipende mai dal nome del
modello. Le opzioni opzionali non supportate dal runtime vengono rimosse con
degradazione graziosa quando il server risponde 400 citandole, e la
degradazione e' registrata nel risultato; le capacita rilevate dal doctor
(`Capabilities`) permettono di evitare a priori i campi non supportati.
L'annullamento (asyncio.CancelledError) chiude la risposta HTTP in corso.
"""

from __future__ import annotations

import asyncio
import json
import math
import random
import time
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import httpx
from pydantic import BaseModel, Field

from nodes.config import Node

Message = Mapping[str, Any]


class AdapterError(RuntimeError):
    """Errore generico dell'adapter (dopo eventuale esaurimento retry)."""


class CapabilityError(AdapterError):
    """Campo richiesto ma non supportato (capacita nota o 400 del server)."""


class NodeHTTPError(AdapterError):
    def __init__(self, status: int, body: str, *, blamed_field: str | None = None):
        self.status = status
        self.body = body[:2000]
        self.blamed_field = blamed_field
        super().__init__(f"HTTP {status}: {self.body[:300]}")


class Capabilities(BaseModel):
    """Capacita rilevate dal doctor (mai dedotte dal nome modello)."""

    tools: bool | None = None
    json_object: bool | None = None
    json_schema: bool | None = None
    streamed_usage: bool | None = None
    chat_template_applied: bool | None = None
    chat_template_source: str | None = None
    effective_ctx: int | None = None
    notes: dict[str, str] = Field(default_factory=dict)
    probed_at: str | None = None
    config_hash: str | None = None


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    reasoning_tokens: int = 0
    estimated: bool = False

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@dataclass
class ChatResult:
    text: str
    reasoning: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    finish_reason: str | None = None
    usage: Usage = field(default_factory=Usage)
    ttft_s: float | None = None
    total_s: float = 0.0
    model: str | None = None
    degraded: tuple[str, ...] = ()
    attempts: int = 0


@dataclass
class AdapterStats:
    requests: int = 0
    retries: int = 0
    degraded: int = 0
    failures: int = 0


RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})

# Campi opzionali che l'adapter puo' degradare se il runtime li rifiuta con 400.
# Ordine di ricerca nel messaggio d'errore: dal piu' lungo (evita che "tools"
# acchiappi l'occorrenza dentro "tool_choice").
_DEGRADABLE_FIELDS = (
    "response_format",
    "stream_options",
    "frequency_penalty",
    "tool_choice",
    "temperature",
    "top_p",
    "stop",
    "seed",
    "tools",
    "stream",
)


def estimate_tokens(text: str) -> int:
    """Stima grezza 1 token ~ 4 caratteri: usata solo se il server non da' usage."""
    return max(1, math.ceil(len(text) / 4))


def messages_text(messages: Sequence[Message]) -> str:
    parts = []
    for m in messages:
        content = m.get("content")
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):  # formato multimodale
            parts.extend(str(p.get("text", "")) for p in content if isinstance(p, dict))
    return "\n".join(parts)


def _blamed_field(body: str) -> str | None:
    lowered = body.lower()
    for key in _DEGRADABLE_FIELDS:
        if key in lowered:
            return key
    return None


class NodeAdapter:
    """Client async per un singolo nodo. Un adapter per nodo; riutilizzabile."""

    def __init__(
        self,
        node: Node,
        *,
        capabilities: Capabilities | None = None,
        max_retries: int = 2,
        backoff_base: float = 0.5,
        backoff_cap: float = 8.0,
        connect_timeout: float = 5.0,
        read_timeout: float = 120.0,
        client: httpx.AsyncClient | None = None,
        degrade: bool = True,
    ):
        self.node = node
        self.capabilities = capabilities
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.backoff_cap = backoff_cap
        self.degrade = degrade
        self.stats = AdapterStats()
        self._timeout = httpx.Timeout(read_timeout, connect=connect_timeout)
        headers = {"Authorization": f"Bearer {node.api_key or 'none'}"}
        if client is not None:
            self._client = client
            self._owns_client = False
        else:
            self._client = httpx.AsyncClient(timeout=self._timeout, headers=headers)
            self._owns_client = True

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> NodeAdapter:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    # ---------------------------------------------------------------- payload

    def _build_payload(
        self,
        messages: Sequence[Message],
        *,
        model: str | None,
        max_tokens: int | None,
        temperature: float | None,
        top_p: float | None,
        stop: list[str] | None,
        tools: list[dict] | None,
        tool_choice: Any,
        response_format: dict | None,
        stream: bool,
        include_stream_usage: bool,
        extra_body: Mapping[str, Any] | None,
        dropped: set[str],
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"model": model or self.node.model, "messages": list(messages)}
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if temperature is not None and "temperature" not in dropped:
            payload["temperature"] = temperature
        if top_p is not None and "top_p" not in dropped:
            payload["top_p"] = top_p
        if stop and "stop" not in dropped:
            payload["stop"] = stop
        if tools and "tools" not in dropped:
            payload["tools"] = tools
            if tool_choice is not None and "tool_choice" not in dropped:
                payload["tool_choice"] = tool_choice
        if response_format and "response_format" not in dropped:
            payload["response_format"] = response_format
        if stream:
            payload["stream"] = True
            if include_stream_usage and "stream_options" not in dropped:
                payload["stream_options"] = {"include_usage": True}
        if extra_body:
            payload.update({k: v for k, v in extra_body.items() if k not in dropped})
        return payload

    def _gate_capabilities(
        self,
        *,
        tools: list[dict] | None,
        response_format: dict | None,
        dropped: set[str],
        strict: bool,
    ) -> list[str]:
        """Salta a priori i campi che il probe capacita sa non supportati."""
        degraded: list[str] = []
        caps = self.capabilities
        if caps is None:
            return degraded
        checks = (
            (tools, caps.tools, "tools"),
            (
                response_format
                if isinstance(response_format, dict)
                and response_format.get("type") in ("json_schema", "json_object")
                else None,
                caps.json_schema
                if isinstance(response_format, dict)
                and response_format.get("type") == "json_schema"
                else caps.json_object,
                f"response_format:{response_format.get('type')}"
                if isinstance(response_format, dict)
                else "response_format",
            ),
        )
        for value, supported, label in checks:
            if value and supported is False:
                if strict:
                    raise CapabilityError(
                        f"nodo {self.node.model!r}: capacita {label} non supportata"
                    )
                dropped.add(label.split(":")[0])
                degraded.append(f"{label} (capacita rilevata: non supportata)")
        return degraded

    # ------------------------------------------------------------------ http

    def _backoff(self, attempt: int, retry_after: str | None) -> float:
        if retry_after:
            try:
                return min(float(retry_after), self.backoff_cap)
            except ValueError:
                pass
        base = min(self.backoff_base * (2**attempt), self.backoff_cap)
        return base * (0.8 + 0.4 * random.random())

    async def _open(
        self, payload: dict[str, Any], *, stream: bool, timeout: httpx.Timeout | None
    ) -> tuple[httpx.Response, set[str], list[str], int]:
        """POST con retry/backoff + degradazione 400. Ritorna (resp, dropped, degraded, attempts).

        La responsabilita` di chiudere `resp` e' del chiamante.
        """
        dropped: set[str] = set()
        degraded: list[str] = []
        url = f"{self.node.endpoint.rstrip('/')}/chat/completions"
        last_exc: Exception | None = None
        retry_after: str | None = None
        attempt = 0
        degrade_budget = len(_DEGRADABLE_FIELDS)  # anti-loop: ogni campo al massimo una volta
        while True:
            try:
                req = self._client.build_request(
                    "POST", url, json=payload, timeout=timeout or self._timeout
                )
                resp = await self._client.send(req, stream=stream)
            except httpx.HTTPError as exc:
                last_exc = exc
                retry_after = None
            else:
                if resp.status_code in RETRY_STATUSES:
                    body = await resp.aread()
                    retry_after = resp.headers.get("retry-after")
                    await resp.aclose()
                    last_exc = NodeHTTPError(resp.status_code, body.decode(errors="replace"))
                elif resp.status_code >= 400:
                    body = (await resp.aread()).decode(errors="replace")
                    await resp.aclose()
                    blamed = _blamed_field(body)
                    if self.degrade and blamed and blamed in payload and degrade_budget > 0:
                        degrade_budget -= 1
                        dropped.add(blamed)
                        if blamed == "tools":
                            dropped.add("tool_choice")
                        degraded.append(f"{blamed} (rimosso: 400 del server)")
                        self.stats.degraded += 1
                        payload = {k: v for k, v in payload.items() if k not in dropped}
                        continue  # la degradazione non consuma budget di retry
                    raise NodeHTTPError(resp.status_code, body, blamed_field=blamed)
                else:
                    self.stats.requests += 1
                    return resp, dropped, degraded, attempt + 1
            if attempt < self.max_retries:
                attempt += 1
                self.stats.retries += 1
                await asyncio.sleep(self._backoff(attempt - 1, retry_after))
            else:
                self.stats.failures += 1
                raise AdapterError(
                    f"nodo {self.node.endpoint}: chat/completions fallita dopo "
                    f"{attempt + 1} tentativi: {type(last_exc).__name__}: {last_exc}"
                ) from last_exc

    # ------------------------------------------------------------------ chat

    async def chat(
        self,
        messages: Sequence[Message],
        *,
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = 0.0,
        top_p: float | None = None,
        stop: list[str] | None = None,
        tools: list[dict] | None = None,
        tool_choice: Any = None,
        response_format: dict | None = None,
        stream: bool = False,
        extra_body: Mapping[str, Any] | None = None,
        read_timeout: float | None = None,
        strict: bool = False,
        on_delta: Callable[[str], None] | None = None,
    ) -> ChatResult:
        """Chat completion unica via: sync-like (stream=False) o SSE (stream=True).

        `on_delta` riceve i chunk di testo durante lo streaming. Il conteggio
        token usa l'usage del server se presente; altrimenti stima locale
        marcata `usage.estimated=True`.
        """
        dropped: set[str] = set()
        pre_degraded = self._gate_capabilities(
            tools=tools, response_format=response_format, dropped=dropped, strict=strict
        )
        include_stream_usage = stream and (
            self.capabilities is None or self.capabilities.streamed_usage is not False
        )
        timeout = (
            httpx.Timeout(read_timeout, connect=self._timeout.connect) if read_timeout else None
        )
        t_start = time.monotonic()
        resp, dropped, degraded, attempts = await self._open(
            self._build_payload(
                messages,
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
                stop=stop,
                tools=tools,
                tool_choice=tool_choice,
                response_format=response_format,
                stream=stream,
                include_stream_usage=include_stream_usage,
                extra_body=extra_body,
                dropped=dropped,
            ),
            stream=stream,
            timeout=timeout,
        )
        try:
            if stream:
                result = await self._consume_stream(resp, on_delta=on_delta)
            else:
                body = await resp.aread()
                result = self._consume_json(body.decode(errors="replace"))
        finally:
            await resp.aclose()
        result.total_s = time.monotonic() - t_start
        result.attempts = attempts
        result.degraded = tuple(pre_degraded + degraded)
        if result.usage.estimated or not result.usage.completion_tokens:
            out = result.text + result.reasoning
            result.usage = Usage(
                prompt_tokens=result.usage.prompt_tokens
                or estimate_tokens(messages_text(messages)),
                completion_tokens=result.usage.completion_tokens or estimate_tokens(out),
                reasoning_tokens=result.usage.reasoning_tokens,
                estimated=True,
            )
        return result

    async def stream_text(self, messages: Sequence[Message], **kwargs: Any) -> AsyncIterator[str]:
        """Convenienza: itera solo il testo. Timeout/annullamento chiudono la risposta."""
        queue: asyncio.Queue[str | None] = asyncio.Queue()

        async def pump() -> None:
            try:
                await self.chat(messages, stream=True, on_delta=queue.put_nowait, **kwargs)
            finally:
                queue.put_nowait(None)

        task = asyncio.create_task(pump())
        try:
            while True:
                chunk = await queue.get()
                if chunk is None:
                    break
                yield chunk
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def _consume_stream(
        self, resp: httpx.Response, *, on_delta: Callable[[str], None] | None
    ) -> ChatResult:
        result = ChatResult(text="")
        parts: list[str] = []
        reasoning_parts: list[str] = []
        usage: Usage | None = None
        ttft: float | None = None
        t0 = time.monotonic()
        async for raw in resp.aiter_lines():
            line = raw.strip()
            if not line or not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                chunk = json.loads(data)
            except json.JSONDecodeError:
                continue
            if isinstance(chunk.get("usage"), dict):
                u = chunk["usage"]
                usage = Usage(
                    prompt_tokens=int(u.get("prompt_tokens") or 0),
                    completion_tokens=int(u.get("completion_tokens") or 0),
                    reasoning_tokens=int(
                        (u.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0
                    ),
                )
            if chunk.get("model"):
                result.model = chunk["model"]
            for choice in chunk.get("choices") or []:
                if choice.get("finish_reason"):
                    result.finish_reason = choice["finish_reason"]
                delta = choice.get("delta") or {}
                content = delta.get("content")
                reasoning = delta.get("reasoning_content") or delta.get("reasoning")
                if isinstance(content, str) and content:
                    if ttft is None:
                        ttft = time.monotonic() - t0
                    parts.append(content)
                    if on_delta is not None:
                        on_delta(content)
                if isinstance(reasoning, str) and reasoning:
                    if ttft is None:
                        ttft = time.monotonic() - t0
                    reasoning_parts.append(reasoning)
        result.text = "".join(parts)
        result.reasoning = "".join(reasoning_parts)
        result.tool_calls = []
        result.ttft_s = ttft
        result.usage = usage or Usage()
        return result

    def _consume_json(self, body: str) -> ChatResult:
        try:
            data = json.loads(body)
        except json.JSONDecodeError as exc:
            raise AdapterError(f"risposta non-JSON dal nodo: {body[:200]}") from exc
        result = ChatResult(text="")
        result.model = data.get("model")
        choices = data.get("choices") or []
        if choices:
            choice = choices[0]
            result.finish_reason = choice.get("finish_reason")
            msg = choice.get("message") or {}
            result.text = str(msg.get("content") or "")
            result.reasoning = str(msg.get("reasoning_content") or msg.get("reasoning") or "")
            if not result.text and result.reasoning:
                # runtime thinking che mette tutto nel campo reasoning
                result.text, result.reasoning = result.reasoning, ""
            result.tool_calls = list(msg.get("tool_calls") or [])
        u = data.get("usage") or {}
        if u:
            result.usage = Usage(
                prompt_tokens=int(u.get("prompt_tokens") or 0),
                completion_tokens=int(u.get("completion_tokens") or 0),
                reasoning_tokens=int(
                    (u.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0
                ),
            )
        else:
            result.usage = Usage(estimated=True)
        return result


__all__ = [
    "AdapterError",
    "AdapterStats",
    "Capabilities",
    "CapabilityError",
    "ChatResult",
    "NodeAdapter",
    "NodeHTTPError",
    "Usage",
    "estimate_tokens",
    "messages_text",
]
