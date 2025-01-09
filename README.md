# README

## Digitaler Bilderrahmen mit Sprachsteuerung

Dieses Projekt implementiert einen digitalen Bilderrahmen, der mit einem Raspberry Pi, einem 7-Zoll-Touchdisplay und einem USB-Mikrofon realisiert wurde. Die Steuerung erfolgt über Sprachbefehle, während die Bilder in einer automatisierten Diashow präsentiert werden.

---

## Anforderungen

### Hardware
- Raspberry Pi 4 Model B
- 7-Zoll-Touchdisplay
- USB-Mikrofon
- 16 GB SD-Karte

### Software
- **Betriebssystem:** Raspberry Pi OS
- **Programmiersprache:** Python 3.9 oder höher

### Python-Bibliotheken
Installieren Sie die folgenden Abhängigkeiten mit `pip`:
```bash
pip install opencv-python
pip install SpeechRecognition
pip install numpy
pip install rapidfuzz
```

## Installation
### Repository klonen
```bash
git clone <REPOSITORY_URL>
cd digital-frame-project
```

### Python-Umgebung einrichten
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Ordnerstruktur erstellen
```bash
mkdir -p /home/pi/DigiBilderrahmen/script/images
```

### Skript ausführen
```bash
python3 digital_frame_code.py
```

## Sprachbefehle
Die folgenden Sprachbefehle werden vom System unterstützt:
-"stopp": Stoppt die Diashow.
- "schneller": Erhöht die Abspielgeschwindigkeit.
- "langsamer": Verringert die Abspielgeschwindigkeit.
- "weiter": Setzt die Diashow fort.
- "speichern als favorit": Speichert das aktuelle Bild als Favorit.
- "spiele favoriten ab": Startet eine Diashow mit den gespeicherten Favoriten.
- "alle bilder anzeigen": Zeigt alle Bilder in einer Diashow.
- "bild löschen": Entfernt das aktuelle Bild aus dem Verzeichnis.

## Hinweise
- Die Mikrofoneinstellung (Index) kann variieren. Passen Sie ggf. den device_index in der Funktion listen_for_command() an.
- Stellen Sie sicher, dass alle Bilder im Verzeichnis /home/pi/DigiBilderrahmen/script/images gespeichert sind.
