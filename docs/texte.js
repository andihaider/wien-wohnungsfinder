"use strict";
/* Persönliche Anfrage-Texte, regelbasiert, ohne KI-Dienst, läuft komplett auf dem Handy.
   Jede Anfrage greift konkrete Punkte aus dem Inserat auf (Lage, Straße, Ausstattung, Befristung …)
   und verbindet sie mit deinem Profil. "Andere Formulierung" würfelt neue Varianten. */

// Ausstattung, die im Text erwähnt werden kann: [Test, Formulierung im Dativ ("mit …")]
const FEATURES = [
  [it => has(it, "Terrasse"), "der Terrasse"],
  [it => has(it, "Garten"), "dem Garten"],
  [it => has(it, "Loggia"), "der Loggia"],
  [it => has(it, "Balkon"), "dem Balkon"],
  [(it, t) => /fischgr[äa]t/.test(t), "dem Fischgrätparkett"],
  [(it, t) => /hohe(n)? r[äa]ume|raumh[öo]he|stuck/.test(t), "den hohen Räumen", true],
  [it => has(it, "Altbau"), "dem Altbau-Charme"],
  [(it, t) => /dachgescho|\bdg[- ]|dachterrasse/.test(t), "der Dachgeschosslage"],
  [(it, t) => /lichtdurchflutet|sehr hell|helle|sonnig/.test(t), "dem vielen Licht"],
  [(it, t) => /hofseitig|ruhige|ruhig gelegen|innenhof|grünblick|grünruhelage/.test(t), "der ruhigen Lage"],
  [it => has(it, "Neubau/Erstbezug"), "dem Erstbezug"],
  [it => has(it, "saniert"), "der frischen Sanierung"],
  [(it, t) => /einbauk[üu]che|neue k[üu]che|voll ausgestattete k[üu]che|k[üu]che mit ger[äa]ten/.test(t), "der ausgestatteten Küche"],
  [(it, t) => /badewanne/.test(t), "der Badewanne"],
  [(it, t) => /parkett/.test(t), "dem Parkettboden"],
];
const UBAHN = /\b(u[1-6])\b/i;

// Kleiner, reproduzierbarer Zufall: gleiche Wohnung + gleiche Variante = gleicher Text
function rng(seed) {
  let h = 2166136261;
  for (const c of String(seed)) h = Math.imul(h ^ c.charCodeAt(0), 16777619);
  return () => { h = Math.imul(h ^ (h >>> 15), 2246822507); h = Math.imul(h ^ (h >>> 13), 3266489909); return ((h ^= h >>> 16) >>> 0) / 4294967296; };
}
const sentence = s => { s = (s || "").trim(); return !s ? "" : /[.!?…)]$/.test(s) ? s : s + "."; };
const joinAnd = a => a.length < 2 ? a.join("") : a.slice(0, -1).join(", ") + " und " + a[a.length - 1];

function contactName(it) {
  const c = (it.contact || "").trim();
  if (/^[A-ZÄÖÜ][\wäöüß.-]+(\s+[A-ZÄÖÜ][\wäöüß.-]+){1,2}$/.test(c)) return c;
  // willhaben liefert bei Maklern oft "Firma (Vorname Nachname)"
  const m = (it.advertiser || "").match(/\(([^()]{3,40})\)\s*$/);
  return m && /^[A-ZÄÖÜ][\wäöüß.-]+(\s+[A-ZÄÖÜ][\wäöüß.-]+){1,2}$/.test(m[1].trim()) ? m[1].trim() : "";
}

function streetPhrase(it) {
  const a = (it.address || "").split(",")[0].trim().replace(/\s+\d.*$/, "");
  if (!a || /^\d{4}\b|wien|bezirk|vienna/i.test(a) || a.length > 40) return "";
  if (/(gasse|straße|strasse|zeile|allee|lände|promenade|hauptstraße)$/i.test(a)) return "in der " + a;
  if (/(platz|ring|gürtel|markt|weg|steig|berg|graben|kai|hof)$/i.test(a)) return "am " + a;
  return "";
}
function districtName(it) {
  const n = DISTRICTS[it.zip];
  return n ? n.replace(/^(\d+)\. (.*)$/, "$1. Bezirk") : "Wien";
}
function districtOnly(it) {
  const n = DISTRICTS[it.zip];
  return n ? n.split(". ")[1] : "";
}

function featuresOf(it) {
  const t = ((it.title || "") + " " + (it.description || "")).toLowerCase();
  const out = [];
  for (const [test, label, plural] of FEATURES) {
    if (out.length >= 3) break;
    // Wohnungstyp-Dopplungen vermeiden
    if (label === "der frischen Sanierung" && out.some(o => o.label === "dem Erstbezug")) continue;
    if (label === "dem Parkettboden" && out.some(o => o.label === "dem Fischgrätparkett")) continue;
    if (test(it, t)) out.push({ label, plural: !!plural });
  }
  const u = t.match(UBAHN);
  if (u) out.push({ label: "der Nähe zur " + u[1].toUpperCase(), plural: false });
  return out;
}

