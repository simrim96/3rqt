"""Unit test del calibratore che non toccano la rete."""

from pathlib import Path

from nodes.calibrate import save_report


def _rep(node: str, measures: dict) -> dict:
    return {"node": node, "date": "d1", "measures": measures}


def test_save_report_fonde_misure_di_corse_parciali(tmp_path: Path) -> None:
    """Una corsa con --skip non deve cancellare le misure del report esistente."""
    save_report(_rep("n1", {"stream": {"tokens_per_s": 10}}), tmp_path)
    save_report(_rep("n1", {"mini_eval": {"n": 40, "correct": 30}}), tmp_path)
    import json

    data = json.loads((tmp_path / "n1.json").read_text(encoding="utf-8"))
    assert set(data["measures"]) == {"stream", "mini_eval"}


def test_save_report_non_fonde_nodi_diversi(tmp_path: Path) -> None:
    save_report(_rep("a", {"stream": {}}), tmp_path)
    save_report(_rep("b", {"mini_eval": {}}), tmp_path)
    import json

    a = json.loads((tmp_path / "a.json").read_text(encoding="utf-8"))
    b = json.loads((tmp_path / "b.json").read_text(encoding="utf-8"))
    assert set(a["measures"]) == {"stream"}
    assert set(b["measures"]) == {"mini_eval"}


def test_save_report_sopravvive_a_json_corrotto(tmp_path: Path) -> None:
    (tmp_path / "n1.json").write_text("{non-json", encoding="utf-8")
    save_report(_rep("n1", {"stream": {"x": 1}}), tmp_path)
    import json

    data = json.loads((tmp_path / "n1.json").read_text(encoding="utf-8"))
    assert data["measures"] == {"stream": {"x": 1}}
