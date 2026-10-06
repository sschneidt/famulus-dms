"""Erinnerungen an faellige Termine (Anforderungsdokument 4.5) - reine Funktionen, getestet in
tests/test_reminders.py.

Stufen je Wiedervorlage - jede Stufe wird genau einmal gemeldet, damit die taegliche
Zusammenfassung nicht jeden Tag dieselben 30 Tage Vorlauf wiederholt:

    1 Vorlauf     ab "Erinnerung X Tage vorher" (reminder_lead_days)
    2 1 Woche     noch hoechstens 7 Tage
    3 morgen      noch 1 Tag
    4 heute       am Termin selbst
    5 ueberfaellig danach - und dann woechentlich wieder, bis erledigt

Texte erscheinen in der Sprache der Person (homedms/i18n): die Zusammenfassung wird mit
use_language(user.locale) erstellt.
"""
import re
from dataclasses import dataclass, field
from datetime import date
from html import escape

from homedms import i18n
from homedms.i18n import N_, _, _n

LEAD, WEEK, TOMORROW, TODAY, OVERDUE = 1, 2, 3, 4, 5
OVERDUE_REPEAT_DAYS = 7
MAX_PUSH_LINES = 3

WEEKDAYS = {
    "de": ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"),
    "en": ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"),
    "ru": ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"),
}

# Einheitliche Bezeichnungen der KI-Fristen (ai/extraction.py, _CANONICAL_LABELS)
NOTE_LABELS = {N_("Kündigungsfrist"), N_("Widerspruchsfrist"), N_("Zahlungsfrist"), N_("Vertragsende"),
               N_("TÜV-Termin"), N_("Prüftermin"), N_("Frist")}
# Text der Aufbewahrungs-Termine (core/wiedervorlage.py, retention_note) - wie im Frontend (lib/format.ts)
RETENTION_NOTE = re.compile(
    r"^Aufbewahrungsfrist \((.+), (?:(\d+) Jahre?)? ?(?:(\d+) Monate?)?\) endet - Dokument kann danach vernichtet "
    r"werden\.( Das Papier-Original muss bis dahin aufbewahrt werden\.)?$"
)


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


def duration_text(months: int) -> str:
    years, rest = divmod(months, 12)
    parts = []
    if years:
        parts.append(_n("{count} Jahr", "{count} Jahre", years))
    if rest:
        parts.append(_n("{count} Monat", "{count} Monate", rest))
    return " ".join(parts) or _n("{count} Monat", "{count} Monate", 0)


