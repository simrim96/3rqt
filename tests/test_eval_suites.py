"""Suite di valutazione: schema, golden data, soluzioni di riferimento (Fase 2).

Nodo mock/CI: nessuna chiamata di rete. Le soluzioni di riferimento in
``src/evals/suites/verificabili/solutions/`` devono passare i test in sandbox;
i golden ``semi`` devono canonizzarsi in se stessi; i criteri ``aperti`` e il
parser dei punteggi del giudice sono verificati con testo fisso.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from evals.answer import (
    canonicalize_row,
    extract_code_block,
    extract_final_line,
    match_row,
    validate_row,
)
from evals.grader import (
    build_judge_prompt,
    grade_aperti,
    grade_verificabili,
    parse_judge,
)
from evals.suite import SUITE_KINDS, SemiItem, load_all_suites, load_suite, suite_version

SUITES_DIR = Path(__file__).resolve().parents[1] / "src" / "evals" / "suites"


@pytest.fixture(scope="module")
def suites():
    return load_all_suites()


# ------------------------------------------------------------------ struttura


def test_tre_suites_caricate_con_minimi_suff(suites):
    assert set(suites) == set(SUITE_KINDS)
    assert len(suites["verificabili"].items) >= 20  # richiesta: 20-30 item
    assert len(suites["semi"].items) >= 8
    assert len(suites["aperti"].items) >= 5


def test_id_unici_e_prefissi_coerenti(suites):
    for name, prefix in (
        ("verificabili", "vv_"),
        ("semi", "sv_"),
        ("aperti", "op_"),
    ):
        ids = suites[name].item_ids()
        assert len(ids) == len(set(ids))
        assert all(i.startswith(prefix) for i in ids), (name, ids[:3])


def test_versione_content_addressed(suites):
    for name, s in suites.items():
        assert len(s.content_hash) == 16
        assert suite_version(s) == f"{name}-{s.version}-{s.content_hash}"


def test_verificabili_ogni_item_con_almeno_2_test(suites):
    for it in suites["verificabili"].items:
        assert len(it.tests) >= 2, it.id
        assert 0 < it.timeout_s <= 30, it.id


# ------------------------------------------------- soluzioni di riferimento


def _soluzione(item_id: str) -> str:
    f = SUITES_DIR / "verificabili" / "solutions" / f"{item_id}.py"
    assert f.exists(), f"soluzione di riferimento mancante per {item_id}"
    return f.read_text(encoding="utf-8")


def test_soluzioni_riferimento_passano_tutti_i_test(suites):
    """Ogni item verificabile ha una soluzione golden che passa ogni test in
    sandbox: senza questo, un fallimento del modello non e' distinguibile da
    un golden rotto."""
    for it in suites["verificabili"].items:
        answer = f"Ecco la soluzione:\n```python\n{_soluzione(it.id)}\n```\nfine"
        g = grade_verificabili(it, answer)
        assert g["pass"] is True, (it.id, g["failed_test"])


def test_verificabili_bocciano_risposta_sbagliata(suites):
    it = suites["verificabili"].items[0]
    g = grade_verificabili(it, "```python\ndef solve(data):\n    return 'nope'\n```")
    assert g["pass"] is False
    assert g["reason"] == "test_failed"
    assert g["failed_test"] is not None


def test_verificabili_bocciano_assenza_di_codice(suites):
    it = suites["verificabili"].items[0]
    g = grade_verificabili(it, "non so, non produco codice")
    assert g["pass"] is False
    assert g["reason"] == "empty_code" or g["failed_test"] is not None


# ------------------------------------------------------------------- semi


def test_semi_golden_validi_e_canonici(suites):
    for it in suites["semi"].items:
        goldens = {g.strip() for g in it.golden}
        for gstr in goldens:
            row = json.loads(gstr)  # ogni golden e' JSON object
            assert validate_row(row, it.row_schema) is None, (it.id, gstr)
            canon = canonicalize_row(row, it.row_schema)
            assert canon == gstr, (it.id, canon, gstr)  # i golden sono gia' canonici
            ok, _, _ = match_row(row, it.row_schema, goldens)
            assert ok, it.id


def test_semi_rifiutano_righe_non_conformi(suites):
    for it in suites["semi"].items:
        goldens = {g.strip() for g in it.golden}
        ok, _, why = match_row({"campo_inesistente": 1}, it.row_schema, goldens)
        assert ok is False and why, (it.id, why)


def test_semi_build_prompt_sostituisce_data():
    """Nessun segnaposto {data} residuo nei prompt risolti; il meccanismo
    data_file/data_inline deve comunque funzionare se un item lo usa."""
    suite = load_suite("semi")
    for it in suite.items:
        assert isinstance(it, SemiItem)
        p = it.build_prompt()
        assert p.startswith(it.prompt.split("{data}")[0][:40])
        assert "{data}" not in p


# ----------------------------------------------------------------- aperti


def test_aperti_rubrica_minima(suites):
    for it in suites["aperti"].items:
        assert len(it.rubric) >= 3, it.id
        assert it.max_points >= 3
        assert 0 < it.pass_fraction <= 1
        assert it.category in ("scrittura", "analisi", "ricerca")


def test_build_judge_prompt_contiene_rubrica_e_risposta(suites):
    it = suites["aperti"].items[0]
    sys_p, user_p = build_judge_prompt(it, "RISPOSTA-CANDIDATO-XYZ")
    assert "RUBRICA (id:" in sys_p or "RUBRICA (id:" in user_p
    for c in it.rubric:
        assert c.id in user_p
    assert "RISPOSTA-CANDIDATO-XYZ" in user_p


def test_parse_judge_e_punteggio(suites):
    it = suites["aperti"].items[0]
    pieno = {c.id: c.points for c in it.rubric}
    testo = "Valutazione.\n" + json.dumps({"scores": pieno})
    scores, err = parse_judge(it, testo)
    assert err is None and scores == pieno

    g = grade_aperti(it, testo)
    assert g["pass"] is True and g["score"] == it.max_points
    assert g["low_confidence"] is True

    # chiavi sbagliate / fuori range / assenti
    _, err_keys = parse_judge(it, '{"scores": {"x": 1}}')
    assert err_keys is not None and err_keys.startswith("judge_scores_keys")
    cattivo = {c.id: c.points + 1 for c in it.rubric}
    _, err_range = parse_judge(it, json.dumps({"scores": cattivo}))
    assert err_range is not None and err_range.startswith("judge_score_out")
    assert parse_judge(it, "nessun punteggio qui")[1] == "judge_no_scores_line"


def test_grade_aperti_soglia_pass_fraction(suites):
    it = next(i for i in suites["aperti"].items if i.pass_fraction < 1)
    meta = int(it.max_points * it.pass_fraction)
    # punteggio appena sotto soglia: distribuisci meta-1 punti sui criteri
    punteggi = {c.id: 0 for c in it.rubric}
    rimasti = meta - 1
    for c in it.rubric:
        dai = min(rimasti, c.points)
        punteggi[c.id] = dai
        rimasti -= dai
        if rimasti <= 0:
            break
    assert sum(punteggi.values()) < meta
    g = grade_aperti(it, json.dumps({"scores": punteggi}))
    assert g["pass"] is False
    assert g["score"] == sum(punteggi.values())


# ------------------------------------------------------------ answer.py


def test_extract_code_block_e_fallback():
    assert extract_code_block("x\n```python\nA=1\n```\ny") == "A=1"
    assert extract_code_block("testo nudo") == "testo nudo"
    assert extract_code_block("") == ""


def test_extract_final_line_ultima_riga_vince():
    testo = '{"a": 1}\nriflessione\n{"a": 2}\n'
    row, err = extract_final_line(testo)
    assert err is None and row == {"a": 2}
    row, _ = extract_final_line('Answer: {"a": 3}')
    assert row == {"a": 3}
    assert extract_final_line("[1, 2]")[1] == "last_json_line_not_object"
    assert extract_final_line("niente json")[1] == "no_json_line"


def test_canonicalize_equivalenze():
    schema = {
        "type": "object",
        "properties": {
            "n": {"type": "integer"},
            "v": {"type": "string", "any_of": ["x", "ex"]},
            "d": {"type": "integer", "default": 0},
        },
        "required": ["n"],
        "additionalProperties": False,
    }
    a = canonicalize_row({"v": "ex", "n": 3.0, "d": 0}, schema)
    b = canonicalize_row({"d": 0, "n": 3, "v": "x "}, schema)
    assert a == b == '{"n":3,"v":"x"}'
    assert validate_row({"n": "3"}, schema) == "bad_type:n:expected=integer:got=str"
    assert validate_row({"v": "no"}, schema) == "missing_field:n"
    assert validate_row({"n": 1, "z": 2}, schema) == "extra_fields:['z']"
