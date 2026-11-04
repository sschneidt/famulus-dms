#!/bin/sh
# Famulus DMS: Update-Helfer. Fuehrt ein in der Anwendung angefordertes Update aus (Diagnose > "Jetzt aktualisieren").
#
# Die Anwendung selbst hat KEINEN Zugriff auf Docker. Sie legt nur eine Anforderung in den Sicherungsordner
# (update-request.txt, Zeile "version=X.Y.Z") - dieses Skript holt sie dort ab und macht das Update:
#   1. neue Version laden (docker pull) - schlaegt das fehl, bleibt alles wie es ist
#   2. die Versionsnummer im Image der Compose-Datei austauschen (alte Datei bleibt als *.vorher liegen)
#   3. app-api und app-worker neu erzeugen (docker compose up -d)
#   4. warten, bis die neue Version meldet, dass sie gesund ist; sonst alte Compose-Datei zurueck
# Die Datenbank wird NICHT hier gesichert, sondern von der Anwendung, bevor sie die Anforderung schreibt.
#
# Aufruf:  sh update-agent.sh          einmal pruefen und ausfuehren (Aufgabenplaner der Synology, jede Minute)
#          sh update-agent.sh --loop   dauernd laufen, alle 10 Sekunden pruefen (als Container)
# Einstellungen (Umgebungsvariablen), alle optional:
#   UPDATE_DIR       Sicherungsordner, in dem Anforderung und Status liegen   (Standard /volume1/famulus/backups)
#   COMPOSE_PROJECT  Name des Compose-Projekts                                (Standard homedms)
#   COMPOSE_FILE     Pfad der Compose-Datei (sonst aus den Docker-Etiketten des Projekts)
#   FAMULUS_IMAGE    Image ohne Versionsnummer                                (Standard ghcr.io/sschneidt/famulus-dms)
#   HEALTH_WAIT      Sekunden, die auf die neue Version gewartet wird         (Standard 240)
#   HEALTH_POLL      Sekunden zwischen zwei Pruefungen                        (Standard 5)
#
# Sicherheit: Der Inhalt von update-request.txt kommt aus der Anwendung und gilt als nicht vertrauenswuerdig. Es wird
# nur eine Versionsnummer der Form X.Y.Z daraus gelesen; geladen wird ausschliesslich FAMULUS_IMAGE:X.Y.Z.
# Dieses Skript muss an einem Ort liegen, an den die Anwendung nicht schreiben kann (nicht im Sicherungsordner!).

PATH="$PATH:/usr/local/bin:/usr/syno/bin:/usr/bin:/bin"
DIR="${UPDATE_DIR:-/volume1/famulus/backups}"
PROJECT="${COMPOSE_PROJECT:-homedms}"
IMAGE="${FAMULUS_IMAGE:-ghcr.io/sschneidt/famulus-dms}"
WAIT="${HEALTH_WAIT:-240}"
LOCK="${TMPDIR:-/tmp}/famulus-update.lock"
REQUEST="$DIR/update-request.txt"
STATUS="$DIR/update-status.json"
BEAT="$DIR/update-agent.txt"

now() { date +%s; }

# Dateien werden ueber eine Hilfsdatei geschrieben und umbenannt: ein Link, den die Anwendung dort abgelegt hat,
# wird so ersetzt statt befolgt.
put() { # put <Datei> <Inhalt>
    tmp="$DIR/.update-tmp.$$"
    printf '%s\n' "$2" > "$tmp" && mv -f "$tmp" "$1"
}

heartbeat() { put "$BEAT" "$(now)"; }

# status <Zustand> <Version> [<Hinweis>]  - Zustaende: checking pulling restarting health done failed rolled_back
status() {
    detail=$(printf '%s' "${3:-}" | tr -c 'A-Za-z0-9 ._:/=-' '_' | cut -c1-200)
    put "$STATUS" "{\"state\":\"$1\",\"version\":\"$2\",\"detail\":\"$detail\",\"at\":$(now)}"
}

compose() {
    if docker compose version >/dev/null 2>&1; then
        docker compose "$@"
    else
        docker-compose "$@"
    fi
}

service_container() { # Container-Nummer eines Dienstes des Projekts
    docker ps -aq --filter "label=com.docker.compose.project=$PROJECT" --filter "label=com.docker.compose.service=$1" | head -n 1
}

