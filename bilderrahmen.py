import os
import cv2
import json
import numpy as np
import speech_recognition as sr
from threading import Thread, Lock
from rapidfuzz import fuzz, process
import ctypes
import re
import time

# Bekannte Befehle
known_commands = [
    "stopp",
    "schneller",
    "langsamer",
    "weiter",
    "speichern als favorit",
    "spiele favoriten ab",
    "alle bilder anzeigen",
    "bild löschen",
    "von vorne",
    "gehe zu bild",
    "ausschalten",
    "vorwärts",
    "zurück",
    "pause",
    "play"
]

# Unterdrückt ALSA-Fehlerausgaben (Raspberry-spezifisch) - sehr viele Log-Meldungen, welche nicht relevant sind
asound = ctypes.CDLL('libasound.so')
asound.snd_lib_error_set_handler(None)

# Globale Variablen
image_folder = "/home/joelh/DigiBilderrahmen/script/images/"
favorites_file = "favorites.json"
icons_folder = "/home/joelh/DigiBilderrahmen/script/Icons/"

current_speed = 10
images = []
favorites = []
running = True
paused = False
current_image = None
current_index = 0
last_image_update_time = time.time()
favorites_mode = False  # Steuert Favoriten-Slideshow vs. normale Bilder

# Menü- und UI-Steuerung
menu_visible = False
menu_last_interaction = 0.0
menu_highlight_end = 0.0
MENU_HIDE_DELAY = 5.0     # Inaktivität -> Menü verschwindet
BUTTON_HIDE_DELAY = 3.0   # Nach Button-Klick -> Menü verschwindet
highlighted_button = None

# Info-Overlay (Legende) beim Klick auf info-Button
info_visible = False       # Ist das Info-Overlay an?
info_hide_time = 0.0       # Bis wann soll es sichtbar sein? (time.time() + 10)

# Visuelles Feedback
hotword_feedback_until = 0.0    # Blauer Rand
command_success_until = 0.0     # Grüner Rand
command_fail_until = 0.0        # Roter Rand

# Lock für Thread-Sicherheit
lock = Lock()

# Anzeigegrößen (z. B. 800x480-Display)
ICON_SIZE = 64
MENU_HEIGHT = 80
SCREEN_WIDTH = 800
SCREEN_HEIGHT = 480

# 8 Buttons. Definiert in fester Reihenfolge:
buttons_in_order = [
    "langsamer",
    "zurück",
    "pause_play",
    "vorwärts",
    "schneller",
    "favorit",
    "modus",
    "info"
]

# Zentrierte Layout-Berechnung
start_x = 74
gap = 20
y1 = SCREEN_HEIGHT - MENU_HEIGHT + 8
y2 = y1 + ICON_SIZE

button_layout = {}
x = start_x
for btn_id in buttons_in_order:
    button_layout[btn_id] = (x, y1, x + ICON_SIZE, y2)
    x += ICON_SIZE + gap

def load_icon_with_white_bg(icon_path, size=(64, 64)):
    icon_rgba = cv2.imread(icon_path, cv2.IMREAD_UNCHANGED)
    if icon_rgba is None:
        print(f"Konnte Icon '{icon_path}' nicht laden.")
        return None

    if len(icon_rgba.shape) == 3 and icon_rgba.shape[2] == 4:
        b, g, r, a = cv2.split(icon_rgba)
        alpha_float = a.astype(np.float32) / 255.0
        white_bg = np.full((icon_rgba.shape[0], icon_rgba.shape[1], 3), 255, dtype=np.uint8)
        for c, channel in enumerate([b, g, r]):
            ch_f = channel.astype(np.float32)
            white_bg[:, :, c] = (alpha_float * ch_f + (1.0 - alpha_float) * 255.0).astype(np.uint8)
        icon_bgr = white_bg
    else:
        icon_bgr = icon_rgba

    icon_scaled = cv2.resize(icon_bgr, size, interpolation=cv2.INTER_AREA)
    return icon_scaled

