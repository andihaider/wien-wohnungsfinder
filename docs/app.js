"use strict";

const DISTRICTS = {
  "1010": "1. Innere Stadt", "1030": "3. Landstraße", "1040": "4. Wieden", "1050": "5. Margareten",
  "1060": "6. Mariahilf", "1070": "7. Neubau", "1080": "8. Josefstadt", "1120": "12. Meidling",
  "1150": "15. Rudolfsheim-Fünfhaus",
};
const OLD_DEFAULT_DISTRICTS = ["1040", "1050", "1060", "1070"];

const DEFAULT_TEMPLATE = `Sehr geehrte Damen und Herren,

ich interessiere mich sehr für Ihr Inserat „{titel}“ ({adresse}, {preis}, {flaeche}) und würde die Wohnung gerne so bald wie möglich besichtigen.

{ueber_mich}

Telefon: {telefon}
Meine Mietervorstellung: {mietervorstellung}
Inserat: {link}

Mit freundlichen Grüßen
{name}`;

const DEFAULT_WG_TEMPLATE = `Hallo!

euer Zimmer „{titel}“ ({preis}, {flaeche}) klingt richtig gut – ich würde euch gerne kennenlernen und es mir anschauen.

{ueber_mich}

Telefon: {telefon}
Meine Mietervorstellung: {mietervorstellung}

Liebe Grüße
{name}`;
// Frühere Standard-Vorlagen – werden automatisch auf die neue Version gehoben
const OLD_TEMPLATES = [`Sehr geehrte Damen und Herren,

ich interessiere mich sehr für Ihr Inserat „{titel}“ ({adresse}, {preis}, {flaeche}) und würde die Wohnung gerne so bald wie möglich besichtigen.

{ueber_mich}

Telefon: {telefon}
Inserat: {link}

Mit freundlichen Grüßen
{name}`, `Hallo!

euer Zimmer „{titel}“ ({preis}, {flaeche}) klingt richtig gut – ich würde euch gerne kennenlernen und es mir anschauen.

{ueber_mich}

Telefon: {telefon}

Liebe Grüße
{name}`];

const DEFAULTS = {
  maxPrice: 700, minPrice: 0, minArea: 0,
  wgMaxPrice: 600, wgMinRoom: 15, wgMaxPeople: 4, maxEigenmittel: 50000,
  districts: Object.keys(DISTRICTS),
  hidePaywall: true, hideSublet: true, hideWomenOnly: false, hideBefristet: false, hideMoebliert: false, hideEstimated: false,
  name: "", phone: "", about: "", template: DEFAULT_TEMPLATE, wgTemplate: DEFAULT_WG_TEMPLATE, docScript: "", docKey: "",
  sort: "score", tab: "new",
};
const TABS = ["new", "flats", "wg", "mine", "out"];
const STATUS = { asked: "Angefragt", visit: "Besichtigung", no: "Abgesagt" };

/* ---------- Speicher (nur dieses Gerät) ---------- */
const store = {
  get(k, d) { try { const v = localStorage.getItem("wf_" + k); return v == null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem("wf_" + k, JSON.stringify(v)); } catch {} },
};
let S = Object.assign({}, DEFAULTS, store.get("settings", {}));
if (S.template === OLD_TEMPLATES[0]) S.template = DEFAULT_TEMPLATE;
// Umstellung Okt. 2026: mehr Bezirke und 700 € – alte Standardwerte automatisch mitziehen
if (S.maxPrice === 650) S.maxPrice = 700;
if (S.districts && S.districts.length === 4 && OLD_DEFAULT_DISTRICTS.every(z => S.districts.includes(z))) {
  S.districts = Object.keys(DISTRICTS);
}
if (S.wgTemplate === OLD_TEMPLATES[1]) S.wgTemplate = DEFAULT_WG_TEMPLATE;
let docLinks = store.get("docLinks", {});         // Adresse -> PDF-Link der Mietervorstellung
if (!TABS.includes(S.tab)) S.tab = "new";
let favs = new Set(store.get("favs", []));
let hidden = new Set(store.get("hidden", []));
let statuses = store.get("status", {});            // id -> {s: "asked"|"visit"|"no", t: ISO}
const lastVisit = store.get("lastVisit", null);
let DATA = { items: [] };

