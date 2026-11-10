"""`harness calibrate`: misure reali di throughput, latenza, concorrenza,
stabilita' e mini-valutazione fixed-suite; salvataggio in `calibration/<nodo>.json`.

Ogni misura e' opzionale via flag per rispettare il budget sui nodi condivisi
(mid/tabbyAPI: concorrenza 1). Il file di output contiene data, hash della
config, fingerprint del runtime e versione della suite mini.
"""

from __future__ import annotations

import asyncio
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from evals.mini import SUITE_VERSION, extract_answer, grade, load_items
from nodes.adapter import AdapterError, Capabilities, NodeAdapter
from nodes.config import Node, NodesConfig

_CALIB_SYS = "You are a benchmark harness. Follow the output format exactly. Do not explain."
_COUNT_PROMPT = (
    "Output the numbers 1, 2, 3, ... in order, one per line, separated by "
    "newlines, up to {n} inclusive. Output ONLY the numbers."
)


def _usage_completion(res: Any, text: str) -> int:
    if res.usage.completion_tokens:
        return res.usage.completion_tokens
    return max(len(text.split()), 1)


async def measure_stream(adapter: NodeAdapter, *, prompt: str, max_tokens: int) -> dict[str, Any]:
    """TTFT e tokens/s in streaming (rilevazione reale, non dichiarata)."""
    parts: list[str] = []

    def on_delta(chunk: str) -> None:
        parts.append(chunk)

    res = await adapter.chat(
        [
            {"role": "system", "content": _CALIB_SYS},
            {"role": "user", "content": prompt},
        ],
        max_tokens=max_tokens,
        temperature=0.0,
        stream=True,
        on_delta=on_delta,
        read_timeout=300.0,
    )
    gen_s = max(res.total_s - (res.ttft_s or 0.0), 1e-6)
    n_tok = _usage_completion(res, res.text)
    return {
        "ttft_s": round(res.ttft_s, 4) if res.ttft_s is not None else None,
        "gen_tokens": n_tok,
        "gen_seconds": round(res.total_s, 4),
        "tokens_per_s": round(n_tok / gen_s, 2),
        "stream": True,
        "degraded": list(res.degraded),
    }


async def measure_concurrency(
    adapter: NodeAdapter, *, concurrency: int, max_tokens: int, repeats: int = 1
) -> dict[str, Any]:
    """Comportamento a concorrenza N: throughput aggregato e degradazione TTFT."""
    per_rep: list[dict[str, Any]] = []
    for _ in range(max(repeats, 1)):

        async def one() -> dict[str, Any]:
            parts: list[str] = []
            t0 = time.monotonic()
            res = await adapter.chat(
                [
                    {"role": "system", "content": _CALIB_SYS},
                    {
                        "role": "user",
                        "content": "Write one sentence about the sea.",
                    },
                ],
                max_tokens=max_tokens,
                temperature=0.7,
                stream=True,
                on_delta=parts.append,
                read_timeout=300.0,
            )
            return {
                "ttft": res.ttft_s,
                "tok": _usage_completion(res, res.text),
                "wall": time.monotonic() - t0,
                "ok": bool(res.text or res.usage.completion_tokens),
            }

        results = await asyncio.gather(*(one() for _ in range(concurrency)), return_exceptions=True)
        ok = [r for r in results if isinstance(r, dict) and r["ok"]]
        failed = len(results) - len(ok)
        wall = max((r["wall"] for r in ok), default=0.0) or 1e-6
        ttfts = [r["ttft"] for r in ok if r["ttft"] is not None]
        tot_tok = sum(r["tok"] for r in ok)
        per_rep.append(
            {
                "ok": len(ok),
                "failed": failed,
                "agg_tokens_per_s": round(tot_tok / wall, 2),
                "mean_ttft_s": round(sum(ttfts) / len(ttfts), 4) if ttfts else None,
                "max_ttft_s": round(max(ttfts), 4) if ttfts else None,
                "wall_s": round(wall, 4),
            }
        )
    return {"concurrency": concurrency, "repeats": per_rep}


