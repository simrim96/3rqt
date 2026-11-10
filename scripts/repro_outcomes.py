"""Confronto esiti (pass/score) tra due dir di run, ignorando sha/token/tempo."""

import json
import sys
from pathlib import Path


def run_dir(root: str) -> Path:
    return next(p for p in Path(root).iterdir() if p.name.startswith("2026"))


def outcomes(d: Path):
    return [
        (r["item"], r["sample"], r["pass"], r["score"])
        for r in map(json.loads, (d / "results.jsonl").read_text().splitlines())
    ]


a = run_dir(sys.argv[1])
b = run_dir(sys.argv[2])
oa, ob = sorted(outcomes(a)), sorted(outcomes(b))
print("OUTCOMES_EQUAL:", oa == ob, "| righe:", len(oa))
diff = [(x, y) for x, y in zip(oa, ob, strict=True) if x != y]
print("diff:", diff[:6])


def shas(d: Path):
    return sorted(
        (r["item"], r["sample"], r["answer_sha"], r["total_tokens"])
        for r in map(json.loads, (d / "results.jsonl").read_text().splitlines())
    )


print("SHA_TOKENS_EQUAL:", shas(a) == shas(b))