const saveSettings = () => store.set("settings", S);
const $ = (s, el = document) => el.querySelector(s);

/* ---------- Bewertung (gleiche Logik wie scraper/scoring.py) ---------- */
const clamp = (x, a = 0, b = 1) => Math.max(a, Math.min(b, x));
const hours = iso => iso ? (Date.now() - new Date(iso).getTime()) / 36e5 : 1e9;
const has = (it, f) => (it.flags || []).includes(f);
const isWG = it => it.category === "wg";
const outdoor = it => ["Balkon", "Terrasse", "Loggia", "Garten"].some(f => has(it, f));

function freshPoints(it) {
  const age = Math.min(hours(it.first_seen), hours(it.published));
  return age < 24 ? 15 : age < 72 ? 9 : age < 168 ? 4 : 0;
}

function score(it) {
  const price = it.price_total, area = it.area || 0;
  let s = 0;
  if (isWG(it)) {
    s += 30 * clamp((S.wgMaxPrice - price) / (S.wgMaxPrice * 0.35));
    s += 30 * clamp((area - 12) / 13);
    s += { 2: 10, 3: 7, 4: 3 }[it.wg_size] || 0;
    s += freshPoints(it);
    if (outdoor(it)) s += 6;
    if (has(it, "Altbau") || has(it, "saniert") || has(it, "Neubau/Erstbezug")) s += 4;
    if (has(it, "unbefristet")) s += 3;
    if (has(it, "befristet")) s -= 5;
  } else {
    s += 25 * clamp((S.maxPrice - price) / (S.maxPrice * 0.35));
    if (it.ppsqm) s += 30 * clamp((20 - it.ppsqm) / 10);
    s += 20 * clamp((area - 25) / 30);
    s += freshPoints(it);
    if (has(it, "provisionsfrei")) s += 5;
    if (outdoor(it)) s += 5;
    if (has(it, "unbefristet")) s += 4;
    if (has(it, "Lift")) s += 2;
    if (it.email) s += 3;
    if (has(it, "befristet")) s -= 5;
    if (has(it, "Ablöse")) s -= 4;
    if (it.price_estimated) s -= 3;
  }
  if (has(it, "Bezahlportal")) s -= 15;
  if (has(it, "Zwischenmiete")) s -= 10;
  if (it.eigenmittel) s -= Math.min(12, it.eigenmittel / 2500);
  return Math.round(clamp(s, 0, 100));
}

function visible(it) {
  if (it.excluded || hidden.has(it.id)) return false;
  if ((statuses[it.id] || {}).s === "no") return false;
  if (S.maxEigenmittel < 50000 && (it.eigenmittel || 0) > S.maxEigenmittel) return false;
  if (!S.districts.includes(it.zip)) return false;
  if (S.hidePaywall && has(it, "Bezahlportal")) return false;
  if (S.hideSublet && has(it, "Zwischenmiete")) return false;
  if (S.hideBefristet && has(it, "befristet")) return false;
  if (S.hideMoebliert && !isWG(it) && has(it, "möbliert")) return false;
  if (isWG(it)) {
    if (S.hideWomenOnly && has(it, "nur Frauen/FLINTA*")) return false;
    if (it.price_total > S.wgMaxPrice) return false;
    if ((it.area || 0) < S.wgMinRoom) return false;
    if (it.wg_size && it.wg_size > S.wgMaxPeople) return false;
    return true;
  }
  if (it.price_total > S.maxPrice || it.price_total < S.minPrice) return false;
  if (S.minArea && (it.area || 0) < S.minArea) return false;
  if (S.hideEstimated && it.price_estimated) return false;
  return true;
}

// "Neu" = in den letzten 24 h auf dem Markt (Veröffentlichungsdatum, sonst wann wir es gefunden haben)
const isNew = it => Math.max(hours(it.first_seen), it.published ? hours(it.published) : 0) < 24;
const isNewSinceVisit = it => lastVisit && it.first_seen > lastVisit;

