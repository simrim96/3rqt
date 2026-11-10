"""Confronto riproducibilità live: due dir di run a stesso seed -> stesse righe
a meno del solo tempo."""

import json
import os
import sys
from pathlib import Path


def run_dir(root: str) -> Path:
    return next(p for p in Path(root).iterdir() if p.name.startswith("2026"))


def rows(d: Path):
    return [
        (r["item"], r["sample"], r["pass"], r["total_tokens"], r["answer_sha"])
        for r in map(json.loads, (d / "results.jsonl").read_text().splitlines())
    ]


def norm(d: Path):
    out = []
    for line in (d / "summary.md").read_text().splitlines():
        if line.startswith("| ") and "±" in line:
            p = line.split("|")
            p[7] = " X "
            line = "|".join(p)
        out.append(line)
    return out


a = run_dir(sys.argv[1])
b = run_dir(sys.argv[2])
print("TABLE_EQUAL:", norm(a) == norm(b))
ra, rb = rows(a), rows(b)
print("ROWS_EQUAL:", ra == rb, "| righe:", len(ra))
print("dir:", a.name, "vs", b.name)
print("sha mismatch:", [x[0] for x, y in zip(ra, rb, strict=True) if x[4] != y[4]][:5])
print(os.getpid())
