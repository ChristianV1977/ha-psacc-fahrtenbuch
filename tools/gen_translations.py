#!/usr/bin/env python3
"""Erzeugt translations/{de,en}.json und strings.json (en) aus einer Tabelle."""
import json, pathlib

D = pathlib.Path(__file__).resolve().parent.parent / "custom_components" / "psacc_fahrtenbuch"
# platform -> key -> (de, en[, states_de, states_en])
E = {
 "sensor": {
  "soc": ("Batterie SOC", "Battery SOC"), "reichweite": ("Reichweite", "Range"),
  "kilometerstand": ("Kilometerstand", "Odometer"), "batteriespannung": ("Batteriespannung", "Battery voltage"),
  "soh": ("Batterie SOH", "Battery SOH"), "umgebungstemperatur": ("Umgebungstemperatur", "Ambient temperature"),
  "umgebungslicht": ("Umgebungslicht", "Ambient light", {"day": "Tag", "night": "Nacht"}, {"day": "Day", "night": "Night"}),
  "zuendung": ("Zündung", "Ignition"), "geschwindigkeit": ("Geschwindigkeit", "Speed"), "tueren": ("Türen", "Doors"),
  "lademodus": ("Lademodus", "Charging mode", {"fast": "Schnellladen (DC)", "slow": "Langsamladen (AC)", "none": "Inaktiv"}, {"fast": "Fast (DC)", "slow": "Slow (AC)", "none": "Inactive"}),
  "laderate": ("Laderate", "Charging rate"),
  "ladestatus": ("Ladestatus", "Charging status", {"failure": "Fehler", "in_progress": "Am Laden", "stopped": "Gestoppt", "finished": "Fertig", "disconnected": "Getrennt", "unknown": "Unbekannt"}, {"failure": "Failure", "in_progress": "Charging", "stopped": "Stopped", "finished": "Finished", "disconnected": "Disconnected", "unknown": "Unknown"}),
  "verbleibende_ladezeit": ("Verbleibende Ladezeit", "Remaining charge time"),
  "vorklimatisierung_status": ("Vorklimatisierung Status", "Preconditioning status"),
  "vorklimatisierung_fehler": ("Vorklimatisierung Fehler", "Preconditioning failure", {"defect": "Beschädigt", "door_opened": "Geöffnete Tür", "low_battery": "Batterie schwach", "low_fuel": "Treibstoff gering", "too_many_programs": "Zu viele unbenutzte Programme"}, {"defect": "Defect", "door_opened": "Door opened", "low_battery": "Low battery", "low_fuel": "Low fuel", "too_many_programs": "Too many unused programs"}),
  "letztes_update": ("Letztes Update", "Last update"), "naechste_stoppzeit": ("Nächste Stoppzeit", "Next stop time"),
  "monat_fahrten": ("Fahrtenbuch Monat Fahrten", "Logbook month trips"), "monat_km": ("Fahrtenbuch Monat km", "Logbook month km"),
  "monat_kwh": ("Fahrtenbuch Monat kWh", "Logbook month kWh"), "monat_kwh_pro_100km": ("Fahrtenbuch Monat kWh pro 100 km", "Logbook month kWh per 100 km"),
  "monat_kwh_pro_fahrt": ("Fahrtenbuch Monat kWh pro Fahrt", "Logbook month kWh per trip"),
  "gesamt_fahrten": ("Fahrtenbuch Gesamt Fahrten", "Logbook total trips"), "gesamt_km": ("Fahrtenbuch Gesamt km", "Logbook total km"),
  "gesamt_kwh": ("Fahrtenbuch Gesamt kWh", "Logbook total kWh"), "gesamt_kwh_pro_100km": ("Fahrtenbuch Gesamt kWh pro 100 km", "Logbook total kWh per 100 km"),
  "gesamt_kwh_pro_fahrt": ("Fahrtenbuch Gesamt kWh pro Fahrt", "Logbook total kWh per trip"),
 },
 "binary_sensor": {"angesteckt": ("Angesteckt", "Plugged in"), "in_bewegung": ("In Bewegung", "Moving"),
   "daten_aktuell": ("Cloud-Daten aktuell", "Cloud data fresh"), "fahrt_aktiv": ("Fahrt aktiv", "Trip active")},
 "device_tracker": {"standort": ("Standort", "Location")},
 "button": {"wakeup": ("Wakeup", "Wake up"), "hupe": ("Hupe", "Horn"), "lichter": ("Lichter", "Lights"),
   "tueren_verriegeln": ("Türen verriegeln", "Lock doors"), "tueren_entriegeln": ("Türen entriegeln", "Unlock doors"),
   "aktueller_monat": ("Fahrtenbuch aktueller Monat", "Logbook current month"), "hinweis_speichern": ("Fahrtenbuch Hinweis speichern", "Logbook save note")},
 "switch": {"vorklimatisierung": ("Vorklimatisierung", "Preconditioning")},
 "number": {"ladelimit": ("Ladelimit", "Charge limit"), "akkukapazitaet": ("Akkukapazität", "Battery capacity"),
   "fahrtenbuch_jahr": ("Fahrtenbuch Jahr", "Logbook year"), "fahrtenbuch_bearbeiten_id": ("Fahrtenbuch Bearbeiten-ID", "Logbook edit ID")},
 "select": {"fahrtenbuch_monat": ("Fahrtenbuch Monat", "Logbook month")},
 "text": {"fahrtenbuch_hinweis": ("Fahrtenbuch Hinweis", "Logbook note")},
 "time": {"ladezeit": ("Ladezeit", "Charge time")},
}
def entities(i):
    out = {}
    for plat, keys in E.items():
        out[plat] = {}
        for k, v in keys.items():
            d = {"name": v[i]}
            if len(v) > 2:
                d["state"] = v[2 + i]
            out[plat][k] = d
    return out