/* ---------- Formatierung ---------- */
const eur = n => "€ " + Math.round(n).toLocaleString("de-AT");
const num = n => (Math.round(n * 10) / 10).toLocaleString("de-AT");
function ago(iso) {
  const h = hours(iso);
  if (h < 1) return "vor " + Math.max(1, Math.round(h * 60)) + " Min.";
  if (h < 24) return "vor " + Math.round(h) + " Std.";
  const d = Math.round(h / 24);
  return d === 1 ? "gestern" : "vor " + d + " Tagen";
}
const FLAG_CLASS = {
  "provisionsfrei": "good", "unbefristet": "good", "Balkon": "good", "Terrasse": "good", "Loggia": "good", "Garten": "good",
  "befristet": "warn", "Ablöse": "warn", "möbliert": "warn", "Zwischenmiete": "warn",
  "Bezahlportal": "bad", "Genossenschaft": "good",
};
const escapeHtml = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

/* ---------- Anfrage-Text ---------- */
function defaultAddress(it) {
  const a = (it.address || "").trim();
  if (!a || /^\d{4}\s*Wien$/.test(a)) return `${it.zip} Wien`;
  return /\b1\d{3}\b/.test(a) ? a : `${a}, ${it.zip} Wien`;
}
function fillTemplate(it, address, docLink) {
  const tpl = isWG(it) ? S.wgTemplate : S.template;
  const map = {
    titel: it.title, adresse: address || defaultAddress(it),
    preis: eur(it.price_total) + (it.price_estimated ? " (geschätzt)" : ""),
    flaeche: it.area ? num(it.area) + " m²" : "", link: (it.links[0] || {}).url || "",
    name: S.name || "", telefon: S.phone || "", ueber_mich: S.about || "",
    mietervorstellung: docLink || "",
  };
  return tpl.replace(/\{(\w+)\}/g, (m, k) => (k in map ? map[k] : m))
    .replace(/^[^\n:]{1,30}:[ \t]*$/gm, "")   // leere Felder wie "Telefon: " weglassen
    .replace(/\n{3,}/g, "\n\n");
}
function mailto(it, text) {
  return "mailto:" + encodeURIComponent(it.email) +
    "?subject=" + encodeURIComponent("Anfrage: " + it.title.slice(0, 90)) + "&body=" + encodeURIComponent(text);
}

/* ---------- Anfrage-Fenster: Text und Adresse anpassen, Mietervorstellung erstellen ---------- */
function insertDocLink(text, link) {
  const line = "Meine Mietervorstellung: " + link;
  if (/^Meine Mietervorstellung:.*$/m.test(text)) return text.replace(/^Meine Mietervorstellung:.*$/m, line);
  // vor der Grußformel einfügen, sonst ans Ende
  const m = text.match(/\n(Mit freundlichen Grüßen|Liebe Grüße|Viele Grüße|Beste Grüße|LG|Lg)\b/);
  return m ? text.slice(0, m.index) + "\n" + line + "\n" + text.slice(m.index) : text.trimEnd() + "\n\n" + line;
}

