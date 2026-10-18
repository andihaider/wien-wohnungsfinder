# Mietervorstellung per Knopfdruck – Einrichtung (ca. 5 Minuten, einmalig)

Ziel: In der App auf **„📄 Mietervorstellung für diese Adresse“** tippen → in deinem Google Drive entsteht
eine Kopie deiner Mietervorstellung mit der richtigen Adresse, plus PDF.
Deine Vorlage und die PDFs bleiben in **deinem** Google-Konto – nichts davon landet auf GitHub.

## 1. Vorlage vorbereiten
1. Dein Google Doc öffnen → *Datei → Kopie erstellen* → Name z. B. **„Mietervorstellung VORLAGE“**.
2. In der Kopie die Adresse der Wohnung durch **`{{ADRESSE}}`** ersetzen (genau so, mit den Klammern).
   Optional: das Datum durch **`{{DATUM}}`** ersetzen.
3. Den Link dieser Vorlage aus der Adresszeile kopieren.

## 2. Skript anlegen
1. [script.google.com](https://script.google.com) öffnen → **Neues Projekt**.
2. Den gesamten Inhalt von [`Mietervorstellung.gs`](Mietervorstellung.gs) in den Editor einfügen
   (vorhandenen Code ersetzen).
3. In der Zeile `const VORLAGE = '…'` deinen Link aus Schritt 1 einsetzen. Speichern (💾).
4. Oben die Funktion **`test`** auswählen → **Ausführen** → Google fragt nach Berechtigungen
   (Drive + Docs) → *Zulassen*. Falls „Google hat diese App nicht überprüft“ erscheint:
   *Erweitert → Zu … wechseln (unsicher)* – das ist dein eigenes Skript.
   In deinem Drive liegt jetzt der Ordner **Mietervorstellungen** mit einer Testdatei.

## 3. Als Web-App bereitstellen
1. **Bereitstellen → Neue Bereitstellung** → Zahnrad → **Web-App**.
2. *Ausführen als:* **Ich** · *Zugriff:* **Nur ich** → **Bereitstellen**.
3. Die **Web-App-URL** (endet auf `/exec`) kopieren.

## 4. In der App eintragen
Wohnungsfinder → Einstellungen (⚙︎) → **Mietervorstellung (Google Doc)** → URL einfügen. Fertig.

**Hinweise**
- „Nur ich“ heißt: Nur du (eingeloggt in Google) kannst das auslösen. Wenn der Browser beim ersten Mal
  nach dem Google-Login fragt, einmal anmelden.
- Bist du mit mehreren Google-Konten angemeldet, kann Google einen Fehler zeigen – dann im Browser nur mit
  dem Konto angemeldet sein, dem das Skript gehört.
- „Link zum Teilen erstellen“ macht das PDF für jeden mit dem Link sichtbar – praktisch für Kontaktformulare
  ohne Anhang, aber nur nutzen, wenn du das willst.
- Wenn du das Skript später änderst: *Bereitstellen → Bereitstellungen verwalten → Bearbeiten → Neue Version*.