# Icons
icon_langsamer  = load_icon_with_white_bg(os.path.join(icons_folder, "langsamer.png"), (ICON_SIZE, ICON_SIZE))
icon_schneller  = load_icon_with_white_bg(os.path.join(icons_folder, "schneller.png"), (ICON_SIZE, ICON_SIZE))
icon_left       = load_icon_with_white_bg(os.path.join(icons_folder, "linker-pfeil.png"), (ICON_SIZE, ICON_SIZE))
icon_right      = load_icon_with_white_bg(os.path.join(icons_folder, "rechter-pfeil.png"), (ICON_SIZE, ICON_SIZE))
icon_pause      = load_icon_with_white_bg(os.path.join(icons_folder, "pause.png"), (ICON_SIZE, ICON_SIZE))
icon_play       = load_icon_with_white_bg(os.path.join(icons_folder, "play-taste.png"), (ICON_SIZE, ICON_SIZE))
icon_star       = load_icon_with_white_bg(os.path.join(icons_folder, "star.png"), (ICON_SIZE, ICON_SIZE))
icon_star_true  = load_icon_with_white_bg(os.path.join(icons_folder, "star_true.png"), (ICON_SIZE, ICON_SIZE))
icon_modus_all  = load_icon_with_white_bg(os.path.join(icons_folder, "all.png"), (ICON_SIZE, ICON_SIZE))
icon_modus_fav  = load_icon_with_white_bg(os.path.join(icons_folder, "favorite_only.png"), (ICON_SIZE, ICON_SIZE))
icon_info       = load_icon_with_white_bg(os.path.join(icons_folder, "info.png"), (ICON_SIZE, ICON_SIZE))

# lädt alle Bilder aus dem Image-Pfad
def load_images():
    global images, current_image
    if not os.path.exists(image_folder):
        print(f"Fehler: Ordner {image_folder} existiert nicht!")
        return

    with lock:
        images = [
            os.path.join(image_folder, f)
            for f in os.listdir(image_folder)
            if f.lower().endswith(('.png', '.jpg', '.jpeg'))
        ]
        if images:
            current_image = images[0]
        else:
            print(f"Keine Bilder im Ordner {image_folder} gefunden.")

# Lädt alle Bilder, welche im JSON-File als Favorit abgespeichert sind
def load_favorites():
    global favorites
    if os.path.exists(favorites_file):
        with open(favorites_file, "r") as f:
            try:
                favorites = json.load(f)
            except json.JSONDecodeError:
                favorites = []
    else:
        favorites = []

# Speichert ein Bild als Favorit ab -> Eintrag in JSON-File
def save_favorite(image):
    with lock:
        if image not in favorites:
            favorites.append(image)
            with open(favorites_file, "w") as f:
                json.dump(favorites, f)

# Löscht ein Bild aus Favoriten -> Eintrag löschen in JSON-File
def remove_favorite(image):
    with lock:
        if image in favorites:
            favorites.remove(image)
            with open(favorites_file, "w") as f:
                json.dump(favorites, f)

# Bild auf Display anpassen
def resize_and_center_image(image, screen_width, screen_height):
    background = np.zeros((screen_height, screen_width, 3), dtype=np.uint8)
    image_height, image_width = image.shape[:2]
    aspect_ratio = image_width / image_height

    if aspect_ratio > screen_width / screen_height:
        new_width = screen_width
        new_height = int(screen_width / aspect_ratio)
    else:
        new_height = screen_height
        new_width = int(screen_height * aspect_ratio)

    resized_image = cv2.resize(image, (new_width, new_height))
    x_offset = (screen_width - new_width) // 2
    y_offset = (screen_height - new_height) // 2
    background[y_offset:y_offset + new_height, x_offset:x_offset + new_width] = resized_image
    return background

# Verbessert Erkennung mittels bekannter Befehle. Befehl erkannt bei > 70% übereinstimmung
def find_best_match(command):
    command = command.strip().lower()
    result = process.extractOne(command, known_commands, scorer=fuzz.token_sort_ratio)
    if result and result[1] > 70:
        return result[0]
    return None

# Vermeidung von Umlauten -> Können nicht dargestellt werden.
def ascii_fallback(text):
    text = text.replace("ä", "ae").replace("Ä", "Ae")
    text = text.replace("ö", "oe").replace("Ö", "Oe")
    text = text.replace("ü", "ue").replace("Ü", "Ue")
    text = text.replace("ß", "ss")
    return text