function openAsk(it, onAsked) {
  const dlg = $("#ask"), addr = $("#a-address"), text = $("#a-text"), box = $(".ask-actions", dlg), hint = $("#a-hint");
  $(".ask-title", dlg).textContent = `${it.title} · ${eur(it.price_total)}`;
  addr.value = defaultAddress(it);
  const linkFor = () => docLinks[addr.value.trim()] || "";
  text.value = fillTemplate(it, addr.value, linkFor());
  let edited = false;
  text.oninput = () => { edited = true; };
  addr.oninput = () => { if (!edited) text.value = fillTemplate(it, addr.value, linkFor()); syncDocBtn(); };

  box.innerHTML = "";
  const btn = (label, cls, fn) => {
    const b = document.createElement("button");
    b.type = "button"; b.className = "btn " + (cls || ""); b.textContent = label;
    b.onclick = fn; box.appendChild(b); return b;
  };
  const copy = () => navigator.clipboard?.writeText(text.value).catch(() => {});
  const open = url => window.open(url, "_blank", "noopener");

  if (it.email) btn("✉︎ Per Mail senden", "primary", () => { onAsked(); location.href = mailto(it, text.value); });
  btn("Text kopieren & Inserat öffnen", it.email ? "" : "primary", () => { copy(); onAsked(); open(it.links[0].url); });

  const docBtn = btn("", "", async () => {
    const a = addr.value.trim();
    if (!S.docScript || !S.docKey) {
      hint.textContent = "Zuerst in den Einstellungen Skript-Link und Schlüssel eintragen (siehe Anleitung).";
      return;
    }
    if (!/\d/.test(a)) { hint.textContent = "Bitte zuerst die genaue Adresse mit Hausnummer eintragen."; addr.focus(); return; }
    docBtn.disabled = true; docBtn.textContent = "📄 Wird in Google erstellt … (ca. 5–10 Sek.)"; hint.textContent = "";
    try {
      const url = S.docScript + (S.docScript.includes("?") ? "&" : "?") +
        "key=" + encodeURIComponent(S.docKey) + "&adresse=" + encodeURIComponent(a);
      const res = await (await fetch(url, { redirect: "follow" })).json();
      if (!res.ok) throw new Error(res.error || "Unbekannter Fehler");
      docLinks[a] = res.pdfUrl; store.set("docLinks", docLinks);
      text.value = edited ? insertDocLink(text.value, res.pdfUrl) : fillTemplate(it, a, res.pdfUrl);
      hint.innerHTML = (res.platzhalter ? "" : "⚠︎ In deiner Vorlage fehlt {{ADRESSE}} – die Adresse wurde nicht eingesetzt. ") +
        `Link eingefügt. <a href="${escapeHtml(res.pdfUrl)}" target="_blank" rel="noopener">PDF ansehen</a>`;
    } catch (e) {
      hint.textContent = "Mietervorstellung fehlgeschlagen: " + e.message + " – Skript-Link/Schlüssel prüfen.";
    }
    docBtn.disabled = false; syncDocBtn();
  });
  const syncDocBtn = () => {
    docBtn.textContent = linkFor() ? "📄 Mietervorstellung ✓ (neu erstellen)" : "📄 Mietervorstellung erstellen & Link einfügen";
  };
  syncDocBtn();
  btn("Nur Text kopieren", "ghost", e => { copy(); e.target.textContent = "✓ Kopiert"; });
  hint.textContent = it.email ? "" :
    "Dieses Portal zeigt keine Mail-Adresse: Text wird kopiert, im Kontaktformular einfach einfügen.";
  dlg.showModal();
}

/* ---------- Listen ---------- */
function buildLists() {
  const withScore = arr => arr.map(it => Object.assign(it, { _score: score(it) }));
  const vis = withScore(DATA.items.filter(visible));
  const mine = withScore(DATA.items.filter(it => favs.has(it.id) || statuses[it.id]));
  return {
    new: vis.filter(isNew),
    flats: vis.filter(it => !isWG(it)),
    wg: vis.filter(isWG),
    mine,
    out: withScore(DATA.items.filter(it => it.excluded && S.districts.includes(it.zip))),
  };
}

const SORTERS = {
  score: (a, b) => b._score - a._score,
  new: (a, b) => (b.first_seen || "").localeCompare(a.first_seen || "") || b._score - a._score,
  price: (a, b) => a.price_total - b.price_total,
  ppsqm: (a, b) => (a.ppsqm || 99) - (b.ppsqm || 99),
};
const STATUS_ORDER = { visit: 0, asked: 1, undefined: 2, no: 3 };

