# Änderungen

## 1.0.0 – 2026-10-27

Erste lauffähige Version für Windows x64.

- Eigenständige Agent- und Zentralen-EXE mit Tray-Menü und lokaler Weboberfläche.
- Regelmäßige SMART-Abfragen für durch smartmontools erreichbare HDD-, SSD-, NVMe- und SAS/SCSI-Geräte.
- Verschlüsselte und authentifizierte Übertragung, Replay-Schutz und lokale Verwaltungsoberfläche.
- Konfigurierbare gelbe/rote Warnregeln, Zuwachsregeln und Laufwerksfilter.
- Optionale Windows-Benachrichtigungen, Ton und Alarm-Pause.
- Offline-Anzeige ohne Laufwerksalarm, Hinweise auf fehlende oder nicht lesbare Laufwerke.
- Messhistorie, Verlauf und ATA-Rohdatenansicht.

Validiert durch 22 automatische Tests, EXE-Selbsttests, Tray-/Browserprüfung und echte Erfassung zweier NVMe-Laufwerke mit lokaler verschlüsselter Übertragung. Ein Test zwischen zwei physischen Rechnern und Langzeitbetrieb stehen aus.

Kein automatischer Windows-Dienst/Autostart. EXEs sind nicht digital signiert. SMART ist eine Frühwarnhilfe und ersetzt keine Datensicherung.