# Listener Funktion: Wartet auf das Erkennungswort "Hey Berry"
def listen_for_command():
    recognizer = sr.Recognizer()
    mic = sr.Microphone(device_index=2)  # Mikrofon-Index auf 2 fest kodiert
    try:
        with mic as source:
            recognizer.adjust_for_ambient_noise(source)
            print("Warte auf das Erkennungswort...")
            audio = recognizer.listen(source, timeout=5, phrase_time_limit=3)
        text = recognizer.recognize_google(audio, language="de-DE").lower()
        print(f"Debug: Erkanntes Audio: {text}")
        if any(variant in text for variant in ["hey berry", "hey baby", "hey barry"]):
            print("Erkennungswort erkannt!")
            global hotword_feedback_until
            hotword_feedback_until = time.time() + 1.0  # 1 Sekunde blauer Rand
            return True
    except sr.UnknownValueError:
        print("Ich konnte dich nicht verstehen.")
    except sr.WaitTimeoutError:
        print("Kein Erkennungswort erkannt.")
    except Exception as e:
        print(f"Fehler im Listener: {e}")
    return False

# Listener Funktion: Wartet auf einen Befehl, nachdem das Erkennungswort erkannt wurde
def listen_for_following_command():
    """
    Gibt (best_match, original_text) zurück.
    Falls kein passender Befehl => best_match=None
    """
    recognizer = sr.Recognizer()
    mic = sr.Microphone(device_index=2)
    try:
        with mic as source:
            recognizer.adjust_for_ambient_noise(source)
            print("Sprich jetzt deinen Befehl...")
            audio = recognizer.listen(source, timeout=5, phrase_time_limit=3)
        command_text = recognizer.recognize_google(audio, language="de-DE").lower()
        best_match = find_best_match(command_text)
        if best_match:
            print(f"Befehl erkannt: {best_match} (Original: '{command_text}')")
            return best_match, command_text
        else:
            print(f"Unbekannter Befehl: '{command_text}'")
            return None, command_text
    except sr.UnknownValueError:
        print("Ich konnte den Befehl nicht verstehen.")
    except sr.WaitTimeoutError:
        print("Kein Befehl erkannt (Timeout).")
    except Exception as e:
        print(f"Fehler beim Erfassen des Befehls: {e}")
    return None, None

# Erkannter Befehl wird ausgeführt. Diashow kurz Pausieren, um Deadlocks zu vermeiden
def execute_command(command, original_text=""):
    global paused, current_image, current_index, running, favorites_mode, current_speed
    print(f"DEBUG: execute_command aufgerufen mit command='{command}'")

    with lock:
        print("DEBUG: In with lock angekommen")

        if command in ["stopp", "pause"]:
            paused = True
            print("Diashow gestoppt/pausiert.")
        elif command in ["weiter", "play"]:
            paused = False
            print("Diashow fortgesetzt.")
        elif command == "schneller":
            if current_speed > 1:
                current_speed -= 1
            print("Geschwindigkeit erhöht (Intervall verkürzt).")
        elif command == "langsamer":
            current_speed += 1
            print("Geschwindigkeit verringert (Intervall erhöht).")
        elif command == "vorwärts":
            clist = favorites if favorites_mode else images
            if clist:
                current_index = (current_index + 1) % len(clist)
                current_image = clist[current_index]
            print("Ein Bild vorwärts.")
        elif command == "zurück":
            clist = favorites if favorites_mode else images
            if clist:
                current_index = (current_index - 1) % len(clist)
                current_image = clist[current_index]
            print("Ein Bild zurück.")
        elif command == "speichern als favorit":
            if current_image:
                save_favorite(current_image)
                print(f"Bild {current_image} als Favorit gespeichert.")
        elif command == "spiele favoriten ab":
            if favorites:
                favorites_mode = True
                current_index = 0
                print("Wechsle in Favoriten-Slideshow.")
            else:
                print("Keine Favoriten vorhanden!")
        elif command == "alle bilder anzeigen":
            favorites_mode = False
            current_index = 0
            print("Wechsle zur normalen Slideshow (alle Bilder).")
        elif command == "bild löschen":
            if current_image:
                if favorites_mode:
                    if current_image in favorites:
                        favorites.remove(current_image)
                        with open(favorites_file, "w") as f:
                            json.dump(favorites, f)
                        print(f"Bild {current_image} aus Favoriten gelöscht.")
                    else:
                        print("Bild nicht in Favoriten enthalten.")
                else:
                    if current_image in images:
                        images.remove(current_image)
                        print(f"Bild {current_image} gelöscht.")

                clist = favorites if favorites_mode else images
                if clist:
                    current_index %= len(clist)
                    current_image = clist[current_index]
                else:
                    current_image = None
        elif command == "von vorne":
            current_index = 0
            print("Diashow startet von vorne.")
        elif command == "gehe zu bild":
            match = re.search(r'\b(\d+)\b', original_text)
            if match:
                bild_nummer = int(match.group(1))
                clist = favorites if favorites_mode else images
                if clist:
                    if 1 <= bild_nummer <= len(clist):
                        current_index = bild_nummer - 1
                        current_image = clist[current_index]
                        print(f"Springe zu Bild {bild_nummer}.")
                    else:
                        print("Nummer außerhalb der Liste.")
                else:
                    print("Keine Bilder vorhanden.")
            else:
                print("Keine gültige Bildnummer erkannt.")
        elif command == "ausschalten":
            running = False
            print("Gerät wird heruntergefahren.")

