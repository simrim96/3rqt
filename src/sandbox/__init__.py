"""Esecuzione sicura di codice e test in isolamento (Fase 3+/9).

Seed: esecuzione subprocess con timeout, sul pattern del verificatore metodo-di-riferimento
(sottoprocesso reale, stdout catturato, timeout per caso). La sandbox vera
(worktree/container) e' pianificata; NON usare per codice non fidato prima
della Fase 9.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass


@dataclass
class RunResult:
    ok: bool
    returncode: int | None
    stdout: str
    stderr: str
    timed_out: bool


def run_python(
    code: str, stdin: str = "", timeout: float = 10.0, python: str = "python3"
) -> RunResult:
    """Esegue codice Python come subprocess reale con timeout (pattern metodo-di-riferimento)."""
    try:
        proc = subprocess.run(  # noqa: S603 - Fase 0/3: ambiente locale fidato, sandbox in Fase 9
            [python, "-c", code],
            input=stdin,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        return RunResult(
            ok=False,
            returncode=None,
            stdout=(exc.stdout or "") if isinstance(exc.stdout, str) else "",
            stderr="timeout",
            timed_out=True,
        )
    return RunResult(
        ok=proc.returncode == 0,
        returncode=proc.returncode,
        stdout=proc.stdout,
        stderr=proc.stderr,
        timed_out=False,
    )


__all__ = ["RunResult", "run_python"]
