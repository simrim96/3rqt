"""Scheduler: code per nodo, concorrenza, fallback (Fase 4).

Fase 0: solo lo scheletro dei dati. La coda reale (SQLite + asyncio) arriva
con l'orchestrazione multi-nodo.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Job:
    task_id: str
    role: str
    node: str | None = None  # assegnato dallo scheduler in base a ruoli_allowed
    attempts: int = 0


@dataclass
class NodeQueue:
    """Coda locale per nodo: concorrenza = numero massimo di Job in volo."""

    node: str
    concurrency: int = 1
    pending: list[Job] = field(default_factory=list)
    in_flight: int = 0

    def can_start(self) -> bool:
        return self.in_flight < self.concurrency and bool(self.pending)


__all__ = ["Job", "NodeQueue"]