function render() {
  const lists = buildLists();
  for (const t of TABS) $("#cnt-" + t).textContent = lists[t].length;
  document.querySelectorAll(".tab").forEach(t => t.classList.toggle("active", t.dataset.tab === S.tab));

  let items = lists[S.tab].slice().sort(SORTERS[S.sort]);
  if (S.tab === "mine") items.sort((a, b) => STATUS_ORDER[(statuses[a.id] || {}).s] - STATUS_ORDER[(statuses[b.id] || {}).s]);
  if (S.tab === "out") items.sort(SORTERS.new);

  const all = Object.keys(DISTRICTS).every(z => S.districts.includes(z));
  const d = all ? `${S.districts.length} Bezirke` : S.districts.map(z => z.slice(1, 3) * 1 + ".").sort((a, b) => parseInt(a) - parseInt(b)).join(" ");
  $("#filter-summary").textContent = S.tab === "wg" ? `WG bis ${eur(S.wgMaxPrice)} · ab ${S.wgMinRoom} m²` : `bis ${eur(S.maxPrice)} · ${d}`;
  $(".sortbar label").style.visibility = ["mine", "out"].includes(S.tab) ? "hidden" : "";

  const main = $("#list");
  main.innerHTML = "";
  if (S.tab === "out" && items.length) {
    main.insertAdjacentHTML("beforeend", `<p class="muted small hint">Diese Inserate hat der Filter aussortiert. Falls hier etwas Passendes dabei ist, sag Bescheid – dann wird die Regel angepasst.</p>`);
  }
  if (!items.length) {
    const msg = {
      new: ["Seit gestern nichts Neues", "Gesucht wird alle 5 Minuten. Unter „Wohnungen“ und „WG“ findest du alle aktuellen Treffer."],
      flats: ["Keine Treffer", "Probier in den Einstellungen ein höheres Budget oder weniger Ausschlüsse."],
      wg: ["Keine passenden WG-Zimmer", "Die Kriterien (Preis, Zimmergröße, WG-Größe) kannst du in den Einstellungen ändern."],
      mine: ["Noch nichts hier", "Tippe auf ☆ oder setze einen Status (Angefragt, Besichtigung), um Wohnungen hier zu sammeln."],
      out: ["Nichts aussortiert", ""],
    }[S.tab];
    main.innerHTML = `<div class="empty"><b>${msg[0]}</b>${msg[1]}</div>`;
  }
  const tpl = $("#card-tpl");
  for (const it of items) main.appendChild(card(it, tpl));
}

