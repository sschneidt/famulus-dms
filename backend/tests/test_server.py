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
