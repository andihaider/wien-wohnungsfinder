"use strict";

const DISTRICTS = { "1040": "4. Wieden", "1050": "5. Margareten", "1060": "6. Mariahilf", "1070": "7. Neubau" };

const DEFAULT_TEMPLATE = `Sehr geehrte Damen und Herren,

ich interessiere mich sehr für Ihre Wohnung „{titel}“ ({adresse}, {preis}, {flaeche}) und würde sie gerne so bald wie möglich besichtigen.

{ueber_mich}

Telefon: {telefon}
Inserat: {link}

Mit freundlichen Grüßen
{name}`;

const DEFAULTS = {
  maxPrice: 650, minPrice: 0, minArea: 0,
  districts: Object.keys(DISTRICTS),
  hidePaywall: true, hideGemeinde: false, hideBefristet: false, hideMoebliert: false, hideEstimated: false,
  name: "", phone: "", about: "", template: DEFAULT_TEMPLATE,
  sort: "score", tab: "new",
};

/* ---------- Speicher (nur dieses Gerät) ---------- */
const store = {
  get(k, d) { try { const v = localStorage.getItem("wf_" + k); return v == null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem("wf_" + k, JSON.stringify(v)); } catch {} },
};
let S = Object.assign({}, DEFAULTS, store.get("settings", {}));
let favs = new Set(store.get("favs", []));
let hidden = new Set(store.get("hidden", []));
const lastVisit = store.get("lastVisit", null);
let DATA = { items: [] };

const saveSettings = () => store.set("settings", S);
const $ = (s, el = document) => el.querySelector(s);

/* ---------- Bewertung ---------- */
const clamp = (x, a = 0, b = 1) => Math.max(a, Math.min(b, x));
const hours = iso => iso ? (Date.now() - new Date(iso).getTime()) / 36e5 : 1e9;
const has = (it, f) => (it.flags || []).includes(f);

function score(it) {
  const price = it.price_total;
  let s = 0;
  s += 25 * clamp((S.maxPrice - price) / (S.maxPrice * 0.35));            // günstiger = besser
  if (it.ppsqm) s += 30 * clamp((20 - it.ppsqm) / 10);                     // €/m² 10 → voll, 20 → 0
  if (it.area) s += 20 * clamp((it.area - 25) / 30);                       // 25 m² → 0, 55 m² → voll
  const age = Math.min(hours(it.first_seen), hours(it.published) || 1e9);
  s += age < 24 ? 15 : age < 72 ? 9 : age < 168 ? 4 : 0;                    // frisch = schneller sein
  if (has(it, "provisionsfrei")) s += 5;
  if (["Balkon", "Terrasse", "Loggia", "Garten"].some(f => has(it, f))) s += 5;
  if (has(it, "unbefristet")) s += 4;
  if (has(it, "Lift")) s += 2;
  if (it.email) s += 3;
  if (has(it, "befristet")) s -= 5;
  if (has(it, "Gemeindebau – Wohn-Ticket nötig")) s -= 8;
  if (has(it, "Ablöse")) s -= 4;
  if (it.price_estimated) s -= 3;
  if (has(it, "Bezahlportal")) s -= 15;
  return Math.round(clamp(s, 0, 100));
}

function visible(it) {
  if (it.excluded) return false;
  if (hidden.has(it.id)) return false;
  if (it.price_total > S.maxPrice || it.price_total < S.minPrice) return false;
  if (S.minArea && (it.area || 0) < S.minArea) return false;
  if (!S.districts.includes(it.zip)) return false;
  if (S.hidePaywall && has(it, "Bezahlportal")) return false;
  if (S.hideGemeinde && has(it, "Gemeindebau – Wohn-Ticket nötig")) return false;
  if (S.hideBefristet && has(it, "befristet")) return false;
  if (S.hideMoebliert && has(it, "möbliert")) return false;
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
  "befristet": "warn", "Ablöse": "warn", "möbliert": "warn", "Gemeindebau – Wohn-Ticket nötig": "warn",
  "Bezahlportal": "bad",
};

/* ---------- Anfrage-Mail ---------- */
function fillTemplate(tpl, it) {
  const link = (it.links[0] || {}).url || "";
  const map = {
    titel: it.title, adresse: it.address || DISTRICTS[it.zip] || "Wien",
    preis: eur(it.price_total) + (it.price_estimated ? " (geschätzt)" : ""),
    flaeche: it.area ? num(it.area) + " m²" : "", link,
    name: S.name || "", telefon: S.phone || "", ueber_mich: S.about || "",
  };
  return tpl.replace(/\{(\w+)\}/g, (m, k) => (k in map ? map[k] : m))
    .replace(/^[^\n:]{1,20}:[ \t]*$/gm, "")   // leere Felder wie "Telefon: " weglassen
    .replace(/\n{3,}/g, "\n\n");
}
function mailto(it) {
  const subject = "Anfrage: " + it.title.slice(0, 90);
  return "mailto:" + encodeURIComponent(it.email) +
    "?subject=" + encodeURIComponent(subject) + "&body=" + encodeURIComponent(fillTemplate(S.template, it));
}

