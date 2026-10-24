// Nur Entwicklung: node --test tests/js
import test from "node:test";
import assert from "node:assert/strict";
import {
  resolveEntities, formatDuration, formatNumber, chargeInfo, hasNoData, plugColor, socColor, batteryIcon,
  stepLimit, normalizeConfig, isValid, formatUpdated, LAYOUT, stackStyle, headerParts, symbolsStyle, noticeStyle, climateVisual,
  plugTitle, climateAction, pendingStatus,
} from "../../custom_components/psacc_fahrtenbuch/frontend/psacc-fahrzeug-card.js";

const ent = (entity_id, translation_key, device_id = "dev1", platform = "psacc_fahrtenbuch") =>
  ({ entity_id, translation_key, device_id, platform });
const hass = {
  devices: { dev1: { primary_config_entry: "entry1" }, dev2: { primary_config_entry: "other" } },
  entities: {
    "sensor.mokka_batterie_soc": ent("sensor.mokka_batterie_soc", "soc"),
    "sensor.mokka_kilometerstand": ent("sensor.mokka_kilometerstand", "kilometerstand"),
    "switch.mokka_vorklimatisierung": ent("switch.mokka_vorklimatisierung", "vorklimatisierung"),
    "sensor.mokka_vorklimatisierung_status": ent("sensor.mokka_vorklimatisierung_status", "vorklimatisierung_status"),
    "number.mokka_ladelimit": ent("number.mokka_ladelimit", "ladelimit"),
    "sensor.fremd_batterie_soc": ent("sensor.fremd_batterie_soc", "soc", "dev2"),
    "sensor.andere_integration_soc": ent("sensor.andere_integration_soc", "soc", "dev1", "andere"),
  },
};

test("Aufloesung ueber config_entry_id und translation_key (Domain beachtet)", () => {
  const r = resolveEntities(hass, { config_entry_id: "entry1" });
  assert.equal(r.soc, "sensor.mokka_batterie_soc");
  assert.equal(r.climate, "switch.mokka_vorklimatisierung");
  assert.equal(r.limit, "number.mokka_ladelimit");
  assert.equal(r.range, undefined); // fehlend -> Element wird ausgelassen
});

test("Aufloesung ueber device_id und Override", () => {
  const r = resolveEntities(hass, { device_id: "dev2", entities: { odometer: "sensor.eigene" } });
  assert.equal(r.soc, "sensor.fremd_batterie_soc");
  assert.equal(r.odometer, "sensor.eigene");
});

test("Fallback ueber ID-Suffix ohne translation_key", () => {
  const h = { devices: {}, entities: { "sensor.x_reichweite": ent("sensor.x_reichweite", null) } };
  assert.equal(resolveEntities(h, { device_id: "dev1" }).range, "sensor.x_reichweite");
});

test("Dauerformat", () => {
  assert.equal(formatDuration(90), "1 h 30 min");
  assert.equal(formatDuration(120), "2 h");
  assert.equal(formatDuration(45), "45 min");
  assert.equal(formatDuration(0), "");
  assert.equal(formatDuration("x"), "");
});

test("Zahlenformat de", () => {
  assert.equal(formatNumber(38061.2, "de", 1), "38.061,2");
  assert.equal(formatNumber(118, "de", 0), "118");
  assert.equal(formatNumber("abc", "de", 0), "–");
});

test("Stand lokal formatiert", () => {
  assert.match(formatUpdated("2026-01-01T12:00:00+00:00", "de", "Europe/Berlin"), /13:00/);
  assert.equal(formatUpdated("kaputt", "de"), "–");
});

const st = (state, attributes = {}) => ({ state, attributes });

test("Ladeinfo nur beim Laden mit Restzeit > 0", () => {
  assert.equal(chargeInfo(st("in_progress"), st("90"), st("11"), "de"), "Fertig in 1 h 30 min · +11 km/h");
  assert.equal(chargeInfo(st("in_progress"), st("90"), st("unavailable"), "de"), "Fertig in 1 h 30 min");
  assert.equal(chargeInfo(st("in_progress"), st("0"), st("11"), "de"), "Lädt · +11 km/h");
  assert.equal(chargeInfo(st("in_progress"), st("unknown"), st("0"), "de"), "Lädt");
  assert.equal(chargeInfo(st("disconnected"), st("90"), st("11"), "de"), "");
  assert.equal(chargeInfo(undefined, st("90"), st("11"), "de"), "");
});

test("unavailable-Regeln", () => {
  assert.equal(isValid(st("unavailable")), false);
  assert.equal(isValid(st("unknown")), false);
  assert.equal(isValid(undefined), false);
  assert.equal(isValid(st("0")), true);
  assert.equal(hasNoData({ soc: st("unavailable"), updated: undefined }), true);
  assert.equal(hasNoData({ soc: st("53"), updated: undefined }), false);
  assert.equal(hasNoData({ soc: undefined, updated: st("2026-01-01T12:00:00+00:00") }), false);
});

test("Farben und Icons", () => {
  assert.match(plugColor(st("off"), st("disconnected")), /disabled/);
  assert.match(plugColor(st("on"), st("failure")), /error/);
  assert.match(plugColor(st("off"), st("failure")), /error/);
  assert.equal(plugTitle(st("off"), st("disconnected")), "Stecker: nicht bestätigt");
  assert.match(plugColor(st("on"), st("stopped")), /warning/);
  assert.match(plugColor(st("on"), st("in_progress")), /success/);
  assert.match(plugColor(st("unavailable"), undefined), /disabled/);
  assert.match(socColor(10), /error/);
  assert.match(socColor(35), /warning/);
  assert.match(socColor(53), /success/);
  assert.equal(batteryIcon(53), "mdi:battery-50");
  assert.equal(batteryIcon(100), "mdi:battery");
  assert.equal(batteryIcon(2), "mdi:battery-outline");
  assert.equal(batteryIcon(NaN), "mdi:battery-unknown");
  assert.equal(batteryIcon(53, true), "mdi:battery-charging-50");
  assert.equal(batteryIcon(2, true), "mdi:battery-charging-outline");
  assert.equal(batteryIcon(100, true), "mdi:battery-charging-100");
});

