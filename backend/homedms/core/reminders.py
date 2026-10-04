"""Erinnerungen an faellige Termine (Anforderungsdokument 4.5) - reine Funktionen, getestet in
tests/test_reminders.py.

Stufen je Wiedervorlage - jede Stufe wird genau einmal gemeldet, damit die taegliche
Zusammenfassung nicht jeden Tag dieselben 30 Tage Vorlauf wiederholt:

    1 Vorlauf     ab "Erinnerung X Tage vorher" (reminder_lead_days)
    2 1 Woche     noch hoechstens 7 Tage
    3 morgen      noch 1 Tag
    4 heute       am Termin selbst
    5 ueberfaellig danach - und dann woechentlich wieder, bis erledigt
"""
from dataclasses import dataclass, field
from datetime import date
from html import escape

LEAD, WEEK, TOMORROW, TODAY, OVERDUE = 1, 2, 3, 4, 5
OVERDUE_REPEAT_DAYS = 7
MAX_PUSH_LINES = 3

WEEKDAYS = ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")


def stage_for(days_left: int, lead_days: int) -> int:
    """Aktuelle Erinnerungsstufe; 0 = noch nicht im Vorlauf."""
    if days_left < 0:
        return OVERDUE
    if days_left == 0:
        return TODAY
    if days_left > lead_days:
        return 0
    if days_left == 1:
        return TOMORROW
    if days_left <= 7:
        return WEEK
    return LEAD


def should_remind(stage: int, last_stage: int, reminded_on: date | None, today: date) -> bool:
    if stage == 0:
        return False
    if stage > last_stage:
        return True
    if stage == OVERDUE and reminded_on is not None:
        return (today - reminded_on).days >= OVERDUE_REPEAT_DAYS
    return False


@dataclass
class ReminderItem:
    wiedervorlage_id: str
    document_id: str
    document_title: str
    note: str
    due_date: date
    days_left: int
    stage: int


