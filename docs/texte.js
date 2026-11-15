"use strict";
/* Persönliche Anfrage-Texte – regelbasiert, ohne KI-Dienst, läuft komplett auf dem Handy.
   Jede Anfrage greift konkrete Punkte aus dem Inserat auf (Lage, Straße, Ausstattung, Befristung …)
   und verbindet sie mit deinem Profil. "Andere Formulierung" würfelt neue Varianten. */

// Ausstattung, die im Text erwähnt werden kann: [Test, Formulierung, Plural?]
const FEATURES = [
  [it => has(it, "Terrasse"), "die Terrasse"],
  [it => has(it, "Garten"), "der Garten"],
  [it => has(it, "Loggia"), "die Loggia"],
  [it => has(it, "Balkon"), "der Balkon"],
  [(it, t) => /fischgr[äa]t/.test(t), "der Fischgrätparkett"],
  [(it, t) => /hohe(n)? r[äa]ume|raumh[öo]he|stuck/.test(t), "die hohen Räume", true],
  [it => has(it, "Altbau"), "der Altbau-Charme"],
  [(it, t) => /dachgescho|\bdg[- ]|dachterrasse/.test(t), "die Dachgeschosslage"],
  [(it, t) => /lichtdurchflutet|sehr hell|helle|sonnig/.test(t), "die helle Wohnung"],
  [(it, t) => /hofseitig|ruhige|ruhig gelegen|innenhof|grünblick|grünruhelage/.test(t), "die ruhige Lage"],
  [it => has(it, "Neubau/Erstbezug"), "der Erstbezug"],
  [it => has(it, "saniert"), "die frisch sanierte Wohnung"],
  [(it, t) => /einbauk[üu]che|neue k[üu]che|voll ausgestattete k[üu]che|k[üu]che mit ger[äa]ten/.test(t), "die ausgestattete Küche"],
  [(it, t) => /badewanne/.test(t), "die Badewanne"],
  [(it, t) => /parkett/.test(t), "der Parkettboden"],
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
    if (label === "die frisch sanierte Wohnung" && out.some(o => o.label === "der Erstbezug")) continue;
    if (label === "der Parkettboden" && out.some(o => o.label === "der Fischgrätparkett")) continue;
    if (test(it, t)) out.push({ label, plural: !!plural });
  }
  const u = t.match(UBAHN);
  if (u) out.push({ label: "die Nähe zur " + u[1].toUpperCase(), plural: false });
  return out;
}

