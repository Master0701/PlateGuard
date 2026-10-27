# Prüfprotokoll – 27. Oktober 2026

## Automatische Tests

22 Tests erfolgreich (`python -m unittest discover -s tests -v`). Abgedeckt:

- HDD-Sektoren, SATA-SSD-Ausdauer, NVMe-Reserve, Medienfehler und einzelne Warnbits.
- Grenzwerte, Regel-Deaktivierung, Laufwerkseinschränkung, Zuwachs, erste Messung und Zählerreset.
- Unbekannte/unvollständige Berichte; SMART-Exit-Bitmasken.
- Authentifizierte, verschlüsselte Berichte; falscher Schlüssel, Replay und Zeitablauf.
- Verwaltungs-Authentifizierung und Trennung vom Netzwerk-Empfänger.
- Persistenz, verspätete Nachrichten, fehlende Laufwerke und keine Alarme bei veralteten Messungen.

## Praktische Prüfungen

- Beide Single-file-EXEs: Selbsttest mit eingebettetem smartctl 7.5, Kryptografie und Webressourcen erfolgreich.
- Tray-Lebenszyklus: Symbol sichtbar, Menü initialisiert, sauber beendet.
- Weboberfläche: Dashboard, kritischer synthetischer HDD-Fall, Detailansicht, Verlauf und Speichern der Einstellungen geprüft. Keine JavaScript-Fehler im Browserprotokoll.
- Reale SMART-Erfassung: zwei NVMe-Laufwerke erkannt und vollständig gelesen; verschlüsselte Übertragung über echte HTTP-Loopback-Verbindung an eine separate Testzentrale erfolgreich.
- Die konkrete Hardware-Messhistorie bleibt lokal und wird nicht mit dem Quellcode veröffentlicht. Ein erfolgreicher Test ist keine Ausfallgarantie.

## Noch nicht praktisch verifiziert

Verbindung zwischen zwei physischen Windows-Rechnern einschließlich Firewall, Langzeitbetrieb, tatsächliche HDD-/SATA-/SAS-/USB-/RAID-Hardware und Windows-Benachrichtigungen unter unterschiedlichen Fokusmodus-Einstellungen. Die entsprechenden Parser-/Regelfälle wurden synthetisch getestet.

Die Programme sind nicht digital signiert. Keine automatische Firewall-Änderung, kein Dienst und kein Autostart wurden eingerichtet.
