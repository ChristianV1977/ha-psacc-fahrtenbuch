# PSA Car Controller Fahrtenbuch

Home-Assistant-Custom-Integration für Fahrzeuge (Opel/Peugeot/Citroën/DS/Vauxhall), die über das Add-on **PSA Car Controller** (psacc) angebunden sind. Sie ersetzt YAML-REST-Sensoren, REST-Commands, Shell-Commands und Helper durch **eine** Integration und führt ein **Fahrtenbuch** (SQLite) mit Monats-/Gesamtauswertung. Alle Daten bleiben lokal, es gibt keine Cloud außer der des Add-ons und optional Nominatim für Ortsnamen.

*English: HA custom integration on top of the PSA Car Controller add-on: vehicle sensors, remote buttons, charge limit, hourly wakeup and a local SQLite trip logbook (ignition-based trip detection, consumption from SoC difference, monthly/overall statistics, notes per trip). No shell commands needed.*

## Installation

**HACS:** Custom repository `https://github.com/ChristianV1977/ha-psacc-fahrtenbuch`, Kategorie "Integration", installieren, HA neu starten.
**Manuell:** `custom_components/psacc_fahrtenbuch` nach `<config>/custom_components/` kopieren.
Danach: Einstellungen > Geräte & Dienste > Integration hinzufügen > "PSA Car Controller Fahrtenbuch". Der Dialog fragt die psacc-URL (Standard `http://b9f12d83-psacc:5000`), das Fahrzeug (aus `/get_vehicles`), den Namen (Präfix der Entity-IDs) und die angenommene Akkukapazität. Es ist ein Eintrag möglich (ein Fahrzeug).

## Funktionen

- **Sensoren** (Abfrage per Koordinator, Standard 20 s; SOH stündlich, Ladesteuerung minütlich): Batterie-SOC, Reichweite, Kilometerstand, Spannung, SOH, Außentemperatur, Umgebungslicht, Zündung, Geschwindigkeit, Türen, Lademodus, -rate, -status, verbleibende Ladezeit, Vorklimatisierung (Status/Fehler), letztes Cloud-Update (Zeitstempel), nächste Stoppzeit. Dazu Binärsensoren (angesteckt, in Bewegung, Cloud-Daten aktuell, Fahrt aktiv) und ein `device_tracker` (Standort).
- **Steuerung:** Button Wakeup, Schalter Vorklimatisierung, `number` Ladelimit, `time` Ladezeit. Hupe, Lichter, Türen ver-/entriegeln sind als Buttons vorhanden, aber standardmäßig **deaktiviert** (reale Fahrzeugaktion). Laden starten/stoppen ist bewusst nicht enthalten.
- **Wakeup:** stündlich zur vollen Stunde (Option) und optional sofort bei Ladeende (Option: Binärsensor "lädt", z. B. von evcc, Wechsel on→off).
- **Fahrtenbuch:** Fahrtbeginn bei Zündung `StartUp`, Ende bei `Stop`. Erfasst Zeiten (PSA-Zeitstempel, lokal), Orte, Distanz, Dauer, Ø-Geschwindigkeit, Verbrauch = (SoC-Start − SoC-Ende)/100 × Akkukapazität (nur bei SoC-Abfall, sonst 0 und Markierung "SoC Anstieg"), Hinweis "Cloud-Daten evtl. veraltet" (Daten > 30 min) und "Kilometerstand-Anomalie ignoriert". 90 s nach Fahrtbeginn wird der SoC-Startwert korrigiert, falls die Cloud inzwischen frischer ist. Orte: Zone (z. B. "Zuhause") hat Vorrang, sonst Nominatim (max. 1 Anfrage/s, eigener User-Agent, abschaltbar). Die laufende Fahrt überlebt einen HA-Neustart.
- **Auswertung:** Sensoren für Monat (gewählt) und Gesamt (Fahrten, km, kWh, kWh/100 km, kWh/Fahrt); Auswahl über `select` Monat, `number` Jahr, Button "aktueller Monat". Fahrtenliste als Attribut `trips` am Sensor `…_fahrtenbuch_monat_fahrten`. Monats-Cache nur für abgeschlossene Monate, wird bei Nachträgen verworfen.
- **Hinweis je Fahrt:** `number` Bearbeiten-ID wählt die Fahrt und füllt `text` Hinweis vor; Button "Hinweis speichern" schreibt.
- **Services:** `hinweis_setzen`, `soc_anstieg_setzen`, `fahrten_abfragen` (Antwortdaten, Monat oder gesamt), `fahrt_hinzufuegen`, `auswahl_setzen`, `wakeup`. Event `psacc_fahrtenbuch_fahrt_erfasst` (ID, km, kWh).

## Daten und Migration

Die Fahrten liegen in `<config>/psacc_fahrtenbuch/fahrten.db`. Existiert dort bereits eine Datenbank im Schema des früheren Skript-Fahrtenbuchs (`fahrten`, `monatswerte`), wird sie unverändert weiterverwendet (IDs bleiben erhalten); es genügt, die Datei vor dem ersten Start dorthin zu kopieren. Beim Entfernen der Integration bleibt die Datei bewusst erhalten.

## Dashboard

[`examples/dashboard-fahrtenbuch.yaml`](examples/dashboard-fahrtenbuch.yaml) (Raw-Konfigurationseditor, unter `views:`). Für ein anderes Präfix: `python3 tools/gen_dashboard.py PRAEFIX`.

## Datenschutz

Fahrten enthalten Orte und frei wählbare Hinweise (oft Personen). Die Fahrtenliste (`trips`) ist per `_unrecorded_attributes` vom Recorder ausgenommen, Diagnosedaten schwärzen VIN, URL, Koordinaten und Fahrten. **Empfohlen:** `text.*_fahrtenbuch_hinweis` und `device_tracker.*` aus Recorder, Logbuch und InfluxDB ausschließen. Nominatim erhält nur Koordinaten außerhalb von Zonen. Das Repo enthält keine echten Daten (Tests nutzen fiktive Werte und anonymisierte Antworten).

## Entwicklung

`python3 -m venv .venv && .venv/bin/pip install pytest homeassistant && .venv/bin/python -m pytest tests`. Selbsttest gegen eine Kopie einer echten Datenbank: `python3 tools/selftest_real_db.py <kopie.db>`. Übersetzungen werden mit `tools/gen_translations.py` erzeugt. Lizenz: MIT.

## Hinweis zu HACS und GitLab

HACS unterstützt nur öffentliche GitHub-Repositories. Die Entwicklung läuft auf einer privaten GitLab-Instanz; das GitHub-Repo ist ein Spiegel. Nicht affiliiert mit Stellantis oder dem psacc-Projekt.