# Overlay, bei klick auf Button "info" -> Alle Sprachbefehle werden aufgelistet
def draw_info_overlay(frame):
    overlay = frame.copy()
    rect_x1, rect_y1 = 50, 50
    rect_x2, rect_y2 = SCREEN_WIDTH - 50, SCREEN_HEIGHT - 50
    cv2.rectangle(overlay, (rect_x1, rect_y1), (rect_x2, rect_y2), (0, 0, 0), -1)
    alpha = 0.7
    frame = cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0)

    text_lines = [
        "Moegliche Sprachbefehle:",
        "- stopp / pause",
        "- weiter / play",
        "- langsamer / schneller",
        "- vorwaerts / zurueck",
        "- speichern als favorit",
        "- alle bilder anzeigen",
        "- spiele favoriten ab",
        "- bild loeschen",
        "- gehe zu bild [nummer]",
        "- ausschalten"
    ]

    x_text = rect_x1 + 30
    y_text = rect_y1 + 50
    for line in text_lines:
        line_asc = ascii_fallback(line)
        cv2.putText(frame, line_asc, (x_text, y_text),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)
        y_text += 40
    return frame

# Zeichne Menu bei klick auf Bildschrim
def draw_menu(frame):
    cv2.rectangle(
        frame,
        (0, SCREEN_HEIGHT - MENU_HEIGHT),
        (SCREEN_WIDTH, SCREEN_HEIGHT),
        (50, 50, 50),
        -1
    )

    # langsamer
    if icon_langsamer is not None:
        x1,y1,x2,y2 = button_layout["langsamer"]
        frame[y1:y2, x1:x2] = icon_langsamer

    # zurück (linker-pfeil)
    if icon_left is not None:
        x1,y1,x2,y2 = button_layout["zurück"]
        frame[y1:y2, x1:x2] = icon_left

    # pause_play
    icon_pp = icon_play if paused else icon_pause
    if icon_pp is not None:
        x1,y1,x2,y2 = button_layout["pause_play"]
        frame[y1:y2, x1:x2] = icon_pp

    # vorwärts (rechter-pfeil)
    if icon_right is not None:
        x1,y1,x2,y2 = button_layout["vorwärts"]
        frame[y1:y2, x1:x2] = icon_right

    # schneller
    if icon_schneller is not None:
        x1,y1,x2,y2 = button_layout["schneller"]
        frame[y1:y2, x1:x2] = icon_schneller

    # favorit
    if current_image in favorites:
        icon_fav = icon_star_true
    else:
        icon_fav = icon_star
    if icon_fav is not None:
        x1,y1,x2,y2 = button_layout["favorit"]
        frame[y1:y2, x1:x2] = icon_fav

    # modus
    icon_modus = icon_modus_fav if favorites_mode else icon_modus_all
    if icon_modus is not None:
        x1,y1,x2,y2 = button_layout["modus"]
        frame[y1:y2, x1:x2] = icon_modus

    # info
    if icon_info is not None:
        x1,y1,x2,y2 = button_layout["info"]
        frame[y1:y2, x1:x2] = icon_info

    # Highlight-Rahmen
    if highlighted_button in button_layout:
        x1,y1,x2,y2 = button_layout[highlighted_button]
        cv2.rectangle(frame, (x1,y1), (x2,y2), (0,255,255), 3)

