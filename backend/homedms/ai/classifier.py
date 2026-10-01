"""Entscheidungslogik der zweistufigen Klassifikation (Anforderungsdokument 4.3).

Reine Funktionen ohne Datenbank und ohne Sprachmodell - dadurch einzeln testbar
(tests/test_classifier.py). Den Ablauf mit Datenbank und Ollama steuert
homedms/tasks/classification.py.

Stufe 1 (Embedding): Der Text wird mit den bestaetigten Beispiel-Dokumenten ("Exemplaren") jeder
Kategorie verglichen. Ist die beste Kategorie eindeutig, wird sie ohne Sprachmodell zugewiesen.
Stufe 2 (LLM): sonst entscheidet das lokale Sprachmodell. Ist auch das unsicher, landet das
Dokument im Feedback-Loop ("needs_review").
"""
import uuid
from dataclasses import dataclass
from typing import Any

NO_CATEGORY = "KEINE"


@dataclass(frozen=True)
class Thresholds:
    auto_similarity: float  # ab dieser Aehnlichkeit weist Stufe 1 direkt zu
    min_similarity: float  # darunter gilt Stufe 1 als "keine brauchbare Aehnlichkeit"
    margin: float  # ...oder: so viel Abstand zur zweitbesten Kategorie (bei >= min_similarity)
    llm_confidence: float  # Mindest-Konfidenz, damit die Antwort des Sprachmodells uebernommen wird
    min_exemplars: int  # erst ab so vielen Beispielen einer Kategorie traut man Stufe 1


# Startwerte laut Anforderungsdokument 4.3 ("normal"); ein Regler statt Einzelwerten.
# Muessen an echten Dokumenten kalibriert werden (Anforderungsdokument 7).
_LEVELS = {
    "vorsichtig": dict(auto_similarity=0.90, min_similarity=0.70, margin=0.20, llm_confidence=0.85),
    "normal": dict(auto_similarity=0.85, min_similarity=0.65, margin=0.15, llm_confidence=0.80),
    "mutig": dict(auto_similarity=0.80, min_similarity=0.60, margin=0.10, llm_confidence=0.75),
}


def thresholds_for(caution_level: str, min_exemplars: int = 5) -> Thresholds:
    return Thresholds(**_LEVELS.get(caution_level, _LEVELS["normal"]), min_exemplars=min_exemplars)


@dataclass(frozen=True)
class CategoryScore:
    category_id: uuid.UUID
    similarity: float  # hoechste Kosinus-Aehnlichkeit zu einem Exemplar dieser Kategorie (0..1)
    exemplar_count: int


@dataclass(frozen=True)
class Stage1Decision:
    category_id: uuid.UUID | None  # gesetzt = direkt zuweisen, sonst weiter zu Stufe 2
    similarity: float | None
    reason: str

    @property
    def assigned(self) -> bool:
        return self.category_id is not None


def decide_stage1(scores: list[CategoryScore], t: Thresholds) -> Stage1Decision:
    ranked = sorted((s for s in scores if s.exemplar_count > 0), key=lambda s: s.similarity, reverse=True)
    if not ranked:
        return Stage1Decision(None, None, "Noch keine Beispiel-Dokumente vorhanden")

    best = ranked[0]
    sim = best.similarity
    if best.exemplar_count < t.min_exemplars:
        return Stage1Decision(
            None, sim, f"Beste Kategorie hat erst {best.exemplar_count} von {t.min_exemplars} Beispielen"
        )
    if sim >= t.auto_similarity:
        return Stage1Decision(best.category_id, sim, f"Aehnlichkeit {sim:.0%} zu bestaetigten Beispielen")

    # Abstand zur zweitbesten Kategorie zaehlt nur, wenn es eine zweite trainierte Kategorie gibt -
    # sonst wuerde anfangs jedes Dokument in die einzige trainierte Kategorie rutschen.
    if len(ranked) >= 2 and sim >= t.min_similarity:
        margin = sim - ranked[1].similarity
        if margin >= t.margin:
            return Stage1Decision(
                best.category_id, sim, f"Aehnlichkeit {sim:.0%}, deutlicher Abstand ({margin:.0%}) zur naechsten Kategorie"
            )
    if sim >= t.min_similarity:
        return Stage1Decision(None, sim, f"Aehnlichkeit {sim:.0%} nicht eindeutig - Sprachmodell entscheidet")
    return Stage1Decision(None, sim, f"Aehnlichkeit {sim:.0%} zu gering - Sprachmodell entscheidet")


