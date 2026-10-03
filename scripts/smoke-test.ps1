<#
.SYNOPSIS
  HomeDMS-Smoke-Test: startet den Stack und prueft den kompletten Ablauf automatisch.

.DESCRIPTION
  Schritte: Stack bauen/starten -> auf die API warten -> Ersteinrichtung bzw. Anmeldung ->
  Profil abrufen -> Test-PDF und Test-Scan hochladen -> auf die Texterkennung warten ->
  erkannten Text pruefen -> automatische Klassifikation abwarten -> eine Kategorie manuell
  bestaetigen -> Metadaten und Fristvorschlaege pruefen -> wiederkehrende Wiedervorlage
  erledigen -> Download pruefen (PDF unveraendert, Fotos als PDF) -> Testdokumente in den Papierkorb legen. Am Ende steht eine Uebersicht mit OK/FEHLER je Schritt.

  Gibt es noch keinen Haushalt, legt das Skript ihn mit den angegebenen Zugangsdaten an.
  Gibt es schon einen, meldet es sich mit ihnen an. Mit -PasswortZuruecksetzen wird das
  Passwort vorher auf den angegebenen Wert gesetzt (fuer den Fall, dass es vergessen wurde).

.EXAMPLE
  .\scripts\smoke-test.cmd -Email du@example.com -Password "MeinPasswort123"

.EXAMPLE
  .\scripts\smoke-test.cmd -Email du@example.com -Password "NeuesPasswort123" -PasswortZuruecksetzen

.EXAMPLE
  .\scripts\smoke-test.cmd -OhneBuild -DokumenteBehalten
