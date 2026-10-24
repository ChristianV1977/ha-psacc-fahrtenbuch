/* PSA Fahrzeug – Lovelace-Karte der Integration psacc_fahrtenbuch.
 * ES-Modul ohne Build. Lit wird aus Home Assistant bezogen. Die reinen Funktionen sind exportiert
 * (Tests: tests/js/card.test.mjs, nur Entwicklung). */

export const CARD_VERSION = "1.0.7";
const HOLD_MS = 700;
export const DOMAIN = "psacc_fahrtenbuch";
export const DEFAULT_IMAGE = "/psacc_fahrtenbuch/frontend/fahrzeug.svg";

/** Element -> [Domain, translation_key, Fallback-Suffixe der Entity-ID (deutsch)] */
export const ELEMENTS = {
  soc: ["sensor", "soc", ["batterie_soc"]],
  range: ["sensor", "reichweite", ["reichweite"]],
  odometer: ["sensor", "kilometerstand", ["kilometerstand"]],
  voltage: ["sensor", "batteriespannung", ["batteriespannung"]],
  charge_rate: ["sensor", "laderate", ["laderate"]],
  charge_status: ["sensor", "ladestatus", ["ladestatus"]],
  charge_time: ["sensor", "verbleibende_ladezeit", ["verbleibende_ladezeit"]],
  updated: ["sensor", "letztes_update", ["letztes_update"]],
  plug: ["binary_sensor", "angesteckt", ["angesteckt"]],
  limit: ["number", "ladelimit", ["ladelimit"]],
  climate: ["switch", "vorklimatisierung", ["vorklimatisierung"]],
};

/** Positionen (Mitte des Elements) in % der Bildflaeche. */
export const LAYOUT = {
  // A/C (links) und Stecker (rechts) in einer Zeile: gleiche Oberkante, nah an der Kopfzeile (% der Bildgroesse)
  symbols: { gap: 1.5, side: 6 },
  nodata: { x: 50, y: 50 },
  // Reichweite, Ladestand und Ladelimit: ein gemeinsamer, rechtsbuendiger Block (Abstaende in % der Kartengroesse)
  stack: { right: 8, bottom: 4 },
  odometer: { x: 27, y: 91 },
};

const BAD = new Set(["unavailable", "unknown", undefined, null, ""]);

/** Abstand/Seitenrand der Symbolzeile unter der Kopfzeile (Vierergruppe liegt oben im Bild, % der Kartenbreite). */
export function symbolsStyle(layout = LAYOUT) {
  return `margin-top:${layout.symbols.gap}%;padding:0 ${layout.symbols.side}%;`;
}

/** CSS-Position des rechtsbuendigen Blocks unten rechts. */
export function stackStyle(layout = LAYOUT) {
  return `right:${layout.stack.right}%;bottom:${layout.stack.bottom}%;`;
}

export function isValid(stateObj) {
  return !!stateObj && !BAD.has(stateObj.state);
}

/** Entity-IDs je Element: config.entities > hass.entities (Device + translation_key) > ID-Suffix. */
export function resolveEntities(hass, config) {
  const out = {};
  const override = config.entities || {};
  const ents = hass.entities || {};
  const deviceIds = new Set();
  if (config.device_id) deviceIds.add(config.device_id);
  if (config.config_entry_id) {
    for (const [id, dev] of Object.entries(hass.devices || {})) {
      if (dev.primary_config_entry === config.config_entry_id) deviceIds.add(id);
    }
  }
  const own = Object.values(ents).filter((e) => e.platform === DOMAIN && deviceIds.has(e.device_id));
  for (const [el, [domain, tkey, suffixes]] of Object.entries(ELEMENTS)) {
    if (override[el]) { out[el] = override[el]; continue; }
    let hit = own.find((e) => e.entity_id.startsWith(domain + ".") && e.translation_key === tkey);
    if (!hit) {
      // Fallback, falls hass.entities keinen translation_key liefert
      hit = own.find((e) => e.entity_id.startsWith(domain + ".") && !e.translation_key
        && suffixes.some((s) => e.entity_id.endsWith("_" + s)));
    }
    if (hit) out[el] = hit.entity_id;
  }
  return out;
}

