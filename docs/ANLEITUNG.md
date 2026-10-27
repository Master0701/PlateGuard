# PlateGuard – Windows SMART-Monitor

[Zur Projektübersicht](../README.md) · [Aktuelle Downloads](https://github.com/Master0701/PlateGuard/releases/latest)

Zwei eigenständige Windows-x64-Programme. Keine Python-Installation, kein separat installiertes smartmontools, keine Dateien neben der jeweiligen EXE erforderlich.

## Start

1. `dist/PlateGuard-Zentrale.exe` auf dem Hauptrechner starten.
2. Im Infobereich der Taskleiste (ggf. unter dem Pfeil) das PlateGuard-Symbol rechtsklicken → **Einstellungen**.
3. Verbindungsschlüssel kopieren. In der Windows-Firewall eingehendes TCP **9766** nur im privaten Netzwerk für die gewünschten Agent-Rechner erlauben. Das Programm ändert die Firewall nicht automatisch.
4. `dist/PlateGuard-Agent.exe` auf jedem überwachten Rechner starten. Der Agent fordert Administratorrechte zum Lesen der physischen Laufwerke an.
5. Im Agenten unter Einstellungen `http://IP-DER-ZENTRALE:9766` und denselben Schlüssel eintragen, speichern. **Jetzt aktualisieren** stößt eine Abfrage an.
6. Auf dem Hauptrechner ebenfalls einen Agenten starten, wenn dessen Laufwerke überwacht werden sollen; Adresse dann `http://127.0.0.1:9766`.

Beide Programme laufen im Tray. Rechtsklick: Übersicht, Einstellungen, Abfrage/Aktualisierung, Alarme pausieren/aktivieren, Beenden. Die Weboberflächen öffnen sich lokal im Standardbrowser. Manuell gestartete Programme müssen für die Überwachung laufen; ein Windows-Dienst oder automatischer Start wird nicht eingerichtet. Windows 10/11 x64 ist das Zielsystem, praktisch geprüft auf dem vorhandenen Windows 11.

## Funktionen

- Automatische smartctl-Gerätesuche; HDD, SATA-SSD, NVMe und durch smartmontools erreichbare SAS/SCSI-/USB-/RAID-Laufwerke.
- Regelmäßige Abfrage, standardmäßig alle 300 Sekunden; 30 Sekunden bis 24 Stunden einstellbar. Der Abstand beginnt nach Abschluss einer Abfrage.
- Lokale und zentrale Auswertung, gelbe/rote Regeln je Messwert, ein-/ausschaltbar, absolute Werte oder Zuwächse. Optionale Einschränkung auf eine Laufwerk-ID. Mehrere Regeln wirken additiv; spezielle Regeln ersetzen globale Regeln nicht automatisch.
- Windows-Tray-Benachrichtigung bei neuen/geänderten Warnungen, optional Ton, stundenweise Pause. Meldungen werden pro Laufwerk mindestens 60 Sekunden begrenzt. Unveränderte Warnungen werden nicht dauernd wiederholt.
- Offline-Rechner bleiben mit letzter Messung sichtbar und lösen keinen Laufwerksalarm aus. Frist = Maximum aus zentral eingestellter Frist und drei gemeldeten Agent-Abfrageintervallen.
- Lesefehler und unbekannte SMART-Daten werden nicht als gesund ausgegeben. Verschwundene Laufwerke bleiben als Hinweis sichtbar.
- 90 Tage Messhistorie und Warnereignisse; Verlauf zeigt bis zu 500 letzte Messungen. ATA-Attribute mit Rohwerten, Normalwerten und Herstellergrenzen.
- Agent speichert auch ohne Zentrale lokal. Beim nächsten Intervall wird ein aktueller Bericht gesendet. Historische Offline-Messungen werden nicht nachträglich zur Zentrale synchronisiert.

## Sicherheit und Speicherung

Die Netzwerk-API nimmt ausschließlich Fernet-authentifizierte und verschlüsselte Berichte an (AES-128-CBC + HMAC-SHA256). Der Inhalt bleibt auch bei einer `http://`-Adresse verschlüsselt. Die HTTP-Transportmetadaten sind nicht verschlüsselt. Nachrichten haben eine Lebensdauer von 5 Minuten und einen Replay-Schutz. Systemuhren synchron halten. Alle Agenten einer Zentrale teilen einen Schlüssel; deshalb nur vertrauenswürdige Rechner koppeln. Keine öffentliche Internet-Portfreigabe.

Die Verwaltungsoberflächen lauschen nur auf `127.0.0.1`: Zentrale **9765**, Agent **9767**, jeweils mit zufälligem Sitzungstoken. Die Empfangs-API lauscht auf **9766**. Fremde Webseiten erhalten weder CORS-Freigabe noch Zugriff auf die Verwaltung. Nachrichten sind auf 8 MiB und 16 gleichzeitige Verbindungen begrenzt.

Einstellungen, gemeinsamer Schlüssel, SQLite-Historie und rotierende Logs liegen unter `%LOCALAPPDATA%\PlateGuard\hub` bzw. `agent`. Der Schlüssel ist in der lokalen Konfigurationsdatei gespeichert; der Windows-Benutzerordner muss geschützt sein. Single-file-EXEs entpacken eingebettete Komponenten beim Start temporär. „Keine externen Dateien“ bedeutet keine manuell mitzuliefernden Abhängigkeiten, nicht einen Betrieb ohne temporäre Dateien oder Datenspeicherung.

Regeln sind pro Programm gespeichert. Die Zentrale kann eigene Alarmgrenzen haben; sie verändert die lokalen Agent-Regeln nicht. Für nur zentrale Meldungen die Benachrichtigungen im Agenten abschalten.

## Fachliche Grundlage

- [Backblaze: What SMART Stats Indicate Hard Drive Failures?](https://www.backblaze.com/blog/what-smart-stats-indicate-hard-drive-failures/): HDD-Attribute 5, 187, 188, 197, 198 als relevante Indikatoren; keine Garantie einer individuellen Ausfallvorhersage.
- [Microsoft: NVME_HEALTH_INFO_LOG](https://learn.microsoft.com/en-us/windows/win32/api/nvme/ns-nvme-nvme_health_info_log): kritische Warnbits, Reserve/Herstellergrenze, verbrauchte Lebensdauer, Medienfehler und weitere NVMe-Zähler.
- [smartmontools 7.5](https://github.com/smartmontools/smartmontools/releases/tag/RELEASE_7_5): Geräteerkennung, Herstellerdatenbank und JSON-Berichte; smartctl-Exitcodes sind Bitmasken und werden nicht pauschal als fehlgeschlagene Abfrage interpretiert.

Die Standardregeln sind konservative Startwerte. Temperaturen (50/60 °C), herstellerspezifische ATA-Rohwerte und SSD-Verschleiß sollten zum Modell passen. 100 % verbrauchte SSD-Ausdauer bedeutet nicht zwangsläufig einen unmittelbaren Defekt. CRC-Anstiege können am Kabel/Controller liegen. Fehlerlog-Einträge und unsichere Abschaltungen sind sichtbar, lösen standardmäßig aber keinen Defektalarm aus. Individuelle NVMe-Bits stehen als `nvme_warning_*` für eigene Regeln bereit.

SMART kann nicht jeden plötzlichen Ausfall erkennen. Für hohe Verfügbarkeit bleiben Backups, Wiederherstellungstests und ggf. Redundanz erforderlich. USB-Bridges und RAID-Controller können SMART blockieren. Es werden keine schreibenden Befehle und keine Selbsttests automatisch gestartet; Abfragen können schlafende Laufwerke aufwecken.

## Entwicklung und Prüfung

```powershell
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python build.py
```

Die offiziellen smartmontools-7.5-Builddateien liegen unter `vendor`. Der Build prüft den SHA-256-Hash von smartctl, bettet den unveränderten smartmontools-Quelltext und Drittanbieter-Lizenzen ein und erzeugt beide EXEs sowie `dist/SHA256.json`. Quellpaket und Lizenzen sind über **Hilfe & Quellen** in beiden Programmen herunterladbar. EXEs sind nicht digital signiert.

`tests/preview.py` bietet explizit markierte synthetische Daten für UI-Tests. `tests/live_check.py` liest echte Geräte und sendet nur an eine Loopback-Testzentrale. Testdaten unter `build` sind nicht Teil der Auslieferung.

Geprüft: Regel-/API-/Persistenztests, Browserdarstellung und Speichern von Einstellungen, EXE-Selbsttests sowie tatsächliche Erfassung zweier NVMe-Laufwerke mit verschlüsselter Übertragung auf demselben Windows-Rechner. Nicht praktisch geprüft: zweiter physischer Rechner, alle USB-/RAID-/SATA-Controller, Langzeitbetrieb und Windows-Benachrichtigungen unter jeder Fokusmodus-Konfiguration.