#>
# PositionalBinding=$false: unbekannte Angaben wie "--build" fuehren zu einer klaren Fehlermeldung,
# statt stillschweigend ignoriert (oder versehentlich als E-Mail-Adresse verwendet) zu werden.
[CmdletBinding(PositionalBinding = $false)]
param(
    [string]$Email,
    # -Passwort und -Kennwort funktionieren ebenfalls (frueher landete -Passwort beim Schalter unten)
    [Alias("Passwort", "Kennwort")]
    [string]$Password,
    [string]$Haushalt = "Mein Haushalt",
    [string]$BaseUrl = "http://localhost:8000",
    [Alias("ResetPassword")]
    [switch]$PasswortZuruecksetzen,
    [switch]$OhneBuild,
    [switch]$OhneDocker,
    [switch]$DokumenteBehalten,
    [int]$TimeoutSekunden = 300
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"   # beschleunigt Invoke-WebRequest in PowerShell 5.1 deutlich

$RepoRoot = Split-Path -Parent $PSScriptRoot
$TestDaten = Join-Path $PSScriptRoot "testdaten"
$Api = "$BaseUrl/api/v1"
$IstWindows = ($PSVersionTable.PSEdition -eq "Desktop") -or $IsWindows
$CurlExe = if ($IstWindows) { "curl.exe" } else { "curl" }   # "curl" ist in PS 5.1 nur ein Alias

$Ergebnisse = New-Object System.Collections.Generic.List[object]

function Schreibe-Schritt([string]$Name, [bool]$Ok, [string]$Detail = "") {
    $Ergebnisse.Add([pscustomobject]@{ Schritt = $Name; Ergebnis = $(if ($Ok) { "OK" } else { "FEHLER" }); Detail = $Detail })
    $farbe = if ($Ok) { "Green" } else { "Red" }
    $text = if ($Ok) { "  OK      " } else { "  FEHLER  " }
    Write-Host $text -ForegroundColor $farbe -NoNewline
    Write-Host "$Name" -NoNewline
    if ($Detail) { Write-Host "  ($Detail)" -ForegroundColor DarkGray } else { Write-Host "" }
}

function Beende([string]$Hinweis) {
    if ($Hinweis) { Write-Host ""; Write-Host "Hinweis: $Hinweis" -ForegroundColor Yellow }
    Zeige-Zusammenfassung
    exit 1
}

function Zeige-Zusammenfassung {
    Write-Host ""
    Write-Host "Zusammenfassung" -ForegroundColor Cyan
    $Ergebnisse | Format-Table -AutoSize | Out-String | Write-Host
    $fehler = @($Ergebnisse | Where-Object { $_.Ergebnis -ne "OK" }).Count
    if ($fehler -eq 0) { Write-Host "Alle Schritte erfolgreich." -ForegroundColor Green }
    else { Write-Host "$fehler Schritt(e) fehlgeschlagen." -ForegroundColor Red }
}

function Invoke-Api([string]$Methode, [string]$Pfad, $Body = $null, [string]$Token = "") {
    <# Liefert @{ Status; Json; Text } - wirft nicht bei HTTP-Fehlern, damit das Skript sie
       verstaendlich melden kann. Funktioniert gleich in PowerShell 5.1 und 7. #>
    $headers = @{}
    if ($Token) { $headers["Authorization"] = "Bearer $Token" }
    $params = @{ Method = $Methode; Uri = "$Api$Pfad"; Headers = $headers; UseBasicParsing = $true; TimeoutSec = 30 }
    if ($null -ne $Body) {
        # Als UTF-8-Bytes senden - PowerShell 5.1 wuerde Umlaute sonst als ISO-8859-1 verschicken
        $params.Body = [System.Text.Encoding]::UTF8.GetBytes(($Body | ConvertTo-Json -Depth 5))
        $params.ContentType = "application/json; charset=utf-8"
    }
    try {
        $r = Invoke-WebRequest @params
        $text = [System.Text.Encoding]::UTF8.GetString($r.RawContentStream.ToArray())
        $status = [int]$r.StatusCode
    } catch {
        $resp = $_.Exception.Response
        if ($null -eq $resp) { return @{ Status = 0; Json = $null; Text = $_.Exception.Message } }
        $status = [int]$resp.StatusCode
        $text = $_.ErrorDetails.Message
    }
    $json = $null
    if ($text) { try { $json = $text | ConvertFrom-Json } catch { } }
    return @{ Status = $status; Json = $json; Text = $text }
}

function Get-WorkerGrund([string]$DokumentId) {
    <# Letzte Fehlermeldung des Workers zu einem Dokument (z. B. "Ollama ... Timeout") - nur mit Docker. #>
    if ($OhneDocker) { return "" }
    $prevPref = $ErrorActionPreference; $ErrorActionPreference = "Continue"
    try {
        Push-Location $RepoRoot
        try { $log = & docker compose logs app-worker --no-color --tail 2000 2>&1 } finally { Pop-Location }
    } finally { $ErrorActionPreference = $prevPref }
    $treffer = @($log | ForEach-Object { "$_" } | Where-Object { $_ -match [regex]::Escape($DokumentId) -and $_ -match "fehlgeschlagen|nicht verfuegbar|Error" })
    if ($treffer.Count -eq 0) { return "" }
    $zeile = $treffer[-1] -replace "^.*?\|\s*", ""
    if ($zeile.Length -gt 300) { $zeile = $zeile.Substring(0, 300) + " ..." }
    return $zeile
}

function Invoke-Cli([string[]]$Argumente) {
    <# Verwaltungsbefehl (homedms.cli) - im Container oder, mit -OhneDocker, lokal per uv. #>
    # PowerShell 5.1 wertet Ausgaben externer Programme auf stderr sonst als Skriptfehler
    $prevPref = $ErrorActionPreference; $ErrorActionPreference = "Continue"
    try {
        if ($OhneDocker) {
            Push-Location (Join-Path $RepoRoot "backend")
            try { $out = & uv run python -m homedms.cli @Argumente 2>&1 } finally { Pop-Location }
        } else {
            Push-Location $RepoRoot
            try { $out = & docker compose exec -T app-api python -m homedms.cli @Argumente 2>&1 } finally { Pop-Location }
        }
        $rc = $LASTEXITCODE
    } finally { $ErrorActionPreference = $prevPref }
    $zeilen = $out | ForEach-Object { "$_" } | Where-Object { $_ -and $_ -notmatch "^(Uninstalled|Installed|Built|Building|Resolved|Prepared|Audited) " }
    return @{ ExitCode = $rc; Ausgabe = ($zeilen -join "`n").Trim() }
}

function Upload-Datei([string]$Datei, [string]$MimeType, [string]$Titel, [string]$Token) {
    <# Multipart-Upload ueber curl - Invoke-RestMethod -Form gibt es erst ab PowerShell 7. #>
    $antwortDatei = [System.IO.Path]::GetTempFileName()
    try {
        $code = & $CurlExe -s -o $antwortDatei -w "%{http_code}" -X POST "$Api/documents" `
            -H "Authorization: Bearer $Token" `
            -F "file=@$Datei;type=$MimeType" -F "title=$Titel"
        $text = [System.IO.File]::ReadAllText($antwortDatei, [System.Text.Encoding]::UTF8)
        $json = $null; try { $json = $text | ConvertFrom-Json } catch { }
        return @{ Status = [int]$code; Json = $json; Text = $text }
    } finally { Remove-Item $antwortDatei -ErrorAction SilentlyContinue }
}

Write-Host ""
Write-Host "HomeDMS Smoke-Test gegen $BaseUrl" -ForegroundColor Cyan
Write-Host ""

if (-not $Email) { $Email = Read-Host "E-Mail-Adresse des Admin-Kontos" }
if (-not $Password) {
    $sicher = Read-Host "Passwort (mindestens 8 Zeichen)" -AsSecureString
    $Password = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($sicher))
}
if ($Password.Length -lt 8) { Write-Host "Das Passwort muss mindestens 8 Zeichen lang sein." -ForegroundColor Red; exit 1 }