function card(it, tpl) {
  const el = tpl.content.firstElementChild.cloneNode(true);
  const img = $("img", el);
  if (it.image) { img.src = it.image; img.onerror = () => img.classList.add("noimg"); }
  else img.classList.add("noimg");

  const sc = $(".score", el);
  if (it.excluded) { sc.textContent = "Aussortiert: " + it.excluded; sc.classList.add("out"); }
  else { sc.textContent = it._score + " Punkte"; if (it._score >= 60) sc.classList.add("hi"); }
  if (isWG(it)) $(".media", el).insertAdjacentHTML("beforeend", `<span class="badge-cat">WG-Zimmer</span>`);
  if (!(isNewSinceVisit(it) || isNew(it)) || it.excluded) el.classList.add("seen-old");

  const fav = $(".fav", el);
  const syncFav = () => { fav.textContent = favs.has(it.id) ? "★" : "☆"; fav.classList.toggle("on", favs.has(it.id)); };
  syncFav();
  fav.onclick = () => {
    favs.has(it.id) ? favs.delete(it.id) : favs.add(it.id);
    store.set("favs", [...favs]); syncFav(); $("#cnt-mine").textContent = buildLists().mine.length;
  };

  $(".price", el).innerHTML = eur(it.price_total) +
    `<small>${it.price_estimated ? "ca. gesamt (" + eur(it.price) + " netto)" : (it.price_note || "Miete")}</small>`;
  $(".facts", el).textContent = (isWG(it)
    ? [it.area && num(it.area) + " m² Zimmer", it.wg_size && it.wg_size + "er WG"]
    : [it.area && num(it.area) + " m²", it.rooms && num(it.rooms) + " Zi.", it.ppsqm && "€ " + num(it.ppsqm) + "/m²"]
  ).filter(Boolean).join(" · ");
  if (it.eigenmittel) {
    $(".flags", el).insertAdjacentHTML("beforebegin",
      `<p class="eigenmittel">+ ${eur(it.eigenmittel)} Eigenmittel / Finanzierungsbeitrag (einmalig)</p>`);
  }
  $(".title", el).textContent = it.title;
  $(".where", el).textContent = [DISTRICTS[it.zip], it.address && !/^\d{4}\s*Wien$/.test(it.address) ? it.address : "", ago(it.first_seen)]
    .filter(Boolean).join(" · ");

  const flags = $(".flags", el);
  for (const f of it.flags || []) {
    const s = document.createElement("span");
    s.className = "flag " + (FLAG_CLASS[f] || "");
    s.textContent = f;
    flags.appendChild(s);
  }

  const desc = (it.description || "").trim();
  if (desc) $(".desc", el).textContent = desc; else $("details", el).remove();

  // Status: Angefragt / Besichtigung / Abgesagt
  const st = $(".status", el);
  const syncStatus = () => {
    const cur = (statuses[it.id] || {}).s;
    st.querySelectorAll("button").forEach(b => b.classList.toggle("on", b.dataset.s === cur));
    const t = (statuses[it.id] || {}).t;
    $(".status-note", el).textContent = cur ? STATUS[cur] + " " + ago(t) : "";
  };
  st.innerHTML = Object.entries(STATUS).map(([k, v]) => `<button type="button" data-s="${k}">${v}</button>`).join("");
  st.onclick = e => {
    const b = e.target.closest("button"); if (!b) return;
    const cur = (statuses[it.id] || {}).s;
    if (cur === b.dataset.s) delete statuses[it.id]; else statuses[it.id] = { s: b.dataset.s, t: new Date().toISOString() };
    store.set("status", statuses);
    if (b.dataset.s === "no" && S.tab !== "mine") { el.style.transition = "opacity .2s"; el.style.opacity = "0"; setTimeout(render, 200); }
    else { syncStatus(); $("#cnt-mine").textContent = buildLists().mine.length; }
  };
  syncStatus();

  const actions = $(".actions", el);
  const add = (label, href, cls, target) => {
    const a = document.createElement("a");
    a.className = "btn " + (cls || ""); a.textContent = label; a.href = href;
    if (target) { a.target = "_blank"; a.rel = "noopener"; }
    actions.appendChild(a); return a;
  };
  const markAsked = () => {
    if (!statuses[it.id]) { statuses[it.id] = { s: "asked", t: new Date().toISOString() }; store.set("status", statuses); syncStatus(); }
  };
  const ask = add("Anfragen", "#", "primary");
  ask.onclick = e => { e.preventDefault(); openAsk(it, markAsked); };
  add("Inserat öffnen", it.links[0].url, "", true);
  if (it.phone) add("☎ Anrufen", "tel:" + it.phone.replace(/[^\d+]/g, ""), "");
  if (!it.excluded) {
    const hide = add("Ausblenden", "#", "ghost");
    hide.onclick = e => {
      e.preventDefault(); hidden.add(it.id); store.set("hidden", [...hidden]);
      el.style.transition = "opacity .2s"; el.style.opacity = "0"; setTimeout(render, 200);
    };
  }

  $(".src", el).innerHTML = "Gefunden auf: " + it.links.map(l =>
    `<a href="${escapeHtml(l.url)}" target="_blank" rel="noopener">${l.label}</a>`).join(", ") +
    (it.advertiser ? " · Anbieter: " + escapeHtml(it.advertiser) : "") +
    (it.email ? " · " + escapeHtml(it.email) : "");
  return el;
}

/* ---------- Quellen-Status & Warnungen ---------- */
const SOURCE_NAMES = {
  willhaben: "willhaben", derstandard: "DER STANDARD", immoscout24: "ImmoScout24", immowelt: "immowelt",
  wggesucht: "WG-Gesucht", immmo: "IMMMO (inkl. Kurier, Bazar, Wohnkrone)",
  makler: "Makler-Websites (Brezina, TICON, ARWAG, Siedlungsunion)",
  gewofinder: "Genossenschaften (GEWOFinder: Sozialbau, GESIBA, ÖSW, …)",
};

