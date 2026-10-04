"""E-Mail-Versand (core/mailer.py) - ohne echten Mailserver."""
import smtplib

import pytest

from homedms.core import mailer

SETTINGS = {"host": "smtp.example.com", "port": 587, "security": "starttls", "username": "ich@example.com",
            "sender": "ich@example.com"}


def test_password_is_encrypted():
    token = mailer.encrypt_password("geheim-123")
    assert "geheim" not in token
    assert mailer.decrypt_password(token) == "geheim-123"
    with pytest.raises(mailer.MailError, match="neu eingeben"):
        mailer.decrypt_password("kaputt")


def test_message_has_text_and_html():
    msg = mailer.build_message(SETTINGS, "du@example.com", "HomeDMS: 1 heute fällig", "Text", "<p>HTML</p>")
    assert msg["From"] == "HomeDMS <ich@example.com>"
    assert msg["Auto-Submitted"] == "auto-generated"
    assert [p.get_content_type() for p in msg.iter_parts()] == ["text/plain", "text/html"]


class FakeSMTP:
    sent: list = []
    fail_login = False

    def __init__(self, host, port, timeout=None, **kw):
        self.calls = [("connect", host, port)]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def ehlo(self):
        pass

    def starttls(self, context=None):
        self.calls.append("starttls")

    def login(self, user, password):
        if FakeSMTP.fail_login:
            raise smtplib.SMTPAuthenticationError(535, b"nope")
        self.calls.append(("login", user, password))

    def send_message(self, msg):
        FakeSMTP.sent.append((self.calls, msg))


async def test_send(monkeypatch):
    monkeypatch.setattr(mailer.smtplib, "SMTP", FakeSMTP)
    FakeSMTP.sent.clear()
    FakeSMTP.fail_login = False
    settings = {**SETTINGS, "password": mailer.encrypt_password("pw")}
    await mailer.send(settings, "du@example.com", "Betreff", "Text")
    calls, msg = FakeSMTP.sent[0]
    assert calls == [("connect", "smtp.example.com", 587), "starttls", ("login", "ich@example.com", "pw")]
    assert msg["To"] == "du@example.com"

    FakeSMTP.fail_login = True
    with pytest.raises(mailer.MailError, match="App-Passwort"):
        await mailer.send(settings, "du@example.com", "Betreff", "Text")


async def test_not_configured():
    with pytest.raises(mailer.MailError, match="nicht eingerichtet"):
        await mailer.send({}, "du@example.com", "x", "y")
