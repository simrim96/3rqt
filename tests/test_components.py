"""Test config ruoli + smoke test dei moduli seed (sandbox, scheduler, evals)."""

from __future__ import annotations

from pathlib import Path

import pytest

from evals import SUITES, SuiteSpec
from roles import load_roles_config
from sandbox import run_python
from scheduler import Job, NodeQueue

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_roles_reali():
    roles = load_roles_config(REPO_ROOT / "config" / "roles.yaml")
    assert {"planner", "worker", "verifier", "reviewer", "router", "edge"} <= set(roles)
    # temperatura ereditata dai prompt metodo-di-riferimento (docs/reference-metodo-di-riferimento.md §2)
    assert roles["planner"].temperature == 0.3
    assert roles["router"].temperature == 0.0
    assert roles["worker"].temperature == 0.2


def test_roles_temperatura_fuori_range(tmp_path):
    bad = tmp_path / "roles.yaml"
    bad.write_text("roles:\n  x:\n    temperature: 9\n")
    with pytest.raises(ValueError, match="non valida"):
        load_roles_config(bad)


def test_sandbox_run_python_ok():
    r = run_python("print(6*7)")
    assert r.ok and r.stdout.strip() == "42" and not r.timed_out


def test_sandbox_run_python_errore():
    r = run_python("raise ValueError('boom')")
    assert not r.ok and "boom" in r.stderr


def test_sandbox_timeout():
    r = run_python("import time; time.sleep(5)", timeout=0.5)
    assert r.timed_out and not r.ok


def test_scheduler_scheletro():
    job = Job(task_id="t1", role="worker")
    q = NodeQueue(node="mid", concurrency=1, pending=[job])
    assert q.can_start()
    q.in_flight = 1
    assert not q.can_start()


def test_evals_registro_vuoto_ma_tipizzato():
    assert isinstance(SUITES, dict)
    spec = SuiteSpec(name="x", description="d", modes=("single",))
    assert spec.modes == ("single",)