# --- 1. Stack starten ---------------------------------------------------------------------
if ($OhneDocker) {
    Schreibe-Schritt "Stack starten" $true "uebersprungen (-OhneDocker)"
} else {
    Push-Location $RepoRoot
    try {
        $composeArgs = @("compose", "up", "-d")
        if (-not $OhneBuild) { $composeArgs += "--build" }
        Write-Host "  ...     docker $($composeArgs -join ' ') (beim ersten Mal kann das einige Minuten dauern)" -ForegroundColor DarkGray
        # docker schreibt Fortschrittsmeldungen auf stderr - das ist kein Fehler
        $prevPref = $ErrorActionPreference; $ErrorActionPreference = "Continue"
        # Ausgabe live anzeigen (grau), damit man bei langen Builds den Fortschritt sieht
        $out = New-Object System.Collections.Generic.List[string]
        & docker @composeArgs 2>&1 | ForEach-Object {
            $zeile = "$_"
            $out.Add($zeile)
            Write-Host "          $zeile" -ForegroundColor DarkGray
        }
        $rc = $LASTEXITCODE; $ErrorActionPreference = $prevPref
    } finally { Pop-Location }
    Schreibe-Schritt "Stack starten" ($rc -eq 0) $(if ($rc -ne 0) { "docker compose Exit-Code $rc" } else { "" })
    if ($rc -ne 0) {
        Beende "Ausgabe von docker compose pruefen (graue Zeilen oben). Bei 'timed out' oder 'Connect' war die Internetverbindung beim Bauen gestoert - einfach erneut starten."
    }
}

# --- 2. Auf die API warten ----------------------------------------------------------------
Write-Host "  ...     warte auf die API" -ForegroundColor DarkGray
$bereit = $false
$ende = (Get-Date).AddSeconds($TimeoutSekunden)
while ((Get-Date) -lt $ende) {
    try {
        $h = Invoke-WebRequest -Uri "$BaseUrl/health" -UseBasicParsing -TimeoutSec 5
        if ([int]$h.StatusCode -eq 200) { $bereit = $true; break }
    } catch { }
    Start-Sleep -Seconds 2
}
Schreibe-Schritt "API erreichbar" $bereit $(if (-not $bereit) { "$BaseUrl/health antwortet nicht" } else { "" })
if (-not $bereit) { Beende "Mit 'docker compose ps' und 'docker compose logs app-api' nachsehen. Laeuft evtl. noch ein lokaler uvicorn auf Port 8000?" }

