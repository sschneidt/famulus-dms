"""Versionsnummer: eine Quelle in homedms/__init__.py, pyproject.toml und CHANGELOG.md ziehen mit."""
import re
from pathlib import Path

import homedms

BACKEND = Path(__file__).resolve().parents[1]
CHANGELOG = BACKEND.parent / "CHANGELOG.md"


def test_version_ist_semver():
    assert re.fullmatch(r"\d+\.\d+\.\d+", homedms.__version__)


def test_pyproject_hat_dieselbe_version():
    text = (BACKEND / "pyproject.toml").read_text(encoding="utf-8")  # kein tomllib: Python 3.10 hat es nicht
    assert re.search(rf'^version = "{re.escape(homedms.__version__)}"$', text, re.MULTILINE)


async def test_diagnose_zeigt_die_version_aus_dem_code():
    """Frueher stand dort eine fest eingetragene Version - im Docker-Image zeigte die Diagnose dann immer die alte."""
    from homedms.core import diagnostics

    component = await diagnostics.check_app()
    assert dict(component.details)["Version"] == homedms.__version__


def test_changelog_hat_einen_eintrag_fuer_die_version():
    text = CHANGELOG.read_text(encoding="utf-8")
    assert re.search(rf"^## \[{re.escape(homedms.__version__)}\] – \d{{4}}-\d{{2}}-\d{{2}}$", text, re.MULTILINE)
