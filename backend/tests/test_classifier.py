"""homedms/ai/classifier.py - Entscheidungsregeln der Klassifikation (Anforderungsdokument 4.3)."""
import uuid

import pytest

from homedms.ai.classifier import (
    NO_CATEGORY,
    CategoryScore,
    LlmAnswer,
    accept_llm,
    build_prompt,
    decide_stage1,
    parse_llm_answer,
    thresholds_for,
)

A, B, C = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
T = thresholds_for("normal")  # 85 % / 65 % / Abstand 15 / LLM 80 % / 5 Beispiele


def score(cat, sim, n=10):
    return CategoryScore(cat, sim, n)


def test_thresholds_follow_caution_level():
    v, n, m = thresholds_for("vorsichtig"), thresholds_for("normal"), thresholds_for("mutig")
    assert v.auto_similarity > n.auto_similarity > m.auto_similarity
    assert v.llm_confidence > n.llm_confidence > m.llm_confidence
    assert (n.auto_similarity, n.min_similarity, n.margin, n.llm_confidence) == (0.85, 0.65, 0.15, 0.80)
    assert thresholds_for("unbekannt") == thresholds_for("normal")
    assert thresholds_for("normal", min_exemplars=3).min_exemplars == 3


def test_no_exemplars_goes_to_llm():
    d = decide_stage1([], T)
    assert not d.assigned and d.similarity is None
    assert not decide_stage1([score(A, 0.99, n=0)], T).assigned


def test_high_similarity_assigns_directly():
    d = decide_stage1([score(A, 0.91), score(B, 0.88)], T)
    assert d.assigned and d.category_id == A and d.similarity == pytest.approx(0.91)


def test_too_few_exemplars_goes_to_llm_even_if_similar():
    d = decide_stage1([score(A, 0.97, n=4)], T)
    assert not d.assigned and "4 von 5" in d.reason


def test_clear_margin_in_grey_zone_assigns():
    # 75 % liegt im Graubereich, aber 20 Punkte vor der zweitbesten Kategorie
    d = decide_stage1([score(A, 0.75), score(B, 0.55)], T)
    assert d.assigned and d.category_id == A


def test_small_margin_in_grey_zone_goes_to_llm():
    d = decide_stage1([score(A, 0.75), score(B, 0.70)], T)
    assert not d.assigned and "nicht eindeutig" in d.reason


def test_margin_rule_needs_a_second_trained_category():
    # Nur eine Kategorie hat Beispiele: kein "Abstand" ableitbar -> nicht blind zuweisen
    d = decide_stage1([score(A, 0.75), score(B, 0.0, n=0)], T)
    assert not d.assigned


def test_low_similarity_goes_to_llm_even_with_margin():
    d = decide_stage1([score(A, 0.60), score(B, 0.20)], T)
    assert not d.assigned and "zu gering" in d.reason


def test_prompt_lists_categories_and_restricts_answer():
    system, user, schema = build_prompt([("Rechnungen", "Zahlungen"), ("Sonstiges", "")], "Text " * 2000, max_chars=100)
    assert "- Rechnungen: Zahlungen" in user and "- Sonstiges" in user
    assert schema["properties"]["kategorie"]["enum"] == ["Rechnungen", "Sonstiges", NO_CATEGORY]
    assert len(user) < 1000  # Dokumenttext wird gekuerzt
    assert "JSON" in system


@pytest.mark.parametrize(
    "answer,expected_id,expected_conf",
    [
        ({"kategorie": "Rechnungen", "konfidenz": 0.9}, A, 0.9),
        ({"kategorie": "rechnungen", "konfidenz": 0.9}, A, 0.9),  # Schreibweise tolerieren
        ({"kategorie": "Rechnungen", "konfidenz": 87}, A, 0.87),  # Prozentangabe
        ({"kategorie": "Rechnungen", "konfidenz": "abc"}, A, 0.0),
        ({"kategorie": "Rechnungen", "konfidenz": -1}, A, 0.0),
        ({"kategorie": NO_CATEGORY, "konfidenz": 0.9}, None, 0.9),
        ({"kategorie": "Erfunden", "konfidenz": 0.9}, None, 0.9),
        ({}, None, 0.0),
    ],
)
def test_parse_llm_answer(answer, expected_id, expected_conf):
    parsed = parse_llm_answer(answer, {"Rechnungen": A, "Verträge": B})
    assert parsed.category_id == expected_id
    assert parsed.confidence == pytest.approx(expected_conf)


def test_accept_llm_needs_category_and_confidence():
    assert accept_llm(LlmAnswer(A, "X", 0.80, ""), T)
    assert not accept_llm(LlmAnswer(A, "X", 0.79, ""), T)
    assert not accept_llm(LlmAnswer(None, None, 0.99, ""), T)


def test_prompt_erst_beschreiben_dann_entscheiden():
    """Kleine Modelle erzeugen die JSON-Felder in Schema-Reihenfolge - dokumentart und bezug
    muessen VOR kategorie stehen, damit die Entscheidung darauf aufbaut."""
    from homedms.ai.classifier import build_prompt, parse_llm_answer

    _, user, schema = build_prompt([("Haus & Reparaturen", "Handwerker am Haus"), ("Fahrzeug", "Kfz")], "Text")
    keys = list(schema["properties"])
    assert keys.index("dokumentart") < keys.index("kategorie")
    assert keys.index("bezug") < keys.index("kategorie")
    assert "worauf" in user.lower()

    import uuid as _uuid

    cid = _uuid.uuid4()
    answer = parse_llm_answer(
        {"dokumentart": "Rechnung", "bezug": "Wohnung", "kategorie": "Haus & Reparaturen", "konfidenz": 0.9,
         "begruendung": "Handwerker"},
        {"Haus & Reparaturen": cid},
    )
    assert answer.category_id == cid
    assert answer.reason.startswith("Art: Rechnung, Bezug: Wohnung.")


def test_aehnlichkeit_je_kategorie_ohne_pgvector():
    """Stufe 1 rechnet die Kosinus-Aehnlichkeit selbst (alembic 0010) - beste je Kategorie + Anzahl."""
    import uuid

    from homedms.tasks.classification import category_scores

    strom, kfz = uuid.uuid4(), uuid.uuid4()
    scores = {s.category_id: s for s in category_scores(
        [1.0, 0.0, 0.0],
        [(strom, [2.0, 0.0, 0.0]), (strom, [0.0, 1.0, 0.0]), (kfz, [1.0, 1.0, 0.0]), (kfz, [0.0, 0.0, 0.0])],
    )}
    assert scores[strom].similarity == pytest.approx(1.0) and scores[strom].exemplar_count == 2
    assert scores[kfz].similarity == pytest.approx(2 ** -0.5) and scores[kfz].exemplar_count == 2
    assert category_scores([1.0, 0.0], []) == []
