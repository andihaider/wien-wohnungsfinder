# Mietervorstellung per Knopfdruck – Einrichtung (ca. 5 Minuten, einmalig)

Ziel: Im Anfrage-Fenster auf **„📄 Mietervorstellung erstellen & Link einfügen“** tippen →
in deinem Google Drive entsteht eine Kopie deiner Mietervorstellung mit der richtigen Adresse als PDF,
und der Link dazu wird automatisch in deine Nachricht eingefügt.

Deine Vorlage und die PDFs bleiben in **deinem** Google-Konto – nichts davon landet auf GitHub.
Die PDFs sind nur für Leute sichtbar, die den Link bekommen (also die Vermieter, denen du schreibst).

## 1. Vorlage vorbereiten
1. Dein Google Doc öffnen → *Datei → Kopie erstellen* → Name z. B. **„Mietervorstellung VORLAGE“**.
2. In der Kopie die Adresse der Wohnung durch **`{{ADRESSE}}`** ersetzen (genau so, mit den Klammern).
   Optional: das Datum durch **`{{DATUM}}`** ersetzen.
3. Den Link dieser Vorlage aus der Adresszeile kopieren.

## 2. Skript anlegen
1. [script.google.com](https://script.google.com) öffnen → **Neues Projekt**.
2. Den gesamten Inhalt von [`Mietervorstellung.gs`](Mietervorstellung.gs) in den Editor einfügen
   (vorhandenen Code ersetzen).
3. Zwei Zeilen ausfüllen:
   - `const VORLAGE = '…'` → dein Link aus Schritt 1
   - `const SCHLUESSEL = '…'` → ein langes Geheimwort, z. B. `blau-Tisch-Wolke-7392-Fenster`
   Speichern (💾).
4. Oben die Funktion **`test`** auswählen → **Ausführen** → Google fragt nach Berechtigungen
   (Drive + Docs) → *Zulassen*. Falls „Google hat diese App nicht überprüft“ erscheint:
   *Erweitert → Zu … wechseln (unsicher)* – das ist dein eigenes Skript.
   In deinem Drive liegt jetzt der Ordner **Mietervorstellungen** mit einer Testdatei.

## 3. Als Web-App bereitstellen
1. **Bereitstellen → Neue Bereitstellung** → Zahnrad → **Web-App**.
2. *Ausführen als:* **Ich** · *Zugriff:* **Jeder** → **Bereitstellen**.
   („Jeder“ ist nötig, damit die App das Ergebnis zurückbekommt. Ohne deinen Schlüssel macht das Skript nichts.)
3. Die **Web-App-URL** (endet auf `/exec`) kopieren.

## 4. In der App eintragen
Wohnungsfinder → Einstellungen (⚙︎) → **Mietervorstellung (Google Doc)**:
URL einfügen und denselben **Schlüssel** wie im Skript eintragen. Fertig.

**Hinweise**
- Gleiche Adresse zweimal? Dann wird das vorhandene PDF wiederverwendet statt ein neues angelegt.
- Wenn du das Skript später änderst: *Bereitstellen → Bereitstellungen verwalten → Bearbeiten → Version: Neue Version*.
