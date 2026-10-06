"""Verwaltungsbefehle fuer den Betrieb - v. a. fuer den Fall "Admin-Passwort vergessen", der bei
einer selbst gehosteten Installation ohne E-Mail-Reset sonst nur per SQL zu loesen waere.

Im Container:  docker compose exec app-api python -m homedms.cli users
               docker compose exec app-api python -m homedms.cli reset-password <email>
               docker compose exec app-api python -m homedms.cli refile
Lokal:         uv run python -m homedms.cli ...
"""
import argparse
import getpass
import sys
from datetime import datetime, timezone

from sqlalchemy import func, select, update

from homedms import runtime
from homedms.core.security import hash_password
from homedms.db import async_session_factory, engine
from homedms.models.tenant import RefreshToken, Tenant, User

MIN_PASSWORD_LENGTH = 8  # wie in schemas/setup.py (BootstrapRequest.admin_password)


async def list_users() -> int:
    async with async_session_factory() as db:
        rows = (
            await db.execute(
                select(Tenant.name, User.email, User.role, User.display_name, User.is_active)
                .join(Tenant, Tenant.id == User.tenant_id)
                .order_by(Tenant.name, User.email)
            )
        ).all()
    if not rows:
        print("Noch keine Nutzer vorhanden - die Ersteinrichtung (POST /api/v1/setup/bootstrap) fehlt.")
        return 0
    for tenant_name, email, role, display_name, is_active in rows:
        state = "" if is_active else "  (deaktiviert)"
        print(f"{tenant_name:<30} {email:<40} {role.value:<8} {display_name}{state}")
    return 0


async def reset_password(email: str, password: str) -> int:
    async with async_session_factory() as db:
        users = (await db.execute(select(User).where(func.lower(User.email) == email.lower()))).scalars().all()
        if not users:
            print(f"Kein Nutzer mit der E-Mail-Adresse {email} gefunden.", file=sys.stderr)
            return 1
        if len(users) > 1:
            print(f"{email} existiert in mehreren Haushalten - bitte eindeutige Adresse verwenden.", file=sys.stderr)
            return 1
        user = users[0]
        user.password_hash = hash_password(password)
        user.failed_logins, user.locked_until = 0, None  # Sperre nach Fehlversuchen aufheben
        # Bestehende Anmeldungen beenden: wer das alte Passwort kannte, soll nicht angemeldet bleiben.
        await db.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=datetime.now(timezone.utc))
        )
        await db.commit()
    print(f"Passwort fuer {email} wurde geaendert. Bestehende Anmeldungen wurden beendet.")
    return 0


async def reset_two_factor(email: str) -> int:
    """Handy verloren und keine Wiederherstellungscodes mehr (z. B. beim einzigen Admin):
    Zwei-Faktor-Anmeldung ausschalten und alle Anmeldungen beenden."""
    async with async_session_factory() as db:
        users = (await db.execute(select(User).where(func.lower(User.email) == email.lower()))).scalars().all()
        if len(users) != 1:
            print(f"Kein eindeutiger Nutzer mit der E-Mail-Adresse {email} gefunden.", file=sys.stderr)
            return 1
        user = users[0]
        user.totp_secret = user.totp_pending_secret = None
        user.totp_last_step = None
        user.recovery_codes = None
        user.failed_logins, user.locked_until = 0, None
        await db.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=datetime.now(timezone.utc))
        )
        await db.commit()
    print(f"Zwei-Faktor-Anmeldung fuer {email} ausgeschaltet - bitte nach der Anmeldung neu einrichten.")
    return 0


async def refile_all() -> int:
    """Ablage fuer alle Dokumente einreihen (der Worker verschiebt/benennt dann bei Bedarf).
    Laeuft auch automatisch beim Start des API-Containers (docker-entrypoint.sh) - so landen
    Dateien aus aelteren Versionen ohne weiteres Zutun in der Ordnerstruktur."""
    from homedms.jobs import app as jobs_app
    from homedms.models.document import Document
    from homedms.tasks.filing import defer_filing

    async with async_session_factory() as db:
        ids = (await db.execute(select(Document.id))).scalars().all()
    async with jobs_app.open_async():
        for document_id in ids:
            await defer_filing(document_id)
    print(f"Ablage fuer {len(ids)} Dokument(e) eingereiht - der Worker erledigt den Rest.")
    return 0


def _ask_password() -> str | None:
    first = getpass.getpass("Neues Passwort: ")
    if len(first) < MIN_PASSWORD_LENGTH:
        print(f"Das Passwort muss mindestens {MIN_PASSWORD_LENGTH} Zeichen lang sein.", file=sys.stderr)
        return None
    if getpass.getpass("Passwort wiederholen: ") != first:
        print("Die Passwoerter stimmen nicht ueberein.", file=sys.stderr)
        return None
    return first


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m homedms.cli", description="Famulus-DMS-Verwaltung")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("users", help="Alle Haushalte und Nutzer auflisten")
    reset = sub.add_parser("reset-password", help="Passwort eines Nutzers neu setzen")
    reset.add_argument("email")
    reset.add_argument("--password", help="Neues Passwort (ohne Angabe wird es sicher abgefragt)")
    sub.add_parser("refile", help="Alle Dateien nach Kategorie/Jahr ablegen und sprechend benennen")
    two_factor = sub.add_parser("reset-2fa", help="Zwei-Faktor-Anmeldung eines Nutzers ausschalten (Handy verloren)")
    two_factor.add_argument("email")
    args = parser.parse_args(argv)

    async def run() -> int:
        try:
            if args.command == "users":
                return await list_users()
            if args.command == "refile":
                return await refile_all()
            if args.command == "reset-2fa":
                return await reset_two_factor(args.email)
            password = args.password if args.password is not None else _ask_password()
            if password is None:
                return 1
            if len(password) < MIN_PASSWORD_LENGTH:
                print(f"Das Passwort muss mindestens {MIN_PASSWORD_LENGTH} Zeichen lang sein.", file=sys.stderr)
                return 1
            return await reset_password(args.email, password)
        finally:
            await engine.dispose()

    return runtime.run(run())


if __name__ == "__main__":
    sys.exit(main())
