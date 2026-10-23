#!/usr/bin/env python3
"""Gibt die Fahrtenbuch-Ansicht (Sections-View, YAML) fuer ein Namenspraefix aus: gen_dashboard.py [PRAEFIX]

PRAEFIX = Name des Geraets als Slug (Standard: mokka), also z. B. sensor.<praefix>_fahrtenbuch_monat_fahrten.
Im Raw-Konfigurationseditor eines Dashboards unter `views:` einfuegen.
"""
import sys

p = sys.argv[1] if len(sys.argv) > 1 else "mokka"
T = """\
- title: Fahrtenbuch
  path: fahrtenbuch
  icon: mdi:notebook-outline
  type: sections
  max_columns: 3
  badges:
    - {type: entity, entity: button.P_fahrtenbuch_aktueller_monat, name: Aktueller Monat, show_name: true, show_state: false, tap_action: {action: toggle}}
    - {type: entity, entity: select.P_fahrtenbuch_monat, name: Monat, show_name: true}
    - {type: entity, entity: number.P_fahrtenbuch_jahr, name: Jahr, show_name: true}
  sections:
    - type: grid
      cards:
        - type: markdown
          title: Gesamtuebersicht (alle Fahrten)
          grid_options: {columns: full, rows: auto}
          content: |
            | Fahrten | km gesamt | kWh gesamt | Ø kWh/Fahrt | kWh/100km |
            |--:|--:|--:|--:|--:|
            | {{ states('sensor.P_fahrtenbuch_gesamt_fahrten') }} | {{ states('sensor.P_fahrtenbuch_gesamt_km') }} | {{ states('sensor.P_fahrtenbuch_gesamt_kwh') }} | {{ states('sensor.P_fahrtenbuch_gesamt_kwh_pro_fahrt') }} | {{ states('sensor.P_fahrtenbuch_gesamt_kwh_pro_100_km') }} |
    - type: grid
      cards:
        - type: markdown
          title: Monatsauswertung
          grid_options: {columns: full}
          content: |
            **Monat {{ state_attr('sensor.P_fahrtenbuch_monat_fahrten', 'monat') }}/{{ state_attr('sensor.P_fahrtenbuch_monat_fahrten', 'jahr') }}**

            | Fahrten | km gesamt | kWh gesamt | Ø kWh/Fahrt | kWh/100km |
            |--:|--:|--:|--:|--:|
            | {{ states('sensor.P_fahrtenbuch_monat_fahrten') }} | {{ states('sensor.P_fahrtenbuch_monat_km') }} | {{ states('sensor.P_fahrtenbuch_monat_kwh') }} | {{ states('sensor.P_fahrtenbuch_monat_kwh_pro_fahrt') }} | {{ states('sensor.P_fahrtenbuch_monat_kwh_pro_100_km') }} |
    - type: grid
      cards:
        - type: heading
          icon: mdi:comment
          heading: Hinweis/Kommentar bearbeiten
          heading_style: title
        - type: entities
          grid_options: {columns: 6, rows: auto}
          entities:
            - {entity: number.P_fahrtenbuch_bearbeiten_id, name: ID}
            - {entity: text.P_fahrtenbuch_hinweis, name: Hinweis/Kommentar}
        - type: button
          entity: button.P_fahrtenbuch_hinweis_speichern
          name: Speichern
          show_state: false
          tap_action: {action: toggle}
    - type: grid
      column_span: 3
      cards:
        - type: markdown
          title: Fahrten
          grid_options: {columns: full}
          content: >-
            {% set trips = state_attr('sensor.P_fahrtenbuch_monat_fahrten', 'trips') | default([]) %}{% if trips | count == 0 %}_Noch keine Fahrten in diesem Monat._{% else %}| ID | Start | Von | Ende | Nach | km | Dauer | Ø km/h | kWh | Ø kWh/100km | SoC Anstieg | Hinweis |
            |--:|---|---|---|---|--:|--:|--:|--:|--:|:--:|---|
            {% for t in trips %}| {{ t.id }} | {{ t.start_zeit }} | {{ t.start_ort }} | {{ t.end_zeit }} | {{ t.end_ort }} | {{ t.distanz_km }} | {{ t.dauer_min }} min | {{ t.geschwindigkeit_kmh }} | {{ t.verbrauch_kwh }} | {{ (t.verbrauch_kwh / t.distanz_km * 100) | round(1) if t.distanz_km > 0 else '-' }} | {{ t.soc_anstieg or '' }} | {{ t.hinweis or '' }} |
            {% endfor %}{% endif %}
    - type: grid
      cards:
        - type: entities
          title: Annahme fuer die Verbrauchsberechnung
          grid_options: {columns: full}
          entities:
            - {entity: number.P_akkukapazitaet, name: Angenommene Akkukapazitaet (netto)}
        - type: markdown
          grid_options: {columns: full}
          content: Der Verbrauch je Fahrt wird als *(SoC-Differenz / 100) x Akkukapazitaet* geschaetzt, da die PSA-Cloud keine kWh liefert.
"""
print(T.replace("P_", p + "_").replace(".P_", "." + p + "_"))
