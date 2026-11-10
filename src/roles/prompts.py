"""Prompt dei ruoli planner/worker del ciclo deep (Fase 3).

Nessun nome di modello nel codice (PLAN §0.2). I prompt sono contratti di
formato: il parser in cycle.py si aspetta esattamente le sezioni dichiarate.
"""

from __future__ import annotations

PLANNER_SYSTEM = (
    "Sei il PIANIFICATORE di un piccolo team di agenti che coordinano il lavoro solo "
    "tramite un ledger condiviso (piano e note). Tu non scrivi codice né soluzioni. "
    "Rispondi ESATTAMENTE con due sezioni markdown:\n"
    "### PLAN\nstrategia in 3-6 frasi.\n"
    "### TASKS\nun sotto-task per riga, ognuno inizia con '- ' (da 2 a 5, "
    "ordinati per esecuzione)."
)

# NB: non contiene la stringa esatta "ESITO VERIFICA" usata come marcatore del
# blocco di feedback: i mock e i test la usano per distinguere worker con e
# senza feedback.
WORKER_SYSTEM_TAIL = (
    "Sei un LAVORATORE del team: ricevi UN solo sotto-task del piano e lo esegui "
    "per intero in contesto fresco (vedi solo il ledger: piano, note dei "
    "colleghi, soluzione attuale, esito dell'ultima verifica). Rispondi "
    "ESATTAMENTE con tre sezioni markdown:\n"
    "### SOLUTION\nla SOLUZIONE COMPLETA (per codice: un unico blocco ```python "
    "completo ed eseguibile).\n"
    "### NOTES\n3-6 frasi: scelte fatte, difficoltà, prove; varrà solo l'ultima "
    "versione che scrivi.\n"
    "### STATUS\nuna parola: solved oppure continue"
)


def planner_user(task: str) -> str:
    return f"PIANIFICA.\n\nTASK:\n{task}"


def replanner_user(task: str, plan: str, feedback: str) -> str:
    return (
        "PIANIFICA (ri-pianificazione dopo verifica fallita).\n\n"
        f"FEEDBACK DALLA VERIFICA:\n{feedback}\n\n"
        f"PIANO ATTUALE:\n{plan}\n\n"
        f"TASK:\n{task}"
    )


def worker_user(
    *,
    task: str,
    plan: str,
    notes: str,
    subtask_idx: int,
    n_subtasks: int,
    subtask: str,
    solution: str,
    feedback: str | None,
) -> str:
    parts = [
        f"ESEGUI il sotto-task {subtask_idx + 1}/{n_subtasks}: {subtask}",
        f"TASK ORIGINALE:\n{task}",
        f"PIANO DEL TEAM:\n{plan}",
    ]
    if notes:
        parts.append(f"NOTE DEL TEAM:\n{notes}")
    if solution:
        parts.append(f"SOLUZIONE ATTUALE:\n{solution}")
    if feedback:
        parts.append(f"ESITO VERIFICA (verità di programma, correggi proprio questo):\n{feedback}")
    return "\n\n".join(parts)


FAST_SYSTEM = "Rispondi in modo completo, corretto e diretto al task."

__all__ = [
    "FAST_SYSTEM",
    "PLANNER_SYSTEM",
    "WORKER_SYSTEM_TAIL",
    "planner_user",
    "replanner_user",
    "worker_user",
]
