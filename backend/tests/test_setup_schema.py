"""Einrichtung: Ohne Haushaltsname heisst der Haushalt "Home" (homedms/schemas/setup.py)."""
import pytest

from homedms.schemas.setup import BootstrapRequest

BASE = {
    "admin_email": "max@example.com", "admin_password": "ein-langes-Passwort",
    "admin_display_name": "Max", "setup_code": "abc",
}


def test_ohne_haushaltsnamen_wird_home_genommen():
    assert BootstrapRequest(**BASE).household_name == "Home"


@pytest.mark.parametrize("value", ["", "   ", None])
def test_leerer_haushaltsname_wird_home(value):
    assert BootstrapRequest(**BASE, household_name=value).household_name == "Home"


def test_angegebener_name_bleibt_und_wird_getrimmt():
    assert BootstrapRequest(**BASE, household_name="  Familie Muster ").household_name == "Familie Muster"
