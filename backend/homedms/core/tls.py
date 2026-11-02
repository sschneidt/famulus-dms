"""HTTPS mit eigener, lokaler Zertifizierungsstelle (TLS_MODE=auto).

Warum: Ohne HTTPS gehen im WLAN Passwort, Anmeldung und die Dokumente selbst im Klartext durchs
Netz. Oeffentliche Zertifikate (Let's Encrypt) brauchen eine Internet-Domain - fuer ein System,
das nur im Heimnetz bzw. per VPN erreichbar sein soll, passt eine eigene kleine
Zertifizierungsstelle (CA) besser: Sie wird einmal pro Geraet als vertrauenswuerdig installiert
(Hilfeseite http://<server>:8000/zertifikat), danach ist die Verbindung ohne Warnung verschluesselt.

Sicherheit der CA selbst:
- Namensbeschraenkung (Name Constraints): Die CA darf NUR Zertifikate fuer Namen/Adressen im
  Heimnetz ausstellen (private IP-Bereiche, .local/.lan/.home.arpa/.fritz.box/.ts.net ..., der
  Rechnername). Selbst wenn jemand ihren Schluessel stiehlt, kann er damit nicht z. B. die Seite
  der eigenen Bank faelschen.
- Schluessel nur im TLS-Ordner (Rechte 600), nicht im Dokumente-Ordner.

Server-Zertifikat: 397 Tage gueltig (Vorgabe von Apple/Browsern), wird beim Start automatisch
erneuert (30 Tage vor Ablauf oder wenn ein Name/eine Adresse fehlt). Die CA bleibt - Geraete
muessen also nichts neu installieren.
"""
import ipaddress
import logging
import re
import socket
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from homedms.i18n import _

logger = logging.getLogger("homedms.core.tls")

CA_DAYS = 3650
SERVER_DAYS = 397
RENEW_BEFORE = timedelta(days=30)
CURRENT: "TlsFiles | None" = None  # vom Starter gesetzt (server.py) - fuer die Diagnose
UNCOVERED: set[str] = set()  # aufgerufene Adressen, die das Zertifikat nicht abdeckt (cert_page.HostTracker)
HOSTNAMES_FILE = "hostnames.txt"  # Namen/Adressen aus der Ersteinrichtung, im TLS-Ordner (zusaetzlich zu TLS_HOSTNAMES)
RELOAD_HOOKS: list = []  # Funktionen(TlsFiles), die ein neues Zertifikat in den laufenden Server laden (server.py)
HOST_NAME = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)*$")
PRIVATE_SUFFIXES = ("local", "lan", "home", "home.arpa", "internal", "fritz.box", "ts.net", "localhost", "localdomain")
PRIVATE_NETWORKS = ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "100.64.0.0/10", "127.0.0.0/8", "169.254.0.0/16")


@dataclass(frozen=True)
class TlsFiles:
    ca_cert: Path
    cert: Path
    key: Path
    fingerprint: str  # SHA-256 der CA, zum Vergleichen beim Installieren
    names: tuple[str, ...]  # abgedeckte Namen und Adressen
    expires: datetime


def detect_names(extra: str = "") -> list[str]:
    """Rechnername, rechnername.local, localhost und die IP-Adressen dieses Rechners + TLS_HOSTNAMES."""
    names: list[str] = ["localhost", "127.0.0.1"]
    host = socket.gethostname().strip().lower()
    if host:
        names += [host, f"{host}.local"]
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            names.append(info[4][0])
    except OSError:
        pass
    try:  # Adresse, ueber die dieser Rechner ins Netz geht (es wird nichts gesendet)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("10.255.255.255", 1))
            names.append(probe.getsockname()[0])
    except OSError:
        pass
    names += [n.strip().lower() for n in extra.replace(";", ",").split(",") if n.strip()]
    result = []
    for name in names:
        if name and name not in result and name != "0.0.0.0":
            result.append(name)
    return result


def _is_ip(name: str) -> bool:
    try:
        ipaddress.ip_address(name)
        return True
    except ValueError:
        return False


def _permitted(name: str) -> bool:
    """Liegt der Name im erlaubten Bereich der CA (siehe Namensbeschraenkung)?"""
    if _is_ip(name):
        return any(ipaddress.ip_address(name) in ipaddress.ip_network(n) for n in PRIVATE_NETWORKS)
    return "." not in name or any(name == s or name.endswith("." + s) for s in PRIVATE_SUFFIXES)


def _write_private(path: Path, data: bytes) -> None:
    path.write_bytes(data)
    try:
        path.chmod(0o600)
    except OSError:
        pass


def _fingerprint(cert: x509.Certificate) -> str:
    return ":".join(f"{b:02X}" for b in cert.fingerprint(hashes.SHA256()))