test("Ladelimit-Schritte", () => {
  assert.equal(stepLimit(100, 1, 5, 20, 100), 100);
  assert.equal(stepLimit(80, -1, 5, 20, 100), 75);
  assert.equal(stepLimit(20, -1, 5, 20, 100), 20);
  assert.equal(stepLimit(80, 1, 100, 20, 100), 100); // Schritt auf 1..20 begrenzt
  assert.equal(stepLimit(NaN, 1, 5, 20, 100), 25);
});

test("Konfiguration", () => {
  assert.throws(() => normalizeConfig({}));
  const c = normalizeConfig({ config_entry_id: "x", limit_step: 99, show_soc: false });
  assert.equal(c.limit_step, 20); assert.equal(c.show_soc, false);
  assert.equal(c.show_limit, true); assert.equal(c.limit_delay, 3000);
});

test("Reichweite, Ladestand und Ladelimit sitzen in einem gemeinsamen rechtsbuendigen Block", () => {
  assert.equal(LAYOUT.range, undefined);
  assert.equal(LAYOUT.soc, undefined);
  assert.equal(LAYOUT.limit, undefined);
  assert.equal(stackStyle(), `right:${LAYOUT.stack.right}%;bottom:${LAYOUT.stack.bottom}%;`);
  assert.ok(LAYOUT.stack.right >= 0 && LAYOUT.stack.bottom >= 0);
});

test("Kopfzeile: Stand links, Ladeinfo rechts nur beim Laden; nicht mehr als Overlay im Bild", () => {
  assert.equal(LAYOUT.updated, undefined);
  assert.equal(LAYOUT.charge, undefined);
  const cfg = { show_updated: true, show_charge_info: true };
  const ids = { updated: "sensor.x_letztes_update" };
  const S = { updated: st("2026-01-01T12:00:00+00:00"), charge_status: st("in_progress"), charge_time: st("630"), charge_rate: st("6") };
  const h = headerParts(cfg, ids, S, "de", "UTC");
  assert.match(h.stand, /^Stand: /);
  assert.equal(h.info, "Fertig in 10 h 30 min · +6 km/h");
  assert.equal(headerParts(cfg, ids, { ...S, charge_status: st("disconnected") }, "de", "UTC").info, "");
  assert.equal(headerParts({ ...cfg, show_updated: false }, ids, S, "de", "UTC").stand, "");
  assert.equal(headerParts(cfg, ids, { ...S, updated: st("unavailable") }, "de", "UTC").stand, "Stand: –");
});

test("Vierergruppe: Kopfzeile und Symbolzeile in einem Block oben im Bild, Abstand wie 1.0.4", () => {
  assert.equal(LAYOUT.climate, undefined);
  assert.equal(LAYOUT.plug, undefined);
  assert.equal(symbolsStyle(), `margin-top:${LAYOUT.symbols.gap}%;padding:0 ${LAYOUT.symbols.side}%;`);
  assert.ok(LAYOUT.symbols.gap > 0 && LAYOUT.symbols.gap <= 3);
});

test("A/C: Schalten mit Bestaetigung und Sperre", () => {
  assert.equal(climateAction(undefined, st("off")), "turn_on");
  assert.equal(climateAction(undefined, st("on")), "turn_off");
  assert.equal(climateAction({ target: "on", at: 0 }, st("off")), null); // gesperrt
  assert.equal(climateAction(undefined, st("unavailable")), null);
  const p = { target: "on", at: 1000 };
  assert.equal(pendingStatus(p, st("off"), 2000, 240000), "pending");
  assert.equal(pendingStatus(p, st("on"), 2000, 240000), "confirmed");
  assert.equal(pendingStatus(p, st("off"), 1000 + 240000, 240000), "timeout");
  assert.equal(normalizeConfig({ device_id: "d" }).climate_timeout, 240000);
});

test("A/C-Bedienung: Tap per click, Halten nur ohne Pending, Pending nicht klick-blockiert", async () => {
  const { readFileSync } = await import("node:fs");
  const src = readFileSync(new URL("../../custom_components/psacc_fahrtenbuch/frontend/psacc-fahrzeug-card.js", import.meta.url), "utf8");
  assert.match(src, /@click=\$\{climate\.onclick\}/);
  assert.match(src, /if \(!this\._ac\) this\._moreInfo\(el\)/);
  assert.match(src, /this\._flash\("schaltet…"\)/);
  assert.doesNotMatch(src, /\.icon\.pending \{ pointer-events/);
});

test("Hinweis: gleicher Seitenrand wie Symbolzeile (linksbuendig unter A/C)", () => {
  assert.equal(noticeStyle(), `padding:0 ${LAYOUT.symbols.side}%;`);
});

test("A/C-Symbol: vier klar getrennte Zustaende", () => {
  const st = (state) => ({ state });
  assert.equal(climateVisual(st("off"), undefined), "off");
  assert.equal(climateVisual(st("on"), undefined), "on");
  assert.equal(climateVisual(st("on"), { target: "off", at: 0 }), "pending");
  assert.equal(climateVisual(st("unavailable"), undefined), "unknown");
  assert.equal(climateVisual(undefined, undefined), "unknown");
});