def flow(de):
    t = (lambda a, b: a if de else b)
    return {
     "config": {
      "step": {
       "user": {"title": t("PSA Car Controller", "PSA Car Controller"), "description": t("Adresse der lokalen REST-API des Add-ons.", "Address of the add-on's local REST API."), "data": {"url": "URL"}},
       "vehicle": {"title": t("Fahrzeug", "Vehicle"), "data": {"vin": t("Fahrzeug", "Vehicle")}},
       "settings": {"title": t("Einstellungen", "Settings"), "data": {
         "titel": t("Name (Gerät, Präfix der Entity-IDs)", "Name (device, entity ID prefix)"),
         "kapazitaet_kwh": t("Angenommene nutzbare Akkukapazität", "Assumed usable battery capacity"),
         "scan_interval": t("Abfrageintervall", "Polling interval"), "wakeup_stuendlich": t("Wakeup stündlich", "Hourly wakeup"),
         "wakeup_bei_ladeende_entity": t("Wakeup bei Ladeende (Binärsensor 'lädt', optional)", "Wakeup at charge end (binary sensor 'charging', optional)"),
         "geocoding": t("Orte per Nominatim auflösen", "Resolve places via Nominatim"), "user_agent": "User-Agent (Nominatim)"}}},
      "error": {"cannot_connect": t("psacc nicht erreichbar.", "Cannot reach psacc."), "no_vehicles": t("psacc meldet kein Fahrzeug.", "psacc reports no vehicle.")},
      "abort": {"already_configured": t("Fahrzeug ist bereits eingerichtet.", "Vehicle already configured."), "single_instance_allowed": t("Nur ein Eintrag möglich.", "Only one entry allowed.")}},
     "options": {"step": {"init": {"title": t("Optionen", "Options"), "data": {
         "scan_interval": t("Abfrageintervall", "Polling interval"), "wakeup_stuendlich": t("Wakeup stündlich", "Hourly wakeup"),
         "wakeup_bei_ladeende_entity": t("Wakeup bei Ladeende (Binärsensor 'lädt', optional)", "Wakeup at charge end (binary sensor 'charging', optional)"),
         "geocoding": t("Orte per Nominatim auflösen", "Resolve places via Nominatim"), "user_agent": "User-Agent (Nominatim)"}}}},
     "entity": entities(0 if de else 1),
     "services": {k: {"name": n, "description": dsc} for k, (n, dsc) in {
       "hinweis_setzen": (t("Hinweis setzen", "Set note"), t("Setzt den Hinweis-/Kommentartext einer Fahrt per ID.", "Sets the note of a trip by ID.")),
       "soc_anstieg_setzen": (t("SoC-Anstieg setzen", "Set SoC rise flag"), t("Setzt oder löscht die Markierung 'SoC Anstieg'.", "Sets or clears the SoC-rise flag.")),
       "fahrten_abfragen": (t("Fahrten abfragen", "Query trips"), t("Liefert Fahrten und Kennzahlen eines Monats oder die Gesamtsumme.", "Returns trips and totals of a month or overall.")),
       "fahrt_hinzufuegen": (t("Fahrt hinzufügen", "Add trip"), t("Trägt eine Fahrt nach (Rekonstruktion).", "Adds a trip retroactively.")),
       "auswahl_setzen": (t("Auswahl setzen", "Set selection"), t("Setzt Monat/Jahr der Fahrtenbuch-Ansicht.", "Sets month/year of the logbook view.")),
       "wakeup": (t("Wakeup", "Wake up"), t("Weckt das Fahrzeug über psacc.", "Wakes the vehicle via psacc."))}.items()},
    }
(D / "translations").mkdir(exist_ok=True)
for lang in ("de", "en"):
    (D / "translations" / f"{lang}.json").write_text(json.dumps(flow(lang == "de"), ensure_ascii=False, indent=2) + "\n")
(D / "strings.json").write_text(json.dumps(flow(False), ensure_ascii=False, indent=2) + "\n")
