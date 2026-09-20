#!/usr/bin/env python3
"""
Auto Spotify - surveillance + commandes clavier + icône barre d'état.

Commandes (terminal) :
  help      Affiche les commandes
  status    Affiche l'état de Spotify
  play      Lecture
  pause     Pause
  toggle    Lecture / pause
  next      Morceau suivant
  prev      Morceau précédent
  restart   Redémarre Spotify
  stop      Arrête le programme

Une icône est également ajoutée dans la barre d'état système (system tray)
avec un menu proposant les mêmes actions.

Dépendances supplémentaires :
    pip install pystray pillow

Remarque (GNOME) : GNOME Shell n'affiche pas nativement les icônes
"system tray" / AppIndicator. Il faut installer l'extension
"AppIndicator and KStatusNotifierItem Support" (extensions.gnome.org)
pour que l'icône apparaisse dans la barre du haut. Sous KDE, XFCE,
Cinnamon, MATE, etc. ça fonctionne nativement.
"""

import shutil
import subprocess
import threading
import time

try:
    import pystray
    from pystray import MenuItem as Item
    from PIL import Image, ImageDraw
    TRAY_AVAILABLE = True
except ImportError:
    TRAY_AVAILABLE = False

CHECK_INTERVAL = 0.5
AD_CONFIRMATION_TIME = 2
SPOTIFY_PLAYER = "spotify"

stop_event = threading.Event()
state_lock = threading.Lock()
last_song = None
ad_start = None

tray_icon = None  # instance pystray.Icon, assignée dans main()


def run_command(*args, check=False):
    """Exécute une commande et retourne CompletedProcess."""
    return subprocess.run(
        list(args),
        capture_output=True,
        text=True,
        check=check,
    )


def playerctl(*args):
    """Exécute playerctl pour Spotify."""
    return run_command("playerctl", "-p", SPOTIFY_PLAYER, *args)


def wait_for_player_and_play(timeout=20, poll_interval=0.5):
    """
    Attend que l'interface MPRIS de Spotify soit disponible (le lancement de
    l'appli ne veut pas dire que playerctl peut déjà lui parler), puis lance
    la lecture automatiquement. C'est ce qui donne l'impression que la pub
    a été "skippée" dès l'ouverture.
    """
    deadline = time.time() + timeout

    while time.time() < deadline:
        if stop_event.is_set():
            return

        result = playerctl("play")
        if result.returncode == 0:
            print("▶️ Lecture lancée automatiquement.")
            return

        time.sleep(poll_interval)

    print("⚠️ Spotify n'a pas répondu à temps, lecture automatique annulée.")


