"""Esecuzione in sandbox e correzione per famiglia (PLAN §3 Fase 2).

Sandbox dei task verificabili: sottoprocesso Python isolato (``python -I``,
cwd in directory temporanea, ambiente ripulito da variabili sensibili,
RLIMIT_AS/NPROC/FSIZE posti nel figlio prima dell'esecuzione) con timeout
duro (kill del gruppo). Non e' una jail completa: gli item sono task puri
stdlib senza rete richiesta; il limite documentato e' "il codice generato non
puo' scrivere fuori dalla tmpdir ne' eccedere memoria/CPU".

Correzione:
- verificabili: tutti i test stdin/stdout devono passare (match esatto su
  output stripato);
- semi: l'ultima riga-JSON deve rispettare lo schema e canonizzarsi in uno
  dei golden;
- aperti: rubrica fissa, giudice DIVERSO dal generatore, punteggio
  sommativo, risultato marcato low_confidence.
"""

from __future__ import annotations

import contextlib
import json
import os
import signal
import subprocess
import sys
import tempfile
from typing import Any

from .answer import extract_code_block, extract_final_line, match_row
from .suite import OpenItem, SemiItem, VerifItem

#: memoria max del processo modello (byte) e limiti collaterali
SANDBOX_MEM_BYTES = 1024 * 1024 * 1024
SANDBOX_NPROC = 64
SANDBOX_FSIZE_BLOCKS = 8192  # 4 MB

_HARNESS = """
import resource, runpy, sys
for _lim, _val in (
    (resource.RLIMIT_AS, ({mem}, {mem})),
    (resource.RLIMIT_NPROC, ({nproc}, {nproc})),
    (resource.RLIMIT_FSIZE, ({fsize}, {fsize})),
):
    try:
        resource.setrlimit(_lim, _val)
    except (ValueError, OSError):
        pass
runpy.run_path("harness.py", run_name="__main__")
"""

_RUNNER = """
import os, sys
sys.path.insert(0, os.getcwd())
sys.setrecursionlimit(30000)
from solution import solve
data = sys.stdin.read()
result = solve(data)
sys.stdout.write(result if isinstance(result, str) else str(result))
sys.stdout.write("\\n")
"""


def run_solution(
    code: str,
    stdin: str,
    *,
    timeout_s: float = 10.0,
    python_exe: str | None = None,
) -> dict[str, Any]:
    """Esegue ``code`` (che definisce ``solve``) in sandbox. Non solleva per
    errori del codice: ogni fallimento e' un returncode != 0 nel risultato."""
    with tempfile.TemporaryDirectory(prefix="evalsb-") as tmp:
        tmp_path = os.path.realpath(tmp)
        with open(os.path.join(tmp_path, "solution.py"), "w", encoding="utf-8") as fh:
            fh.write(code)
        with open(os.path.join(tmp_path, "harness.py"), "w", encoding="utf-8") as fh:
            fh.write(_RUNNER)
        with open(os.path.join(tmp_path, "run_sandboxed.py"), "w", encoding="utf-8") as fh:
            fh.write(
                _HARNESS.format(
                    mem=SANDBOX_MEM_BYTES, nproc=SANDBOX_NPROC, fsize=SANDBOX_FSIZE_BLOCKS
                )
            )
        env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": tmp_path,
            "TMPDIR": tmp_path,
            "LANG": "C.UTF-8",
            "PYTHONIOENCODING": "utf-8",
        }
        argv = [python_exe or sys.executable, "-I", "run_sandboxed.py"]
        try:
            proc = subprocess.run(
                argv,
                input=stdin,
                capture_output=True,
                text=True,
                timeout=timeout_s,
                cwd=tmp_path,
                env=env,
                start_new_session=True,
            )
            return {
                "returncode": proc.returncode,
                "stdout": proc.stdout,
                "stderr": proc.stderr[-4000:],
                "timed_out": False,
            }
        except subprocess.TimeoutExpired as exc:
            with contextlib.suppress(ProcessLookupError, PermissionError, OSError):
                os.killpg(os.getpgid(exc.__dict__.get("pid") or 0), signal.SIGKILL)
            return {
                "returncode": -1,
                "stdout": str(exc.stdout or ""),
                "stderr": "sandbox timeout",
                "timed_out": True,
            }