# Prüft, ob der Klick auf den Display im Bereich eines Buttons liegt. True = liegt im Bereich, False=Ausserhalb des Bereichs
def point_in_rect(x, y, rect):
    x1, y1, x2, y2 = rect
    return (x1 <= x <= x2) and (y1 <= y <= y2)

# Führt den Befehl des angeklickten Buttons aus
def handle_button_click(btn_key):
    global menu_highlight_end, highlighted_button, current_image, current_index
    global favorites_mode, info_visible, info_hide_time

    print(btn_key + " wurde geklickt")

    if btn_key == "langsamer":
        execute_command("langsamer")
    elif btn_key == "schneller":
        execute_command("schneller")
    elif btn_key == "zurück":
        execute_command("zurück")
    elif btn_key == "vorwärts":
        execute_command("vorwärts")
    elif btn_key == "pause_play":
        if paused:
            execute_command("play")
        else:
            execute_command("pause")
    elif btn_key == "favorit":
        with lock:
            if current_image:
                if current_image in favorites:
                    print("Bild aus Favoriten entfernen")
                    favorites.remove(current_image)
                    with open(favorites_file, "w") as f:
                        json.dump(favorites, f)
                    if favorites_mode:
                        if favorites:
                            current_index %= len(favorites)
                            current_image = favorites[current_index]
                        else:
                            current_image = None
                else:
                    print("Bild zu Favoriten hinzufuegen")
                    if current_image not in favorites:
                        favorites.append(current_image)
                        with open(favorites_file, "w") as f:
                            json.dump(favorites, f)
    elif btn_key == "modus":
        with lock:
            if favorites_mode:
                favorites_mode = False
                current_index = 0
                print("Wechsle zur normalen Slideshow.")
                if images:
                    current_image = images[0]
                else:
                    current_image = None
            else:
                if favorites:
                    favorites_mode = True
                    current_index = 0
                    print("Wechsle in Favoriten-Slideshow.")
                    current_image = favorites[0]
                else:
                    print("Keine Favoriten vorhanden!")
    elif btn_key == "info":
        info_visible = True
        info_hide_time = time.time() + 10
        print("Zeige Info-Overlay (Legende)")

    highlighted_button = btn_key
    menu_highlight_end = time.time() + BUTTON_HIDE_DELAY
    print("End handle_button_click")

# Funktion wird bei einer Berührung auf das Touch-Display aufgerufen
def mouse_callback(event, x, y, flags, param):
    global menu_visible, menu_last_interaction, menu_highlight_end, highlighted_button
    global info_visible

    if event == cv2.EVENT_LBUTTONDOWN:
        x_corr = SCREEN_WIDTH - 1 - x
        y_corr = SCREEN_HEIGHT - 1 - y

        now = time.time()
        menu_last_interaction = now

        # Falls Info-Overlay an => bei Klick ausblenden
        if info_visible:
            info_visible = False
            return

        if not menu_visible:
            menu_visible = True
            highlighted_button = None
            menu_highlight_end = 0
            return

        clicked_button = None
        # Prüfen, ob ein Button geklickt wurde
        for key, rect in button_layout.items():
            if point_in_rect(x_corr, y_corr, rect):
                clicked_button = key
                break

        if clicked_button:
            handle_button_click(clicked_button)
        else:
            # Außerhalb geklickt => Menü ausblenden
            menu_visible = False
            highlighted_button = None
            menu_highlight_end = 0