/* ---------- Rendern ---------- */
function render() {
  const all = DATA.items.filter(visible).map(it => Object.assign(it, { _score: score(it) }));
  const lists = {
    new: all.filter(isNew),
    all,
    fav: DATA.items.filter(it => favs.has(it.id)).map(it => Object.assign(it, { _score: score(it) })),
  };
  $("#cnt-new").textContent = lists.new.length;
  $("#cnt-all").textContent = lists.all.length;
  $("#cnt-fav").textContent = lists.fav.length;
  document.querySelectorAll(".tab").forEach(t => t.classList.toggle("active", t.dataset.tab === S.tab));

  const sorters = {
    score: (a, b) => b._score - a._score,
    new: (a, b) => (b.first_seen || "").localeCompare(a.first_seen || "") || b._score - a._score,
    price: (a, b) => a.price_total - b.price_total,
    ppsqm: (a, b) => (a.ppsqm || 99) - (b.ppsqm || 99),
  };
  const items = lists[S.tab].slice().sort(sorters[S.sort]);
  $("#filter-summary").textContent = `bis ${eur(S.maxPrice)} · ${S.districts.length === 4 ? "4.–7. Bezirk" : S.districts.map(z => z.slice(1, 3) * 1 + ".").join(" ")}`;

  const main = $("#list");
  main.innerHTML = "";
  if (!items.length) {
    const msg = {
      new: ["Heute noch nichts Neues", "Die Suche läuft 2× täglich. Schau unter „Alle“ für alle aktuellen Treffer."],
      all: ["Keine Treffer", "Probier in den Einstellungen ein höheres Budget oder weniger Ausschlüsse."],
      fav: ["Noch nichts gemerkt", "Tippe auf ☆ bei einer Wohnung, um sie hier zu sammeln."],
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
  sc.textContent = it._score + " Punkte";
  if (it._score >= 60) sc.classList.add("hi");
  if (!(isNewSinceVisit(it) || isNew(it))) el.classList.add("seen-old");

  const fav = $(".fav", el);
  const syncFav = () => { fav.textContent = favs.has(it.id) ? "★" : "☆"; fav.classList.toggle("on", favs.has(it.id)); };
  syncFav();
  fav.onclick = () => {
    favs.has(it.id) ? favs.delete(it.id) : favs.add(it.id);
    store.set("favs", [...favs]); syncFav(); $("#cnt-fav").textContent = DATA.items.filter(x => favs.has(x.id)).length;
  };

  $(".price", el).innerHTML = eur(it.price_total) +
    `<small>${it.price_estimated ? "ca. gesamt (" + eur(it.price) + " netto)" : (it.price_note || "Miete")}</small>`;
  $(".facts", el).textContent = [
    it.area && num(it.area) + " m²", it.rooms && num(it.rooms) + " Zi.", it.ppsqm && "€ " + num(it.ppsqm) + "/m²",
  ].filter(Boolean).join(" · ");
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

  const actions = $(".actions", el);
  const add = (label, href, cls, target) => {
    const a = document.createElement("a");
    a.className = "btn " + (cls || ""); a.textContent = label; a.href = href;
    if (target) { a.target = "_blank"; a.rel = "noopener"; }
    actions.appendChild(a); return a;
  };
  if (it.email) add("✉︎ Anfrage per Mail", mailto(it), "primary");
  const main = it.links[0];
  add(it.email ? "Inserat öffnen" : "Zum Inserat & anfragen", main.url, it.email ? "" : "primary", true);
  if (it.phone) add("☎ Anrufen", "tel:" + it.phone.replace(/[^\d+]/g, ""), "");
  if (!it.email) {
    const copy = add("Text kopieren", "#", "");
    copy.onclick = e => {
      e.preventDefault();
      navigator.clipboard?.writeText(fillTemplate(S.template, it)).then(() => { copy.textContent = "✓ Kopiert"; });
    };
  }
  const hide = add("Ausblenden", "#", "ghost");
  hide.onclick = e => {
    e.preventDefault(); hidden.add(it.id); store.set("hidden", [...hidden]);
    el.style.transition = "opacity .2s"; el.style.opacity = "0"; setTimeout(render, 200);
  };

  $(".src", el).innerHTML = "Gefunden auf: " + it.links.map(l =>
    `<a href="${l.url}" target="_blank" rel="noopener">${l.label}</a>`).join(", ") +
    (it.advertiser ? " · Anbieter: " + escapeHtml(it.advertiser) : "") +
    (it.email ? " · " + escapeHtml(it.email) : "");
  return el;
}

const escapeHtml = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

function renderMeta() {
  const u = DATA.updated;
  $("#meta").textContent = u ? "Zuletzt gesucht " + ago(u) + " · " +
    new Date(u).toLocaleString("de-AT", { weekday: "short", hour: "2-digit", minute: "2-digit" }) : "Noch keine Daten";
  const src = DATA.sources || {};
  const names = { willhaben: "willhaben", derstandard: "DER STANDARD", immoscout24: "ImmoScout24", immowelt: "immowelt", immmo: "IMMMO (inkl. Kurier, Bazar, Wohnkrone)" };
  $("#footer").innerHTML = "<b>Quellen beim letzten Lauf</b><ul>" + Object.entries(src).map(([k, v]) =>
    `<li class="${v.ok && v.count ? "ok" : "fail"}">${names[k] || k}: ${v.ok && v.count ? v.count + " Inserate" : k === "derstandard" ? "gesperrt – Inserate kommen über IMMMO" : "nicht erreichbar"}</li>`).join("") +
    "</ul>Gesucht wird in Wien 4.–7. Bezirk, 2× täglich. Preise laut Inserat – bitte immer im Original prüfen.";
}

/* ---------- Einstellungen ---------- */
function bindSettings() {
  const dlg = $("#settings");
  $("#btn-settings").onclick = () => { syncSettingsUI(); dlg.showModal(); };
  dlg.addEventListener("close", render);

  const range = (id, key, out, fmt) => {
    const r = $(id);
    r.oninput = () => { S[key] = +r.value; $(out).textContent = fmt(S[key]); saveSettings(); };
  };
  range("#s-max", "maxPrice", "#o-max", eur);
  range("#s-min", "minPrice", "#o-min", v => v ? eur(v) : "egal");
  range("#s-area", "minArea", "#o-area", v => v ? v + " m²" : "egal");

  const chips = $("#s-districts");
  chips.innerHTML = Object.entries(DISTRICTS).map(([z, n]) =>
    `<label><input type="checkbox" value="${z}"><span>${n}</span></label>`).join("");
  chips.onchange = () => {
    S.districts = [...chips.querySelectorAll("input:checked")].map(i => i.value);
    saveSettings();
  };

  const checks = { "#h-paywall": "hidePaywall", "#h-gemeinde": "hideGemeinde", "#h-befristet": "hideBefristet", "#h-moebliert": "hideMoebliert", "#h-estimated": "hideEstimated" };
  for (const [id, key] of Object.entries(checks)) $(id).onchange = e => { S[key] = e.target.checked; saveSettings(); };

  const texts = { "#p-name": "name", "#p-phone": "phone", "#p-about": "about", "#p-template": "template" };
  for (const [id, key] of Object.entries(texts)) $(id).oninput = e => { S[key] = e.target.value; saveSettings(); };
  $("#btn-reset-template").onclick = () => { S.template = DEFAULT_TEMPLATE; $("#p-template").value = S.template; saveSettings(); };
  $("#btn-unhide").onclick = () => { hidden.clear(); store.set("hidden", []); $("#cnt-hidden").textContent = 0; };
}

function syncSettingsUI() {
  $("#s-max").value = S.maxPrice; $("#o-max").textContent = eur(S.maxPrice);
  $("#s-min").value = S.minPrice; $("#o-min").textContent = S.minPrice ? eur(S.minPrice) : "egal";
  $("#s-area").value = S.minArea; $("#o-area").textContent = S.minArea ? S.minArea + " m²" : "egal";
  $("#s-districts").querySelectorAll("input").forEach(i => { i.checked = S.districts.includes(i.value); });
  $("#h-paywall").checked = S.hidePaywall; $("#h-gemeinde").checked = S.hideGemeinde;
  $("#h-befristet").checked = S.hideBefristet; $("#h-moebliert").checked = S.hideMoebliert;
  $("#h-estimated").checked = S.hideEstimated;
  $("#p-name").value = S.name; $("#p-phone").value = S.phone; $("#p-about").value = S.about; $("#p-template").value = S.template;
  $("#cnt-hidden").textContent = hidden.size;
}

/* ---------- Start ---------- */
document.querySelectorAll(".tab").forEach(t => t.onclick = () => { S.tab = t.dataset.tab; saveSettings(); render(); window.scrollTo(0, 0); });
$("#sort").value = S.sort;
$("#sort").onchange = e => { S.sort = e.target.value; saveSettings(); render(); };
bindSettings();

async function load() {
  try {
    const r = await fetch("data/listings.json?t=" + Date.now(), { cache: "no-store" });
    DATA = await r.json();
  } catch (e) {
    $("#meta").textContent = "Daten konnten nicht geladen werden – offline?";
  }
  renderMeta();
  render();
  store.set("lastVisit", new Date().toISOString());
}
load();
document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible") load(); });

if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js").catch(() => {});
