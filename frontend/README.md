# HomeDMS – Weboberfläche

React 19 + TypeScript + [Mantine](https://mantine.dev) als installierbare PWA (Desktop und Handy).
Im Betrieb baut das Docker-Image diese Oberfläche mit und das Backend liefert sie unter `/` aus –
ein separater Webserver ist nicht nötig.

## Entwicklung

```bash
npm install
npm run dev          # http://localhost:5173, leitet /api an http://localhost:8000 weiter
                     # anderes Backend: HOMEDMS_BACKEND=http://nas:8000 npm run dev
npm test             # Vitest (Komponenten- und Logiktests)
npm run typecheck
npm run lint
npm run build        # -> dist/
```

Ändert sich die API des Backends:

```bash
curl http://localhost:8000/openapi.json -o src/api/openapi.json
npm run gen:api      # erzeugt src/api/schema.d.ts neu; tsc meldet dann betroffene Stellen
```

## Aufbau

| Pfad | Inhalt |
|---|---|
| `src/api/client.ts` | typisierter API-Client, Token-Erneuerung (ein Refresh für parallele Anfragen) |
| `src/api/queries.ts` | alle Abfragen/Änderungen (TanStack Query), automatisches Neuladen während der Verarbeitung |
| `src/pages/` | Anmeldung/Ersteinrichtung, Dokumente, Dokument-Detail, Prüfen, Termine, Papierkorb, Aufbewahrung |
| `src/components/` | Layout, Upload (inkl. Kamera), Termin-Karten und -Formular, Detail-Bereiche |
| `src/lib/format.ts` | deutsche Datums-/Betragsformate und Bezeichnungen |