function profileFacts(wg) {
  const habe = [];
  if (S.pNoPets) habe.push("keine Haustiere");
  if (S.pIncome && !wg) habe.push("ein festes, regelmäßiges Einkommen");
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

/* tone: "personal" (ausführlich) | "short" (für Kontaktformulare) */
function composeInquiry(it, { tone = "personal", variant = 0, address = "", docLink = "" } = {}) {
  const r = rng(it.id + "|" + variant + "|" + tone);
  const pick = arr => arr.filter(Boolean)[Math.floor(r() * arr.filter(Boolean).length)] || "";
  const wg = isWG(it);
  const priv = has(it, "privat");
  const short = tone === "short";
  const feats = featuresOf(it);
  const street = streetPhrase(it) || (address && streetPhrase({ address }));
  const where = street || "im " + districtName(it);
  const rooms = it.rooms && !wg ? `${Math.round(it.rooms)}-Zimmer-Wohnung` : wg ? "Zimmer" : "Wohnung";
  const size = it.area ? ` mit ${num(it.area)} m²` : "";
  const out = [];

  /* Anrede */
  if (wg) out.push(pick(["Hallo zusammen,", "Hey ihr,", "Hallo ihr Lieben,"]));
  else {
    const n = contactName(it);
    out.push(n ? `Guten Tag ${n},` : priv ? pick(["Guten Tag,", "Hallo,"]) : "Sehr geehrte Damen und Herren,");
  }

  /* Einstieg mit konkretem Bezug */
  let hook;
  if (wg) {
    hook = pick([
      `euer ${rooms} ${where} hat mich sofort angesprochen`,
      `ich hab gerade eure Anzeige für das ${rooms} ${where} gesehen und bin direkt hängen geblieben`,
      `euer WG-${rooms} ${where} klingt richtig gut`,
    ]);
  } else {
    hook = pick([
      `ich habe gerade Ihr Inserat für die ${rooms}${size} ${where} gesehen und bin sehr interessiert`,
      `Ihre ${rooms} ${where} hat mich sofort angesprochen und ich würde sie mir sehr gerne ansehen`,
      `mit großem Interesse habe ich Ihr Inserat für die ${rooms}${size} ${where} gelesen`,
    ]);
  }
  let feat = "";
  if (feats.length && !short) {
    const f = feats.slice(0, r() < 0.35 ? 1 : 2);
    const plural = f.length > 1 || f[0].plural;
    const labels = f.map(x => x.label);
    feat = wg
      ? pick([`Vor allem ${joinAnd(labels)} ${plural ? "gefallen" : "gefällt"} mir richtig gut.`,
              `${cap(joinAnd(labels))} ${plural ? "sind" : "ist"} genau mein Ding.`])
      : pick([`Besonders ${joinAnd(labels)} ${plural ? "gefallen" : "gefällt"} mir sehr.`,
              `Vor allem ${joinAnd(labels)} ${plural ? "haben" : "hat"} mich überzeugt.`,
              `${cap(joinAnd(labels))} ${plural ? "sind" : "ist"} genau das, wonach ich suche.`]);
  } else if (!wg && !short && districtOnly(it) && !street) {
    feat = pick([`${districtOnly(it)} ist genau die Gegend, in der ich wohnen möchte.`,
                 `Ich suche gezielt in ${districtOnly(it)}, die Lage passt also perfekt.`]);
  }
  out.push(sentence(hook) + (feat ? " " + feat : ""));

  /* Über mich */
  const about = [];
  if (S.pJob) about.push(sentence("Kurz zu mir: Ich " + S.pJob.replace(/^ich\s+/i, "")));
  if (S.about && !short) about.push(sentence(S.about));
  else if (S.about && short && !S.pJob) about.push(sentence(S.about.split(/(?<=[.!?])\s/)[0]));
  if (!short) {
    const facts = profileFacts(wg);
    if (facts) about.push(facts);
  }
  const who = S.pPersons === "2" ? (wg ? "" : "Einziehen würden wir zu zweit") : (wg ? "" : "Ich würde alleine einziehen");
  const moveIn = S.pMoveIn ? (/^(sofort|ab sofort|jederzeit|flexibel)$/i.test(S.pMoveIn.trim()) ? "ab sofort" : "ab " + S.pMoveIn.replace(/^ab\s+/i, "")) : "";
  if (!short && who) about.push(sentence(who + (moveIn ? ", " + moveIn + " möglich" : "")));
  else if (moveIn) about.push(sentence("Einziehen könnte ich " + moveIn));
  if (about.length) out.push(about.join(" "));

  /* Bezug auf Konditionen */
  if (!short) {
    const fit = [];
    if (has(it, "befristet") && !wg) fit.push(pick(["Die Befristung ist für mich kein Problem.", "Mit der Befristung habe ich kein Problem."]));
    if (has(it, "unbefristet") && S.pLongTerm) fit.push(pick(["Ich suche etwas Langfristiges – die unbefristete Vermietung passt daher perfekt.", "Da ich langfristig bleiben möchte, kommt mir der unbefristete Vertrag sehr entgegen."]));
    else if (S.pLongTerm && !has(it, "befristet") && !has(it, "Zwischenmiete")) fit.push(wg ? "Ich suche etwas für länger, nicht nur für ein paar Monate." : "Ich suche etwas Langfristiges und möchte gerne länger bleiben.");
    if (has(it, "Ablöse")) fit.push("Über die Ablöse können wir gerne sprechen.");
    if (fit.length) out.push(fit.join(" "));
  }

  /* Besichtigung */
  out.push(wg
    ? pick([`Ich würde euch gern kennenlernen und auf einen Kaffee vorbeikommen – zeitlich bin ich flexibel, ${nextDays(r)}.`,
            `Habt ihr Zeit für ein Kennenlernen? Ich bin zeitlich flexibel, ${nextDays(r)}.`])
    : pick([`Für eine Besichtigung bin ich sehr flexibel, ${nextDays(r)}.`,
            `Über einen Besichtigungstermin würde ich mich sehr freuen – ich hätte auch kurzfristig Zeit, ${nextDays(r)}.`,
            `Ich würde die Wohnung gerne so bald wie möglich besichtigen und bin zeitlich flexibel, ${nextDays(r)}.`]));

  /* Unterlagen & Kontakt */
  const tail = [];
  if (docLink) tail.push("Meine Mietervorstellung: " + docLink);
  else if (!wg && !short) tail.push(pick(["Meine Unterlagen (Mietervorstellung, Einkommensnachweis) schicke ich Ihnen gerne sofort.", "Alle nötigen Unterlagen kann ich Ihnen sofort zukommen lassen."]));
  if (S.phone) tail.push(wg ? `Erreichen könnt ihr mich unter ${S.phone}.` : `Am besten erreichen Sie mich unter ${S.phone}.`);
  if (tail.length) out.push(tail.join("\n"));

  /* Gruß */
  out.push((wg ? pick(["Liebe Grüße", "Viele Grüße"]) : pick(["Viele Grüße", "Beste Grüße", "Mit freundlichen Grüßen"])) + (S.name ? "\n" + S.name : ""));
  return out.filter(Boolean).join("\n\n").replace(/ {2,}/g, " ");
}
const cap = s => s.charAt(0).toUpperCase() + s.slice(1);

function profileMissing() {
  const miss = [];
  if (!S.name) miss.push("Name");
  if (!S.phone) miss.push("Telefon");
  if (!S.pJob && !S.about) miss.push("ein Satz über dich");
  if (!S.pMoveIn) miss.push("Einzugsdatum");
  return miss;
}
