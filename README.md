# meos-obs-live

Wiederverwendbare Live-Anzeige für Orientierungslauf: Holt Live-Daten aus [MeOS](https://www.melin.nu/meos/) über den eingebauten
**Informationsserver** und zeigt sie als Vollbild-Szene (1920×1080) in OBS an:

- Ergebnisliste pro Klasse inkl. **Zwischenzeiten an Funkposten** (Zeit + Platz, Bestzeit grün)
- Läufer „im Wald“ mit Rückstand am letzten Funkposten
- **Staffeln/Teams**: Strecken, Streckenzeit/-platz, Gesamtzeit nach Strecke
- **Ticker „Letzte Zieleinläufe“** (neue Einläufe werden hervorgehoben)
- **Läuferprofil** mit allen Funkposten, Zwischenzeiten und Platzierungen
- **Head-to-Head**: ausgewählter Läufer gegen bis zu drei Läufer der Spitzengruppe
- **Sieger-Ansicht**: Top 6 einer ausgewählten Klasse für die Siegerehrung
- **Funkpostenansicht**: bereits durchgelaufene und noch offene Läufer je Klasse
- **Neueste Informationen**: neue Zieleinläufe und Funkposten-Durchgänge
- **Automatische Rotation** durch die Klassen (mit Seitenumbruch bei langen Listen)
  *und* manuelle Auswahl über eine Regie-Seite

```
MeOS (Windows, Hauptrechner)  ──LAN──▶  Python-Server (Arch-Laptop)  ──▶  OBS Browser-Quelle
  Informationsserver :2009                 /overlay   /control   /api/*
```

## Funktionsweise

Der Server fragt alle 2 s `http://<meos>:2009/meos?difference=<id>` ab.
Die erste Abfrage (`difference=zero`) liefert den kompletten Wettkampf (`MOPComplete`),
danach liefert MeOS nur noch Änderungen (`MOPDiff`). Das ist dasselbe Format
(MeOS Online Protocol), das MeOS auch für Online-Ergebnisdienste nutzt.
Startet MeOS neu, wird automatisch wieder komplett geladen.

Es wird nur gelesen, MeOS wird nicht verändert.

## Installation (Arch Linux)

```bash
sudo pacman -S python
cd meos-obs
python -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Veranstaltung konfigurieren

Die Anwendung enthält keine fest verdrahteten Veranstaltungsnamen, Logos oder
Funkposten. Vor einem Wettkampf wird die Vorlage kopiert und lokal angepasst:

```bash
cp config.example.yaml config.yaml
```

`config.yaml` wird nicht in Git eingecheckt. Dort können daher ein lokaler
Logo-Pfad und veranstaltungsspezifische Angaben stehen. Ohne `config.yaml`
übernimmt die Anwendung den Namen aus MeOS, zeigt kein Logo an und verwendet
keine zusätzlichen Funkposten als Ausweichliste.

| Einstellung | Zweck |
|---|---|
| `event.name` | Überschreibt den von MeOS gelieferten Wettkampfnamen. |
| `event.short_name`, `date`, `organizer`, `location` | Zusätzliche Metadaten für APIs und spätere Erweiterungen. |
| `event.logo` | Logo-Datei relativ zur YAML-Datei; wird in den Browserquellen angezeigt. |
| `event.radio_controls` | Ausweichliste, wenn MeOS für eine Klasse keine Funkposten meldet. |

## In MeOS den Informationsserver starten

MeOS → Reiter **Dienste** (engl. „Services“) → **Informationsserver** →
„Automatischen Dienst starten“. Standard-Port ist `2009`. In der Windows-Firewall
eingehende Verbindungen auf diesem Port erlauben.

Test vom Laptop aus:

```bash
curl "http://<ip-des-meos-rechners>:2009/meos?get=status"
```

Kommt XML zurück (`<status .../>`), passt alles.

## Starten

```bash
.venv/bin/python -m meos_obs --meos http://<ip-des-meos-rechners>:2009/meos --config config.yaml
```

| URL | Zweck |
|-----|-------|
| `http://127.0.0.1:8080/overlay` | OBS **Browser-Quelle** (Breite 1920, Höhe 1080) |
| `http://127.0.0.1:8080/control` | Regie: Rotation/feste Klasse, Ticker, Sekunden pro Seite |
| `http://127.0.0.1:8080/runner?runner=<id>` | Läuferprofil für eine OBS-Browser-Quelle |
| `http://127.0.0.1:8080/head-to-head?runner=<id>` | Direktvergleich mit der Spitzengruppe |
| `http://127.0.0.1:8080/podium?class=<id>` | Sieger-Ansicht mit den Top 6 einer Klasse |
| `http://127.0.0.1:8080/radio?class=<id>&control=<id>` | Funkpostenansicht für eine OBS-Browser-Quelle |
| `http://127.0.0.1:8080/news` | Übersicht der neuesten Zieleinläufe und Funkposten-Durchgänge |

Optionen: `--poll 2` (Abfrageintervall), `--port 8080`,
`--host 0.0.0.0` (Regie-Seite auch vom Handy/Tablet im LAN bedienen).

Overlay-URL-Parameter: `?class=<id>` (feste Klasse, unabhängig von der Regie),
`?ticker=0`, `?transparent=1`. So lassen sich auch mehrere Szenen mit
unterschiedlichen Ansichten bauen.

### Läufer- und Funkpostenansichten

Auf der Regie-Seite im Bereich **Spezialansichten** zuerst eine Einzelklasse
wählen. Danach lassen sich ein Läufer sowie einer der vorhandenen Funkposten
dieser Klasse auswählen. Die jeweils darunter angezeigte URL in OBS als eigene
Browser-Quelle verwenden. Das Läuferprofil und der Direktvergleich (Head-to-Head)
aktualisieren sich wie die
Ergebnisliste alle zwei Sekunden.

Der Direktvergleich zeigt den gewählten Läufer zuerst und ergänzt bis zu drei
Läufer der Spitzengruppe. Je Funkposten werden Zeit, Rang und Rückstand zur schnellsten
Zeit gezeigt. Sobald Zieleinläufe vorliegen, richtet sich die Führung nach dem
offiziellen Zieleinlauf; vorher nach dem Live-Fortschritt. Er ist für
Einzelklassen vorgesehen.

Für die Siegerehrung kann die Sieger-Ansicht in der Regie nach Auswahl der
Klasse manuell gesteuert werden: zuerst **Platz 3**, dann **Platz 2** und
abschließend **Platz 1** auswählen. Jeder Platz wird in der OBS-Quelle mit
einer kurzen Animation eingeblendet. „Zurücksetzen“ verbirgt alle Plätze für
eine erneute Enthüllung. Alternativ steuern die Tasten `3`, `2`, `1` die
jeweiligen Plätze und `R` setzt die Enthüllung zurück, solange die Regie-Seite
im Browser den Tastaturfokus besitzt.

Wenn MeOS die Funkposten nicht zusammen mit den Klassen übermittelt, verwendet
die Anwendung optional die in `event.radio_controls` konfigurierte Ausweichliste.

### OBS-Hinweis (Arch)

Die Browser-Quelle muss in OBS verfügbar sein. Falls sie fehlt: die Flatpak-Version
(`com.obsproject.Studio`) oder ein AUR-Paket mit Browser-Unterstützung verwenden.
Notlösung: Overlay in Chromium im Vollbild/Kiosk-Modus öffnen und per
Fenster-Aufnahme einbinden.

## Testen ohne MeOS (Simulation)

```bash
.venv/bin/python -m meos_obs --demo            # Simulation, 10-facher Zeitraffer
.venv/bin/python -m meos_obs --demo --demo-speed 30
```

Simuliert einen Wettkampf mit 5 Einzelklassen (mit Funkposten, Fehlstempel,
Aufgaben, Nichtstarter) und einer 3er-Staffel. Der Simulator spricht exakt das
MeOS-Differenzprotokoll, d. h. der echte Abfrage-Code wird mitgetestet.

Netzwerk-Test mit getrenntem Simulator (z. B. auf einem anderen Rechner):

```bash
.venv/bin/python -m meos_obs.mock_meos --host 0.0.0.0 --port 2009
.venv/bin/python -m meos_obs --meos http://<ip>:2009/meos
```

Unit-Tests: `.venv/bin/pip install pytest && .venv/bin/python -m pytest`

## Checkliste Wettkampftag

1. Laptop per LAN im Netz, IP des MeOS-Rechners bekannt
2. In MeOS Informationsserver starten, Firewall-Port freigeben
3. `curl …/meos?get=status` vom Laptop aus testen
4. `python -m meos_obs --meos …` starten, `/control` öffnen → „verbunden“
5. In MeOS prüfen, dass die Funkposten als Funkposten markiert sind
   (sonst gibt es keine Zwischenzeitspalten)
6. In OBS Browser-Quelle `http://127.0.0.1:8080/overlay` (1920×1080) anlegen

Der grüne Punkt unten rechts im Overlay wird rot, wenn länger als 15 s keine
Daten von MeOS kamen.

## Veröffentlichung auf GitHub

Für ein öffentliches Repository sollten nur die Projektdateien aus diesem
Ordner veröffentlicht werden. `config.yaml`, Logos unter `assets/`, virtuelle
Umgebungen und Python-Caches sind bereits über `.gitignore` ausgeschlossen.
Prüfe vor dem ersten Push dennoch `git status`, insbesondere auf exportierte
MeOS-Dateien, Startlisten, Ergebnisdaten oder Medien, für die keine
Veröffentlichungsrechte vorliegen.

Dieses Projekt steht unter der [MIT-Lizenz](LICENSE).
