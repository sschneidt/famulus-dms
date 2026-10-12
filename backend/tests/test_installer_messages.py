"""Installations- und Update-Skripte in mehreren Sprachen (scripts/*.ps1, *.sh, *.cmd, scripts/lang/*.msg).

Wie beim Frontend (src/i18n/i18n.test.ts): Jeder im Skript benutzte Text muss in allen Sprachen
vorhanden sein, mit denselben Platzhaltern - sonst sieht ein Nutzer mitten in der Installation
einen Schluesselnamen statt eines Satzes.

Familien: Windows-Installer (install-windows.ps1), Windows-Deinstallation (uninstall-windows.ps1),
Linux-Installer (install-linux.sh) und die Update-Skripte (update.ps1 + update.sh teilen sich einen Katalog).
"""
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
LANGS = ("en", "de", "ru")
LINE = re.compile(r"^\s*(\w+)\s*=\s*'((?:[^']|'')*)'\s*$")  # dasselbe Format lesen PowerShell und bash
# Katalog -> Skripte, die ihn benutzen
FAMILIES = {
    "install-windows": ("install-windows.ps1",),
    "uninstall-windows": ("uninstall-windows.ps1",),
    "install-linux": ("install-linux.sh",),
    "update": ("update.ps1", "update.sh"),
}
# Texte, die in jeder Sprache gleich lauten duerfen (Eigennamen)
SAME_IN_ALL_LANGUAGES = {  # Eigennamen und Befehlszeilen
    "install-windows": {"step_postgres"},
    "uninstall-windows": {"item_program"},
    "install-linux": {"help_2"},
    "update": set(),
}


def catalog(family: str, lang: str) -> dict[str, str]:
    text = (SCRIPTS / "lang" / f"{family}.{lang}.msg").read_text(encoding="utf-8-sig")
    return {m.group(1): m.group(2).replace("''", "'") for line in text.splitlines() if (m := LINE.match(line))}


def code_of(script: str) -> str:
    """Skripttext ohne Kommentarzeilen (dort stehen Beispiele wie  T 'key')."""
    lines = (SCRIPTS / script).read_text(encoding="utf-8").splitlines()
    return "\n".join(line for line in lines if not line.lstrip().startswith("#"))


def keys_of(script: str) -> set[str]:
    code = code_of(script)
    if script.endswith(".ps1"):
        return set(re.findall(r"\bT '(\w+)'", code))
    keys = set(re.findall(r"\$\(t (\w+)", code))                       # echo "$(t step_done ...)"
    for group in re.findall(r"for k in ([a-z0-9_ ]+); do", code):       # Hilfetexte: for k in help_1 help_2 ...; do
        keys |= set(group.split())
    return keys


def used_keys(family: str) -> set[str]:
    return set().union(*(keys_of(script) for script in FAMILIES[family]))


def placeholders(text: str) -> set[str]:
    return set(re.findall(r"\{\d\}", text))


FAMILY_LANG = [(family, lang) for family in FAMILIES for lang in LANGS]
FAMILY_TRANSLATED = [(family, lang) for family in FAMILIES for lang in ("de", "ru")]


@pytest.mark.parametrize("family", FAMILIES)
def test_skripte_benutzen_texte(family):
    assert len(used_keys(family)) > 20


@pytest.mark.parametrize(("family", "lang"), FAMILY_LANG)
def test_jeder_benutzte_text_ist_uebersetzt(family, lang):
    missing = sorted(used_keys(family) - catalog(family, lang).keys())
    assert missing == [], f"{family}/{lang}: fehlt {missing}"


@pytest.mark.parametrize(("family", "lang"), FAMILY_LANG)
def test_keine_ungenutzten_texte(family, lang):
    assert sorted(catalog(family, lang).keys() - used_keys(family)) == []


@pytest.mark.parametrize(("family", "lang"), FAMILY_TRANSLATED)
def test_platzhalter_stimmen_mit_englisch_ueberein(family, lang):
    en = catalog(family, "en")
    wrong = {k: (sorted(placeholders(en[k])), sorted(placeholders(v))) for k, v in catalog(family, lang).items()
             if k in en and placeholders(v) != placeholders(en[k])}
    assert wrong == {}


@pytest.mark.parametrize(("family", "lang"), FAMILY_TRANSLATED)
def test_texte_sind_wirklich_uebersetzt(family, lang):
    """Ein Text, der noch dem englischen gleicht, ist vermutlich vergessen worden (Eigennamen ausgenommen)."""
    en = catalog(family, "en")
    same = {k for k, v in catalog(family, lang).items() if v == en[k]}
    assert same <= SAME_IN_ALL_LANGUAGES[family], sorted(same)


