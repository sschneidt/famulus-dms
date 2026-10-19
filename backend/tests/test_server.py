"""Starter ohne Docker (homedms/server.py): Einstellungen aus homedms.env muessen auch fuer die
Kommandozeilen-Vorgaben gelten."""
from homedms import server


def _isolated_env(monkeypatch, *names):
    # load_dotenv schreibt direkt in os.environ - setenv + delenv sorgt dafuer, dass der Test es am Ende zurueckstellt
    for name in names:
        monkeypatch.setenv(name, "x")
        monkeypatch.delenv(name)


def test_port_und_host_kommen_aus_der_env_datei(tmp_path, monkeypatch):
    env = tmp_path / "homedms.env"
    env.write_text("PORT=18123\nHOST=127.0.0.1\n", encoding="utf-8")
    monkeypatch.setenv("HOMEDMS_ENV", str(env))
    _isolated_env(monkeypatch, "PORT", "HOST")
    args, used = server.parse_args([])
    assert (args.port, args.host, used) == (18123, "127.0.0.1", env)


def test_kommandozeile_hat_vorrang_vor_der_env_datei(tmp_path, monkeypatch):
    env = tmp_path / "homedms.env"
    env.write_text("PORT=18123\n", encoding="utf-8")
    monkeypatch.setenv("HOMEDMS_ENV", str(env))
    _isolated_env(monkeypatch, "PORT")
    assert server.parse_args(["--port", "9000"])[0].port == 9000


def test_ohne_env_datei_gilt_port_8000(tmp_path, monkeypatch):
    monkeypatch.setenv("HOMEDMS_ENV", str(tmp_path / "gibt-es-nicht.env"))
    _isolated_env(monkeypatch, "PORT", "HOST")
    args, used = server.parse_args([])
    assert (args.port, used) == (8000, None)


def _umgebung(monkeypatch, tmp_path, jwt_secret):
    from homedms.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "jwt_secret", jwt_secret)
    monkeypatch.setattr(settings, "documents_path", str(tmp_path / "documents"))
    monkeypatch.setattr(settings, "scan_path", str(tmp_path / "scan"))
    return server.check_environment()


def test_platzhalter_aus_der_vorlage_wird_als_jwt_secret_gemeldet(tmp_path, monkeypatch):
    """Wer die Vorlage kopiert und den Platzhalter stehen laesst, bekommt eine Warnung - sonst liefe die App mit
    einem oeffentlich bekannten Schluessel."""
    for secret in ("CHANGE_ME_LONG_RANDOM_STRING", "dev-only-change-me"):
        assert any("JWT_SECRET" in problem for problem in _umgebung(monkeypatch, tmp_path, secret)), secret


def test_echtes_jwt_secret_wird_nicht_gemeldet(tmp_path, monkeypatch):
    assert not any("JWT_SECRET" in problem for problem in _umgebung(monkeypatch, tmp_path, "k9Zt2Qm7VxP4"))