def _create_ca(directory: Path, names: list[str]) -> tuple[x509.Certificate, ec.EllipticCurvePrivateKey]:
    key = ec.generate_private_key(ec.SECP256R1())
    host = socket.gethostname() or "HomeDMS"
    subject = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, f"HomeDMS lokale Zertifizierungsstelle ({host})"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "HomeDMS"),
    ])
    # Einzelne Rechnernamen ohne Punkt muessen einzeln erlaubt werden; Suffixe decken Unterdomains ab
    dns = list(PRIVATE_SUFFIXES) + [n for n in names if not _is_ip(n) and "." not in n and n not in PRIVATE_SUFFIXES]
    permitted = [x509.DNSName(d) for d in dict.fromkeys(dns)]
    permitted += [x509.IPAddress(ipaddress.ip_network(n)) for n in PRIVATE_NETWORKS]
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject).issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=CA_DAYS))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(x509.KeyUsage(
            digital_signature=False, content_commitment=False, key_encipherment=False, data_encipherment=False,
            key_agreement=False, key_cert_sign=True, crl_sign=True, encipher_only=False, decipher_only=False,
        ), critical=True)
        .add_extension(x509.NameConstraints(permitted_subtrees=permitted, excluded_subtrees=None), critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .sign(key, hashes.SHA256())
    )
    _write_private(directory / "ca.key", key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    (directory / "ca.crt").write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    logger.info("Neue lokale Zertifizierungsstelle erstellt (Fingerabdruck %s)", _fingerprint(cert))
    return cert, key


def _create_server_cert(directory: Path, names: list[str], ca: x509.Certificate,
                        ca_key: ec.EllipticCurvePrivateKey) -> x509.Certificate:
    key = ec.generate_private_key(ec.SECP256R1())
    san: list[x509.GeneralName] = []
    for name in names:
        san.append(x509.IPAddress(ipaddress.ip_address(name)) if _is_ip(name) else x509.DNSName(name))
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, names[0] if names else "homedms")]))
        .issuer_name(ca.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=SERVER_DAYS))
        .add_extension(x509.SubjectAlternativeName(san), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.KeyUsage(
            digital_signature=True, content_commitment=False, key_encipherment=False, data_encipherment=False,
            key_agreement=False, key_cert_sign=False, crl_sign=False, encipher_only=False, decipher_only=False,
        ), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .sign(ca_key, hashes.SHA256())
    )
    _write_private(directory / "server.key", key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    # Kette (Server + CA) - manche Geraete wollen die CA mitgeliefert bekommen
    (directory / "server.crt").write_bytes(cert.public_bytes(serialization.Encoding.PEM) + ca.public_bytes(serialization.Encoding.PEM))
    logger.info("Server-Zertifikat erstellt fuer: %s (gueltig bis %s)", ", ".join(names), cert.not_valid_after_utc.date())
    return cert


def _server_names(cert: x509.Certificate) -> set[str]:
    try:
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    except x509.ExtensionNotFound:
        return set()
    return {str(v).lower() for v in san.get_values_for_type(x509.DNSName)} | {
        str(v) for v in san.get_values_for_type(x509.IPAddress)
    }


def parse_names(text: str) -> list[str]:
    """Namen/Adressen aus einer Eingabe: durch Komma, Semikolon, Leerzeichen getrennt; eine eingefuegte
    Browser-Adresse (https://192.168.1.10:8443/...) wird auf den Rechnernamen reduziert."""
    names: list[str] = []
    for raw in re.split(r"[,;\s]+", text.strip().lower()):
        name = raw.split("://", 1)[-1].split("/", 1)[0]
        if name.startswith("["):  # [::1]:8443
            name = name[1:].split("]", 1)[0]
        elif name.count(":") == 1:  # name:8443
            name = name.split(":", 1)[0]
        if name and name not in names:
            names.append(name)
    return names


def validate_names(names: list[str]) -> None:
    """Wirft ValueError mit lesbarer Meldung, wenn ein Name kein Rechnername/keine Adresse ist oder nicht ins
    Heimnetz gehoert (dafuer stellt die Zertifizierungsstelle absichtlich nichts aus)."""
    for name in names:
        if not _is_ip(name) and not (len(name) <= 253 and HOST_NAME.match(name)):
            raise ValueError(_("„{name}“ ist kein gültiger Rechnername und keine IP-Adresse.", name=name))
        if not _permitted(name):
            raise ValueError(_("„{name}“ ist keine Heimnetz-Adresse (z. B. 192.168.x.x oder name.local) - für Zugriff von außen bitte ein VPN nutzen.", name=name))


def saved_names(directory: str | Path) -> list[str]:
    try:
        return parse_names((Path(directory) / HOSTNAMES_FILE).read_text(encoding="utf-8"))
    except OSError:
        return []


def apply_hostnames(directory: str | Path, text: str, env_extra: str = "") -> tuple[TlsFiles, bool]:
    """Ersteinrichtung: Namen/Adressen dauerhaft merken, Zertifikat damit neu ausstellen und in den laufenden
    Server laden (ohne Neustart). Gibt (Dateien, CA_ersetzt) zurueck; ist die CA ersetzt, muessen Geraete, die der
    alten schon vertrauen, die neue installieren (Hilfeseite /zertifikat). Die CA wird nur ersetzt, wenn sie einen
    neuen Rechnernamen ohne Punkt (z. B. "nas") nicht abdeckt - Adressen und Namen mit Punkt gehen mit der alten.
    ValueError bei ungueltigen Namen."""
    global CURRENT
    directory = Path(directory)
    new = parse_names(text)
    validate_names(new)
    directory.mkdir(parents=True, exist_ok=True)
    names = list(dict.fromkeys([*saved_names(directory), *new]))
    (directory / HOSTNAMES_FILE).write_text("\n".join(names) + "\n", encoding="utf-8")

    replaced = False
    ca_path = directory / "ca.crt"
    if ca_path.exists():
        constraints = x509.load_pem_x509_certificate(ca_path.read_bytes()).extensions.get_extension_for_class(
            x509.NameConstraints).value
        allowed = {str(d.value).lower() for d in constraints.permitted_subtrees or [] if isinstance(d, x509.DNSName)}
        if any(not _is_ip(n) and "." not in n and n not in allowed for n in new):
            for stale in ("ca.crt", "ca.key", "server.crt", "server.key"):
                (directory / stale).unlink(missing_ok=True)
            replaced = True
    files = ensure_certificates(directory, env_extra)
    CURRENT = files
    UNCOVERED.difference_update(files.names)
    for hook in RELOAD_HOOKS:
        try:
            hook(files)
        except Exception:  # noqa: BLE001 - das neue Zertifikat gilt spaetestens nach dem naechsten Start
            logger.exception("Neues Zertifikat konnte nicht in den laufenden Server geladen werden")
    return files, replaced


def ensure_certificates(directory: str | Path, extra_names: str = "") -> TlsFiles:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    try:
        directory.chmod(0o700)
    except OSError:
        pass
    wanted = detect_names(",".join([extra_names, *saved_names(directory)]))
    names = [n for n in wanted if _permitted(n)]
    for skipped in (n for n in wanted if n not in names):
        logger.warning("„%s“ ist keine Heimnetz-Adresse - das HomeDMS-Zertifikat deckt sie nicht ab "
                       "(fuer Zugriff von aussen VPN nutzen)", skipped)

    ca_cert_path, ca_key_path = directory / "ca.crt", directory / "ca.key"
    if ca_cert_path.exists() and ca_key_path.exists():
        ca = x509.load_pem_x509_certificate(ca_cert_path.read_bytes())
        ca_key = serialization.load_pem_private_key(ca_key_path.read_bytes(), password=None)
        # Neuer Rechnername ohne Punkt (z. B. umbenannter PC) ist von der alten CA nicht gedeckt
        constraints = ca.extensions.get_extension_for_class(x509.NameConstraints).value
        allowed = {str(d.value).lower() for d in constraints.permitted_subtrees or [] if isinstance(d, x509.DNSName)}
        for name in [n for n in names if not _is_ip(n) and "." not in n and n not in allowed]:
            logger.warning("Rechnername „%s“ ist neu - fuer ihn gilt die Zertifizierungsstelle nicht. Adresse mit "
                           ".local verwenden oder den TLS-Ordner loeschen (dann Zertifikat auf allen Geraeten neu "
                           "installieren).", name)
            names.remove(name)
    else:
        ca, ca_key = _create_ca(directory, names)

    cert_path = directory / "server.crt"
    server = None
    if cert_path.exists() and (directory / "server.key").exists():
        server = x509.load_pem_x509_certificate(cert_path.read_bytes())
        outdated = server.not_valid_after_utc - datetime.now(timezone.utc) < RENEW_BEFORE
        wrong_ca = server.issuer != ca.subject
        if outdated or wrong_ca or not set(names) <= _server_names(server):
            server = None
    if server is None:
        server = _create_server_cert(directory, names, ca, ca_key)
    return TlsFiles(ca_cert_path, cert_path, directory / "server.key", _fingerprint(ca),
                    tuple(sorted(_server_names(server))), server.not_valid_after_utc)


def certificate_info(directory: str | Path) -> dict | None:
    """Fuer die Diagnose: Namen, Ablaufdatum, Fingerabdruck - ohne etwas zu erzeugen."""
    directory = Path(directory)
    try:
        ca = x509.load_pem_x509_certificate((directory / "ca.crt").read_bytes())
        server = x509.load_pem_x509_certificate((directory / "server.crt").read_bytes())
    except (OSError, ValueError):
        return None
    return {"fingerprint": _fingerprint(ca), "names": sorted(_server_names(server)), "expires": server.not_valid_after_utc,
            "ca_expires": ca.not_valid_after_utc}
