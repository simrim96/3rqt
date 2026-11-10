"""`harness doctor`: fingerprint runtime + capacita *rilevate con probe* (PLAN §3 Fase 1).

Niente fiducia alla memoria ne' ai valori dichiarati: contesto massimo
effettivo, tool calling, output strutturato e template di chat vengono
verificati con chiamate probe contro il nodo reale. I risultati finiscono in
`Capabilities`, che e' l'unica fonte che l'adapter usa per discriminare il
comportamento (mai il nome del modello — PLAN §0.2).
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from datetime import UTC, datetime
from typing import Any

import httpx
from pydantic import BaseModel, Field

from nodes.adapter import (
    AdapterError,
    Capabilities,
    NodeAdapter,
    NodeHTTPError,
    estimate_tokens,
)
from nodes.config import Node

TEMPLATE_LEAK_MARKERS = (
    "<|im_start|>",
    "<|im_end|>",
    "<|sys|>",
    "[INST]",
    "[/INST]",
    "<<SYS>>",
    "<system>",
    "[SYS]",
)

_TEMPLATE_REPORT_KEYS = ("chat_template", "chat_format", "template_type", "template")
_TEMPLATE_GET_PATHS = ("props", "server_info", "info", "v1/props", "tokenize")


class NodeHealth(BaseModel):
    name: str
    endpoint: str
    reachable: bool = False
    runtime: str = "unknown"
    version: str | None = None
    server_header: str | None = None
    models: list[str] = Field(default_factory=list)
    configured_model_present: bool | None = None
    declared_ctx: int | None = None
    chat_ok: bool = False
    chat_reply: str | None = None
    latency_s: float | None = None
    error: str | None = None
    capabilities: Capabilities | None = None
    warnings: list[str] = Field(default_factory=list)


def _root(endpoint: str) -> str:
    base = endpoint.rstrip("/")
    return base[: base.rfind("/")] if "/" in base[len("http://") :] else base


async def _get_json(
    client: httpx.AsyncClient, url: str, headers: dict[str, str], timeout: float = 8.0
) -> Any:
    resp = await client.get(url, headers=headers, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


async def probe_fingerprint(
    node: Node, client: httpx.AsyncClient
) -> tuple[bool, str, str | None, str | None, list[str], bool | None]:
    """Raggiungibilita + modelli + fingerprint runtime (health, owned_by, header Server)."""
    headers = {"Authorization": f"Bearer {node.api_key or 'none'}"}
    base = node.endpoint.rstrip("/")
    try:
        resp = await client.get(f"{base}/models", headers=headers, timeout=15.0)
        resp.raise_for_status()
        models_raw = resp.json().get("data", [])
    except (httpx.HTTPError, ValueError):
        return False, "unknown", None, None, [], None

    models = [m.get("id", "?") for m in models_raw if isinstance(m, dict)]
    server = (resp.headers.get("server") or "").strip() or None
    version: str | None = None
    engine: str | None = None
    for health_url in (f"{base}/health", f"{_root(node.endpoint)}/health"):
        try:
            hj = await _get_json(client, health_url, headers, timeout=5.0)
        except (httpx.HTTPError, ValueError):
            continue
        if isinstance(hj, dict):
            engine = hj.get("engine") or hj.get("service") or engine
            version = hj.get("version") or version
            if engine or version:
                break
    if version is None and server and "/" in server:
        version = server.partition("/")[2].split(" ")[0]
    owned = {m.get("owned_by") for m in models_raw if isinstance(m, dict) and m.get("owned_by")}
    if engine:
        runtime = str(engine)
    elif len(owned) == 1:
        runtime = str(next(iter(owned)))
    elif server:
        runtime = server.partition("/")[0]
    else:
        runtime = "openai-compatible"
    present = any(m == node.model for m in models)
    return True, runtime, version, server, models, present


async def probe_chat(node: Node, adapter: NodeAdapter) -> tuple[bool, str | None, float]:
    t0 = time.monotonic()
    res = await adapter.chat(
        [
            {"role": "system", "content": "Reply with exactly: OK"},
            {"role": "user", "content": "ping"},
        ],
        max_tokens=24,
        temperature=0.0,
        read_timeout=60.0,
    )
    reply = (res.text or res.reasoning).strip()
    return bool(reply), reply or "(vuoto)", time.monotonic() - t0


async def probe_chat_template(
    node: Node, adapter: NodeAdapter, client: httpx.AsyncClient, caps: Capabilities
) -> None:
    """Template di chat: dichiarato (se il runtime lo espone) + prova comportamentale.

    Un runtime senza template applicato tende a ecostruttare i marker del
    template nella risposta: la markerizziamo come template non applicato.
    """
    headers = {"Authorization": f"Bearer {node.api_key or 'none'}"}
    root, base = _root(node.endpoint), node.endpoint.rstrip("/")
    reported: str | None = None
    for path in _TEMPLATE_GET_PATHS:
        for prefix in (root, base):
            url = f"{prefix}/{path}"
            try:
                data = await _get_json(client, url, headers, timeout=5.0)
            except (httpx.HTTPError, ValueError):
                continue
            if isinstance(data, dict):
                hit = next((k for k in _TEMPLATE_REPORT_KEYS if k in data), None)
                if hit:
                    reported = f"GET /{path}:{hit}"
                    break
        if reported:
            break
    caps.chat_template_source = reported or "non esposto dal runtime"

    try:
        res = await adapter.chat(
            [
                {"role": "system", "content": "Reply with exactly: OK"},
                {"role": "user", "content": "ping"},
            ],
            max_tokens=48,
            temperature=0.0,
            read_timeout=60.0,
        )
        out = res.text + res.reasoning
        leaks = [m for m in TEMPLATE_LEAK_MARKERS if m.lower() in out.lower()]
        if res.text.strip() and not leaks:
            caps.chat_template_applied = True
        else:
            caps.chat_template_applied = False
            caps.notes["chat_template"] = (
                f"marker template nella risposta: {leaks} — template server non applicato?"
                if leaks
                else "risposta vuota alla probe template"
            )
    except (AdapterError, NodeHTTPError) as exc:
        caps.chat_template_applied = None
        caps.notes["chat_template"] = f"probe fallita: {exc}"


async def probe_tools(adapter: NodeAdapter, caps: Capabilities) -> None:
    tool = {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get current weather for a city.",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string"}},
                "required": ["city"],
            },
        },
    }
    msgs = [{"role": "user", "content": "What is the weather in Rome? Use the tool."}]
    for choice in ("required", "auto"):
        try:
            res = await adapter.chat(
                msgs, tools=[tool], tool_choice=choice, max_tokens=96, read_timeout=90.0
            )
        except NodeHTTPError as exc:
            if exc.blamed_field in ("tools", "tool_choice"):
                caps.tools = False
                caps.notes["tools"] = f"400 sul campo {exc.blamed_field}"
                return
            caps.tools = None
            caps.notes["tools"] = f"probe error: HTTP {exc.status}"
            return
        except AdapterError as exc:
            caps.tools = None
            caps.notes["tools"] = f"probe error: {exc}"
            return
        if res.tool_calls:
            caps.tools = True
            return
        if any("tools" in d or "tool_choice" in d for d in res.degraded):
            caps.tools = False
            caps.notes["tools"] = "tools/tool_choice rimossi dal server (400)"
            return
        if choice == "required":
            continue  # richiesto ma non chiamato: riprova con auto prima di giudicare
    caps.tools = None
    caps.notes["tools"] = "payload accettato ma nessuna tool_calls nella risposta"


_JSON_SCHEMA_RF = {
    "type": "json_schema",
    "json_schema": {
        "name": "answer",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {"answer": {"type": "integer"}},
            "required": ["answer"],
            "additionalProperties": False,
        },
    },
}


def _first_json_object(text: str) -> dict | None:
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


async def probe_structured(adapter: NodeAdapter, caps: Capabilities) -> None:
    """JSON schema (grammar) e json_object, ciascuno con probe dedicata."""
    msg = [
        {
            "role": "user",
            "content": 'Return JSON with key "answer" = 2 + 2. No prose.',
        }
    ]
    for rf_key, rf, attr in (
        ("json_schema", _JSON_SCHEMA_RF, "json_schema"),
        ("json_object", {"type": "json_object"}, "json_object"),
    ):
        try:
            res = await adapter.chat(
                msg, response_format=rf, max_tokens=96, temperature=0.0, read_timeout=90.0
            )
        except NodeHTTPError as exc:
            body = exc.body.lower()
            if exc.blamed_field == "response_format" or rf_key in body or "json" in body:
                setattr(caps, attr, False)
                caps.notes[attr] = f"400: {exc.body[:160]}"
            else:
                setattr(caps, attr, None)
                caps.notes[attr] = f"probe error: HTTP {exc.status}"
            continue
        except AdapterError as exc:
            setattr(caps, attr, None)
            caps.notes[attr] = f"probe error: {exc}"
            continue
        # se il campo e' stato degradato dall'adapter il probe non e' valido
        if any("response_format" in d for d in res.degraded):
            setattr(caps, attr, False)
            caps.notes[attr] = "response_format rimosso dal server (400)"
            continue
        obj = _first_json_object(res.text or res.reasoning)
        if obj is not None and (attr == "json_object" or "answer" in obj):
            setattr(caps, attr, True)
        else:
            setattr(caps, attr, True)
            caps.notes[attr] = f"accettato ma output non parsato: {(res.text or '')[:120]!r}"


def _filler_tokens(n_tokens: int) -> str:
    words = "alpha bravo charlie delta echo foxtrot golf hotel india juliet "
    chars = max(n_tokens * 4, 10)
    reps = chars // len(words) + 1
    return (words * reps)[:chars]


async def probe_effective_ctx(
    node: Node,
    adapter: NodeAdapter,
    *,
    declared: int | None,
    budget_tokens: int = 400_000,
    probe_timeout: float = 600.0,
    steps: int = 4,
) -> dict[str, Any]:
    """Contesto massimo EFFETTIVO con binary search su prefilled (probe, non dichiarato).

    Ritorna {"effective": int|None, "resolution": int, "note": str, "probes": [...]}.
    Il budget (in token di prefill) limita la spesa su nodi lenti/condivisi.
    """
    probes: list[dict[str, Any]] = []
    spent = 0

    async def accepted(n: int) -> bool | None:
        nonlocal spent
        filler = _filler_tokens(n)
        est = estimate_tokens(filler)
        if spent + est > budget_tokens:
            return None  # budget esaurito
        spent += est
        try:
            await adapter.chat(
                [{"role": "user", "content": filler + "\n\nReply with exactly: OK"}],
                max_tokens=1,
                temperature=0.0,
                read_timeout=probe_timeout,
            )
            ok, why = True, None
        except NodeHTTPError as exc:
            ok, why = False, f"HTTP {exc.status}: {exc.body[:140]}"
        except AdapterError as exc:
            ok, why = False, f"{type(exc).__name__}: {exc}"
        probes.append({"tokens": n, "accepted": ok, "note": why})
        return ok

    lo = 0
    hi: int | None = None
    start = declared or 2048
    verdict = await accepted(start)
    if verdict is None:
        return {
            "effective": None,
            "resolution": None,
            "note": "budget probe esaurito",
            "probes": probes,
        }
    if verdict:
        lo = start
        # il dichiarato regge: risaliamo finche' regge (o finche' serve)
        for cand in (int(start * 1.1), int(start * 1.25)):
            if spent + cand > budget_tokens:
                break
            v = await accepted(cand)
            if v is None:
                break
            if v:
                lo = cand
            else:
                hi = cand
                break
        if hi is None:
            return {
                "effective": lo,
                "resolution": None,
                "note": f"accettato almeno {lo} (limite superiore non raggiunto nel budget)",
                "probes": probes,
            }
    else:
        # il dichiarato NON regge: scendi a meta' finche' accetta
        cand = start
        for _ in range(steps):
            cand = max(cand // 2, _MIN_CTX_PROBE)
            v = await accepted(cand)
            if v is None:
                break
            if v:
                lo = cand
                hi = start if hi is None else hi
                break
            if cand <= _MIN_CTX_PROBE:
                break
        else:
            return {
                "effective": None,
                "resolution": None,
                "note": f"nessun contesto accettato gia' a {cand} token",
                "probes": probes,
            }
        if hi is None:
            hi = start

    # raffina [lo, hi) con binary search (accepta < hi)
    resolution = max(1, (hi - lo) // 2**2)
    while hi - lo > resolution:
        mid = (lo + hi) // 2
        v = await accepted(mid)
        if v is None:
            break
        if v:
            lo = mid
        else:
            hi = mid
    return {
        "effective": lo,
        "resolution": max(1, hi - lo),
        "note": f"binaria completata: accettato {lo}, rifiutato {hi}",
        "probes": probes,
    }


_MIN_CTX_PROBE = 256


async def assemble_node(
    name: str,
    node: Node,
    *,
    client: httpx.AsyncClient,
    probe_ctx: bool = True,
    ctx_budget_tokens: int = 400_000,
    max_retries: int = 1,
) -> tuple[NodeHealth, Capabilities]:
    """Fingerprint + chat + tutte le probe capacita per un nodo."""
    health = NodeHealth(name=name, endpoint=node.endpoint, declared_ctx=node.ctx)
    caps = Capabilities(probed_at=datetime.now(UTC).isoformat(timespec="seconds"))
    reachable, runtime, version, server, models, present = await probe_fingerprint(node, client)
    health.reachable = reachable
    health.runtime, health.version, health.server_header = runtime, version, server
    health.models = models
    health.configured_model_present = present
    if not reachable:
        health.error = "endpoint irraggiungibile o /models non risponde"
        return health, caps

    adapter = NodeAdapter(node, max_retries=max_retries)
    try:
        try:
            health.chat_ok, health.chat_reply, health.latency_s = await probe_chat(node, adapter)
        except (AdapterError, asyncio.CancelledError) as exc:
            health.error = f"chat: {exc}"
            return health, caps
        if not health.chat_ok:
            health.warnings.append("chat-completion vuota: probe capacita saltate")
            return health, caps

        await asyncio.gather(
            probe_chat_template(node, adapter, client, caps),
            probe_tools(adapter, caps),
            probe_structured(adapter, caps),
        )
        if probe_ctx:
            try:
                ctx = await probe_effective_ctx(
                    node, adapter, declared=node.ctx, budget_tokens=ctx_budget_tokens
                )
                caps.effective_ctx = ctx["effective"]
                caps.notes["ctx_probe"] = ctx["note"]
                if ctx["effective"] and node.ctx and ctx["effective"] < node.ctx:
                    health.warnings.append(
                        f"contesto effettivo {ctx['effective']} < dichiarato {node.ctx}"
                    )
            except Exception as exc:  # probe mai fatali
                caps.notes["ctx_probe"] = f"probe fallita: {type(exc).__name__}: {exc}"
    finally:
        await adapter.aclose()
    health.capabilities = caps
    return health, caps


def save_capabilities(caps: Capabilities, path: Any) -> None:
    from pathlib import Path

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(
        json.dumps(caps.model_dump(mode="json"), indent=2, ensure_ascii=False), encoding="utf-8"
    )


def load_capabilities(path: Any, *, expected_config_hash: str | None = None) -> Capabilities | None:
    from pathlib import Path

    p = Path(path)
    if not p.exists():
        return None
    try:
        caps = Capabilities.model_validate_json(p.read_text(encoding="utf-8"))
    except ValueError:
        return None
    if expected_config_hash and caps.config_hash not in (None, expected_config_hash):
        return None  # cached contro un'altra config: refresh
    return caps


__all__ = [
    "Capabilities",
    "NodeHealth",
    "assemble_node",
    "load_capabilities",
    "probe_effective_ctx",
    "save_capabilities",
]
