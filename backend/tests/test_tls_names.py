"""Name/Adresse des Servers aus der Ersteinrichtung ins HTTPS-Zertifikat (core/tls.py: apply_hostnames)."""
import asyncio
import ssl

import pytest
from cryptography import x509

from homedms.core import tls


@pytest.fixture(autouse=True)
def isolate(monkeypatch):
    monkeypatch.setattr(tls, "CURRENT", None)
    monkeypatch.setattr(tls, "RELOAD_HOOKS", [])
    monkeypatch.setattr(tls, "UNCOVERED", set())
    # Unabhaengig vom Rechner, auf dem der Test laeuft: keine automatisch erkannten Namen
    monkeypatch.setattr(tls, "detect_names", lambda extra="": ["localhost", "127.0.0.1", *[n.strip() for n in extra.replace(";", ",").split(",") if n.strip()]])


@pytest.mark.parametrize(("text", "expected"), [
    ("192.168.1.10", ["192.168.1.10"]),
    ("192.168.1.10, NAS.local;nas", ["192.168.1.10", "nas.local", "nas"]),
    ("https://192.168.1.10:8443/dokumente/5?x=1", ["192.168.1.10"]),
    ("nas.local:8443", ["nas.local"]),
    ("[::1]:8443", ["::1"]),
    ("  nas   nas  ", ["nas"]),
    ("", []),
])
def test_namen_aus_der_eingabe(text, expected):
    assert tls.parse_names(text) == expected


def test_gueltige_namen_werden_akzeptiert():
    tls.validate_names(["192.168.1.10", "10.0.0.5", "nas", "my-nas.local", "nas.fritz.box"])


@pytest.mark.parametrize("name", ["8.8.8.8", "example.com", "nas.example.org", "a b", "-nas", "nas..local", "x" * 300, "nas/../x"])
def test_unzulaessige_namen_werden_abgelehnt(name):
    with pytest.raises(ValueError):
        tls.validate_names([name])


def sans(files: tls.TlsFiles) -> set[str]:
    return set(files.names)


def test_adresse_wird_ergaenzt_und_ca_bleibt(tmp_path):
    first = tls.ensure_certificates(tmp_path)
    assert "192.168.7.7" not in first.names

    files, replaced = tls.apply_hostnames(tmp_path, "192.168.7.7, nas.local")
    assert replaced is False and files.fingerprint == first.fingerprint  # dieselbe CA: Geraete muessen nichts neu installieren
    assert {"192.168.7.7", "nas.local"} <= sans(files)
    assert tls.CURRENT is files


def test_rechnername_ohne_punkt_ersetzt_die_ca(tmp_path):
    first = tls.ensure_certificates(tmp_path)
    files, replaced = tls.apply_hostnames(tmp_path, "mynas")
    assert replaced is True and files.fingerprint != first.fingerprint
    assert "mynas" in sans(files)
    # und die neue CA darf diesen Namen wirklich ausstellen (Namensbeschraenkung)
    ca = x509.load_pem_x509_certificate(files.ca_cert.read_bytes())
    permitted = {str(d.value) for d in ca.extensions.get_extension_for_class(x509.NameConstraints).value.permitted_subtrees
                 if isinstance(d, x509.DNSName)}
    assert "mynas" in permitted


def test_namen_bleiben_ueber_neustarts_erhalten(tmp_path):
    tls.ensure_certificates(tmp_path)
    tls.apply_hostnames(tmp_path, "192.168.7.7")
    tls.apply_hostnames(tmp_path, "nas.local")  # zweiter Aufruf ergaenzt, ersetzt nicht
    restarted = tls.ensure_certificates(tmp_path, "")  # Neustart ohne TLS_HOSTNAMES
    assert {"192.168.7.7", "nas.local"} <= sans(restarted)
    assert tls.saved_names(tmp_path) == ["192.168.7.7", "nas.local"]


def test_umgebungsvariable_und_gespeicherte_namen_zusammen(tmp_path):
    tls.ensure_certificates(tmp_path, "192.168.7.1")
    files, _ = tls.apply_hostnames(tmp_path, "192.168.7.2", env_extra="192.168.7.1")
    assert {"192.168.7.1", "192.168.7.2"} <= sans(files)


def test_ungueltige_eingabe_aendert_nichts(tmp_path):
    first = tls.ensure_certificates(tmp_path)
    with pytest.raises(ValueError):
        tls.apply_hostnames(tmp_path, "192.168.7.7, example.com")
    assert tls.saved_names(tmp_path) == [] and tls.CURRENT is None
    assert sans(tls.ensure_certificates(tmp_path)) == sans(first)


def test_aufgerufene_unbekannte_adresse_gilt_danach_als_abgedeckt(tmp_path):
    tls.ensure_certificates(tmp_path)
    tls.UNCOVERED.update({"192.168.7.7", "anderer.local"})
    tls.apply_hostnames(tmp_path, "192.168.7.7")
    assert tls.UNCOVERED == {"anderer.local"}


def test_laufender_server_wird_benachrichtigt_und_fehler_im_hook_stoppen_nichts(tmp_path):
    tls.ensure_certificates(tmp_path)
    seen = []
    tls.RELOAD_HOOKS.append(lambda f: (_ for _ in ()).throw(RuntimeError("kaputt")))
    tls.RELOAD_HOOKS.append(seen.append)
    files, _ = tls.apply_hostnames(tmp_path, "192.168.7.7")
    assert seen == [files]


async def served_names(context: ssl.SSLContext, port_holder: list[int]) -> set[str]:
    """Verbindet sich mit dem TLS-Server und liest die Namen des vorgezeigten Zertifikats."""
    client = ssl.create_default_context()
    client.check_hostname = False
    client.verify_mode = ssl.CERT_NONE
    reader, writer = await asyncio.open_connection("127.0.0.1", port_holder[0], ssl=client)
    der = writer.get_extra_info("ssl_object").getpeercert(binary_form=True)
    writer.close()
    await writer.wait_closed()
    cert = x509.load_der_x509_certificate(der)
    san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    return {str(v) for v in san.get_values_for_type(x509.DNSName)} | {str(v) for v in san.get_values_for_type(x509.IPAddress)}


async def test_neues_zertifikat_gilt_im_laufenden_server_fuer_neue_verbindungen(tmp_path):
    """Dieselbe Technik wie server.py: load_cert_chain auf dem Kontext des laufenden Servers."""
    first = tls.ensure_certificates(tmp_path)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(str(first.cert), str(first.key))

    async def handle(reader, writer):
        writer.close()

    server = await asyncio.start_server(handle, "127.0.0.1", 0, ssl=context)
    port = [server.sockets[0].getsockname()[1]]
    try:
        assert "192.168.7.7" not in await served_names(context, port)
        tls.RELOAD_HOOKS.append(lambda f: context.load_cert_chain(str(f.cert), str(f.key)))
        tls.apply_hostnames(tmp_path, "192.168.7.7")
        assert "192.168.7.7" in await served_names(context, port)
    finally:
        server.close()
        await server.wait_closed()