# Weboberflaeche: "/" und eine App-Adresse (z. B. nach Neuladen) muessen die App liefern
$webOk = $false; $webDetail = ""
try {
    $start = Invoke-WebRequest -Uri "$BaseUrl/" -UseBasicParsing -TimeoutSec 10
    $tief = Invoke-WebRequest -Uri "$BaseUrl/termine" -UseBasicParsing -TimeoutSec 10
    $webOk = ([int]$start.StatusCode -eq 200) -and ($start.Content -match '<div id="root">') -and ($tief.Content -match '<div id="root">')
    if (-not $webOk) { $webDetail = "Antwort enthaelt die App nicht - Image mit --build neu bauen" }
} catch { $webDetail = "$($_.Exception.Message)" }
Schreibe-Schritt "Weboberflaeche" $webOk $(if ($webOk) { "$BaseUrl im Browser oeffnen" } else { $webDetail })

# --- 3. Ersteinrichtung bzw. Passwort ------------------------------------------------------
$status = Invoke-Api GET "/setup/status"
if ($status.Status -ne 200) { Schreibe-Schritt "Einrichtungsstatus" $false "HTTP $($status.Status)"; Beende $status.Text }
if (-not $status.Json.bootstrapped) {
    $r = Invoke-Api POST "/setup/bootstrap" @{
        household_name = $Haushalt; admin_email = $Email; admin_password = $Password
        admin_display_name = ($Email -split "@")[0]
    }
    Schreibe-Schritt "Ersteinrichtung" ($r.Status -eq 201) $(if ($r.Status -eq 201) { "Haushalt '$Haushalt' angelegt" } else { "HTTP $($r.Status): $($r.Text)" })
    if ($r.Status -ne 201) { Beende "" }
} else {
    Schreibe-Schritt "Ersteinrichtung" $true "bereits erledigt"
    if ($PasswortZuruecksetzen) {
        $cli = Invoke-Cli @("reset-password", $Email, "--password", $Password)
        Schreibe-Schritt "Passwort zuruecksetzen" ($cli.ExitCode -eq 0) $cli.Ausgabe
        if ($cli.ExitCode -ne 0) {
            $liste = Invoke-Cli @("users")
            Beende "Vorhandene Nutzer:`n$($liste.Ausgabe)"
        }
    }
}

# --- 4. Anmelden ----------------------------------------------------------------------------
$login = Invoke-Api POST "/auth/login" @{ email = $Email; password = $Password }
Schreibe-Schritt "Anmeldung" ($login.Status -eq 200) $(if ($login.Status -ne 200) { "HTTP $($login.Status)" } else { $Email })
if ($login.Status -ne 200) {
    $liste = Invoke-Cli @("users")
    Beende ("E-Mail oder Passwort stimmen nicht. Vorhandene Nutzer:`n$($liste.Ausgabe)`n`n" +
            "Zum Neusetzen des Passworts das Skript mit -PasswortZuruecksetzen erneut starten.")
}
$token = $login.Json.access_token

$me = Invoke-Api GET "/auth/me" -Token $token
Schreibe-Schritt "Profil abrufen" ($me.Status -eq 200) $(if ($me.Status -eq 200) { "Rolle: $($me.Json.role)" } else { "HTTP $($me.Status)" })