find_compose_file() {
    if [ -n "${COMPOSE_FILE:-}" ]; then
        printf '%s' "$COMPOSE_FILE"
        return
    fi
    cid=$(service_container app-api)
    [ -n "$cid" ] || return 1
    docker inspect --format '{{ index .Config.Labels "com.docker.compose.project.config_files" }}' "$cid" | cut -d, -f1
}

wait_healthy() { # wait_healthy <Version>
    end=$(( $(now) + WAIT ))
    while [ "$(now)" -lt "$end" ]; do
        cid=$(service_container app-api)
        if [ -n "$cid" ]; then
            image=$(docker inspect --format '{{.Config.Image}}' "$cid" 2>/dev/null)
            health=$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{end}}' "$cid" 2>/dev/null)
            [ "$image" = "$IMAGE:$1" ] && [ "$health" = "healthy" ] && return 0
        fi
        sleep "${HEALTH_POLL:-5}"
    done
    return 1
}

run_update() {
    version="$1"
    status checking "$version"
    file=$(find_compose_file)
    if [ -z "$file" ] || [ ! -f "$file" ] || ! grep -q "$IMAGE:" "$file"; then
        status failed "$version" "Compose-Datei des Projekts $PROJECT nicht gefunden (COMPOSE_FILE setzen)"
        return 1
    fi

    status pulling "$version"
    if ! docker pull "$IMAGE:$version" >/dev/null 2>&1; then
        status failed "$version" "Image $IMAGE:$version konnte nicht geladen werden - nichts wurde veraendert"
        return 1
    fi

    status restarting "$version"
    cp -p "$file" "$file.vorher" || { status failed "$version" "Compose-Datei nicht beschreibbar"; return 1; }
    escaped=$(printf '%s' "$IMAGE" | sed 's/[.]/\\./g')
    if ! sed -i "s#$escaped:[A-Za-z0-9._-]*#$IMAGE:$version#g" "$file"; then
        cp -p "$file.vorher" "$file"
        status failed "$version" "Compose-Datei konnte nicht geaendert werden"
        return 1
    fi
    dir=$(dirname "$file")
    if ! (cd "$dir" && compose -p "$PROJECT" -f "$file" up -d app-api app-worker >/dev/null 2>&1); then
        status rolled_back "$version" "Neustart fehlgeschlagen - alte Compose-Datei zurueckgespielt"
        cp -p "$file.vorher" "$file"
        (cd "$dir" && compose -p "$PROJECT" -f "$file" up -d app-api app-worker >/dev/null 2>&1)
        return 1
    fi

    status health "$version"
    if wait_healthy "$version"; then
        status done "$version"
        return 0
    fi
    cp -p "$file.vorher" "$file"
    (cd "$dir" && compose -p "$PROJECT" -f "$file" up -d app-api app-worker >/dev/null 2>&1)
    status rolled_back "$version" "Die neue Version wurde nicht gesund - die alte laeuft wieder. Datenbank ggf. aus der Sicherung"
    return 1
}

once() {
    [ -d "$DIR" ] || return 0
    heartbeat
    [ -f "$REQUEST" ] && [ ! -L "$REQUEST" ] || return 0
    version=$(sed -n 's/^version=\([0-9]\{1,4\}\.[0-9]\{1,4\}\.[0-9]\{1,4\}\)[[:space:]]*$/\1/p' "$REQUEST" | head -n 1)
    rm -f "$REQUEST"
    if [ -z "$version" ]; then
        status failed "" "Ungueltige Anforderung"
        return 0
    fi
    run_update "$version"
}

# Nur ein Lauf gleichzeitig (der Aufgabenplaner startet jede Minute einen neuen)
if ! mkdir "$LOCK" 2>/dev/null; then
    # Sperre aelter als 30 Minuten: ein abgebrochener Lauf, aufraeumen
    if [ -n "$(find "$LOCK" -maxdepth 0 -mmin +30 2>/dev/null)" ]; then
        rmdir "$LOCK" 2>/dev/null
        mkdir "$LOCK" 2>/dev/null || exit 0
    else
        exit 0
    fi
fi
trap 'rmdir "$LOCK" 2>/dev/null' EXIT

if [ "${1:-}" = "--loop" ]; then
    while :; do
        once
        sleep 10
    done
else
    once
fi
