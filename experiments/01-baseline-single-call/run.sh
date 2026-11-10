#!/usr/bin/env bash
# Riproduce la baseline single-call Fase 2 (richiede heavy+mid accesi).
# Stessi seed/parametri -> stesse righe (vedi experiments/reproducibility-check.md).
set -euo pipefail
cd "$(dirname "$0")/../.."
for suite in verificabili semi aperti; do
  for node in heavy mid; do
    uv run harness eval --suite "$suite" --mode single --nodes "$node" \
      --samples 3 --seed 1234
  done
done
uv run python scripts/summarize_fase2.py