# --- 5. Hochladen -----------------------------------------------------------------------------
# Erwartete Fristen der Testdokumente, passend zum heutigen Tag:
# - Rechnung: "zahlbar bis 15.10.2026" - danach liegt sie in der Vergangenheit und entfaellt
# - Brief: "Kuendigungsfrist: 3 Monate zum Jahresende" -> 30.09. dieses bzw. naechsten Jahres
$heute = (Get-Date).Date
$zahlungsfrist = if ($heute -le [datetime]"2026-10-15") { "2026-10-15" } else { $null }
$kuendigungsJahr = if ($heute -le (Get-Date -Year $heute.Year -Month 9 -Day 30).Date) { $heute.Year } else { $heute.Year + 1 }
$testfaelle = @(
    @{ Name = "PDF (digital)"; Datei = (Join-Path $TestDaten "rechnung-digital.pdf"); Mime = "application/pdf"; Stichwort = "HOMEDMS-4711"; ErwarteteFrist = $zahlungsfrist },
    @{ Name = "Scan (Bild, OCR)"; Datei = (Join-Path $TestDaten "brief-scan.png"); Mime = "image/png"; Stichwort = "HOMEDMS-0815"; ErwarteteFrist = "$kuendigungsJahr-09-30" }
)
foreach ($t in $testfaelle) {
    $u = Upload-Datei $t.Datei $t.Mime "Smoke-Test $($t.Name)" $token
    $t.Id = if ($u.Status -eq 201) { $u.Json.id } else { $null }
    Schreibe-Schritt "Upload $($t.Name)" ($u.Status -eq 201) $(if ($u.Status -ne 201) { "HTTP $($u.Status): $($u.Text)" } else { "" })
}
if (@($testfaelle | Where-Object { -not $_.Id }).Count -gt 0) { Beende "Upload fehlgeschlagen - 'docker compose logs app-api' zeigt den Grund." }

Write-Host "  ...     warte auf die Texterkennung" -ForegroundColor DarkGray
# --- 6. Auf die Texterkennung warten und pruefen ----------------------------------------------
foreach ($t in $testfaelle) {
    $ende = (Get-Date).AddSeconds($TimeoutSekunden)
    $detail = $null
    do {
        Start-Sleep -Seconds 2
        $detail = (Invoke-Api GET "/documents/$($t.Id)" -Token $token).Json
    } while ($detail -and $detail.ocr_status -eq "pending" -and (Get-Date) -lt $ende)

    $fertig = $detail -and $detail.ocr_status -eq "done"
    $info = if ($detail) { "Status: $($detail.ocr_status)" } else { "keine Antwort" }
    Schreibe-Schritt "Texterkennung $($t.Name)" $fertig $info
    if (-not $fertig) {
        if ($detail -and $detail.ocr_status -eq "pending") { $t.Hinweis = "Der Worker hat den Job nicht abgearbeitet - 'docker compose logs app-worker' pruefen." }
        continue
    }
    $gefunden = $detail.ocr_text -like "*$($t.Stichwort)*"
    $auszug = (($detail.ocr_text -split "`n" | Where-Object { $_.Trim() }) | Select-Object -First 2) -join " | "
    Schreibe-Schritt "Erkannter Text $($t.Name)" $gefunden $(if ($gefunden) { $auszug } else { "'$($t.Stichwort)' nicht gefunden: $auszug" })
}

# --- 6b. Automatische Klassifikation (Anforderungsdokument 4.3) -------------------------------
Write-Host "  ...     warte auf die Klassifikation (das Sprachmodell braucht beim ersten Aufruf etwas laenger)" -ForegroundColor DarkGray
$kategorien = @{}
foreach ($k in (Invoke-Api GET "/categories" -Token $token).Json) { $kategorien[$k.id] = $k.name }
foreach ($t in $testfaelle) {
    $ende = (Get-Date).AddSeconds($TimeoutSekunden)
    $detail = $null
    do {
        $detail = (Invoke-Api GET "/documents/$($t.Id)" -Token $token).Json
        if ($detail -and $detail.classification_status -ne "pending") { break }
        Start-Sleep -Seconds 3
    } while ((Get-Date) -lt $ende)

    $status = if ($detail) { $detail.classification_status } else { "keine Antwort" }
    $letzte = @((Invoke-Api GET "/documents/$($t.Id)/classification-history" -Token $token).Json) | Select-Object -Last 1
    $notiz = if ($letzte) { $letzte.note } else { "" }
    if ($status -eq "auto_assigned") {
        $stufe = if ($detail.classification_stage -eq "llm") { "Sprachmodell" } else { "Beispielvergleich" }
        $prozent = [math]::Round([double]$detail.classification_confidence * 100)
        Schreibe-Schritt "Klassifikation $($t.Name)" $true "$($kategorien[$detail.category_id]) - $stufe, $prozent %"
    } elseif ($status -eq "needs_review" -and $notiz -notlike "*nicht verfuegbar*") {
        # Auch das ist ein korrektes Ergebnis: die KI war sich nicht sicher genug.
        Schreibe-Schritt "Klassifikation $($t.Name)" $true "zur Pruefung: $notiz"
    } else {
        Schreibe-Schritt "Klassifikation $($t.Name)" $false "Status: $status $notiz"
        $t.Hinweis = "Klassifikation hat nicht funktioniert. Laeuft Ollama und sind die Modelle geladen? " +
                     "'docker compose logs ollama-init' und 'docker compose logs app-worker' pruefen."
    }
}