function sourceProblems() {
  const out = [];
  const lastSearch = LAST_RUN || DATA.updated;
  if (lastSearch && hours(lastSearch) > (LAST_RUN ? 1 : 3)) {
    const h = new Date().getHours();
    if (h >= 8 && h <= 23) out.push(`Die automatische Suche ist seit ${ago(lastSearch).replace("vor ", "")} nicht mehr gelaufen.`);
  }
  for (const [k, v] of Object.entries(DATA.sources || {})) {
    if (v.via) continue;
    if (k === "wggesucht") {
      if (!v.last_ok || hours(v.last_ok) > 24) out.push("WG-Gesucht liefert seit über 24 Std. nichts (Captcha-Prüfung).");
    } else if ((v.empty_streak || 0) >= 2) {
      out.push(`${SOURCE_NAMES[k] || k} liefert seit ${v.empty_streak} Läufen keine Inserate.`);
    }
  }
  return out;
}

function renderMeta() {
  const u = DATA.updated;
  const t = iso => new Date(iso).toLocaleTimeString("de-AT", { hour: "2-digit", minute: "2-digit" });
  // "Gesucht" = letzter Suchlauf (von GitHub), "Stand" = letzte inhaltliche Änderung der Liste
  $("#meta").textContent = LAST_RUN
    ? `Zuletzt gesucht ${ago(LAST_RUN)}` + (u ? ` · Liste vom ${t(u)}` : "")
    : (u ? "Aktualisiert " + ago(u) + " · " + t(u) : "Noch keine Daten");

  const probs = sourceProblems();
  const banner = $("#banner");
  banner.hidden = !probs.length;
  banner.innerHTML = probs.length ? "<b>⚠︎ Achtung</b> " + probs.map(escapeHtml).join(" ") : "";

  const src = DATA.sources || {};
  const line = (k, v) => {
    let txt, cls = "ok";
    if (v.via) txt = "gesperrt – Inserate kommen über IMMMO";
    else if (v.skipped) txt = `${v.count} Inserate (seltener abgefragt, zuletzt ${ago(v.last_try || v.last_ok)})`;
    else if (v.ok && v.raw != null) txt = `${v.count} in deinen Bezirken (von ${v.raw} Angeboten insgesamt)`;
    else if (v.ok && v.count) txt = v.count + " Inserate";
    else { txt = v.error || "keine Inserate"; cls = "fail"; }
    return `<li class="${cls}">${SOURCE_NAMES[k] || k}: ${escapeHtml(txt)}</li>`;
  };
  $("#footer").innerHTML = "<b>Quellen beim letzten Lauf</b><ul>" + Object.entries(src).map(([k, v]) => line(k, v)).join("") +
    "</ul>Gesucht wird im 1., 3.–8., 12. und 15. Bezirk alle 5 Minuten (6–23 Uhr): willhaben jedes Mal, ImmoScout24 alle 15 Min., " +
    "immowelt, IMMMO und Makler stündlich, Genossenschaften alle 2 Std., WG-Gesucht alle 4 Std. " +
    "Gespeichert wird nur, wenn sich etwas ändert (spätestens alle 30 Min.). Preise laut Inserat – bitte immer im Original prüfen.";
}

/* ---------- Einstellungen ---------- */
const RANGES = [
  ["#s-max", "maxPrice", "#o-max", eur],
  ["#s-min", "minPrice", "#o-min", v => v ? eur(v) : "egal"],
  ["#s-area", "minArea", "#o-area", v => v ? v + " m²" : "egal"],
  ["#s-wgmax", "wgMaxPrice", "#o-wgmax", eur],
  ["#s-wgroom", "wgMinRoom", "#o-wgroom", v => v ? v + " m²" : "egal"],
  ["#s-wgpeople", "wgMaxPeople", "#o-wgpeople", v => v >= 8 ? "egal" : "max. " + v + "er WG"],
  ["#s-eigen", "maxEigenmittel", "#o-eigen", v => v >= 50000 ? "egal" : v ? "bis " + eur(v) : "keine"],
];
const CHECKS = { "#h-women": "hideWomenOnly", "#h-paywall": "hidePaywall", "#h-sublet": "hideSublet", "#h-befristet": "hideBefristet", "#h-moebliert": "hideMoebliert", "#h-estimated": "hideEstimated" };
const TEXTS = { "#p-docscript": "docScript", "#p-dockey": "docKey", "#p-name": "name", "#p-phone": "phone", "#p-about": "about", "#p-template": "template", "#p-wgtemplate": "wgTemplate" };