@dataclass
class Digest:
    items: list[ReminderItem] = field(default_factory=list)
    new_proposals: int = 0   # neue KI-Fristvorschlaege seit der letzten Zusammenfassung
    open_proposals: int = 0
    new_review: int = 0      # neue Dokumente, deren Kategorie geprueft werden muss
    open_review: int = 0
    new_imports: int = 0     # neu ueber den Scan-Ordner eingegangen

    @property
    def is_empty(self) -> bool:
        return not (self.items or self.new_proposals or self.new_review or self.new_imports)

    @property
    def overdue(self) -> list[ReminderItem]:
        return [i for i in self.items if i.days_left < 0]

    @property
    def due_today(self) -> list[ReminderItem]:
        return [i for i in self.items if i.days_left == 0]

    @property
    def upcoming(self) -> list[ReminderItem]:
        return [i for i in self.items if i.days_left > 0]

    def counts(self) -> list[str]:
        parts = []
        if self.overdue:
            parts.append(f"{len(self.overdue)} überfällig")
        if self.due_today:
            parts.append(f"{len(self.due_today)} heute fällig")
        if self.upcoming:
            parts.append(f"{len(self.upcoming)} demnächst")
        if self.new_proposals:
            parts.append(f"{self.new_proposals} neue{'r' if self.new_proposals == 1 else ''} Fristvorschlag"
                         f"{'' if self.new_proposals == 1 else 'e'}")
        if self.new_review:
            parts.append(f"{self.new_review} zu prüfen")
        if self.new_imports:
            parts.append(f"{self.new_imports} neu{'es' if self.new_imports == 1 else 'e'} Dokument"
                         f"{'' if self.new_imports == 1 else 'e'}")
        return parts

    def subject(self) -> str:
        return "HomeDMS: " + ", ".join(self.counts()[:3])

    def text(self, app_url: str) -> str:
        lines = ["Hallo,", "", "das steht in HomeDMS an:", ""]
        for title, items in self._groups():
            lines.append(f"{title}:")
            for item in items:
                lines.append(f"  - {item_line(item)}")
                if app_url:
                    lines.append(f"    {app_url}/dokumente/{item.document_id}")
            lines.append("")
        for line, path in self._extras():
            lines.append(line + (f"\n  {app_url}{path}" if app_url else ""))
        if self._extras():
            lines.append("")
        lines += _footer(app_url)
        return "\n".join(lines)

    def html(self, app_url: str) -> str:
        parts = ['<div style="font-family:Segoe UI,Arial,sans-serif;font-size:15px;color:#222;max-width:640px">',
                 "<p>Hallo,</p><p>das steht in HomeDMS an:</p>"]
        for title, items in self._groups():
            color = "#c92a2a" if title == "Überfällig" else ("#e8590c" if title == "Heute fällig" else "#1c7ed6")
            parts.append(f'<h3 style="margin:18px 0 6px;color:{color};font-size:16px">{escape(title)}</h3>'
                         '<ul style="padding-left:18px;margin:0">')
            for item in items:
                label = escape(item.note or "Termin")
                doc = escape(item.document_title or "Dokument")
                link = f'<a href="{escape(app_url)}/dokumente/{item.document_id}" style="color:#1c7ed6">{doc}</a>' if app_url else doc
                parts.append(f'<li style="margin:4px 0"><b>{label}</b> – {link}<br>'
                             f'<span style="color:#555">{escape(when(item))}</span></li>')
            parts.append("</ul>")
        extras = self._extras()
        if extras:
            parts.append('<p style="margin-top:18px">')
            for line, path in extras:
                text = escape(line)
                parts.append(f'<a href="{escape(app_url)}{path}" style="color:#1c7ed6">{text}</a><br>' if app_url else f"{text}<br>")
            parts.append("</p>")
        footer = "<br>".join(escape(line) for line in _footer(app_url) if line)
        parts.append(f'<p style="margin-top:24px;color:#888;font-size:12px">{footer}</p></div>')
        return "".join(parts)

    def push(self) -> dict:
        """Kurzfassung fuer die Handy-Benachrichtigung."""
        lines = [f"{i.note or 'Termin'} – {i.document_title}: {when(i)}" for i in self.items[:MAX_PUSH_LINES]]
        rest = len(self.items) - MAX_PUSH_LINES
        if rest > 0:
            lines.append(f"und {rest} weitere Termine")
        lines += [line for line, _ in self._extras()]
        url = "/termine" if self.items or self.new_proposals else ("/pruefen" if self.new_review else "/")
        title = "HomeDMS: " + ", ".join(self.counts()[:2])
        return {"title": title, "body": "\n".join(lines), "url": url, "tag": "homedms-digest"}

    def _groups(self) -> list[tuple[str, list[ReminderItem]]]:
        groups = [("Überfällig", self.overdue), ("Heute fällig", self.due_today), ("Demnächst", self.upcoming)]
        return [(t, sorted(items, key=lambda i: i.due_date)) for t, items in groups if items]

    def _extras(self) -> list[tuple[str, str]]:
        extras = []
        if self.new_proposals:
            extras.append((f"Die KI hat {self.new_proposals} neue Frist{'' if self.new_proposals == 1 else 'en'} "
                           f"erkannt - bitte bestätigen (insgesamt {self.open_proposals} offen).", "/termine"))
        if self.new_review:
            extras.append((f"{self.new_review} neue{'s' if self.new_review == 1 else ''} Dokument"
                           f"{'' if self.new_review == 1 else 'e'}: Kategorie bitte prüfen "
                           f"(insgesamt {self.open_review}).", "/pruefen"))
        if self.new_imports:
            extras.append((f"{self.new_imports} Dokument{' ist' if self.new_imports == 1 else 'e sind'} "
                           f"über den Scan-Ordner eingegangen.", "/"))
        return extras


def fmt_date(d: date) -> str:
    return f"{WEEKDAYS[d.weekday()]}, {d:%d.%m.%Y}"


def when(item: ReminderItem) -> str:
    if item.days_left < -1:
        return f"seit {-item.days_left} Tagen überfällig ({fmt_date(item.due_date)})"
    if item.days_left == -1:
        return f"seit gestern überfällig ({fmt_date(item.due_date)})"
    if item.days_left == 0:
        return f"heute fällig ({fmt_date(item.due_date)})"
    if item.days_left == 1:
        return f"morgen fällig ({fmt_date(item.due_date)})"
    return f"in {item.days_left} Tagen fällig ({fmt_date(item.due_date)})"


def item_line(item: ReminderItem) -> str:
    return f"{item.note or 'Termin'} – {item.document_title or 'Dokument'}: {when(item)}"


def _footer(app_url: str) -> list[str]:
    settings = f" unter {app_url}/konto" if app_url else " unter „Konto & Sicherheit“"
    return ["Diese Zusammenfassung kommt einmal täglich, nur wenn etwas ansteht.",
            f"Uhrzeit und Wege lassen sich in HomeDMS{settings} ändern."]