def note_label(note: str | None) -> str:
    """Bezeichnung eines Termins in der aktuellen Sprache (eigene Texte bleiben, wie sie sind)."""
    if not note:
        return _("Termin")
    if note in NOTE_LABELS:
        return _(note)
    m = RETENTION_NOTE.match(note)
    if m:
        months = int(m.group(2) or 0) * 12 + int(m.group(3) or 0)
        text = _("Aufbewahrungsfrist ({category}, {duration}) endet – Dokument kann danach vernichtet werden.",
                 category=i18n.translate_stored(m.group(1)), duration=duration_text(months))
        return f"{text} {_('Das Papier-Original muss bis dahin aufbewahrt werden.')}" if m.group(4) else text
    return note


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
            parts.append(_("{count} überfällig", count=len(self.overdue)))
        if self.due_today:
            parts.append(_("{count} heute fällig", count=len(self.due_today)))
        if self.upcoming:
            parts.append(_("{count} demnächst", count=len(self.upcoming)))
        if self.new_proposals:
            parts.append(_n("{count} neuer Fristvorschlag", "{count} neue Fristvorschläge", self.new_proposals))
        if self.new_review:
            parts.append(_("{count} zu prüfen", count=self.new_review))
        if self.new_imports:
            parts.append(_n("{count} neues Dokument", "{count} neue Dokumente", self.new_imports))
        return parts

    def subject(self) -> str:
        return "Famulus DMS: " + ", ".join(self.counts()[:3])

    def text(self, app_url: str) -> str:
        lines = [_("Hallo,"), "", _("das steht in Famulus DMS an:"), ""]
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
                 f"<p>{escape(_('Hallo,'))}</p><p>{escape(_('das steht in Famulus DMS an:'))}</p>"]
        for key, title, items in self._groups(with_key=True):
            color = {"overdue": "#c92a2a", "today": "#e8590c"}.get(key, "#1c7ed6")
            parts.append(f'<h3 style="margin:18px 0 6px;color:{color};font-size:16px">{escape(title)}</h3>'
                         '<ul style="padding-left:18px;margin:0">')
            for item in items:
                label = escape(note_label(item.note))
                doc = escape(item.document_title or _("Dokument"))
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
        lines = [item_line(i) for i in self.items[:MAX_PUSH_LINES]]
        rest = len(self.items) - MAX_PUSH_LINES
        if rest > 0:
            lines.append(_n("und {count} weiterer Termin", "und {count} weitere Termine", rest))
        lines += [line for line, _path in self._extras()]
        url = "/termine" if self.items or self.new_proposals else ("/pruefen" if self.new_review else "/")
        title = "Famulus DMS: " + ", ".join(self.counts()[:2])
        return {"title": title, "body": "\n".join(lines), "url": url, "tag": "homedms-digest"}

    def _groups(self, with_key: bool = False) -> list[tuple]:
        groups = [("overdue", _("Überfällig"), self.overdue), ("today", _("Heute fällig"), self.due_today),
                  ("upcoming", _("Demnächst"), self.upcoming)]
        result = [(k, t, sorted(items, key=lambda i: i.due_date)) for k, t, items in groups if items]
        return result if with_key else [(t, items) for _k, t, items in result]

    def _extras(self) -> list[tuple[str, str]]:
        extras = []
        if self.new_proposals:
            extras.append((_n("Die KI hat {count} neue Frist erkannt - bitte bestätigen (insgesamt {total} offen).",
                              "Die KI hat {count} neue Fristen erkannt - bitte bestätigen (insgesamt {total} offen).",
                              self.new_proposals, total=self.open_proposals), "/termine"))
        if self.new_review:
            extras.append((_n("{count} neues Dokument: Kategorie bitte prüfen (insgesamt {total}).",
                              "{count} neue Dokumente: Kategorie bitte prüfen (insgesamt {total}).",
                              self.new_review, total=self.open_review), "/pruefen"))
        if self.new_imports:
            extras.append((_n("{count} Dokument ist über den Scan-Ordner eingegangen.",
                              "{count} Dokumente sind über den Scan-Ordner eingegangen.", self.new_imports), "/"))
        return extras


def fmt_date(d: date) -> str:
    return f"{WEEKDAYS[i18n.current()][d.weekday()]}, {i18n.format_date(d)}"


def when(item: ReminderItem) -> str:
    day = fmt_date(item.due_date)
    if item.days_left < -1:
        return _n("seit {count} Tag überfällig ({date})", "seit {count} Tagen überfällig ({date})",
                  -item.days_left, date=day)
    if item.days_left == -1:
        return _("seit gestern überfällig ({date})", date=day)
    if item.days_left == 0:
        return _("heute fällig ({date})", date=day)
    if item.days_left == 1:
        return _("morgen fällig ({date})", date=day)
    return _n("in {count} Tag fällig ({date})", "in {count} Tagen fällig ({date})", item.days_left, date=day)


def item_line(item: ReminderItem) -> str:
    return f"{note_label(item.note)} – {item.document_title or _('Dokument')}: {when(item)}"


def _footer(app_url: str) -> list[str]:
    where = (_("unter {url}", url=f"{app_url}/konto") if app_url else _("unter „Konto & Sicherheit“"))
    return [_("Diese Zusammenfassung kommt einmal täglich, nur wenn etwas ansteht."),
            _("Uhrzeit und Wege lassen sich in Famulus DMS {where} ändern.", where=where)]
