/**
 * Mietervorstellung – erstellt aus deiner Google-Docs-Vorlage eine Kopie mit der Adresse der Wohnung
 * und speichert sie zusätzlich als PDF im Ordner "Mietervorstellungen" in deinem Google Drive.
 *
 * Läuft in DEINEM Google-Konto. Deine Vorlage und die erzeugten Dateien verlassen dein Drive nicht,
 * außer du tippst ausdrücklich auf "Link zum Teilen erstellen".
 *
 * In der Vorlage an die passenden Stellen schreiben:
 *   {{ADRESSE}}  → wird durch die Adresse der Wohnung ersetzt
 *   {{DATUM}}    → wird durch das heutige Datum ersetzt (optional)
 */

// ▼▼▼ Hier den Link zu deiner Vorlage einfügen (der normale Link aus der Adresszeile von Google Docs) ▼▼▼
const VORLAGE = 'HIER_LINK_ZU_DEINER_VORLAGE_EINFUEGEN';
// ▲▲▲

const ORDNER = 'Mietervorstellungen';

function doGet(e) {
  const p = (e && e.parameter) || {};
  try {
    if (p.share) return seite_(teilen_(p.share));
    const adresse = (p.adresse || '').trim();
    if (!adresse) return seite_('<h1>Keine Adresse</h1><p>Bitte über den Wohnungsfinder öffnen.</p>');
    return seite_(erstellen_(adresse));
  } catch (err) {
    return seite_('<h1>Hoppla</h1><p>' + esc_(err.message) + '</p>');
  }
}

/** Zum Testen im Skript-Editor: Funktion auswählen und "Ausführen" drücken. */
function test() {
  Logger.log(erstellen_('Teststraße 1, 1050 Wien'));
}

function erstellen_(adresse) {
  const id = (VORLAGE.match(/[-\w]{25,}/) || [])[0];
  if (!id) throw new Error('Im Skript ist noch keine Vorlage eingetragen (Zeile "const VORLAGE = ...").');
  const ordner = ordner_();
  const name = 'Mietervorstellung – ' + adresse;
  const kopie = DriveApp.getFileById(id).makeCopy(name, ordner);
  const doc = DocumentApp.openById(kopie.getId());
  const datum = Utilities.formatDate(new Date(), 'Europe/Vienna', 'dd.MM.yyyy');
  let gefunden = false;
  [doc.getBody(), doc.getHeader(), doc.getFooter()].forEach(function (teil) {
    if (!teil) return;
    if (teil.findText('\\{\\{ADRESSE\\}\\}')) gefunden = true;
    teil.replaceText('\\{\\{ADRESSE\\}\\}', adresse);
    teil.replaceText('\\{\\{DATUM\\}\\}', datum);
  });
  doc.saveAndClose();
  const pdf = ordner.createFile(kopie.getAs(MimeType.PDF)).setName(name + '.pdf');

  const hinweis = gefunden ? '' :
    '<p class="warn">Achtung: In deiner Vorlage steht kein <b>{{ADRESSE}}</b> – die Adresse wurde daher nirgends eingesetzt.</p>';
  const self = ScriptApp.getService().getUrl();
  return '<h1>Fertig ✓</h1>' +
    '<p class="muted">' + esc_(name) + '</p>' + hinweis +
    '<a class="btn primary" target="_blank" href="' + pdf.getUrl() + '">PDF öffnen</a>' +
    '<a class="btn" target="_blank" href="' + kopie.getUrl() + '">Im Google Doc bearbeiten</a>' +
    '<a class="btn" target="_top" href="' + self + '?share=' + pdf.getId() + '">Link zum Teilen erstellen</a>' +
    '<p class="muted small">Gespeichert in Google Drive → „' + ORDNER + '“. ' +
    'Den Teilen-Link brauchst du, wenn ein Kontaktformular keine Anhänge erlaubt.</p>';
}

function teilen_(fileId) {
  const file = DriveApp.getFileById(fileId);
  // Nur Dateien aus dem eigenen Ordner freigeben
  const parents = file.getParents();
  let erlaubt = false;
  while (parents.hasNext()) if (parents.next().getName() === ORDNER) erlaubt = true;
  if (!erlaubt) throw new Error('Diese Datei liegt nicht im Ordner „' + ORDNER + '“.');
  file.setSharing(DriveApp.Access.ANYONE_WITH_LINK, DriveApp.Permission.VIEW);
  const url = file.getUrl();
  return '<h1>Link zum Teilen</h1>' +
    '<p class="muted">Jeder mit diesem Link kann das PDF ansehen.</p>' +
    '<input id="l" readonly value="' + esc_(url) + '" onclick="this.select()">' +
    '<button class="btn primary" onclick="var i=document.getElementById(\'l\');i.select();' +
    'try{navigator.clipboard.writeText(i.value)}catch(e){document.execCommand(\'copy\')};this.textContent=\'✓ Kopiert\'">Link kopieren</button>' +
    '<a class="btn" target="_blank" href="' + url + '">PDF öffnen</a>';
}

function ordner_() {
  const it = DriveApp.getFoldersByName(ORDNER);
  return it.hasNext() ? it.next() : DriveApp.createFolder(ORDNER);
}

function esc_(s) {
  return String(s).replace(/[&<>"]/g, function (c) {
    return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
  });
}

function seite_(inhalt) {
  const html = '<!doctype html><html><head><meta charset="utf-8"><style>' +
    'body{font:16px/1.45 -apple-system,Segoe UI,Roboto,sans-serif;margin:0;padding:24px 16px;background:#f4f5f2;color:#1c1f1d}' +
    'h1{font-size:22px;margin:0 0 6px}.muted{color:#69706b}.small{font-size:13px}' +
    '.warn{background:#fbeed7;color:#9a5b00;padding:10px 12px;border-radius:10px}' +
    '.btn{display:block;text-align:center;text-decoration:none;font-weight:600;padding:13px;margin:10px 0;border-radius:12px;' +
    'border:1px solid #e2e4df;background:#fff;color:#1c1f1d;font-size:16px;width:100%;box-sizing:border-box;cursor:pointer}' +
    '.btn.primary{background:#0f766e;border-color:#0f766e;color:#fff}' +
    'input{width:100%;box-sizing:border-box;padding:10px;border:1px solid #e2e4df;border-radius:10px;font-size:14px;margin:8px 0}' +
    '</style></head><body>' + inhalt + '</body></html>';
  return HtmlService.createHtmlOutput(html)
    .setTitle('Mietervorstellung')
    .addMetaTag('viewport', 'width=device-width, initial-scale=1');
}