async def measure_context_cost(adapter: NodeAdapter, *, probe_tokens: int) -> dict[str, Any]:
    """Consumo contesto: prefilla ~probe_tokens e misura TTFT prefill + usage reale.

    Due passaggi: il primo calibra i caratteri-per-token OSSERVATI dal server
    (l'assunzione 4 char/token e' falsa per molti tokenizer BPE), il secondo
    porta il prompt alla taglia richiesta. Streaming per misurare il TTFT reale.
    """
    words = "alpha bravo charlie delta echo foxtrot golf hotel india juliet "

    def filler(n_chars: int) -> str:
        return (words * (n_chars // len(words) + 1))[:n_chars]

    async def attempt(n_chars: int) -> Any:
        parts: list[str] = []
        return await adapter.chat(
            [{"role": "user", "content": filler(n_chars) + "\n\nReply with exactly: OK"}],
            max_tokens=8,
            temperature=0.0,
            stream=True,
            on_delta=parts.append,
            read_timeout=600.0,
        )

    t0 = time.monotonic()
    first = await attempt(probe_tokens * 4)
    observed = first.usage.prompt_tokens or 0
    corrected = probe_tokens * 4
    second: Any = None
    if observed > 0 and abs(observed - probe_tokens) / max(probe_tokens, 1) > 0.1:
        # tasso char/token reale del tokenizer di QUESTO nodo, ricava la taglia giusta
        corrected = max(int(probe_tokens * (probe_tokens * 4 / observed)), 64)
        second = await attempt(corrected)
    res = second or first
    wall = time.monotonic() - t0
    return {
        "requested_tokens_approx": probe_tokens,
        "prompt_tokens_reported": res.usage.prompt_tokens or None,
        "usage_estimated": res.usage.estimated,
        "ttft_prefill_s": round(res.ttft_s, 4) if res.ttft_s is not None else None,
        "wall_s": round(wall, 3),
    }


async def measure_long_generation(
    adapter: NodeAdapter, *, max_tokens: int = 1500, runs: int = 2
) -> dict[str, Any]:
    """Stabilita' su generazioni lunghe: N run da ~max_tokens, niente errori/truncation anomala."""
    runs_out = []
    for _ in range(runs):
        try:
            parts: list[str] = []
            res = await adapter.chat(
                [
                    {"role": "system", "content": _CALIB_SYS},
                    {"role": "user", "content": _COUNT_PROMPT.format(n=400)},
                ],
                max_tokens=max_tokens,
                temperature=0.0,
                stream=True,
                on_delta=parts.append,
                read_timeout=600.0,
            )
            tok = _usage_completion(res, res.text)
            runs_out.append(
                {
                    "ok": True,
                    "gen_tokens": tok,
                    "tokens_per_s": round(tok / max(res.total_s, 1e-6), 2),
                    "finish_reason": res.finish_reason,
                    "ttft_s": round(res.ttft_s, 4) if res.ttft_s is not None else None,
                }
            )
        except AdapterError as exc:
            runs_out.append({"ok": False, "error": str(exc)[:300]})
    stable = all(r["ok"] for r in runs_out)
    return {"runs": runs_out, "stable": stable, "max_tokens": max_tokens}


async def run_mini_eval(
    adapter: NodeAdapter, *, max_items: int | None = None, max_tokens: int = 512
) -> dict[str, Any]:
    # max_tokens deve coprire il ragionamento del modello PRIMA della risposta
    # finale: i modelli reasoning bruciano 100-300 token di reasoning, con budget
    # corti il content resta vuoto e il voto cade sul reasoning (falsato).
    items = load_items()
    if max_items:
        items = items[:max_items]
    per_item = []
    n_ok = 0
    t0 = time.monotonic()
    for item in items:
        use_rf = None
        try:
            res = await adapter.chat(
                [
                    {"role": "system", "content": _CALIB_SYS},
                    {"role": "user", "content": item.prompt},
                ],
                max_tokens=max_tokens,
                temperature=0.0,
                response_format=use_rf,
                read_timeout=180.0,
            )
            out = res.text or res.reasoning
            ok = grade(item, out)
        except AdapterError as exc:
            ok, res = False, None
            per_item.append({"id": item.id, "ok": False, "error": str(exc)[:200]})
            continue
        n_ok += ok
        entry: dict[str, Any] = {"id": item.id, "category": item.category, "ok": ok}
        if not ok:
            entry["got"] = extract_answer(out)[:80]
            entry["expected"] = item.golden[:80]
            entry["answer_in_reasoning"] = not res.text
        per_item.append(entry)
    return {
        "suite": SUITE_VERSION,
        "n": len(items),
        "correct": n_ok,
        "accuracy": round(n_ok / len(items), 4) if items else None,
        "seconds": round(time.monotonic() - t0, 2),
        "items": per_item,
    }


async def calibrate_node(
    node: Node,
    *,
    node_name: str,
    cfg: NodesConfig,
    capabilities: Capabilities | None = None,
    runtime: dict[str, Any] | None = None,
    stream_prompt_tokens: int = 48,
    stream_max_tokens: int = 200,
    concurrency_levels: tuple[int, ...] = (1, 2, 4),
    concurrency_max_tokens: int = 64,
    concurrency_repeats: int = 1,
    context_probe_tokens: int = 8192,
    long_max_tokens: int = 1500,
    long_runs: int = 2,
    mini_max_items: int | None = None,
    skip: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    """Esegue la batteria di misure su un nodo e costruisce il report."""
    adapter = NodeAdapter(node, capabilities=capabilities, max_retries=1)
    report: dict[str, Any] = {
        "node": node_name,
        "endpoint": node.endpoint,
        "model": node.model,
        "date": datetime.now(UTC).isoformat(timespec="seconds"),
        "config_hash": cfg.config_hash(),
        "runtime": runtime or {},
        "suite_version": SUITE_VERSION,
        "capabilities_snapshot": capabilities.model_dump(mode="json") if capabilities else None,
        "measures": {},
        "warnings": [],
    }
    try:
        if "stream" not in skip:
            report["measures"]["stream"] = await measure_stream(
                adapter,
                prompt="Count from 1 to 200, one number per line, nothing else.",
                max_tokens=stream_max_tokens,
            )
        if "concurrency" not in skip:
            report["measures"]["concurrency"] = []
            for level in concurrency_levels:
                report["measures"]["concurrency"].append(
                    await measure_concurrency(
                        adapter,
                        concurrency=level,
                        max_tokens=concurrency_max_tokens,
                        repeats=concurrency_repeats,
                    )
                )
        if "context" not in skip and context_probe_tokens:
            report["measures"]["context"] = await measure_context_cost(
                adapter, probe_tokens=context_probe_tokens
            )
        if "long" not in skip:
            report["measures"]["long_generation"] = await measure_long_generation(
                adapter, max_tokens=long_max_tokens, runs=long_runs
            )
        if "mini" not in skip:
            report["measures"]["mini_eval"] = await run_mini_eval(adapter, max_items=mini_max_items)
    finally:
        await adapter.aclose()
    return report


def save_report(report: dict[str, Any], out_dir: Path) -> Path:
    """Scrive calibration/<nodo>.json fondendo con un eventuale report esistente:
    una corsa parziale (--skip) aggiorna solo le sue misure senza cancellare le altre."""
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{report['node']}.json"
    if path.exists():
        try:
            prev = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            prev = {}
        if prev.get("node") == report["node"]:
            merged = {**prev, **report}
            merged["measures"] = {**(prev.get("measures") or {}), **(report["measures"] or {})}
            report = merged
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


__all__ = [
    "calibrate_node",
    "measure_concurrency",
    "measure_context_cost",
    "measure_long_generation",
    "measure_stream",
    "run_mini_eval",
    "save_report",
]
