# Update-Helfer als Container (nicht dokumentiert, nur fuer Eingeweihte): fuehrt dasselbe Skript aus wie die Aufgabe
# im Aufgabenplaner der Synology (docs/Installation-Synology.md), aber dauernd und ohne eigene Planung.
# Einbinden: docker-compose.updater.yml. Build-Kontext ist das Repo-Wurzelverzeichnis.
FROM docker:cli
COPY scripts/update-agent.sh /usr/local/bin/update-agent.sh
ENV UPDATE_DIR=/backups
ENTRYPOINT ["sh", "/usr/local/bin/update-agent.sh", "--loop"]