def all_scripts() -> list[Path]:
    return sorted([*SCRIPTS.glob("install-*.ps1"), *SCRIPTS.glob("uninstall-*.ps1"), *SCRIPTS.glob("install-*.sh"), *SCRIPTS.glob("update*.ps1"),
                   *SCRIPTS.glob("update*.sh"), *SCRIPTS.glob("update*.cmd"), SCRIPTS / "lib" / "i18n.sh"])


def test_skripte_sind_reines_ascii():
    """Windows PowerShell 5.1 liest eine Skriptdatei ohne BOM als ANSI - Umlaute oder Kyrillisch im Code wuerden
    zerstoert. Alle sichtbaren Texte stehen deshalb in den Katalogen."""
    for path in all_scripts():
        bad = sorted({c for c in path.read_text(encoding="utf-8-sig") if ord(c) > 127})
        assert bad == [], f"{path.name}: {bad}"


def test_shell_skripte_haben_unix_zeilenenden():
    """CRLF in einem Shell-Skript bricht es unter Linux ('bash\\r: command not found')."""
    for path in all_scripts():
        if path.suffix == ".sh":
            assert b"\r" not in path.read_bytes(), path.name


def test_kataloge_sind_utf8():
    for path in (SCRIPTS / "lang").glob("*.msg"):
        path.read_bytes().decode("utf-8-sig")


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("name", ["install-windows.{lang}.ps1", "uninstall-windows.{lang}.ps1", "install-linux.{lang}.sh",
                                  "update.{lang}.sh", "update.{lang}.cmd"])
def test_startskript_je_sprache(name, lang):
    script = (SCRIPTS / name.format(lang=lang)).read_text(encoding="utf-8")
    if name.startswith(("install-windows", "uninstall-windows")):
        assert f'Language   = "{lang}"' in script
    elif name.endswith(".cmd"):
        assert f"-Language {lang} %*" in script
    else:
        assert f"FAMULUS_LANG={lang} exec" in script


def test_hauptskripte_kennen_alle_sprachen():
    for script in ("install-windows.ps1", "uninstall-windows.ps1", "update.ps1"):
        assert 'ValidateSet("auto", "de", "en", "ru")' in (SCRIPTS / script).read_text(encoding="utf-8")
    for family in FAMILIES:
        assert not [lang for lang in LANGS if not (SCRIPTS / "lang" / f"{family}.{lang}.msg").exists()]


# --- Die Shell-Skripte wirklich starten (nur --help: ohne root, ohne Docker, ohne Aenderungen) -----------

