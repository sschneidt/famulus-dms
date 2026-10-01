"""Hilfsfunktionen der Volltextsuche (homedms/core/search.py)."""
from homedms.core.search import (
    HL_POST,
    HL_PRE,
    Segment,
    clean_text,
    has_hit,
    like_pattern,
    search_terms,
    segments_from_marked,
    snippet_for_terms,
)


def test_search_terms():
    assert search_terms("Wasserschaden  Bad") == ["wasserschaden", "bad"]
    assert search_terms("a, Rechnung rechnung!") == ["rechnung"]
    assert search_terms("S-AB 123") == ["s-ab", "123"]
    assert len(search_terms(" ".join(f"wort{i}" for i in range(20)))) == 8


def test_like_pattern_nimmt_platzhalter_woertlich():
    assert like_pattern("100%") == "%100\\%%"
    assert like_pattern("a_b") == "%a\\_b%"


def test_segments_from_marked():
    text = f"Reparatur des {HL_PRE}Wasserschade{HL_POST}ns im\nBad"
    assert segments_from_marked(text) == [
        Segment("Reparatur des ", False), Segment("Wasserschade", True), Segment("ns im Bad", False),
    ]
    assert not has_hit(segments_from_marked("ohne Treffer"))
    assert segments_from_marked("") == []


def test_snippet_teilwort_mit_markierung():
    text = "Sanitär Müller GmbH\n" + "Füllwort " * 40 + "Reparatur des Wasserschadens im Bad. " + "Ende " * 40
    segments = snippet_for_terms(text, ["schaden"])
    assert has_hit(segments)
    hits = [s.text for s in segments if s.hit]
    assert hits == ["schaden"]
    joined = "".join(s.text for s in segments)
    assert joined.startswith("… ") and joined.endswith(" …")
    assert "Wasserschadens" in joined
    assert "\n" not in joined
    assert len(joined) < 260


def test_snippet_gross_klein_und_mehrere_woerter():
    segments = snippet_for_terms("Die STROMRECHNUNG der Stadtwerke", ["stromrechnung", "stadtwerke"])
    assert [s.text for s in segments if s.hit] == ["STROMRECHNUNG", "Stadtwerke"]
    assert snippet_for_terms("kein Treffer", ["xyz"]) == []
    assert snippet_for_terms("", ["a"]) == []


def test_clean_text_entfernt_markierungszeichen():
    assert HL_PRE not in clean_text(f"a{HL_PRE}b{HL_POST}c")
    assert clean_text(None) == ""
