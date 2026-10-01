"""Vorhersehbare Ollama-Attrappe fuer die Integrationstests (kein echtes Sprachmodell noetig).

- /api/embed: "Wortbeutel"-Vektoren - aehnliche Texte ergeben aehnliche Vektoren.
- /api/chat, Klassifikation (Schema mit "kategorie"): Entscheidung nach Stichworten.
- /api/chat, Extraktion (Schema mit "fristen"): Metadaten nach festen Mustern, dazu immer eine
  ERFUNDENE Frist, deren Textstelle nicht im Dokument steht - die muss das System verwerfen.
"""
import json
import math
import re
import zlib

import httpx

from homedms.ai.ollama import OllamaClient

DIM = 768


def bag_of_words(text: str) -> list[float]:
    vec = [0.0] * DIM
    for token in re.findall(r"\w+", text.lower()):
        vec[zlib.crc32(token.encode()) % DIM] += 1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


class FakeOllama:
    def __init__(self) -> None:
        self.embed_calls = 0
        self.classify_calls = 0
        self.extract_calls = 0
        self.down = False

    def client(self, config=None) -> OllamaClient:
        return OllamaClient(base_url="http://ollama.test", transport=httpx.MockTransport(self.handler))

    def handler(self, request: httpx.Request) -> httpx.Response:
        if self.down:
            raise httpx.ConnectError("Verbindung abgelehnt", request=request)
        body = json.loads(request.content)
        if request.url.path == "/api/embed":
            self.embed_calls += 1
            return httpx.Response(200, json={"embeddings": [bag_of_words(body["input"])]})
        if request.url.path != "/api/chat":
            return httpx.Response(404)
        doc = body["messages"][1]["content"].split('"""')[1]
        properties = body["format"]["properties"]
        if "kategorie" in properties:
            self.classify_calls += 1
            answer = self._classify(doc)
        else:
            self.extract_calls += 1
            answer = self._extract(doc)
        return httpx.Response(200, json={"message": {"content": json.dumps(answer)}})

    @staticmethod
    def _classify(doc: str) -> dict:
        if "Wasserschaden" in doc:
            return {"dokumentart": "Rechnung", "bezug": "Wohnung", "kategorie": "Haus & Reparaturen",
                    "konfidenz": 0.9, "begruendung": "Handwerker"}
        if "Versicherung" in doc:
            return {"kategorie": "Versicherungen", "konfidenz": 0.95, "begruendung": "Versicherungsschreiben"}
        if "Stadtwerke" in doc:
            return {"kategorie": "Wohnen & Nebenkosten", "konfidenz": 0.9, "begruendung": "Energie"}
        return {"kategorie": "Sonstiges", "konfidenz": 0.4, "begruendung": "unklar"}

    @staticmethod
    def _extract(doc: str) -> dict:
        first_line = doc.strip().splitlines()[0].strip() if doc.strip() else ""
        m_date = re.search(r"vom (\d{2})\.(\d{2})\.(\d{4})", doc)
        m_amount = re.search(r"Betrag: ([\d.,]+) EUR", doc)
        fristen = [{  # erfunden - Textstelle steht nicht im Dokument
            "datum": "2027-01-01", "bezeichnung": "Vertragsende", "konfidenz": 0.8,
            "textstelle": "Die Mitgliedschaft endet automatisch nach zwei Jahren", "wiederholung": "keine",
        }]
        m_due = re.search(r"zahlbar bis (\d{2})\.(\d{2})\.(\d{4})", doc)
        if m_due:
            d, mo, y = m_due.groups()
            fristen.append({"datum": f"{y}-{mo}-{d}", "bezeichnung": "zahlbar bis", "konfidenz": 0.9,  # wie llama3.2:3b
                            "textstelle": m_due.group(0), "wiederholung": "keine"})
        return {
            "dokumentdatum": f"{m_date.group(3)}-{m_date.group(2)}-{m_date.group(1)}" if m_date else "",
            "absender": first_line,
            "betreff": ("Rechnung Wasserschaden-Reparatur" if "Wasserschaden" in doc
                        else "Stromrechnung" if "Stromrechnung" in doc
                        else "Kuendigungsbestaetigung Mobilfunk"),  # letzteres erfunden -> muss verworfen werden
            "betrag": m_amount.group(1) if m_amount else "",
            # Objektadresse: "Seeweg" in beiden Schreibweisen; sonst die Absenderadresse aus dem
            # Briefkopf (typischer Fehler kleiner Modelle) - die muss das System verwerfen.
            "objektadresse": (
                {"strasse": m_obj.group(1), "plz": m_obj.group(2), "ort": m_obj.group(3)}
                if (m_obj := re.search(r"Objekt: (Seeweg [^,]+), (\d{5}) (\w+)", doc))
                else {"strasse": "Industriestrasse 3", "plz": "70565", "ort": "Stuttgart"}
            ),
            "fristen": fristen,
        }
