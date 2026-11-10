"""Suite di valutazione versionate (PLAN §3 Fase 2).

Tre famiglie di item, un formato per famiglia:

- ``verificabili``: problemi di programmazione con test stdin/stdout (stile
  LiveCodeBench) eseguiti in sandbox subprocess con timeout; il modello deve
  fornire ``def solve(data: str) -> str``.
- ``semi``: estrazione/trasformazione/query; il vincolo "una riga" e' la
  serializzazione canonica del golden (chiavi ordinate, senza spazi) e i campi
  con ``"any_of"`` accettano una delle alternative equivalenti.
- ``aperti``: scrittura/analisi/ricerca con rubrica fissa; il giudice e' un
  modello DIVERSO dal generatore e il risultato e' marcato low_confidence.

Le suite vivono in ``src/evals/suites/<nome>/items.json`` + ``golden/`` e sono
content-addressed: la versione include l'hash sha256 del contenuto, cosi' un
risultato e' sempre riconducibile ai dati esatti che lo hanno prodotto.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SUITE_KINDS = ("verificabili", "semi", "aperti")

_DEFAULT_SUITES_ROOT = Path(__file__).resolve().parent / "suites"


class TestCase(BaseModel):
    stdin: str
    expected_stdout: str


class VerifItem(BaseModel):
    kind: Literal["verificabili"] = "verificabili"
    id: str
    category: str
    difficulty: Literal["easy", "medium", "hard"] = "easy"
    prompt: str
    tests: list[TestCase] = Field(min_length=2)
    timeout_s: float = Field(default=10.0, gt=0, le=60)

    def build_prompt(self) -> str:
        return self.prompt


class SemiItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    kind: Literal["semi"] = "semi"
    id: str
    category: Literal["estrazione", "trasformazione", "query"]
    difficulty: Literal["easy", "medium", "hard"] = "easy"
    #: il segnaposto {data} viene sostituito dal loader con data_inline
    prompt: str
    data_file: str | None = None
    data_inline: str | None = None
    #: schema JSON del vincolo "una riga": object con type object e property;
    #: ogni property e' {type, enum?, any_of?, default?} con type in
    #: string|integer|number|boolean|null (pipe ammesse)
    row_schema: dict[str, Any] = Field(alias="schema")
    #: golden canonico: una o piu' righe valide (alternative d'esame)
    golden: list[str] = Field(min_length=1)

    def build_prompt(self) -> str:
        if "{data}" in self.prompt:
            if self.data_inline is None:
                raise ValueError(f"item {self.id}: {{{{data}}}} presente ma data_inline mancante")
            return self.prompt.replace("{data}", self.data_inline)
        return self.prompt


class RubricCriterion(BaseModel):
    id: str
    criterion: str
    points: int = Field(default=2, ge=1, le=5)


class OpenItem(BaseModel):
    kind: Literal["aperti"] = "aperti"
    id: str
    category: Literal["scrittura", "analisi", "ricerca"]
    difficulty: Literal["easy", "medium", "hard"] = "medium"
    prompt: str
    rubric: list[RubricCriterion] = Field(min_length=3)
    #: frazione di punti per contare l'item come "pass" (misura, non verita)
    pass_fraction: float = Field(default=0.75, gt=0, le=1)

    @model_validator(mode="after")
    def _ids_unic(self) -> OpenItem:
        ids = [c.id for c in self.rubric]
        if len(ids) != len(set(ids)):
            raise ValueError(f"item {self.id}: id criterio duplicati nella rubrica")
        return self

    @property
    def max_points(self) -> int:
        return sum(c.points for c in self.rubric)

    def build_prompt(self) -> str:
        return self.prompt


Item = Annotated[VerifItem | SemiItem | OpenItem, Field(discriminator="kind")]


class Suite(BaseModel):
    name: str
    version: str
    description: str = ""
    gen_system: str
    items: list[Item] = Field(min_length=1)
    #: hash del contenuto su disco, popolato dal loader
    content_hash: str = ""

    @property
    def kind(self) -> str:
        return self.name

    def item_ids(self) -> list[str]:
        return [i.id for i in self.items]

    def by_id(self, item_id: str) -> Item:
        for it in self.items:
            if it.id == item_id:
                return it
        raise KeyError(item_id)


def _read_tree_hash(base: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(base.rglob("*")):
        if p.is_file():
            h.update(str(p.relative_to(base)).encode())
            h.update(p.read_bytes())
    return h.hexdigest()[:16]


_ITEM_MODEL = {"verificabili": VerifItem, "semi": SemiItem, "aperti": OpenItem}


def load_suite(
    name: str,
    *,
    suites_root: str | Path | None = None,
    resolve_data: bool = True,
) -> Suite:
    """Carica ``<root>/<name>/items.json`` validando gli item col modello
    della famiglia; i ``data_file`` sono relativi alla directory della suite
    e diventano ``data_inline``."""
    if name not in SUITE_KINDS:
        raise ValueError(f"suite {name!r} inesistente: note {list(SUITE_KINDS)}")
    root = Path(suites_root) if suites_root else _DEFAULT_SUITES_ROOT
    base = root / name
    raw = json.loads((base / "items.json").read_text(encoding="utf-8"))
    if raw.get("name") != name:
        raise ValueError(f"{base / 'items.json'}: name={raw.get('name')!r} != {name!r}")
    model = _ITEM_MODEL[name]
    items = []
    for it in raw.get("items", []):
        if resolve_data and it.get("data_file"):
            it["data_inline"] = (base / it["data_file"]).read_text(encoding="utf-8")
        items.append(model.model_validate(it))
    suite = Suite.model_validate({**raw, "items": items})
    ids = suite.item_ids()
    if len(ids) != len(set(ids)):
        raise ValueError(f"suite {name}: id item duplicati")
    suite.content_hash = _read_tree_hash(base)
    return suite


def load_all_suites(*, suites_root: str | Path | None = None) -> dict[str, Suite]:
    return {n: load_suite(n, suites_root=suites_root) for n in SUITE_KINDS}


def suite_version(suite: Suite) -> str:
    """Versione content-addressed: <nome>-<version>-<hash16>."""
    return f"{suite.name}-{suite.version}-{suite.content_hash}"


__all__ = [
    "Item",
    "OpenItem",
    "RubricCriterion",
    "SUITE_KINDS",
    "SemiItem",
    "Suite",
    "TestCase",
    "VerifItem",
    "load_all_suites",
    "load_suite",
    "suite_version",
]