function bindSettings() {
  const dlg = $("#settings");
  $("#btn-settings").onclick = () => { syncSettingsUI(); dlg.showModal(); };
  dlg.addEventListener("close", render);

  for (const [id, key, out, fmt] of RANGES) {
    const r = $(id);
    r.oninput = () => { S[key] = +r.value; $(out).textContent = fmt(S[key]); saveSettings(); };
  }
  const chips = $("#s-districts");
  chips.innerHTML = Object.entries(DISTRICTS).map(([z, n]) =>
    `<label><input type="checkbox" value="${z}"><span>${n}</span></label>`).join("");
  chips.onchange = () => { S.districts = [...chips.querySelectorAll("input:checked")].map(i => i.value); saveSettings(); };

  for (const [id, key] of Object.entries(CHECKS)) $(id).onchange = e => { S[key] = e.target.checked; saveSettings(); };
  for (const [id, key] of Object.entries(TEXTS)) $(id).oninput = e => { S[key] = e.target.value; saveSettings(); };
  $("#btn-reset-template").onclick = () => {
    S.template = DEFAULT_TEMPLATE; S.wgTemplate = DEFAULT_WG_TEMPLATE;
    $("#p-template").value = S.template; $("#p-wgtemplate").value = S.wgTemplate; saveSettings();
  };
  $("#btn-unhide").onclick = () => { hidden.clear(); store.set("hidden", []); $("#cnt-hidden").textContent = 0; };
}

function syncSettingsUI() {
  for (const [id, key, out, fmt] of RANGES) { $(id).value = S[key]; $(out).textContent = fmt(S[key]); }
  $("#s-districts").querySelectorAll("input").forEach(i => { i.checked = S.districts.includes(i.value); });
  for (const [id, key] of Object.entries(CHECKS)) $(id).checked = !!S[key];
  for (const [id, key] of Object.entries(TEXTS)) $(id).value = S[key] || "";
  $("#cnt-hidden").textContent = hidden.size;
}

/* ---------- Start ---------- */
document.querySelectorAll(".tab").forEach(t => t.onclick = () => {
  S.tab = t.dataset.tab; saveSettings(); render(); window.scrollTo(0, 0);
  t.scrollIntoView({ inline: "nearest", block: "nearest" });
});
$("#sort").value = S.sort;
$("#sort").onchange = e => { S.sort = e.target.value; saveSettings(); render(); };
bindSettings();

// Daten direkt aus dem Repo laden (max. 5 Min. zwischengespeichert, GitHub Pages bis zu 10 Min. + Build-Zeit)
const REPO = "andihaider/wien-wohnungsfinder";
const DATA_URLS = [`https://raw.githubusercontent.com/${REPO}/main/docs/data/listings.json`, "data/listings.json"];
let LAST_RUN = null;

async function fetchLastRun() {
  // Zeitpunkt des letzten erfolgreichen Suchlaufs – kommt von GitHub, ohne dass gespeichert werden muss
  try {
    const r = await fetch(`https://api.github.com/repos/${REPO}/actions/workflows/suche.yml/runs?per_page=1&status=success`,
      { headers: { Accept: "application/vnd.github+json" } });
    if (r.ok) LAST_RUN = ((await r.json()).workflow_runs || [])[0]?.updated_at || LAST_RUN;
  } catch (e) { /* offline oder Limit erreicht – dann gilt der Listen-Stand */ }
}

async function load() {
  const runP = fetchLastRun();
  let loaded = false;
  for (const url of DATA_URLS) {
    try {
      const r = await fetch(url + (url.startsWith("http") ? "" : "?t=" + Date.now()), { cache: "no-store" });
      if (!r.ok) continue;
      DATA = await r.json();
      loaded = true;
      break;
    } catch (e) { /* nächste Quelle versuchen */ }
  }
  if (!loaded) $("#meta").textContent = "Daten konnten nicht geladen werden – offline?";
  await runP;
  renderMeta();
  render();
  store.set("lastVisit", new Date().toISOString());
}
load();
document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible") load(); });

if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js").catch(() => {});
