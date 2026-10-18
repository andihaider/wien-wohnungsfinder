/**
 * Mietervorstellung – erstellt aus deiner Google-Docs-Vorlage eine Kopie mit der Adresse der Wohnung,
 * speichert sie als PDF im Ordner "Mietervorstellungen" in deinem Google Drive und gibt einen
 * Link zum Ansehen zurück. Den fügt der Wohnungsfinder automatisch in deine Anfrage ein.
 *
 * Läuft in DEINEM Google-Konto. Ohne den richtigen SCHLUESSEL macht das Skript gar nichts.
 * Das PDF ist für alle sichtbar, die den Link haben (dafür ist er ja da) – sonst bleibt alles privat.
 *
 * In der Vorlage an die passenden Stellen schreiben:
 *   {{ADRESSE}}  → wird durch die Adresse der Wohnung ersetzt
 *   {{DATUM}}    → wird durch das heutige Datum ersetzt (optional)
 */

// ▼▼▼ 1) Link zu deiner Vorlage (der normale Link aus der Adresszeile von Google Docs)
const VORLAGE = 'HIER_LINK_ZU_DEINER_VORLAGE_EINFUEGEN';
// ▼▼▼ 2) Ein langes, zufälliges Geheimwort – dasselbe trägst du in der App ein
const SCHLUESSEL = 'HIER_EIN_LANGES_GEHEIMWORT_EINFUEGEN';
// ▲▲▲

const ORDNER = 'Mietervorstellungen';

function doGet(e) {
  const p = (e && e.parameter) || {};
  try {
    if (SCHLUESSEL.indexOf('HIER_') === 0) throw new Error('Im Skript ist noch kein SCHLUESSEL eingetragen.');
    if (p.key !== SCHLUESSEL) return json_({ ok: false, error: 'Falscher Schlüssel.' });
    const adresse = (p.adresse || '').trim().slice(0, 150);
    if (!adresse) return json_({ ok: false, error: 'Keine Adresse übergeben.' });
    return json_(Object.assign({ ok: true }, erstellen_(adresse)));
  } catch (err) {
    return json_({ ok: false, error: err.message });
  }
}

/** Zum Testen im Skript-Editor: Funktion "test" auswählen und "Ausführen" drücken. */
function test() {
  Logger.log(erstellen_('Teststraße 1, 1050 Wien'));
}

function erstellen_(adresse) {
  const id = (VORLAGE.match(/[-\w]{25,}/) || [])[0];
  if (!id) throw new Error('Im Skript ist noch keine Vorlage eingetragen (Zeile "const VORLAGE = ...").');
  const ordner = ordner_();
  const name = 'Mietervorstellung – ' + adresse;

  // Gleiche Adresse schon erstellt? Dann das vorhandene PDF wiederverwenden.
  const vorhanden = ordner.getFilesByName(name + '.pdf');
  if (vorhanden.hasNext()) {
    const pdf = vorhanden.next();
    teilen_(pdf);
    return { name: name, pdfUrl: pdf.getUrl(), wiederverwendet: true, platzhalter: true };
  }

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
  teilen_(pdf);
  return { name: name, pdfUrl: pdf.getUrl(), docUrl: kopie.getUrl(), wiederverwendet: false, platzhalter: gefunden };
}

function teilen_(file) {
  file.setSharing(DriveApp.Access.ANYONE_WITH_LINK, DriveApp.Permission.VIEW);
}

function ordner_() {
  const it = DriveApp.getFoldersByName(ORDNER);
  return it.hasNext() ? it.next() : DriveApp.createFolder(ORDNER);
}

function json_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}