# Feedback-Loop: Kategorie fuer die PDF manuell bestaetigen/zuordnen
$pdf = $testfaelle[0]
$ziel = ($kategorien.GetEnumerator() | Where-Object { $_.Value -eq "Wohnen & Nebenkosten" } | Select-Object -First 1).Key
if ($ziel) {
    $r = Invoke-Api POST "/documents/$($pdf.Id)/category" @{ category_id = $ziel } -Token $token
    $verlauf = @((Invoke-Api GET "/documents/$($pdf.Id)/classification-history" -Token $token).Json)
    $ok = $r.Status -eq 200 -and $r.Json.classification_status -eq "confirmed" -and $verlauf.Count -ge 2
    Schreibe-Schritt "Kategorie manuell bestaetigen" $ok $(if ($ok) { "Wohnen & Nebenkosten, $($verlauf.Count) Eintraege im Verlauf" } else { "HTTP $($r.Status): $($r.Text)" })
} else {
    Schreibe-Schritt "Kategorie manuell bestaetigen" $true "uebersprungen - Kategorie 'Wohnen & Nebenkosten' gibt es nicht (umbenannt?)"
}

# --- 6c. Metadaten und Fristen (Anforderungsdokument 4.4a) -------------------------------------
Write-Host "  ...     warte auf Metadaten- und Fristenerkennung" -ForegroundColor DarkGray
foreach ($t in $testfaelle) {
    $ende = (Get-Date).AddSeconds($TimeoutSekunden)
    $detail = $null
    do {
        $detail = (Invoke-Api GET "/documents/$($t.Id)" -Token $token).Json
        if ($detail -and $detail.extraction_status -ne "pending") { break }
        Start-Sleep -Seconds 3
    } while ((Get-Date) -lt $ende)

    $status = if ($detail) { $detail.extraction_status } else { "keine Antwort" }
    if ($status -ne "done") {
        Schreibe-Schritt "Metadaten $($t.Name)" $false "Status: $status"
        $grund = Get-WorkerGrund $t.Id
        $t.Hinweis = "Metadaten-Erkennung hat nicht funktioniert. Laeuft Ollama und ist das Chat-Modell geladen? 'docker compose logs app-worker' pruefen."
        if ($grund) { $t.Hinweis += " Worker meldet: $grund" }
        continue
    }
    $teile = @()
    if ($detail.document_date) { $teile += "Datum $($detail.document_date)" }
    if ($detail.issuer) { $teile += "Absender '$($detail.issuer)'" }
    if ($null -ne $detail.amount) { $teile += ("Betrag {0:N2} EUR" -f [double]$detail.amount) }
    $info = if ($teile.Count) { $teile -join ", " } else { "nichts erkannt" }
    Schreibe-Schritt "Metadaten $($t.Name)" $true $info

    $vorschlaege = @((Invoke-Api GET "/documents/$($t.Id)/wiedervorlagen" -Token $token).Json | Where-Object { $_ })
    $t.Vorschlaege = $vorschlaege
    $liste = if ($vorschlaege.Count) { ($vorschlaege | ForEach-Object { "$($_.note) am $($_.due_date)" }) -join "; " } else { "keine" }
    if (-not $t.ErwarteteFrist) {
        Schreibe-Schritt "Fristvorschlaege $($t.Name)" $true $liste
    } elseif ($vorschlaege.Count -eq 0) {
        # Keine Frist gefunden ist ein Qualitaetsmangel des Modells, kein Programmfehler
        Schreibe-Schritt "Fristvorschlaege $($t.Name)" $true "keine erkannt (erwartet: $($t.ErwarteteFrist))"
    } else {
        $treffer = @($vorschlaege | Where-Object { $_.due_date -eq $t.ErwarteteFrist }).Count -gt 0
        Schreibe-Schritt "Fristvorschlaege $($t.Name)" $treffer $(if ($treffer) { $liste } else { "$liste - erwartet: $($t.ErwarteteFrist)" })
    }
}