function profileFacts(wg) {
  const habe = [];
  if (S.pNoPets) habe.push("keine Haustiere");
  const parts = [];
  if (S.pNonSmoker) parts.push("rauche nicht");
  if (habe.length) parts.push("habe " + joinAnd(habe));
  if (!parts.length) return "";
  if (parts.length === 2 && habe.length === 2) return `Ich rauche nicht, habe ${habe[0]} und ${habe[1]}.`;
  return "Ich " + joinAnd(parts) + ".";
}

function nextDays(r) {
  const names = ["Sonntag", "Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag"];
  const d = new Date();
  const a = names[(d.getDay() + 1) % 7], b = names[(d.getDay() + 2) % 7];
  return r() < 0.5 ? `z. B. schon morgen oder am ${b}` : `gerne schon morgen (${a}) oder übermorgen`;
}

// Wiener Nachbarbezirke (für "nur wenige Minuten von meinem Arbeitsplatz")
const NEAR = {
  "1010": "1020 1030 1040 1060 1070 1080 1090", "1020": "1010 1030 1090 1200 1220", "1030": "1010 1020 1040 1100 1110",
  "1040": "1010 1030 1050 1060 1100", "1050": "1040 1060 1100 1120", "1060": "1010 1040 1050 1070 1120 1150",
  "1070": "1010 1060 1080 1150 1160", "1080": "1010 1070 1090 1160 1170", "1090": "1010 1020 1080 1170 1180 1190 1200",
  "1100": "1030 1040 1050 1110 1120 1230", "1110": "1020 1030 1100", "1120": "1050 1060 1100 1130 1150 1230",
  "1130": "1120 1140 1150 1230", "1140": "1130 1150 1160 1170", "1150": "1060 1070 1120 1130 1140 1160",
  "1160": "1070 1080 1140 1150 1170", "1170": "1080 1090 1140 1160 1180", "1180": "1090 1170 1190",
  "1190": "1090 1180 1200 1210", "1200": "1020 1090 1190 1210", "1210": "1190 1200 1220", "1220": "1020 1110 1210",
  "1230": "1100 1120 1130",
};
function workplaceNote(it) {
  const w = S.pWorkZip;
  if (!w || !it.zip) return "";
  if (w === it.zip) return "liegt im selben Bezirk wie mein Arbeitsplatz";
  return (NEAR[w] || "").split(" ").includes(it.zip) ? "ist nur wenige Minuten von meinem Arbeitsplatz entfernt" : "";
}
const euro = v => String(v).replace(/[^\d]/g, "").replace(/\B(?=(\d{3})+(?!\d))/g, ".");

/* Text im Stil von Andreas' eigenen Mails: direkt, freundlich, ehrlich begeistert, keine Floskel-Wüste.
   tone: "personal" (ausführlich) | "short" (für Kontaktformulare) */
