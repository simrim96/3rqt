"""Nodo finto OpenAI-compatibile per i test (nessuna rete esterna).

Servizio aiohttp su porta locale con latenza configurabile, risposta in
streaming chunked, usage, errori iniettabili (status N per K richieste) e
capacita dichiarate configurabili. La suite CI usa SOLO questo; i test contro
i nodi reali sono marcati `live`.
"""

from __future__ import annotations

import asyncio
import json
import re
import threading
import time
from dataclasses import dataclass, field

from aiohttp import web


@dataclass
class MockNodeConfig:
    model: str = "mock-model"
    first_token_delay_s: float = 0.05
    per_chunk_delay_s: float = 0.01
    n_chunks: int = 5
    reply: str = "mock reply"
    prompt_tokens: int = 11
    completion_tokens: int | None = None  # default: len(parole risposta)
    ctx: int = 32768
    supports_tools: bool = True
    supports_response_format: bool = True
    supports_stream: bool = True
    include_stream_usage: bool = True
    # iniezione errori: lista di status da restituire (uno per richiesta) prima
    # di tornare a rispondere bene; vuoto = sempre OK
    fail_statuses: list[int] = field(default_factory=list)
    # regole deterministiche per la suite eval CI: lista (regex, risposta); la
    # prima che matcha il testo della richiesta determina la risposta.
    rules: list[tuple[str, str]] = field(default_factory=list)
    # giudice mock deterministico: se la richiesta contiene la firma del prompt
    # giudice ("RUBRICA (id:") risponde con punteggio PIENO su tutti i criteri
    judge_mode: bool = False
    fail_message: str = "mock: errore simulato"
    # campi che il mock "rifiuta" con 400 se presenti nel payload
    rejects: list[str] = field(default_factory=list)
    # se True, richiede max_tokens<=ctx altrimenti 400 (simula contesto reale)
    enforce_ctx: bool = True

    def requests_served(self) -> int:
        return self._served

    _served: int = 0


def _judge_reply(text: str) -> str:
    """Giudice mock deterministico: punteggio PIENO su ogni criterio elencato
    nel prompt giudice ('- "id" (N punti): ...')."""
    scores = {cid: int(pts) for cid, pts in re.findall(r'- "([^"]+)" \((\d+) punti\)', text)}
    return "Valutazione.\n" + json.dumps({"scores": scores}, ensure_ascii=False)


def _pick_reply(cfg: MockNodeConfig, payload: dict) -> str:
    text = "\n".join(str(m.get("content") or "") for m in payload.get("messages", []))
    if cfg.judge_mode and "RUBRICA (id:" in text:
        return _judge_reply(text)
    for pattern, resp in cfg.rules:
        if re.search(pattern, text, re.S):
            return resp
    return cfg.reply