def grade_verificabili(item: VerifItem, answer_text: str) -> dict[str, Any]:
    """(pass, dettaglio) con esecuzione di TUTTI i test in sandbox."""
    code = extract_code_block(answer_text)
    if not code.strip():
        return {"pass": False, "reason": "empty_code", "failed_test": None}
    failed = None
    for idx, test in enumerate(item.tests):
        res = run_solution(code, test.stdin, timeout_s=item.timeout_s)
        got = res["stdout"].strip()
        want = test.expected_stdout.strip()
        ok = res["returncode"] == 0 and got == want
        if not ok:
            failed = {
                "test": idx,
                "returncode": res["returncode"],
                "timed_out": res["timed_out"],
                "expected": want[:300],
                "got": got[:300] if res["returncode"] == 0 else res["stderr"][:300],
            }
            break  # criterio: tutti i test; il primo fallimento chiude
    if failed is None:
        return {"pass": True, "reason": None, "failed_test": None}
    return {"pass": False, "reason": "test_failed", "failed_test": failed}


def grade_semi(item: SemiItem, answer_text: str) -> dict[str, Any]:
    row, err = extract_final_line(answer_text)
    if row is None:
        return {"pass": False, "reason": err, "canonical": ""}
    goldens = {g.strip() for g in item.golden}
    passed, canon, why = match_row(row, item.row_schema, goldens)
    return {"pass": passed, "reason": why, "canonical": canon}


_JUDGE_SYSTEM = (
    "Sei un giudice spietatamente rigoroso di valutazione automatica. Valuti la "
    "risposta del candidato rispetto alla rubrica indicata, criterio per criterio. "
    "Per ogni criterio assegna un intero tra 0 e i punti massimi: 0 = non "
    "soddisfatto, massimo = pienamente e verificabilmente soddisfatto, in mezzo = "
    "parziale. Non premiare la verbosita'. Non fidarti delle affermazioni della "
    "risposta: valuta solo il contenuto concretamente prodotto. NON conoscere i "
    "fatti di dominio pubblico citati NON e' un difetto se la risposta e' coerente "
    "e autoverificabile. Ripeti alla fine, ultima riga, SOLO un oggetto JSON: "
    '{{"scores": {{"<id_criterio>": punti, ...}}}} con tutte e sole le chiavi '
    "della rubrica."
)


def build_judge_prompt(item: OpenItem, answer_text: str) -> tuple[str, str]:
    rubrica = "\n".join(f'- "{c.id}" ({c.points} punti): {c.criterion}' for c in item.rubric)
    user = (
        f"DOMANDA ORIGINALE:\n{item.prompt}\n\n"
        f"RISPOSTA DEL CANDIDATO:\n{(answer_text or '').strip()[:6000]}\n\n"
        f"RUBRICA (id: criterio — punti massimi):\n{rubrica}\n\n"
        'Assegna i punteggi e chiudi con l\'ultima riga {"scores": {...}}.'
    )
    return _JUDGE_SYSTEM, user


def parse_judge(item: OpenItem, judge_text: str) -> tuple[dict[str, int] | None, str | None]:
    """Estrae i punteggi dall'ultima riga JSON con la chiave 'scores'."""
    lines = [ln.strip() for ln in (judge_text or "").splitlines() if ln.strip()]
    for line in reversed(lines):
        if line.startswith("```"):
            continue
        try:
            obj = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(obj, dict) and isinstance(obj.get("scores"), dict):
            scores = obj["scores"]
            expected = {c.id: c.points for c in item.rubric}
            if set(scores) != set(expected):
                return None, f"judge_scores_keys:{sorted(scores)}"
            clean = {}
            for k, v in scores.items():
                if not isinstance(v, int) or isinstance(v, bool) or not (0 <= v <= expected[k]):
                    return None, f"judge_score_out_of_range:{k}={v!r}"
                clean[k] = v
            return clean, None
    return None, "judge_no_scores_line"


def grade_aperti(item: OpenItem, judge_text: str) -> dict[str, Any]:
    scores, err = parse_judge(item, judge_text)
    if scores is None:
        return {"pass": None, "reason": err, "score": None, "max_points": item.max_points}
    score = sum(scores.values())
    threshold = item.pass_fraction * item.max_points
    return {
        "pass": score >= threshold - 1e-9,
        "reason": None,
        "score": score,
        "max_points": item.max_points,
        "criterion_scores": scores,
        "threshold": threshold,
        "low_confidence": True,
    }


__all__ = [
    "build_judge_prompt",
    "grade_aperti",
    "grade_semi",
    "grade_verificabili",
    "parse_judge",
    "run_solution",
]
