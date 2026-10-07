"""Famulus DMS Backend.

Die Versionsnummer steht hier UND in pyproject.toml (im Docker-Image ist das Projekt nicht als Paket
installiert, importlib.metadata taugt dort also nicht) - tests/test_version.py prueft, dass beide
und der oberste Eintrag in CHANGELOG.md zusammenpassen. Release-Ablauf: docs/Updates.md.
"""
__version__ = "0.2.0"