def _split_reply(text: str, chunks: int) -> list[str]:
    if chunks <= 1 or len(text) <= chunks:
        return [text] if text else []
    size = max(1, len(text) // chunks + (1 if len(text) % chunks else 0))
    return [text[i : i + size] for i in range(0, len(text), size)]


def create_app(cfg: MockNodeConfig) -> web.Application:
    async def models(_: web.Request) -> web.Response:
        return web.json_response(
            {"object": "list", "data": [{"id": cfg.model, "object": "model", "owned_by": "mock"}]}
        )

    async def health(_: web.Request) -> web.Response:
        return web.json_response({"status": "ok", "service": "mocknode", "version": "9.9"})

    async def chat(request: web.Request) -> web.Response:
        cfg._served += 1
        if cfg.fail_statuses:
            status = cfg.fail_statuses.pop(0)
            return web.json_response(
                {"error": {"message": cfg.fail_message, "type": "server_error"}}, status=status
            )
        payload = await request.json()
        for field_name in cfg.rejects:
            if field_name in payload:
                return web.json_response(
                    {"error": {"message": f"Unsupported parameter: '{field_name}'"}}, status=400
                )
        if payload.get("stream") is not True and not cfg.supports_stream:
            pass  # sync e' sempre supportato; il gate su stream e' sotto
        if payload.get("stream") and not cfg.supports_stream:
            return web.json_response(
                {"error": {"message": "Unsupported parameter: 'stream'"}}, status=400
            )
        if "tools" in payload and not cfg.supports_tools:
            return web.json_response(
                {"error": {"message": "Unsupported parameter: 'tools'"}}, status=400
            )
        if "response_format" in payload and not cfg.supports_response_format:
            return web.json_response(
                {"error": {"message": "Unsupported parameter: 'response_format'"}}, status=400
            )
        if cfg.enforce_ctx and int(payload.get("max_tokens") or 0) > cfg.ctx:
            return web.json_response(
                {"error": {"message": f"maximum context length is {cfg.ctx}"}}, status=400
            )

        reply = _pick_reply(cfg, payload)
        parts = _split_reply(reply, cfg.n_chunks)
        completion = (
            cfg.completion_tokens if cfg.completion_tokens is not None else max(len(parts), 1)
        )
        tool_calls = None
        if payload.get("tools") and payload.get("tool_choice") in ("required", "auto", None):
            # il mock "chiama" il primo tool quando tools e' presente
            tool = (payload["tools"] or [None])[0]
            if tool and cfg.supports_tools:
                tool_calls = [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": tool["function"]["name"],
                            "arguments": '{"city":"Rome"}',
                        },
                    }
                ]

        if payload.get("stream"):
            resp = web.StreamResponse(
                status=200,
                headers={"Content-Type": "text/event-stream", "Cache-Control": "no-cache"},
            )
            await resp.prepare(request)
            await asyncio.sleep(cfg.first_token_delay_s)

            async def send(obj: dict) -> None:
                await resp.write(f"data: {json.dumps(obj)}\n\n".encode())

            base = {"id": "mock", "object": "chat.completion.chunk", "model": cfg.model}
            if tool_calls:
                await send(
                    {
                        **base,
                        "choices": [
                            {"index": 0, "delta": {"tool_calls": tool_calls}, "finish_reason": None}
                        ],
                    }
                )
            else:
                for _i, part in enumerate(parts):
                    await send(
                        {
                            **base,
                            "choices": [
                                {"index": 0, "delta": {"content": part}, "finish_reason": None}
                            ],
                        }
                    )
                    await asyncio.sleep(cfg.per_chunk_delay_s)
            await send(
                {
                    **base,
                    "choices": [
                        {
                            "index": 0,
                            "delta": {},
                            "finish_reason": "tool_calls" if tool_calls else "stop",
                        }
                    ],
                }
            )
            wants_usage = (payload.get("stream_options") or {}).get("include_usage")
            if wants_usage and cfg.include_stream_usage:
                await send(
                    {
                        **base,
                        "choices": [],
                        "usage": {
                            "prompt_tokens": cfg.prompt_tokens,
                            "completion_tokens": completion,
                            "total_tokens": cfg.prompt_tokens + completion,
                        },
                    }
                )
            await resp.write(b"data: [DONE]\n\n")
            await resp.write_eof()
            return resp

        await asyncio.sleep(cfg.first_token_delay_s + cfg.per_chunk_delay_s * len(parts))
        message: dict = {"role": "assistant", "content": "" if tool_calls else reply}
        if tool_calls:
            message["tool_calls"] = tool_calls
        return web.json_response(
            {
                "id": "mock",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": cfg.model,
                "choices": [
                    {
                        "index": 0,
                        "message": message,
                        "finish_reason": "tool_calls" if tool_calls else "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": cfg.prompt_tokens,
                    "completion_tokens": completion,
                    "total_tokens": cfg.prompt_tokens + completion,
                },
            }
        )

    app = web.Application()
    app.router.add_get("/v1/models", models)
    app.router.add_get("/health", health)
    app.router.add_post("/v1/chat/completions", chat)
    return app


class MockNode:
    """Context manager: avvia il mock su porta effimera e fornisce l'endpoint."""

    def __init__(self, cfg: MockNodeConfig | None = None):
        self.cfg = cfg or MockNodeConfig()
        self._runner: web.AppRunner | None = None
        self.base_url = ""

    @property
    def endpoint(self) -> str:
        return f"{self.base_url}/v1"

    async def start(self) -> MockNode:
        self._runner = web.AppRunner(create_app(self.cfg))
        await self._runner.setup()
        site = web.TCPSite(self._runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]  # type: ignore[union-attr]
        self.base_url = f"http://127.0.0.1:{port}"
        return self

    async def stop(self) -> None:
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None

    async def __aenter__(self) -> MockNode:
        return await self.start()

    async def __aexit__(self, *exc: object) -> None:
        await self.stop()


class MockNodeThread:
    """MockNode in thread dedicato con loop proprio.

    Per i test che vogliono invocare codice CLI che chiama asyncio.run()
    (non si puo' avviare un loop annidato in un loop gia' running).
    """

    def __init__(self, cfg: MockNodeConfig | None = None):
        self.cfg = cfg or MockNodeConfig()
        self.base_url = ""
        self._ready = threading.Event()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    @property
    def endpoint(self) -> str:
        return f"{self.base_url}/v1"

    def _run(self) -> None:
        async def main() -> None:
            async with MockNode(self.cfg) as node:
                self.base_url = node.base_url
                self._ready.set()
                while not self._stop.is_set():
                    await asyncio.sleep(0.05)

        asyncio.run(main())

    def __enter__(self) -> MockNodeThread:
        self._thread.start()
        if not self._ready.wait(10):
            raise RuntimeError("mock node non partito in 10s")
        return self

    def __exit__(self, *exc: object) -> None:
        self._stop.set()
        self._thread.join(10)


__all__ = ["MockNode", "MockNodeConfig", "MockNodeThread", "create_app"]