# --- Stufe 2: Sprachmodell --------------------------------------------------------------------

SYSTEM_PROMPT = (
    "Du ordnest Dokumente eines Privathaushalts genau einer Kategorie zu. "
    "Antworte ausschliesslich mit JSON im vorgegebenen Format."
)


def build_prompt(categories: list[tuple[str, str]], text: str, max_chars: int = 3000) -> tuple[str, str, dict]:
    """Liefert (system, user, json_schema). categories = [(name, beschreibung), ...]."""
    lines = [f"- {name}: {desc}" if desc else f"- {name}" for name, desc in categories]
    # Erst beschreiben, dann entscheiden: Die Felder dokumentart und bezug stehen im Schema VOR
    # kategorie - das Modell erzeugt sie zuerst und stuetzt die Wahl darauf. Kleine Modelle springen
    # sonst auf einzelne Stichwoerter an (Praxisfall: "Reparatur" im Text einer Handwerker-Rechnung
    # zum Wasserschaden -> "Fahrzeug", weil dort "Werkstattrechnungen" steht).
    user = (
        "Kategorien:\n" + "\n".join(lines) + "\n\n"
        f"Dokumenttext (Auszug):\n\"\"\"\n{text[:max_chars]}\n\"\"\"\n\n"
        "Gehe in dieser Reihenfolge vor:\n"
        "1. dokumentart: Was fuer ein Dokument ist das (z. B. Rechnung, Vertrag, Bescheid, Brief)?\n"
        "2. bezug: Worauf bezieht es sich - Haus/Wohnung, Fahrzeug, Person, Arbeit, Geld, Behoerde ...?\n"
        "3. kategorie: die Kategorie, deren Beschreibung zu Dokumentart UND Bezug passt. Einzelne "
        "Stichwoerter wie \"Reparatur\" oder \"Rechnung\" reichen nicht - entscheidend ist, worauf "
        f'sich das Dokument bezieht. Wenn wirklich keine passt: "{NO_CATEGORY}".\n'
        "4. konfidenz: wie sicher du dir bist, als Zahl von 0 bis 1.\n"
        "5. begruendung: ein kurzer Satz."
    )
    schema = {
        "type": "object",
        "properties": {
            "dokumentart": {"type": "string"},
            "bezug": {"type": "string"},
            "kategorie": {"type": "string", "enum": [name for name, _ in categories] + [NO_CATEGORY]},
            "konfidenz": {"type": "number"},
            "begruendung": {"type": "string"},
        },
        "required": ["dokumentart", "bezug", "kategorie", "konfidenz", "begruendung"],
    }
    return SYSTEM_PROMPT, user, schema


@dataclass(frozen=True)
class LlmAnswer:
    category_id: uuid.UUID | None
    category_name: str | None
    confidence: float
    reason: str


def parse_llm_answer(answer: dict[str, Any], categories_by_name: dict[str, uuid.UUID]) -> LlmAnswer:
    name = str(answer.get("kategorie", "")).strip()
    try:
        confidence = float(answer.get("konfidenz", 0))
    except (TypeError, ValueError):
        confidence = 0.0
    if confidence > 1:  # manche Modelle antworten in Prozent
        confidence /= 100
    confidence = min(max(confidence, 0.0), 1.0)
    reason = str(answer.get("begruendung", "")).strip()
    context = ", ".join(
        f"{label}: {value}"
        for label, value in (("Art", answer.get("dokumentart")), ("Bezug", answer.get("bezug")))
        if str(value or "").strip()
    )
    reason = (f"{context}. {reason}" if context else reason).strip()[:500]

    category_id = categories_by_name.get(name)
    if category_id is None:  # Gross-/Kleinschreibung tolerieren
        lowered = {k.lower(): v for k, v in categories_by_name.items()}
        category_id = lowered.get(name.lower())
    if category_id is None:
        return LlmAnswer(None, None if name == NO_CATEGORY else name or None, confidence, reason)
    return LlmAnswer(category_id, name, confidence, reason)


def accept_llm(answer: LlmAnswer, t: Thresholds) -> bool:
    return answer.category_id is not None and answer.confidence >= t.llm_confidence
