"""Harness di valutazione: suite, runner, metriche qualita/costo/tempo (Fase 2).

Fase 0: solo il registro delle suite disponibili; il runner reale e' il
primo componente funzionante della Fase 2 (baseline single-call prima di
tutto il resto, PLAN §3).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SuiteSpec:
    name: str
    description: str
    modes: tuple[str, ...] = ("single", "ledger", "mixed")


SUITES: dict[str, SuiteSpec] = {
    # Popolato in Fase 2 con la suite di calibrazione del PLAN.
}


__all__ = ["SUITES", "SuiteSpec"]