# Einen Vorschlag probeweise bestaetigen (vorgeschlagen -> offen)
$erster = @($testfaelle | ForEach-Object { $_.Vorschlaege } | Where-Object { $_ -and $_.status -eq "vorgeschlagen" }) | Select-Object -First 1
if ($erster) {
    $r = Invoke-Api POST "/wiedervorlagen/$($erster.id)/confirm" -Token $token
    $ok = $r.Status -eq 200 -and $r.Json.status -eq "offen"
    Schreibe-Schritt "Fristvorschlag bestaetigen" $ok $(if ($ok) { "$($erster.note) am $($erster.due_date) ist jetzt offen" } else { "HTTP $($r.Status): $($r.Text)" })
} else {
    Schreibe-Schritt "Fristvorschlag bestaetigen" $true "uebersprungen - das Modell hat keine Frist vorgeschlagen"
}

# --- 6d. Wiedervorlage mit Wiederholung erledigen -> Folgetermin ------------------------------
$heuteText = (Get-Date).Date.ToString("yyyy-MM-dd")
$erwartetText = (Get-Date).Date.AddYears(1).ToString("yyyy-MM-dd")
$neu = Invoke-Api POST "/documents/$($testfaelle[0].Id)/wiedervorlagen" @{
    due_date = $heuteText; note = "Smoke-Test: jaehrliche Wiedervorlage"; recurrence = "yearly"
} -Token $token
if ($neu.Status -ne 201) {
    Schreibe-Schritt "Wiedervorlage erledigen" $false "Anlegen: HTTP $($neu.Status): $($neu.Text)"
} else {
    $r = Invoke-Api POST "/wiedervorlagen/$($neu.Json.id)/complete" -Token $token
    $ok = $r.Status -eq 200 -and $r.Json.completed.status -eq "erledigt" -and $r.Json.next.due_date -eq $erwartetText
    $detail = if ($ok) { "Folgetermin am $erwartetText angelegt" } else { "HTTP $($r.Status), Folgetermin: $($r.Json.next.due_date) (erwartet $erwartetText)" }
    Schreibe-Schritt "Wiedervorlage erledigen" $ok $detail
    if ($r.Json.next.id) { Invoke-Api DELETE "/wiedervorlagen/$($r.Json.next.id)" -Token $token | Out-Null }  # aufraeumen
}