def _working_bash() -> str | None:
    bash = shutil.which("bash")
    if not bash:
        return None
    try:
        out = subprocess.run([bash, "-c", "echo ok"], capture_output=True, text=True, timeout=20, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return bash if out.stdout.strip() == "ok" else None


BASH = _working_bash()
FIRST_HELP_LINE = {"install-linux": {"en": "Install Famulus DMS", "de": "Famulus DMS auf einem Linux-Server", "ru": "Установка Famulus DMS"},
                   "update": {"en": "Update Famulus DMS", "de": "Famulus DMS aktualisieren", "ru": "Обновление Famulus DMS"}}


@pytest.mark.skipif(BASH is None, reason="bash ist auf diesem Rechner nicht verfuegbar (Linux, macOS, Git Bash)")
@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("script", ["install-linux", "update"])
def test_hilfe_erscheint_in_der_sprache(script, lang):
    # relativer Pfad + cwd: funktioniert mit Linux-bash, Git Bash und dem WSL-Starter (versteht keine D:\-Pfade)
    result = subprocess.run([BASH, f"{script}.{lang}.sh", "--help"], capture_output=True, timeout=30, check=False, cwd=SCRIPTS)
    output = result.stdout.decode("utf-8")
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    assert output.startswith(FIRST_HELP_LINE[script][lang]), output[:120]


@pytest.mark.skipif(BASH is None, reason="bash ist auf diesem Rechner nicht verfuegbar (Linux, macOS, Git Bash)")
@pytest.mark.parametrize("script", ["install-linux.sh", "update.sh"])
def test_sprache_per_parameter_und_unbekannte_option(script):
    ok = subprocess.run([BASH, script, "--lang", "ru", "--help"], capture_output=True, timeout=30, check=False, cwd=SCRIPTS)
    assert "Famulus DMS" in ok.stdout.decode("utf-8") and any("а" <= c <= "я" for c in ok.stdout.decode("utf-8"))
    bad = subprocess.run([BASH, script, "--lang=de", "--gibt-es-nicht"], capture_output=True, timeout=30, check=False, cwd=SCRIPTS)
    assert bad.returncode != 0
    assert "Unbekannte Option: --gibt-es-nicht" in bad.stderr.decode("utf-8")


# --- Schutz der Deinstallation: Welche Ordner duerfen geloescht werden? ----------------------------------

POWERSHELL = shutil.which("powershell") or shutil.which("pwsh")


@pytest.mark.skipif(os.name != "nt" or POWERSHELL is None, reason="Windows-Pfade: nur unter Windows mit PowerShell")
def test_deinstallation_loescht_nur_datenordner_der_anwendung(tmp_path):
    """Test-DataFolderSafe aus uninstall-windows.ps1: Laufwerke, Systemordner, der Programmordner und
    beliebige Ordner ohne documents/tls duerfen nie geloescht werden."""
    data = tmp_path / "Famulus-Data"
    (data / "documents").mkdir(parents=True)
    (data / "tls").mkdir()
    fremd = tmp_path / "Eigene Dateien"
    fremd.mkdir()
    app = tmp_path / "app"
    (app / "inner").mkdir(parents=True)
    probe = tmp_path / "probe.ps1"
    probe.write_text(
        f"""$ast = [System.Management.Automation.Language.Parser]::ParseFile("{SCRIPTS / 'uninstall-windows.ps1'}", [ref]$null, [ref]$null)
$fn = $ast.Find({{ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq "Test-DataFolderSafe" }}, $true)
Invoke-Expression $fn.Extent.Text
$script:AppDir = "{app}"
foreach ($p in "{data}", "{data}\", "{fremd}", "{app}", "{app / 'inner'}", "{tmp_path.anchor}", $env:SystemRoot, $env:ProgramFiles, $env:USERPROFILE, "") {{
    "{{0}}|{{1}}" -f $p, (Test-DataFolderSafe $p)
}}
""", encoding="utf-8")
    out = subprocess.run([POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(probe)],
                         capture_output=True, text=True, timeout=60, check=False).stdout.strip().splitlines()
    answers = [line.rsplit("|", 1)[1] for line in out]
    assert answers[:2] == ["True", "True"], out          # der echte Datenordner (auch mit abschliessendem \)
    assert set(answers[2:]) == {"False"}, out            # alles andere


def _probelauf(tmp_path, *extra: str) -> tuple[str, Path]:
    data = tmp_path / "Famulus-Data"
    (data / "documents").mkdir(parents=True)
    (data / "tls").mkdir()
    (data / "documents" / "wichtig.pdf").write_bytes(b"%PDF-")
    result = subprocess.run(
        [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPTS / "uninstall-windows.ps1"),
         "-Language", "en", "-DryRun", "-DataFolder", str(data), *extra],
        capture_output=True, timeout=300, check=False, stdin=subprocess.DEVNULL)
    return result.stdout.decode("utf-8", "replace") + result.stderr.decode("utf-8", "replace"), data


@pytest.mark.skipif(os.name != "nt" or POWERSHELL is None, reason="Windows-Skript: nur unter Windows mit PowerShell")
def test_probelauf_ohne_eingabe_bricht_ab_und_aendert_nichts(tmp_path):
    out, data = _probelauf(tmp_path)
    assert "DRY RUN" in out
    assert "No input possible" in out and "Cancelled - nothing was changed." in out
    assert (data / "documents" / "wichtig.pdf").exists()


@pytest.mark.skipif(os.name != "nt" or POWERSHELL is None, reason="Windows-Skript: nur unter Windows mit PowerShell")
def test_probelauf_mit_ja_zeigt_den_ganzen_plan_und_loescht_nichts(tmp_path):
    """-DryRun -Yes beantwortet ALLE Fragen mit Ja (auch Datenordner und Programme): trotzdem darf nichts passieren."""
    out, data = _probelauf(tmp_path, "-Yes")
    assert "Planned steps:" in out and f"delete the data folder {data}" in out
    assert out.count("(dry run: not executed)") >= 5
    assert "Done. Famulus DMS was removed as selected." in out
    assert (data / "documents" / "wichtig.pdf").exists()                      # Datenordner unberuehrt
    assert (SCRIPTS.parent / "backend" / "pyproject.toml").exists()           # Programmordner unberuehrt


@pytest.mark.skipif(os.name != "nt" or POWERSHELL is None, reason="Windows-Skript: nur unter Windows mit PowerShell")
def test_echter_lauf_ohne_administrator_bricht_ab(tmp_path):
    if subprocess.run(["net", "session"], capture_output=True, check=False).returncode == 0:
        pytest.skip("Die Tests laufen mit Administratorrechten - der Abbruch ohne Administrator ist hier nicht pruefbar")
    data = tmp_path / "Famulus-Data"
    (data / "documents").mkdir(parents=True)
    (data / "tls").mkdir()
    result = subprocess.run(
        [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPTS / "uninstall-windows.ps1"),
         "-Language", "en", "-DataFolder", str(data), "-Yes"],
        capture_output=True, timeout=120, check=False, stdin=subprocess.DEVNULL)
    assert "Please start PowerShell as administrator" in result.stdout.decode("utf-8", "replace")
    assert data.exists()
