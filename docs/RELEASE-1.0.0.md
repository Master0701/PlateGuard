# PlateGuard 1.0.0 – SMART-Überwachung für Windows

Zwei eigenständige Windows-x64-EXEs: Agent zur Laufwerkserfassung, Zentrale für die gemeinsame Webübersicht. Enthalten sind Tray-Menüs, regelmäßige Abfragen, verschlüsselte Übertragung, Historie und einstellbare gelbe/rote Alarme. Offline-Rechner lösen keinen Laufwerksalarm aus.

## Kurzstart

1. **PlateGuard-Zentrale.exe** auf dem Hauptrechner starten. Rechtsklick auf das Tray-Symbol → Einstellungen → Verbindungsschlüssel kopieren.
2. TCP-Port **9766** in der Firewall der Zentrale für die Agenten im privaten Netz zulassen.
3. **PlateGuard-Agent.exe** auf jedem überwachten Rechner starten und Administratorrechte bestätigen.
4. Im Agenten die Adresse `http://IP-DER-ZENTRALE:9766` und denselben Schlüssel eintragen, speichern und „Jetzt aktualisieren“ wählen.

Für die Laufwerke des Hauptrechners dort zusätzlich einen Agenten starten. Beide Programme müssen für die Überwachung laufen; Autostart/Dienst werden nicht automatisch eingerichtet. Keine Python-Installation oder Begleitdateien nötig; Einstellungen und Messhistorie liegen in AppData.

## Dateien

- `PlateGuard-Zentrale.exe` – Zentrale für den Hauptrechner.
- `PlateGuard-Agent.exe` – Agent für die überwachten Windows-Rechner.
- `Kurzinfo.txt` – kurze Einrichtungsinfo.
- `SHA256.json` – SHA-256-Prüfsummen der beiden EXEs.

**Geprüft:** 22 automatische Tests, beide EXE-Selbsttests, Tray und Browser sowie echte Erfassung zweier NVMe-Laufwerke mit verschlüsselter Loopback-Übertragung. Zweiter physischer Rechner, alle Controller-Typen und Langzeitbetrieb sind noch nicht praktisch geprüft. Die EXEs sind nicht digital signiert. SMART kann nicht jeden Ausfall vorhersehen.

[Vollständige Anleitung](https://github.com/Master0701/PlateGuard/blob/v1.0.0/docs/ANLEITUNG.md) · [Projektübersicht](https://github.com/Master0701/PlateGuard) · [Prüfprotokoll](https://github.com/Master0701/PlateGuard/blob/v1.0.0/TESTING.md)
