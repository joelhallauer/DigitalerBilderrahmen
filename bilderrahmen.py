import os
import cv2
import json
import numpy as np
import speech_recognition as sr
from threading import Thread
from rapidfuzz import fuzz, process
import ctypes

# Liste bekannter Befehle
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
    "gehe zu bild"
]

# Unterdrückt ALSA-Fehlerausgaben
asound = ctypes.CDLL('libasound.so')
asound.snd_lib_error_set_handler(None)

# Globale Variablen
image_folder = "/home/joelh/DigiBilderrahmen/script/images/"
favorites_file = "favorites.json"
current_speed = 10
images = []
favorites = []
running = True
paused = False
current_image = None
current_index = 0

# Funktionen
def load_images():
    global images
    images = [os.path.join(image_folder, f) for f in os.listdir(image_folder) if f.endswith(('.png', '.jpg', '.jpeg'))]

def load_favorites():
    global favorites
    if os.path.exists(favorites_file):
        with open(favorites_file, "r") as f:
            favorites = json.load(f)

def save_favorite(image):
    if image not in favorites:
        favorites.append(image)
        with open(favorites_file, "w") as f:
            json.dump(favorites, f)

def remove_favorite(image):
    if image in favorites:
        favorites.remove(image)
        with open(favorites_file, "w") as f:
            json.dump(favorites, f)

def increase_speed():
    global current_speed
    if current_speed > 1:
        current_speed -= 1

def decrease_speed():
    global current_speed
    current_speed += 1

def play_favorites():
    global images, favorites, current_index, paused
    if favorites:
        images = favorites[:]
        current_index = 0
        paused = False
        print("Favoritenmodus aktiviert.")
    else:
        print("Keine Favoriten vorhanden!")

def play_all_images():
    global images, current_index, paused
    load_images()
    current_index = 0
    paused = False
    print("Zeige alle Bilder.")

def delete_current_image():
    global current_image, current_index, images
    if current_image:
        print(f"Lösche Bild: {current_image}")
        os.remove(current_image)
        del images[current_index]
        current_index = current_index % len(images) if images else 0

def jump_to_image(index):
    global current_index, images
    if 0 <= index < len(images):
        current_index = index
        print(f"Springe zu Bild {index + 1} von {len(images)}.")
    else:
        print(f"Bild {index + 1} existiert nicht. Gesamtanzahl: {len(images)}.")

def restart_slideshow():
    global current_index, paused
    current_index = 0
    paused = False
    print("Starte Diashow von vorne.")

def shutdown():
    os.system("sudo shutdown now")

def find_best_match(command):
    """
    Findet den am besten passenden Befehl aus der Liste `known_commands`.
    """
    try:
        # Trimme und normalisiere den Eingabebefehl
        command = command.strip().lower()
        print(f"Normalisierter Befehl: {command}")

        # Fuzzy-Matching auf die bekannte Befehlsliste anwenden
        result = process.extractOne(command, known_commands, scorer=fuzz.token_sort_ratio)
        print(f"Debug: Ergebnis von extractOne: {result}")

        # Sicherstellen, dass das Ergebnis gültig ist
        if result and len(result) == 3:  # result enthält (Befehl, Ähnlichkeit, Index)
            best_match, score, _ = result
            print(f"Gefundener Befehl: {best_match} mit Ähnlichkeit: {score}%")
            if score > 70:  # Schwellenwert für die Ähnlichkeit
                return best_match

        print(f"Kein passender Befehl gefunden für: {command}")
    except Exception as e:
        print(f"Fehler im Matching-Prozess: {e}")
    return None


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

def listen_for_command():
    recognizer = sr.Recognizer()
    mic = sr.Microphone(device_index=1)
    try:
        with mic as source:
            print("Passe mich an Umgebungsgeräusche an...")
            recognizer.adjust_for_ambient_noise(source)
            print("Warte auf das Erkennungswort 'Hey Berry'...")
            audio = recognizer.listen(source, timeout=10, phrase_time_limit=5)
        print("Verarbeite das Gesagte...")
        text = recognizer.recognize_google(audio, language="de-DE").lower()
        wake_word_variants = ["hey berry", "hey baby", "hey barry", "hey bery", "hibery"]
        if any(variant in text for variant in wake_word_variants):
            print("Erkennungswort erkannt!")
            return True
        else:
            print(f"Unbekanntes Wort erkannt: {text}")
            return False
    except sr.UnknownValueError:
        print("Ich konnte dich nicht verstehen.")
    except sr.WaitTimeoutError:
        print("Kein Erkennungswort erkannt (Timeout).")
    except sr.RequestError as e:
        print(f"Fehler beim Zugriff auf den Sprachdienst: {e}")
    return False

def listen_for_following_command():
    recognizer = sr.Recognizer()
    mic = sr.Microphone(device_index=1)
    try:
        with mic as source:
            recognizer.adjust_for_ambient_noise(source)
            print("Sprich jetzt deinen Befehl...")
            audio = recognizer.listen(source, timeout=10, phrase_time_limit=5)
        command = recognizer.recognize_google(audio, language="de-DE").lower()
        print(f"Befehl erkannt: {command}")
        return command
    except sr.UnknownValueError:
        print("Ich konnte den Befehl nicht verstehen.")
    except sr.WaitTimeoutError:
        print("Kein Befehl erkannt (Timeout).")
    except sr.RequestError as e:
        print(f"Fehler beim Zugriff auf den Sprachdienst: {e}")
    return None

def execute_command(command):
    """
    Führt den erkannten Befehl aus.
    """
    global paused, current_image, current_index
    best_match = find_best_match(command)

    if best_match:
        print(f"Befehl erkannt: {best_match}")
        if best_match == "stopp":
            paused = True
        elif best_match == "schneller":
            increase_speed()
        elif best_match == "langsamer":
            decrease_speed()
        elif best_match == "weiter":
            paused = False
        elif best_match == "speichern als favorit":
            if current_image:
                save_favorite(current_image)
        elif best_match == "spiele favoriten ab":
            play_favorites()
        elif best_match == "alle bilder anzeigen":
            play_all_images()
        elif best_match == "bild löschen":
            delete_current_image()
        elif best_match == "von vorne":
            restart_slideshow()
        elif best_match.startswith("gehe zu bild"):
            try:
                # Extrahiere die Bildnummer
                index = int(command.split()[-1]) - 1
                jump_to_image(index)
            except ValueError:
                print("Ungültige Eingabe für Bildnummer.")
        elif best_match == "ausschalten":
            shutdown()
    else:
        print(f"Unbekannter Befehl: {command}")

def slideshow_thread():
    global running, paused, images, current_speed, current_image, current_index
    screen_width, screen_height = 800, 480
    cv2.namedWindow("Digitaler Bilderrahmen", cv2.WND_PROP_FULLSCREEN)
    cv2.setWindowProperty("Digitaler Bilderrahmen", cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

    while running:
        if not images:
            print("Keine Bilder im Ordner gefunden.")
            break

        if not paused:
            current_image = images[current_index]
            image = cv2.imread(current_image)
            resized_image = resize_and_center_image(image, screen_width, screen_height)
            cv2.imshow("Digitaler Bilderrahmen", resized_image)
            current_index = (current_index + 1) % len(images)

        key = cv2.waitKey(100 if paused else current_speed * 1000)
        if key == ord('q'):
            running = False
            break

    cv2.destroyAllWindows()

def voice_control_thread():
    global running
    while running:
        try:
            if listen_for_command():
                print("Erkennungswort erkannt! Warte auf den Befehl...")
                command = listen_for_following_command()
                if command:
                    execute_command(command)
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