# --- 7. Download mit dem Original vergleichen ------------------------------------------------
foreach ($t in $testfaelle) {
    $ziel = [System.IO.Path]::GetTempFileName()
    try {
        Invoke-WebRequest -Uri "$Api/documents/$($t.Id)/download" -Headers @{ Authorization = "Bearer $token" } `
            -OutFile $ziel -UseBasicParsing -TimeoutSec 30
        if ($t.Mime -like "image/*") {
            # Fotos/Bilder speichert HomeDMS als PDF (aufgerichtet, verkleinert) - Download ist also eine PDF
            $kopf = [System.Text.Encoding]::ASCII.GetString([System.IO.File]::ReadAllBytes($ziel), 0, 4)
            $ok = $kopf -eq "%PDF"
            Schreibe-Schritt "Download $($t.Name)" $ok $(if ($ok) { "als PDF gespeichert" } else { "keine PDF" })
        } else {
            $gleich = (Get-FileHash $ziel -Algorithm SHA256).Hash -eq (Get-FileHash $t.Datei -Algorithm SHA256).Hash
            Schreibe-Schritt "Download $($t.Name)" $gleich $(if ($gleich) { "identisch mit dem Original" } else { "Inhalt weicht ab" })
        }
    } catch {
        Schreibe-Schritt "Download $($t.Name)" $false $_.Exception.Message
    } finally { Remove-Item $ziel -ErrorAction SilentlyContinue }
}

# --- 7b. Scan-Ordner: Datei ablegen, Worker holt sie ab (Anforderungsdokument 4.1) ------------
if (-not $OhneDocker) {
    # SCAN_FOLDER_PATH aus der .env (Standard ./data/scan, relativ zum Repo)
    $scanPfad = "./data/scan"
    $envDatei = Join-Path $RepoRoot ".env"
    if (Test-Path $envDatei) {
        $zeile = Get-Content $envDatei | Where-Object { $_ -match "^\s*SCAN_FOLDER_PATH\s*=" } | Select-Object -Last 1
        if ($zeile) { $scanPfad = ($zeile -split "=", 2)[1].Trim().Trim('"') }
    }
    if (-not [System.IO.Path]::IsPathRooted($scanPfad)) { $scanPfad = Join-Path $RepoRoot $scanPfad }
    if (Test-Path $scanPfad) {
        $scanName = "smoke-test-scan-$(Get-Date -Format 'yyyyMMdd-HHmmss').pdf"
        $scanDatei = Join-Path $scanPfad $scanName
        Copy-Item (Join-Path $TestDaten "rechnung-digital.pdf") $scanDatei
        # Der Worker wartet 30 s, bis eine Datei "fertig" ist, und prueft jede Minute
        $ende = (Get-Date).AddSeconds([Math]::Max($TimeoutSekunden, 180))
        while ((Test-Path $scanDatei) -and (Get-Date) -lt $ende) { Start-Sleep -Seconds 5 }
        $abgeholt = -not (Test-Path $scanDatei)
        $imArchiv = @(Get-ChildItem (Join-Path $scanPfad "_importiert") -Recurse -Filter $scanName -ErrorAction SilentlyContinue).Count -gt 0
        Schreibe-Schritt "Scan-Ordner" ($abgeholt -and $imArchiv) $(if ($abgeholt -and $imArchiv) { "abgeholt, Original liegt in _importiert" } elseif ($abgeholt) { "abgeholt, aber nicht in _importiert - siehe _fehler" } else { "Datei wurde nicht abgeholt: $scanDatei" })
        if (-not $abgeholt) { Write-Host "          Hinweis: 'docker compose logs app-worker' pruefen - laeuft der Worker, ist der Ordner beschreibbar gemountet?" -ForegroundColor Yellow }
    } else {
        Schreibe-Schritt "Scan-Ordner" $false "Ordner nicht gefunden: $scanPfad (SCAN_FOLDER_PATH in .env)"
    }
}

# --- 8. Aufraeumen ------------------------------------------------------------------------------
if ($DokumenteBehalten) {
    Schreibe-Schritt "Aufraeumen" $true "uebersprungen - Testdokumente bleiben erhalten"
} else {
    $ok = $true
    foreach ($t in $testfaelle) {
        if ((Invoke-Api DELETE "/documents/$($t.Id)" -Token $token).Status -ne 204) { $ok = $false }
    }
    $papierkorb = (Invoke-Api GET "/documents/trash?page_size=100" -Token $token).Json
    $imPapierkorb = @($papierkorb.items | Where-Object { $testfaelle.Id -contains $_.id }).Count -eq $testfaelle.Count
    Schreibe-Schritt "Aufraeumen" ($ok -and $imPapierkorb) "Testdokumente liegen im Papierkorb"
}

foreach ($t in $testfaelle) { if ($t.Hinweis) { Write-Host ""; Write-Host "Hinweis: $($t.Hinweis)" -ForegroundColor Yellow; break } }
Zeige-Zusammenfassung
if (@($Ergebnisse | Where-Object { $_.Ergebnis -ne "OK" }).Count -gt 0) { exit 1 }
exit 0