def start_spotify():
    """Lance Spotify s'il n'est pas déjà actif, puis démarre la lecture."""
    try:
        result = subprocess.run(
            ["pgrep", "-x", "spotify"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

        if result.returncode == 0:
            print("🎵 Spotify est déjà ouvert.")
            return

        print("🚀 Lancement de Spotify...")
        subprocess.Popen(
            ["spotify-launcher"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

        print("⏳ Attente du démarrage de Spotify...")
        print("▶️ Démarrage automatique de la lecture...")
        wait_for_player_and_play()
        print("✅ Spotify lancé !")
        print()

    except FileNotFoundError:
        print("❌ Impossible de lancer Spotify : 'spotify-launcher' est introuvable.")
        print("   Vérifie que Spotify est installé et que spotify-launcher est disponible.")
    except Exception as e:
        print(f"❌ Erreur lors du lancement de Spotify : {e}")


def get_metadata():
    try:
        result = playerctl(
            "metadata",
            "--format",
            "{{title}}|{{artist}}|{{album}}|{{status}}",
        )

        if result.returncode != 0:
            return None

        parts = result.stdout.strip().split("|", 3)
        if len(parts) != 4:
            return None

        title, artist, album, status = parts
        return {
            "title": title.strip(),
            "artist": artist.strip(),
            "album": album.strip(),
            "status": status.strip().lower(),
        }

    except (OSError, subprocess.SubprocessError):
        return None


def get_status():
    data = get_metadata()
    if data is None:
        return "Spotify non disponible ou playerctl ne répond pas."

    title = data["title"] or "Inconnu"
    artist = data["artist"] or "Inconnu"
    album = data["album"] or "Inconnu"

    return (
        f"État : {data['status']}\n"
        f"Titre : {title}\n"
        f"Artiste : {artist}\n"
        f"Album : {album}"
    )


def is_ad(data):
    """
    Détection prudente :
    - Spotify doit être en lecture
    - l'artiste OU l'album est vide
    """
    if data is None or data["status"] != "playing":
        return False

    return data["artist"] == "" or data["album"] == ""


def restart_spotify():
    print("\n📢 Publicité détectée / redémarrage demandé.")
    print("🔴 Fermeture de Spotify...")

    subprocess.run(
        ["pkill", "-x", "spotify"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    time.sleep(2)

    launcher = shutil.which("spotify-launcher") or shutil.which("spotify")
    if not launcher:
        print("❌ Impossible de trouver spotify-launcher ou spotify.")
        return

    print("🟢 Relancement de Spotify...")
    try:
        subprocess.Popen(
            [launcher],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        print("⏳ Attente du démarrage de Spotify...")
        print("▶️ Reprise automatique de la lecture...")
        wait_for_player_and_play()
        print("✅ Spotify relancé !\n")
    except OSError as exc:
        print(f"❌ Erreur lors du lancement : {exc}")


def print_help():
    print(
        """
╭──────────────── Commandes ────────────────╮
│ help / h       Afficher cette aide        │
│ status / s     État du morceau            │
│ play           Lire                       │
│ pause          Mettre en pause            │
│ toggle         Lecture / pause            │
│ next / n       Morceau suivant            │
│ prev / p       Morceau précédent          │
│ restart / r    Redémarrer Spotify         │
│ stop / quit    Arrêter le programme       │
╰───────────────────────────────────────────╯
"""
    )


def execute_command(command):
    command = command.strip().lower()

    if not command:
        return

    if command in {"help", "h", "?"}:
        print_help()
    elif command in {"status", "s"}:
        print("\n" + get_status() + "\n")
    elif command == "play":
        playerctl("play")
        print("▶️ Lecture")
    elif command == "pause":
        playerctl("pause")
        print("⏸️ Pause")
    elif command == "toggle":
        playerctl("play-pause")
        print("⏯️ Lecture / pause")
    elif command in {"next", "n"}:
        playerctl("next")
        print("⏭️ Morceau suivant")
    elif command in {"prev", "p"}:
        playerctl("previous")
        print("⏮️ Morceau précédent")
    elif command in {"restart", "r"}:
        restart_spotify()
    elif command in {"stop", "quit", "exit"}:
        print("👋 Arrêt demandé.")
        request_shutdown()
    else:
        print(f"❓ Commande inconnue : {command}. Tape 'help'.")


def command_loop():
    """Lit les commandes sans bloquer la surveillance."""
    print("💻 Tape 'help' pour voir les commandes.\n")

    while not stop_event.is_set():
        try:
            command = input("spotify> ")
        except (EOFError, KeyboardInterrupt):
            request_shutdown()
            break

        execute_command(command)


def monitor_loop():
    global last_song, ad_start

    while not stop_event.is_set():
        data = get_metadata()

        if data is None:
            time.sleep(CHECK_INTERVAL)
            continue

        status = data["status"]

        if is_ad(data):
            if ad_start is None:
                ad_start = time.time()
                print("⚠️ Publicité potentielle détectée...")
            elif time.time() - ad_start >= AD_CONFIRMATION_TIME:
                restart_spotify()
                ad_start = None
                last_song = None
                refresh_tray()
        else:
            ad_start = None

            current_song = (
                data["title"],
                data["artist"],
                data["album"],
            )

            if current_song != last_song:
                print(
                    "\n🎵 NOUVELLE MUSIQUE\n"
                    f"   🎶 {data['title'] or 'Inconnu'}\n"
                    f"   👤 {data['artist'] or 'Inconnu'}\n"
                    f"   💿 {data['album'] or 'Inconnu'}\n"
                    f"   ▶️ {status.capitalize()}\n"
                )
                last_song = current_song
                refresh_tray()

        time.sleep(CHECK_INTERVAL)


def request_shutdown():
    """Arrête proprement la surveillance, la boucle de commandes et l'icône tray."""
    stop_event.set()
    if tray_icon is not None:
        try:
            tray_icon.stop()
        except Exception:
            pass


# --------------------------------------------------------------------------
# Icône barre d'état système (system tray)
# --------------------------------------------------------------------------

def make_icon_image():
    """Dessine une petite icône ronde verte façon 'Spotify' avec une note."""
    size = 64
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    # Cercle vert de fond
    draw.ellipse((2, 2, size - 2, size - 2), fill=(30, 215, 96, 255))

    # Trois arcs blancs façon logo Spotify
    for i, y in enumerate((22, 32, 42)):
        offset = i * 3
        draw.arc(
            (14 + offset, y - 6, size - 14 - offset, y + 10),
            start=200,
            end=340,
            fill=(255, 255, 255, 255),
            width=4,
        )

    return image


def tray_action(func):
    """Petit wrapper pour lancer une action tray sans bloquer le thread de l'icône."""
    def handler(icon, item):
        threading.Thread(target=func, daemon=True).start()
    return handler


def build_menu():
    """Construit dynamiquement le menu (en-tête = morceau en cours)."""
    data = get_metadata()
    if data:
        title = data["title"] or "Inconnu"
        artist = data["artist"] or "Inconnu"
        header = f"{title} — {artist}" if title != "Inconnu" else "Spotify"
        state = data["status"].capitalize()
    else:
        header = "Spotify (indisponible)"
        state = "—"

    return pystray.Menu(
        Item(header, None, enabled=False),
        Item(state, None, enabled=False),
        pystray.Menu.SEPARATOR,
        Item("▶️ Lecture", tray_action(lambda: playerctl("play"))),
        Item("⏸️ Pause", tray_action(lambda: playerctl("pause"))),
        Item("⏯️ Lecture / Pause", tray_action(lambda: playerctl("play-pause"))),
        Item("⏭️ Suivant", tray_action(lambda: playerctl("next"))),
        Item("⏮️ Précédent", tray_action(lambda: playerctl("previous"))),
        pystray.Menu.SEPARATOR,
        Item("🔁 Redémarrer Spotify", tray_action(restart_spotify)),
        pystray.Menu.SEPARATOR,
        Item("❌ Quitter", tray_action(request_shutdown)),
    )


def refresh_tray():
    """À appeler après un changement d'état pour rafraîchir le menu/titre de l'icône."""
    if tray_icon is None:
        return
    try:
        data = get_metadata()
        if data and data["title"]:
            tray_icon.title = f"{data['title']} — {data['artist'] or 'Inconnu'}"
        else:
            tray_icon.title = "Auto Spotify"
        tray_icon.menu = build_menu()
    except Exception:
        pass


def build_tray_icon():
    """Crée (sans le démarrer) l'objet pystray.Icon."""
    image = make_icon_image()
    icon = pystray.Icon(
        "auto-spotify",
        icon=image,
        title="Auto Spotify",
        menu=build_menu(),
    )
    return icon


def main():
    global tray_icon

    if shutil.which("playerctl") is None:
        print("❌ playerctl n'est pas installé ou absent du PATH.")
        print("Installe playerctl puis relance le programme.")
        return 1

    start_spotify()

    print("🎵 Auto Spotify démarré")
    print("🔎 Surveillance de Spotify...")
    print("🛑 Ctrl+C (ou 'stop') pour arrêter.")

    monitor = threading.Thread(target=monitor_loop, daemon=True)
    monitor.start()

    cmd_thread = threading.Thread(target=command_loop, daemon=True)
    cmd_thread.start()

    if TRAY_AVAILABLE:
        tray_icon = build_tray_icon()
        try:
            # icon.run() bloque et doit tourner sur le thread principal.
            tray_icon.run()
        finally:
            stop_event.set()
    else:
        print(
            "\n⚠️ Icône de barre d'état désactivée : installe les dépendances avec\n"
            "   pip install pystray pillow\n"
        )
        try:
            while not stop_event.is_set():
                time.sleep(0.5)
        except KeyboardInterrupt:
            stop_event.set()

    stop_event.set()
    monitor.join(timeout=1)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