/** Minuten -> "1 h 30 min" | "45 min" | "2 h". */
export function formatDuration(minutes) {
  const m = Math.round(Number(minutes));
  if (!Number.isFinite(m) || m <= 0) return "";
  const h = Math.floor(m / 60), r = m % 60;
  if (h && r) return `${h} h ${r} min`;
  return h ? `${h} h` : `${r} min`;
}

export function formatNumber(value, language, digits = 0) {
  const n = Number(value);
  if (!Number.isFinite(n)) return "–";
  return new Intl.NumberFormat(language || "de", { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(n);
}

export function formatUpdated(iso, language, timeZone) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "–";
  return new Intl.DateTimeFormat(language || "de", { dateStyle: "short", timeStyle: "short", timeZone }).format(d);
}

/** Zeile unter dem Stand: nur beim Laden mit Restzeit > 0. */
export function chargeInfo(status, remainingMinutes, rate, language) {
  if (!isValid(status) || status.state !== "in_progress") return "";
  // Beim Laden immer "Laedt"; Restzeit und Laderate nur, wenn das Fahrzeug sie meldet (> 0)
  let text = "Lädt";
  const dur = isValid(remainingMinutes) ? formatDuration(remainingMinutes.state) : "";
  if (dur) text = `Fertig in ${dur}`;
  if (isValid(rate) && Number(rate.state) > 0) text += ` · +${formatNumber(rate.state, language, 0)} km/h`;
  return text;
}

/** Texte der Kopfzeile ueber dem Bild: links Stand, rechts Ladeinfo (leer, wenn aus/nicht ladend). */
export function headerParts(config, ids, S, language, timeZone) {
  const stand = config.show_updated && ids.updated
    ? `Stand: ${isValid(S.updated) ? formatUpdated(S.updated.state, language, timeZone) : "–"}` : "";
  const info = config.show_charge_info ? chargeInfo(S.charge_status, S.charge_time, S.charge_rate, language) : "";
  return { stand, info };
}

/** Keine Fahrzeugdaten: SoC UND letztes Update fehlen bzw. sind nicht verfuegbar. */
export function hasNoData(states) {
  return !isValid(states.soc) && !isValid(states.updated);
}

export function socColor(soc) {
  const v = Number(soc);
  if (!Number.isFinite(v)) return "var(--disabled-text-color, #9e9e9e)";
  if (v <= 20) return "var(--error-color, #db4437)";
  if (v <= 40) return "var(--warning-color, #ffa600)";
  return "var(--success-color, #43a047)";
}

export function batteryIcon(soc, charging = false) {
  const v = Number(soc);
  if (!Number.isFinite(v)) return "mdi:battery-unknown";
  const step = Math.max(0, Math.min(100, Math.round(v / 10) * 10));
  if (charging) return step <= 0 ? "mdi:battery-charging-outline" : `mdi:battery-charging-${step}`;
  return step >= 100 ? "mdi:battery" : step <= 0 ? "mdi:battery-outline" : `mdi:battery-${step}`;
}

/** Rot nur bei Ladefehler; grau = PSA meldet nicht angesteckt (oder unbekannt); gruen = laedt; orange = angesteckt, laedt nicht. */
export function plugColor(plug, status) {
  if (isValid(status) && status.state === "failure") return "var(--error-color, #db4437)";
  if (!isValid(plug) || plug.state !== "on") return "var(--disabled-text-color, #9e9e9e)";
  if (isValid(status) && status.state === "in_progress") return "var(--success-color, #43a047)";
  return "var(--warning-color, #ffa600)";
}

export function plugTitle(plug, status) {
  if (isValid(status) && status.state === "failure") return "Stecker: Ladefehler";
  if (!isValid(plug) || plug.state !== "on") return "Stecker: nicht bestätigt";
  return isValid(status) && status.state === "in_progress" ? "Stecker: lädt" : "Stecker: angesteckt, lädt nicht";
}

/** Schalt-Befehl mit Bestaetigung: pending = {target:"on"|"off", at:ms} oder undefined. */
export function climateAction(pending, stateObj) {
  if (pending || !isValid(stateObj)) return null;
  return stateObj.state === "on" ? "turn_off" : "turn_on";
}

/** "pending" | "confirmed" | "timeout" (Zielzustand erreicht bzw. Frist abgelaufen). */
export function pendingStatus(pending, stateObj, now, timeoutMs) {
  if (isValid(stateObj) && stateObj.state === pending.target) return "confirmed";
  return now - pending.at >= timeoutMs ? "timeout" : "pending";
}

/** Ladelimit +/-: auf Raster und Bereich der number-Entity begrenzen. */
export function stepLimit(current, direction, step, min, max) {
  const s = Math.min(20, Math.max(1, Number(step) || 5));
  const lo = Number.isFinite(Number(min)) ? Number(min) : 0;
  const hi = Number.isFinite(Number(max)) ? Number(max) : 100;
  const base = Number.isFinite(Number(current)) ? Number(current) : lo;
  return Math.min(hi, Math.max(lo, base + direction * s));
}

export const DEFAULTS = {
  show_climate: true, show_plug: true, show_range: true, show_soc: true, show_odometer: true,
  show_charge_info: true, show_updated: true, show_limit: true, limit_step: 5, limit_delay: 3000, climate_timeout: 240000,
};

export function normalizeConfig(config) {
  if (!config || (!config.config_entry_id && !config.device_id)) {
    throw new Error("config_entry_id oder device_id ist erforderlich");
  }
  const c = { ...DEFAULTS, ...config };
  c.limit_step = Math.min(20, Math.max(1, Number(c.limit_step) || DEFAULTS.limit_step));
  c.limit_delay = Math.max(0, Number(c.limit_delay ?? DEFAULTS.limit_delay));
  c.climate_timeout = Math.max(5000, Number(c.climate_timeout ?? DEFAULTS.climate_timeout) || DEFAULTS.climate_timeout);
  return c;
}

export const EDITOR_SCHEMA = [
  { name: "config_entry_id", selector: { config_entry: { integration: DOMAIN } } },
  { name: "device_id", selector: { device: { integration: DOMAIN } } },
  { name: "image", selector: { text: {} } },
  {
    type: "grid", name: "", schema: [
      { name: "show_updated", selector: { boolean: {} } },
      { name: "show_charge_info", selector: { boolean: {} } },
      { name: "show_climate", selector: { boolean: {} } },
      { name: "show_plug", selector: { boolean: {} } },
      { name: "show_range", selector: { boolean: {} } },
      { name: "show_soc", selector: { boolean: {} } },
      { name: "show_odometer", selector: { boolean: {} } },
      { name: "show_limit", selector: { boolean: {} } },
    ],
  },
  { name: "limit_step", selector: { number: { min: 1, max: 20, mode: "box" } } },
  { name: "limit_delay", selector: { number: { min: 0, max: 30000, step: 100, unit_of_measurement: "ms", mode: "box" } } },
  { name: "climate_timeout", selector: { number: { min: 5000, max: 900000, step: 1000, unit_of_measurement: "ms", mode: "box" } } },
];

const EDITOR_LABELS = {
  config_entry_id: "Integrationseintrag", device_id: "Gerät (alternativ)", image: "Bild (URL, optional)",
  show_updated: "Stand anzeigen", show_charge_info: "Ladeinfo anzeigen", show_climate: "Klima anzeigen",
  show_plug: "Stecker anzeigen", show_range: "Reichweite anzeigen", show_soc: "Ladestand anzeigen",
  show_odometer: "Fahrleistung anzeigen", show_limit: "Ladelimit anzeigen",
  limit_step: "Ladelimit-Schritt", limit_delay: "Ladelimit-Verzögerung", climate_timeout: "Klima: Zeitlimit Bestätigung",
};

/* ---------------- Custom Elements (nur im Browser) ---------------- */
if (typeof window !== "undefined" && typeof customElements !== "undefined") {
  window.customCards = window.customCards || [];
  if (!window.customCards.some((c) => c.type === "psacc-fahrzeug-card")) {
    window.customCards.push({
      type: "psacc-fahrzeug-card", name: "PSA Fahrzeug",
      description: "Fahrzeug-Übersicht (Ladestand, Reichweite, Stecker, Klima, Ladelimit)", preview: true,
    });
  }

  (async () => {
    await customElements.whenDefined("ha-panel-lovelace");
    const LitElement = Object.getPrototypeOf(customElements.get("ha-panel-lovelace"));
    const { html, css } = LitElement.prototype;

    class PsaccFahrzeugCard extends LitElement {
      static get properties() { return { hass: {}, _config: { state: true }, _pending: { state: true }, _ac: { state: true }, _notice: { state: true } }; }

      static async getConfigElement() { return document.createElement("psacc-fahrzeug-card-editor"); }

      static getStubConfig(hass) {
        const ent = Object.values(hass.entities || {}).find((e) => e.platform === DOMAIN && e.device_id);
        if (!ent) return {};
        const dev = (hass.devices || {})[ent.device_id];
        return dev?.primary_config_entry ? { config_entry_id: dev.primary_config_entry } : { device_id: ent.device_id };
      }

      setConfig(config) { this._config = normalizeConfig(config); this._pending = undefined; this._clearAc(); }
      getCardSize() { return 6; }
      getGridOptions() { return { columns: 12, rows: "auto", min_columns: 6 }; }

      get _ids() { return resolveEntities(this.hass, this._config); }
      _st(el) { const id = this._ids[el]; return id ? this.hass.states[id] : undefined; }
      _lang() { return this.hass.locale?.language || this.hass.language || "de"; }

      _moreInfo(el) {
        const entityId = this._ids[el];
        if (!entityId) return;
        this.dispatchEvent(new CustomEvent("hass-more-info", { bubbles: true, composed: true, detail: { entityId } }));
      }

      _bind(el, onTap) {
        // Tap = natives click (onTap/more-info); Gedrueckthalten = more-info, ausser waehrend Pending. Bewegung/Abbruch verwirft den Halte-Timer.
        let timer, held = false, x = 0, y = 0;
        const cancel = () => clearTimeout(timer);
        return {
          onpointerdown: (e) => { held = false; x = e.clientX; y = e.clientY; cancel(); timer = setTimeout(() => { held = true; if (!this._ac) this._moreInfo(el); }, HOLD_MS); },
          onpointermove: (e) => { if (Math.hypot(e.clientX - x, e.clientY - y) > 10) cancel(); },
          onpointerup: cancel, onpointercancel: cancel, onpointerleave: cancel,
          onclick: () => { if (held) { held = false; return; } onTap ? onTap() : this._moreInfo(el); },
        };
      }

      _clearAc() { clearTimeout(this._acTimer); this._ac = undefined; }

      // Bestaetigung kommt als Zustandswechsel der switch-Entity; bis dahin (oder bis Zeitlimit) sind weitere Klicks gesperrt
      _toggleClimate() {
        const id = this._ids.climate;
        if (id && this._ac) { this._flash("schaltet…"); return; }
        const action = id && climateAction(this._ac, this._st("climate"));
        if (!action) return;
        this._ac = { target: action === "turn_on" ? "on" : "off", at: Date.now() };
        this.hass.callService("switch", action, { entity_id: id }).catch(() => { this._clearAc(); this._flash("Befehl fehlgeschlagen"); });
        this._acTimer = setTimeout(() => this._checkAc(), this._config.climate_timeout);
      }

      _checkAc() {
        if (!this._ac) return;
        const r = pendingStatus(this._ac, this._st("climate"), Date.now(), this._config.climate_timeout);
        if (r === "pending") return;
        this._clearAc();
        if (r === "timeout") this._flash("Befehl nicht bestätigt");
      }

      _flash(text) {
        this._notice = text;
        clearTimeout(this._noticeTimer);
        this._noticeTimer = setTimeout(() => { this._notice = undefined; }, 6000);
      }

      willUpdate(changed) { if (changed.has("hass") && this._ac) this._checkAc(); }

      disconnectedCallback() { super.disconnectedCallback?.(); clearTimeout(this._acTimer); clearTimeout(this._noticeTimer); }

      _changeLimit(direction) {
        const st = this._st("limit");
        if (!isValid(st)) return;
        const cur = this._pending ?? Number(st.state);
        const next = stepLimit(cur, direction, this._config.limit_step, st.attributes.min, st.attributes.max);
        this._pending = next;
        clearTimeout(this._limitTimer);
        this._limitTimer = setTimeout(() => {
          this.hass.callService("number", "set_value", { entity_id: this._ids.limit, value: next });
          this._pending = undefined;
        }, this._config.limit_delay);
      }

      _pos(name, extra = "") {
        const p = LAYOUT[name];
        return `left:${p.x}%;top:${p.y}%;${extra}`;
      }

      _val(el, digits) {
        const st = this._st(el);
        if (!isValid(st)) return "–";
        const unit = st.attributes.unit_of_measurement ? ` ${st.attributes.unit_of_measurement}` : "";
        return `${formatNumber(st.state, this._lang(), digits)}${unit}`;
      }

      render() {
        if (!this._config || !this.hass) return html``;
        const c = this._config, ids = this._ids;
        const S = Object.fromEntries(Object.keys(ELEMENTS).map((k) => [k, this._st(k)]));
        const nodata = hasNoData(S);
        const dim = nodata ? "dim" : "";
        const grey = "var(--disabled-text-color, #9e9e9e)";
        const lang = this._lang();
        const head = headerParts(c, ids, S, lang, this.hass.config?.time_zone);
        const image = c.image || DEFAULT_IMAGE;
        const climate = this._bind("climate", () => this._toggleClimate());
        const socOk = isValid(S.soc);
        const limitOk = isValid(S.limit);
        const limitShown = this._pending ?? (limitOk ? Number(S.limit.state) : undefined);

        return html`<ha-card>
          <div class="frame" style="background-image:url('${image}')">
            ${nodata ? html`<div class="el text big" style=${this._pos("nodata")}>Keine Fahrzeugdaten</div>` : ""}
            <div class="top">
            ${head.stand || head.info ? html`<div class="head ${dim}">
              ${head.stand ? html`<span class="stand" @click=${() => this._moreInfo("updated")}>${head.stand}</span>` : html`<span></span>`}
              ${head.info ? html`<span class="info">${head.info}</span>` : ""}</div>` : ""}
            ${(c.show_climate && ids.climate) || (c.show_plug && ids.plug) ? html`<div class="symbols" style=${symbolsStyle()}>
              ${c.show_climate && ids.climate ? html`<div class="icon ${dim} ${this._ac ? "pending" : ""}" style=${nodata ? "pointer-events:none;" : ""}
                  title=${this._ac ? "schaltet…" : ""} @pointerdown=${climate.onpointerdown} @pointermove=${climate.onpointermove} @pointerup=${climate.onpointerup} @pointercancel=${climate.onpointercancel} @pointerleave=${climate.onpointerleave} @click=${climate.onclick}>
                <ha-icon icon="mdi:air-conditioner" style="color:${isValid(S.climate) ? (S.climate.state === "on" ? "var(--primary-color, #03a9f4)" : "#fff") : grey}"></ha-icon></div>` : html`<span></span>`}
              ${c.show_plug && ids.plug ? html`<div class="icon ${dim}" title=${plugTitle(S.plug, S.charge_status)} @click=${() => this._moreInfo("plug")}>
                <ha-icon icon="mdi:ev-plug-type2" style="color:${plugColor(S.plug, S.charge_status)}"></ha-icon></div>` : ""}
            </div>` : ""}
            ${this._notice ? html`<div class="notice">${this._notice}</div>` : ""}
            </div>
            ${(c.show_range && ids.range) || (c.show_soc && ids.soc) || (c.show_limit && ids.limit) ? html`<div class="stack" style=${stackStyle()}>
              ${c.show_range && ids.range ? html`<div class="row text ${dim}" @click=${() => this._moreInfo("range")}>
                ${this._val("range", 0)}</div>` : ""}
              ${c.show_soc && ids.soc ? html`<div class="row text ${dim}" @click=${() => this._moreInfo("soc")}>
                <ha-icon class="inline" icon=${batteryIcon(socOk ? S.soc.state : NaN, isValid(S.charge_status) && S.charge_status.state === "in_progress")} style="color:${socOk ? socColor(S.soc.state) : grey}"></ha-icon>
                ${this._val("soc", 0)}</div>` : ""}
              ${c.show_limit && ids.limit ? html`<div class="row text limit ${dim}" style=${nodata ? "pointer-events:none;" : ""}>
                <span class="btn" @click=${() => this._changeLimit(-1)}>−</span>
                <span class="val" @click=${() => this._moreInfo("limit")}>${limitShown === undefined ? "–" : `${formatNumber(limitShown, lang, 0)}%`}</span>
                <span class="btn" @click=${() => this._changeLimit(1)}>+</span></div>` : ""}
            </div>` : ""}
            ${c.show_odometer && ids.odometer ? html`<div class="el text ${dim}" style=${this._pos("odometer")} @click=${() => this._moreInfo("odometer")}>
              Fahrleistung: ${this._val("odometer", 1)}</div>` : ""}
          </div></ha-card>`;
      }

      static get styles() {
        return css`
          ha-card { overflow: hidden; }
          .top { position: absolute; top: 0; left: 0; right: 0; background: linear-gradient(rgba(0,0,0,.4), rgba(0,0,0,0)); }
          .head { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: baseline; gap: 2px 12px; padding: 6px 12px 2px; font-size: .95em; color: #fff; text-shadow: 0 0 4px rgba(0,0,0,.9), 1px 1px 2px rgba(0,0,0,.9); }
          .symbols { display: flex; justify-content: space-between; align-items: flex-start; }
          .symbols .icon { cursor: pointer; user-select: none; line-height: 0; }
          .head .stand { cursor: pointer; }
          .head .info { margin-left: auto; font-weight: 500; }
          .frame { position: relative; width: 100%; aspect-ratio: 4 / 3; background-size: cover; background-position: center; color: #fff; }
          .el { position: absolute; transform: translate(-50%, -50%); white-space: nowrap; cursor: pointer; user-select: none; }
          .text { color: #fff; font-size: 1.1em; font-weight: 500; text-shadow: 0 0 4px rgba(0,0,0,.9), 1px 1px 2px rgba(0,0,0,.9); }
          .text.small { font-size: .95em; }
          .text.big { font-size: 1.5em; }
          .icon ha-icon { --mdc-icon-size: 32px; filter: drop-shadow(1px 1px 2px rgba(0,0,0,.9)); }
          .inline { --mdc-icon-size: 24px; vertical-align: middle; filter: drop-shadow(1px 1px 2px rgba(0,0,0,.9)); }
          .dim { opacity: .45; }
          .icon.pending { animation: psacc-pulse 1.2s ease-in-out infinite; }
          .icon.pending ha-icon { color: var(--warning-color, #ffa600) !important; }
          @keyframes psacc-pulse { 50% { opacity: .35; } }
          @media (prefers-reduced-motion: reduce) { .icon.pending { animation: none; } }
          .notice { padding: 2px 12px 4px; font-size: .9em; color: #fff; text-align: center; text-shadow: 0 0 4px rgba(0,0,0,.9); }
          .stack { position: absolute; display: flex; flex-direction: column; align-items: flex-end; gap: 3px; }
          .row { cursor: pointer; user-select: none; white-space: nowrap; display: flex; align-items: center; justify-content: flex-end; gap: 6px; }
          .limit { gap: 10px; }
          .limit .btn:last-child { padding-right: 0; }
          .limit .btn { padding: 0 8px; font-size: 1.3em; }
        `;
      }
    }

    class PsaccFahrzeugCardEditor extends LitElement {
      static get properties() { return { hass: {}, _config: { state: true } }; }
      setConfig(config) { this._config = config; }
      render() {
        if (!this.hass || !this._config) return html``;
        return html`<ha-form .hass=${this.hass} .data=${{ ...DEFAULTS, ...this._config }} .schema=${EDITOR_SCHEMA}
          .computeLabel=${(s) => EDITOR_LABELS[s.name] || s.name} @value-changed=${this._changed}></ha-form>`;
      }
      _changed(ev) {
        const cfg = { ...ev.detail.value };
        // Entweder Eintrag oder Geraet: leere Felder nicht speichern
        for (const k of ["config_entry_id", "device_id", "image"]) if (!cfg[k]) delete cfg[k];
        this.dispatchEvent(new CustomEvent("config-changed", { detail: { config: cfg }, bubbles: true, composed: true }));
      }
    }

    if (!customElements.get("psacc-fahrzeug-card")) customElements.define("psacc-fahrzeug-card", PsaccFahrzeugCard);
    if (!customElements.get("psacc-fahrzeug-card-editor")) customElements.define("psacc-fahrzeug-card-editor", PsaccFahrzeugCardEditor);
  })();
}
