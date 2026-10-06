"""Texte der Zertifikat-Hilfeseite /zertifikat (cert_page.py) - je Sprache eine ganze Seite.

Platzhalter: {lang}, {title}, {languages}, {qr}, {fingerprint}, {target}, {names}; geschweifte
Klammern im CSS sind verdoppelt (str.format).
"""

HEAD = """<!doctype html>
<html lang="{lang}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
body{{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;max-width:760px;margin:0 auto;padding:16px;line-height:1.5;color:#1a1b1e;background:#f8f9fa}}
h1{{font-size:1.5rem}} h2{{font-size:1.1rem;margin-top:1.6em}} .card{{background:#fff;border:1px solid #dee2e6;border-radius:10px;padding:16px;margin:12px 0}}
a.btn{{display:inline-block;background:#228be6;color:#fff;padding:10px 16px;border-radius:8px;text-decoration:none;font-weight:600}}
code{{font-size:.85em;word-break:break-all;background:#f1f3f5;padding:2px 4px;border-radius:4px}} .qr{{float:right;margin:0 0 8px 16px}}
.langs{{float:right;font-size:.9em}} .langs a{{margin-left:8px}}
details{{background:#fff;border:1px solid #dee2e6;border-radius:10px;padding:10px 14px;margin:8px 0}} summary{{font-weight:600;cursor:pointer}}
@media (prefers-color-scheme:dark){{body{{background:#1a1b1e;color:#e9ecef}}.card,.langs{{float:right;font-size:.9em}} .langs a{{margin-left:8px}}
details{{background:#25262b;border-color:#373a40}}code{{background:#373a40}}}}
</style></head><body>"""

TITLES = {
    "de": "Famulus DMS – diesem Gerät die Verbindung erlauben",
    "en": "Famulus DMS – allow this device to connect",
    "ru": "Famulus DMS – разрешить подключение этого устройства",
}

