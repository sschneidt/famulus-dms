"""Installations- und Update-Skripte in mehreren Sprachen (scripts/*.ps1, *.sh, *.cmd, scripts/lang/*.msg).

Wie beim Frontend (src/i18n/i18n.test.ts): Jeder im Skript benutzte Text muss in allen Sprachen
vorhanden sein, mit denselben Platzhaltern - sonst sieht ein Nutzer mitten in der Installation
einen Schluesselnamen statt eines Satzes.

Familien: Windows-Installer (install-windows.ps1), Linux-Installer (install-linux.sh) und die
Update-Skripte (update.ps1 + update.sh teilen sich einen Katalog).
"""
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
    "install-linux": ("install-linux.sh",),
    "update": ("update.ps1", "update.sh"),
}
# Texte, die in jeder Sprache gleich lauten duerfen (Eigennamen)
SAME_IN_ALL_LANGUAGES = {"install-windows": {"step_postgres"}, "install-linux": {"help_2"}, "update": set()}  # help_2 = Befehlszeile


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
    return sorted([*SCRIPTS.glob("install-*.ps1"), *SCRIPTS.glob("install-*.sh"), *SCRIPTS.glob("update*.ps1"),
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
@pytest.mark.parametrize("name", ["install-windows.{lang}.ps1", "install-linux.{lang}.sh", "update.{lang}.sh", "update.{lang}.cmd"])
def test_startskript_je_sprache(name, lang):
    script = (SCRIPTS / name.format(lang=lang)).read_text(encoding="utf-8")
    if name.startswith("install-windows"):
        assert f'Language   = "{lang}"' in script
    elif name.endswith(".cmd"):
        assert f"-Language {lang} %*" in script
    else:
        assert f"FAMULUS_LANG={lang} exec" in script


def test_hauptskripte_kennen_alle_sprachen():
    for script in ("install-windows.ps1", "update.ps1"):
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
