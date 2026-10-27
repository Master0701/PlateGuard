# Eingebettete Drittanbieter-Komponente

Unveränderte Dateien aus dem offiziellen **smartmontools 7.5**-Release:

- [Release und Windows-Paket](https://github.com/smartmontools/smartmontools/releases/tag/RELEASE_7_5)
- [Quellpaket](https://github.com/smartmontools/smartmontools/releases/download/RELEASE_7_5/smartmontools-7.5.tar.gz)

Für den Build enthalten sind ausschließlich `smartctl.exe` (64 Bit), `drivedb.h`, die GPL-Lizenz, die Originalprüfsummen und das unveränderte Quellarchiv. Der Build prüft smartctl gegen SHA-256 `b5db94e5082c042be44994b7a4fa8f7b5c8e713b2ab1c9a560d8f7a7995ea27d` und bettet die Komponente einschließlich Quellarchiv/Lizenz in die EXEs ein.

Installer, Entpackwerkzeuge und entpackte Quellkopien aus der lokalen Entwicklung werden nicht ins Repository übernommen. Weitere Drittanbieter-Lizenzen stehen in `../LICENSES.txt`.
