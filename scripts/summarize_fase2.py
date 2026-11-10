"""Aggrega le run della baseline Fase 2 in una tabella modello × suite.

Scrive docs/2026-11-10-fase2-baseline.md. Per ogni (nodo, suite) usa la run
più recente in experiments/ che contiene results.jsonl. Media ± deviazione
standard su token totali e tempo per item; pass-rate a livello di campione
(verificabili/semi: tutti i test passano; aperti: punteggio ≥ soglia).

Usage:  uv run python scripts/summarize_fase2.py
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
EXPERIMENTS = REPO / "experiments"
SUITES = ["verificabili", "semi", "aperti"]
NODES = ["heavy", "mid"]


def latest_runs() -> dict[tuple[str, str], Path]:
    out: dict[tuple[str, str], Path] = {}
    for d in sorted(EXPERIMENTS.glob("20261110T*-eval-*-single")):
        meta = d / "meta.json"
        rows = d / "results.jsonl"
        if not meta.exists() or not rows.exists():
            continue
        m = json.loads(meta.read_text(encoding="utf-8"))
        for node in m["setup"]["nodes"]:
            key = (node, m["setup"]["suite"])
            if key not in out or d.name > out[key].name:  # SUPERSEDED non ha results.jsonl
                out[key] = d
    return out


def fmt(v: float | None) -> str:
    return f"{v:.1f}" if v is not None else "—"


def main() -> None:
    runs = latest_runs()
    lines = [
        "# Baseline single-call — Fase 2 (2026-11-10)",
        "",
        "Ipotesi: quantificare il pavimento single-call (accuracy, varianza tra campioni,",
        "token, tempo reale) per nodo × suite, prima del ledger di Fase 3.",
        "Setup: `harness eval --suite <s> --mode single --samples 3 --seed 1234`, nodi reali",
        "heavy+mid, sampling greedy documentato in `docs/sampling-params.md` (cap corretti,",
        "vedi `docs/DECISIONS.md` D5). Aperti: giudice = altro nodo, punteggio `low_conf`.",
        "",
        "| nodo | suite | item | camp. | pass-rate | tok/camp (med±std) | s/camp (med±std) | run |",
        "|---|---|---|---|---|---|---|---|",
    ]
    per_item_variance: list[float] = []
    for node in NODES:
        for suite in SUITES:
            d = runs.get((node, suite))
            if d is None:
                lines.append(f"| {node} | {suite} | — | — | — | — | — | (mancante) |")
                continue
            rows = [json.loads(ln) for ln in (d / "results.jsonl").read_text().splitlines() if ln]
            items = sorted({r["item"] for r in rows})
            toks = [r["total_tokens"] for r in rows]
            walls = [r["wall_s"] for r in rows]
            passed = [r for r in rows if r["pass"]]
            rate = 100.0 * len(passed) / len(rows) if rows else 0.0
            # varianza del pass per item tra i 3 campioni (0 = item stabile)
            by_item: dict[str, list] = {}
            for r in rows:
                by_item.setdefault(r["item"], []).append(bool(r["pass"]))
            unstable = {i for i, v in by_item.items() if len(set(v)) > 1}
            per_item_variance.extend(0.0 if i not in unstable else 1.0 for i in by_item)
            tok_s = f"{fmt(statistics.mean(toks))}±{fmt(statistics.stdev(toks))}" if toks else "—"
            w_s = f"{fmt(statistics.mean(walls))}±{fmt(statistics.stdev(walls))}" if walls else "—"
            lines.append(
                f"| {node} | {suite} | {len(items)} | {len(rows)} | {rate:.1f}% "
                f"| {tok_s} | {w_s} | {d.name} |"
            )
            if unstable:
                lines.append(
                    f"| | | | | item instabili tra campioni: {', '.join(sorted(unstable))} | | | |"
                )
    if per_item_variance:
        frac = 100.0 * sum(per_item_variance) / len(per_item_variance)
        lines += [
            "",
            f"Instabilità tra i 3 campioni: {frac:.1f}% degli item (nodi×suite) cambia esito;",
            "è la varianza che il confronto modalità di Fase 3 dovrà battere.",
        ]
    lines += [
        "",
        "## Decisione",
        "",
        "- La modalità single ha un pavimento misurato e riproducibile: baseline per la ledger.",
        "- Gli item aperti sono `low_confidence` per costruzione (giudice = altro modello).",
        "- Verifica riproducibilità (stesso seed, sottoinsieme ripetuto):",
        "  `experiments/reproducibility-check.md` (mid bit-exact; heavy esiti-identici",
        "  anche a server idle; sonde grezze in `experiments/repro-probes/`).",
    ]
    out = REPO / "docs" / "2026-11-10-fase2-baseline.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"scritto {out}")


if __name__ == "__main__":
    main()