function composeInquiry(it, { tone = "personal", variant = 0, address = "", docLink = "" } = {}) {
  const r = rng(it.id + "|" + variant + "|" + tone);
  const pick = arr => { arr = arr.filter(Boolean); return arr[Math.floor(r() * arr.length)] || ""; };
  const wg = isWG(it);
  const short = tone === "short";
  const feats = featuresOf(it);
  const street = streetPhrase(it) || (address && streetPhrase({ address }));
  const where = street || "im " + districtName(it);
  const rooms = it.rooms && !wg ? `${Math.round(it.rooms)}-Zimmer-Wohnung` : wg ? "Zimmer" : "Wohnung";
  const size = it.area ? ` mit ${num(it.area)} m²` : "";
  const work = workplaceNote(it);
  const out = [];

  /* Anrede */
  const n = contactName(it);
  if (wg) out.push(pick(["Hallo zusammen,", "Hey ihr,", "Hallo ihr,"]));
  else out.push(n ? `Guten Tag ${n},` : "Guten Tag,");

  /* Einstieg mit Bezug aufs Inserat */
  let feat = "";
  if (feats.length) {
    const f = feats.slice(0, short ? 1 : r() < 0.35 ? 1 : 2);
    feat = joinAnd(f.map(x => x.label));
  }
  let hook;
  if (wg) {
    hook = pick([
      `euer Zimmer ${where} hat mich sofort angesprochen${feat ? ", vor allem wegen " + feat : ""}.`,
      `ich hab gerade eure Anzeige für das Zimmer ${where} gesehen und würde es mir liebend gerne anschauen.`,
      `euer WG-Zimmer ${where} passt richtig gut zu dem, was ich suche${feat ? ", vor allem mit " + feat : ""}.`,
    ]);
    if (work) hook += ` Außerdem ${work}.`;
  } else {
    const wsent = work ? ` und ${work}` : "";
    hook = pick([
      `ich würde liebend gerne die ${rooms} ${where} besichtigen. Sie passt sehr gut zu meinen Vorstellungen${wsent}.`,
      `ich bin gerade auf Ihr Inserat für die ${rooms}${size} ${where} gestoßen und würde sie mir sehr gerne ansehen. Sie passt richtig gut zu meinen Vorstellungen${wsent}.`,
      `Ihre ${rooms}${size} ${where} hat mich sofort angesprochen und ich würde sie liebend gerne besichtigen${work ? ". Sie " + work : ""}.`,
    ]);
    if (feat && !short) hook += " " + pick([`Besonders gut gefällt mir die Wohnung mit ${feat}.`, `Vor allem mit ${feat} trifft sie genau meinen Geschmack.`]);
    else if (!feat && !street && !short && districtOnly(it) && !work)
      hook += ` ${districtOnly(it)} ist genau die Gegend, in der ich wohnen möchte.`;
  }
  out.push(hook);

  /* Kurz zu mir */
  const me = [];
  if (S.pJob) me.push("Kurz zu mir: Ich " + S.pJob.trim().replace(/^ich\s+/i, "").replace(/[.]$/, "") + ".");
  if (S.pNet && !wg) me.push(S.pJob ? `Somit habe ich ein monatliches Nettoeinkommen von rund ${euro(S.pNet)} €.` : `Mein monatliches Nettoeinkommen liegt bei rund ${euro(S.pNet)} €.`);
  if (S.about && !short) me.push(sentence(S.about));
  if (!short) { const facts = profileFacts(wg); if (facts) me.push(facts); }
  const moveIn = S.pMoveIn ? (/^(ab )?(sofort|jederzeit|flexibel)$/i.test(S.pMoveIn.trim()) ? "ab sofort" : "ab " + S.pMoveIn.trim().replace(/^ab\s+/i, "")) : "";
  if (!short && !wg && S.pPersons === "2") me.push(`Einziehen würden wir zu zweit${moveIn ? ", " + moveIn : ""}.`);
  else if (moveIn) me.push(`Einziehen könnte ich ${moveIn}.`);
  if (me.length) out.push(me.join(" "));

  /* Konditionen */
  if (!short) {
    const fit = [];
    if (has(it, "befristet") && !wg) fit.push("Die Befristung ist für mich kein Problem.");
    if (has(it, "unbefristet") && S.pLongTerm) fit.push("Da ich mich in Wien langfristig niederlassen möchte, passt der unbefristete Vertrag perfekt.");
    else if (S.pLongTerm && !has(it, "befristet") && !has(it, "Zwischenmiete")) fit.push(wg ? "Ich suche etwas für länger, nicht nur für ein paar Monate." : "Ich möchte mich in Wien langfristig niederlassen.");
    if (has(it, "Ablöse")) fit.push("Über die Ablöse können wir gerne sprechen.");
    if (fit.length) out.push(fit.join(" "));
  }

  /* Unterlagen */
  if (!wg) {
    const docs = ["Gehaltsnachweise"];
    if (S.pGuarantor) docs.push("die Bürgschaft " + S.pGuarantor.trim().replace(/^(die )?bürgschaft\s+/i, ""));
    if (docLink) out.push(`Meine Mietervorstellung: ${docLink}\nGerne schicke ich Ihnen auch ${joinAnd(docs)}.`);
    else out.push(pick([
      `Gerne lasse ich Ihnen weitere Unterlagen zukommen: meine Mietervorstellung, ${joinAnd(docs)}.`,
      `Weitere Unterlagen wie meine Mietervorstellung, ${joinAnd(docs)} schicke ich Ihnen jederzeit gerne.`,
    ]));
  }

  /* Besichtigung */
  const when = nextDays(r);
  out.push(wg
    ? pick([`Ich würde euch riesig gern kennenlernen. Zeitlich bin ich flexibel, ${when}.`,
            `Habt ihr Zeit für ein Kennenlernen? Ich bin flexibel, ${when}.`])
    : pick([`Ich würde mich riesig über eine Besichtigung freuen! Zeitlich bin ich flexibel, ${when}.`,
            `Zeitlich bin ich flexibel, auch kurzfristig, ${when}. Ich würde mich riesig über eine Besichtigung freuen!`,
            `Über einen Besichtigungstermin würde ich mich sehr freuen! Ich hätte auch kurzfristig Zeit, ${when}.`]));

  if (S.phone) out.push(wg ? `Meine Nummer: ${S.phone}` : `Am besten erreichen Sie mich unter ${S.phone}.`);
  out.push((wg ? pick(["Liebe Grüße", "LG"]) : pick(["Liebe Grüße", "Viele Grüße", "Beste Grüße"])) + (S.name ? "\n" + S.name : ""));
  return out.filter(Boolean).join("\n\n").replace(/ {2,}/g, " ");
}
const cap = s => s.charAt(0).toUpperCase() + s.slice(1);

function profileMissing() {
  const miss = [];
  if (!S.name) miss.push("Name");
  if (!S.phone) miss.push("Telefon");
  if (!S.pJob) miss.push("was du beruflich machst");
  if (!S.pNet) miss.push("Nettoeinkommen");
  if (!S.pMoveIn) miss.push("Einzugsdatum");
  return miss;
}