# Thread für die Diashow
def slideshow_thread():
    global running, paused, images, favorites, current_speed
    global current_image, current_index, last_image_update_time, favorites_mode
    global menu_visible, menu_last_interaction, menu_highlight_end, highlighted_button
    global info_visible, info_hide_time
    global hotword_feedback_until, command_success_until, command_fail_until

    os.system('unclutter -idle 0.1 -root &')
    cv2.namedWindow("Digitaler Bilderrahmen", cv2.WND_PROP_FULLSCREEN)
    cv2.setWindowProperty("Digitaler Bilderrahmen", cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

    cv2.setMouseCallback("Digitaler Bilderrahmen", mouse_callback)

    try:
        while True:
            with lock:
                if not running:
                    break

                current_list = favorites if favorites_mode else images

                if not paused and (time.time() - last_image_update_time >= current_speed):
                    if current_list:
                        current_index = (current_index + 1) % len(current_list)
                        current_image = current_list[current_index]
                        last_image_update_time = time.time()
                    else:
                        current_image = None

                # Bild laden/zentrieren
                if current_image:
                    img = cv2.imread(current_image)
                    if img is not None:
                        frame = resize_and_center_image(img, SCREEN_WIDTH, SCREEN_HEIGHT)
                    else:
                        print(f"Fehler: Bild {current_image} konnte nicht geladen werden.")
                        frame = np.zeros((SCREEN_HEIGHT, SCREEN_WIDTH, 3), dtype=np.uint8)
                else:
                    frame = np.zeros((SCREEN_HEIGHT, SCREEN_WIDTH, 3), dtype=np.uint8)

                # Menü einzeichnen?
                if menu_visible:
                    draw_menu(frame)

                # Info-Overlay?
                now = time.time()
                if info_visible:
                    if now > info_hide_time:
                        info_visible = False
                    else:
                        frame = draw_info_overlay(frame)

                # Rahmen-Logik
                if now < command_fail_until:
                    # Roter Rand = Befehl nicht erkannt
                    cv2.rectangle(frame, (0,0), (SCREEN_WIDTH-1, SCREEN_HEIGHT-1), (0,0,255), 10)
                elif now < command_success_until:
                    # Grüner Rand = Befehlt erkannt
                    cv2.rectangle(frame, (0,0), (SCREEN_WIDTH-1, SCREEN_HEIGHT-1), (0,255,0), 10)
                elif now < hotword_feedback_until:
                    # Blauer Rand = Erkennungswort erkannt -> Jetzt Befehl sprechen
                    cv2.rectangle(frame, (0,0), (SCREEN_WIDTH-1, SCREEN_HEIGHT-1), (255,0,0), 10)

                # Menü ausblenden nach Highlight/Timeout?
                if menu_highlight_end > 0 and now > menu_highlight_end:
                    menu_visible = False
                    highlighted_button = None
                    menu_highlight_end = 0
                elif menu_highlight_end == 0 and menu_visible:
                    if now - menu_last_interaction > MENU_HIDE_DELAY:
                        menu_visible = False
                        highlighted_button = None

            cv2.imshow("Digitaler Bilderrahmen", frame)
            key = cv2.waitKey(50)
            if key == ord('q'):
                with lock:
                    running = False

    finally:
        cv2.destroyAllWindows()

#Thread für die Spracherkennung/Sprachsteuerung
def voice_control_thread():
    global running, command_success_until, command_fail_until
    while True:
        # Nur kurz lock fuer 'running' checken, um deadlocks zu vermeiden
        with lock:
            if not running:
                break

        try:
            if listen_for_command():
                print("Erkennungswort erkannt, warte auf Folgekommando...")
                matched_command, original_text = listen_for_following_command()

                # => lock nur kurz fuer Zeitstempel
                if matched_command:
                    with lock:
                        command_success_until = time.time() + 1.0
                    # execute_command ausserhalb des lock
                    execute_command(matched_command, original_text)
                else:
                    with lock:
                        command_fail_until = time.time() + 1.0

        except Exception as e:
            print(f"Fehler im Sprachsteuerungsthread: {e}")

def main():
    global running
    load_images()
    load_favorites()
    print("Digitaler Bilderrahmen gestartet!")

    slideshow = Thread(target=slideshow_thread)
    voice_control = Thread(target=voice_control_thread)

    slideshow.start()
    voice_control.start()

    slideshow.join()
    voice_control.join()

if __name__ == "__main__":
    main()