BODIES = {
    "de": """
<p class="langs">{languages}</p>
<h1>Famulus DMS sicher verbinden</h1>
<p>Famulus DMS verschlüsselt alle Verbindungen. Damit dein Gerät der Verschlüsselung vertraut (und keine Warnung zeigt),
installierst du <b>einmal pro Gerät</b> das Zertifikat deiner Famulus-DMS-Installation.</p>
<div class="card"><img class="qr" src="{qr}" alt="QR-Code zum Herunterladen" width="140" height="140">
<p><b>1. Zertifikat laden</b><br>Am Handy: QR-Code scannen. Am PC: Knopf drücken.</p>
<p><a class="btn" href="/homedms-ca.crt">Zertifikat herunterladen</a></p>
<p style="clear:both;font-size:.9em">Fingerabdruck zum Vergleichen (SHA-256):<br><code>{fingerprint}</code></p></div>
<p><b>2. Installieren und vertrauen</b> – je nach Gerät:</p>
<details><summary>iPhone / iPad</summary><ol>
<li>In <b>Safari</b> öffnen und „Zertifikat herunterladen“ antippen, „Zulassen“.</li>
<li><b>Einstellungen</b> → oben „Profil geladen“ → <b>Installieren</b> (Code eingeben).</li>
<li><b>Einstellungen → Allgemein → Info → Zertifikatsvertrauenseinstellungen</b> → „Famulus DMS lokale Zertifizierungsstelle“ einschalten.</li></ol></details>
<details><summary>Android</summary><ol>
<li>Zertifikat herunterladen.</li>
<li><b>Einstellungen → Sicherheit → Weitere Sicherheitseinstellungen → Verschlüsselung &amp; Anmeldedaten → Zertifikat installieren → CA-Zertifikat</b>
(je nach Hersteller leicht anders benannt – in den Einstellungen nach „CA-Zertifikat“ suchen).</li>
<li>„Trotzdem installieren“ bestätigen und die Datei <code>homedms-ca.crt</code> wählen.</li></ol></details>
<details><summary>Windows</summary><ol>
<li>Zertifikat herunterladen, Datei doppelklicken → <b>Zertifikat installieren</b>.</li>
<li><b>Lokaler Computer</b> → „Alle Zertifikate in folgendem Speicher speichern“ → <b>Vertrauenswürdige Stammzertifizierungsstellen</b> → Fertig stellen.</li>
<li>Browser neu starten. (Firefox übernimmt das automatisch, sonst: Einstellungen → Datenschutz &amp; Sicherheit → Zertifikate → Importieren.)</li></ol></details>
<details><summary>Mac</summary><ol>
<li>Zertifikat herunterladen und doppelklicken – es öffnet sich die Schlüsselbundverwaltung (Schlüsselbund „System“).</li>
<li>Eintrag „Famulus DMS lokale Zertifizierungsstelle“ doppelklicken → <b>Vertrauen → Immer vertrauen</b>.</li></ol></details>
<details><summary>Linux</summary><p><code>sudo cp homedms-ca.crt /usr/local/share/ca-certificates/ &amp;&amp; sudo update-ca-certificates</code><br>
Firefox/Chrome: in den Browser-Einstellungen unter „Zertifikate“ importieren und „Websites vertrauen“ ankreuzen.</p></details>
<p><b>3. Fertig:</b> <a class="btn" href="{target}">Weiter zu Famulus DMS</a></p>
<p style="font-size:.85em;color:#868e96">Sicherheit: Diese Zertifizierungsstelle darf nur Adressen im Heimnetz bestätigen
(private Adressen, .local, .lan …) – sie kann keine fremden Webseiten (z. B. deiner Bank) vortäuschen.
Abgedeckt: {names}. Für Zugriff von unterwegs: per VPN ins Heimnetz.</p>
</body></html>""",
    "en": """
<p class="langs">{languages}</p>
<h1>Connect securely to Famulus DMS</h1>
<p>Famulus DMS encrypts every connection. So that your device trusts this encryption (and shows no warning),
install the certificate of your Famulus DMS installation <b>once per device</b>.</p>
<div class="card"><img class="qr" src="{qr}" alt="QR code for the download" width="140" height="140">
<p><b>1. Get the certificate</b><br>On a phone: scan the QR code. On a PC: press the button.</p>
<p><a class="btn" href="/homedms-ca.crt">Download certificate</a></p>
<p style="clear:both;font-size:.9em">Fingerprint to compare (SHA-256):<br><code>{fingerprint}</code></p></div>
<p><b>2. Install and trust it</b> – depending on the device:</p>
<details><summary>iPhone / iPad</summary><ol>
<li>Open this page in <b>Safari</b>, tap “Download certificate”, then “Allow”.</li>
<li><b>Settings</b> → “Profile Downloaded” at the top → <b>Install</b> (enter your passcode).</li>
<li><b>Settings → General → About → Certificate Trust Settings</b> → turn on “Famulus DMS lokale Zertifizierungsstelle”.</li></ol></details>
<details><summary>Android</summary><ol>
<li>Download the certificate.</li>
<li><b>Settings → Security → More security settings → Encryption &amp; credentials → Install a certificate → CA certificate</b>
(names differ slightly between manufacturers – search the settings for “CA certificate”).</li>
<li>Confirm “Install anyway” and choose the file <code>homedms-ca.crt</code>.</li></ol></details>
<details><summary>Windows</summary><ol>
<li>Download the certificate, double-click the file → <b>Install Certificate</b>.</li>
<li><b>Local Machine</b> → “Place all certificates in the following store” → <b>Trusted Root Certification Authorities</b> → Finish.</li>
<li>Restart the browser. (Firefox picks this up automatically; otherwise: Settings → Privacy &amp; Security → Certificates → Import.)</li></ol></details>
<details><summary>Mac</summary><ol>
<li>Download the certificate and double-click it – Keychain Access opens (keychain “System”).</li>
<li>Double-click the entry “Famulus DMS lokale Zertifizierungsstelle” → <b>Trust → Always Trust</b>.</li></ol></details>
<details><summary>Linux</summary><p><code>sudo cp homedms-ca.crt /usr/local/share/ca-certificates/ &amp;&amp; sudo update-ca-certificates</code><br>
Firefox/Chrome: import it in the browser settings under “Certificates” and tick “Trust this CA to identify websites”.</p></details>
<p><b>3. Done:</b> <a class="btn" href="{target}">Continue to Famulus DMS</a></p>
<p style="font-size:.85em;color:#868e96">Security: this certificate authority may only vouch for addresses in your home network
(private addresses, .local, .lan …) – it cannot impersonate other websites (such as your bank).
Covered: {names}. For access on the go: connect to your home network via VPN.</p>
</body></html>""",
    "ru": """
<p class="langs">{languages}</p>
<h1>Безопасное подключение к Famulus DMS</h1>
<p>Famulus DMS шифрует все соединения. Чтобы ваше устройство доверяло этому шифрованию (и не показывало предупреждений),
<b>один раз на каждом устройстве</b> установите сертификат вашей установки Famulus DMS.</p>
<div class="card"><img class="qr" src="{qr}" alt="QR-код для загрузки" width="140" height="140">
<p><b>1. Загрузите сертификат</b><br>На телефоне: отсканируйте QR-код. На компьютере: нажмите кнопку.</p>
<p><a class="btn" href="/homedms-ca.crt">Скачать сертификат</a></p>
<p style="clear:both;font-size:.9em">Отпечаток для сверки (SHA-256):<br><code>{fingerprint}</code></p></div>
<p><b>2. Установите сертификат и включите доверие</b> – в зависимости от устройства:</p>
<details><summary>iPhone / iPad</summary><ol>
<li>Откройте эту страницу в <b>Safari</b>, нажмите «Скачать сертификат», затем «Разрешить».</li>
<li><b>Настройки</b> → вверху «Профиль загружен» → <b>Установить</b> (введите код-пароль).</li>
<li><b>Настройки → Основные → Об этом устройстве → Доверие сертификатам</b> → включите «Famulus DMS lokale Zertifizierungsstelle».</li></ol></details>
<details><summary>Android</summary><ol>
<li>Скачайте сертификат.</li>
<li><b>Настройки → Безопасность → Другие настройки безопасности → Шифрование и учётные данные → Установка сертификата → Сертификат ЦС</b>
(в зависимости от производителя названия немного отличаются – найдите в настройках «Сертификат ЦС»).</li>
<li>Подтвердите «Всё равно установить» и выберите файл <code>homedms-ca.crt</code>.</li></ol></details>
<details><summary>Windows</summary><ol>
<li>Скачайте сертификат, дважды щёлкните по файлу → <b>Установить сертификат</b>.</li>
<li><b>Локальный компьютер</b> → «Поместить все сертификаты в следующее хранилище» → <b>Доверенные корневые центры сертификации</b> → Готово.</li>
<li>Перезапустите браузер. (Firefox подхватит это сам, иначе: Настройки → Приватность и защита → Сертификаты → Импортировать.)</li></ol></details>
<details><summary>Mac</summary><ol>
<li>Скачайте сертификат и дважды щёлкните по нему – откроется «Связка ключей» (связка «Система»).</li>
<li>Дважды щёлкните запись «Famulus DMS lokale Zertifizierungsstelle» → <b>Доверие → Всегда доверять</b>.</li></ol></details>
<details><summary>Linux</summary><p><code>sudo cp homedms-ca.crt /usr/local/share/ca-certificates/ &amp;&amp; sudo update-ca-certificates</code><br>
Firefox/Chrome: импортируйте сертификат в настройках браузера в разделе «Сертификаты» и отметьте «Доверять при идентификации веб-сайтов».</p></details>
<p><b>3. Готово:</b> <a class="btn" href="{target}">Перейти в Famulus DMS</a></p>
<p style="font-size:.85em;color:#868e96">Безопасность: этот центр сертификации может подтверждать только адреса в вашей домашней сети
(частные адреса, .local, .lan …) – он не может выдать себя за чужие сайты (например, ваш банк).
Охвачено: {names}. Для доступа вне дома: подключайтесь к домашней сети через VPN.</p>
</body></html>""",
}
