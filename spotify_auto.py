#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
===========================================================
                    AUTO SPOTIFY v3
                 CachyOS / Arch Linux
===========================================================

Fonctions :
- Installation automatique des dépendances Arch/CachyOS
- Environnement Python virtuel automatique
- Installation pystray + Pillow
- Détection du vrai processus principal Spotify
- Fermeture des instances Spotify supplémentaires
- Détection MPRIS dynamique
- Détection des publicités via métadonnées
- Redémarrage automatique de Spotify
- Passage au morceau suivant
- Icône tray
- Interface terminal

Lancement :
    python3 spotify_auto.py

Commandes terminal :
    status
    debug
    instances
    tree
    play
    pause
    next
    previous
    restart
    quit
===========================================================
"""

import os
import sys
import time
import signal
import subprocess
import shutil
import importlib.util
from pathlib import Path


# =========================================================
# CONFIGURATION
# =========================================================

APP_NAME = "Auto Spotify"

CHECK_INTERVAL = 0.5
AD_CONFIRMATION_TIME = 2.0

PLAYER_TIMEOUT = 30.0
NEXT_DELAY = 0.8

LAUNCH_RETRIES = 3
LAUNCH_WAIT = 2.0

PLAYER_NAME_HINT = "spotify"

AUTO_INSTALL = True

# Répertoire utilisé pour l'environnement Python
APP_DIR = Path.home() / ".local" / "share" / "auto-spotify"
VENV_DIR = APP_DIR / "venv"

# Paquets Arch nécessaires
ARCH_PACKAGES = [
    "playerctl",
    "procps-ng",
    "appmenu-gtk-module",
]

# Paquets Python
PYTHON_PACKAGES = [
    "pystray",
    "Pillow",
]


# =========================================================
# ÉTAT GLOBAL
# =========================================================

running = True

spotify_pid = None
spotify_player = None

last_title = ""
last_artist = ""
last_album = ""

ad_since = None
last_ad_action = 0

tray_icon = None


# =========================================================
# UTILITAIRES
# =========================================================

def log(message):
    print(message, flush=True)


def command_exists(command):
    return shutil.which(command) is not None


def run_command(
    command,
    capture_output=True,
    check=False,
    timeout=None,
):
    try:
        return subprocess.run(
            command,
            text=True,
            capture_output=capture_output,
            check=check,
            timeout=timeout,
        )
    except Exception:
        return None


def command_output(command, timeout=5):
    result = run_command(
        command,
        capture_output=True,
        check=False,
        timeout=timeout,
    )

    if result is None:
        return ""

    if result.returncode != 0:
        return ""

    return result.stdout.strip()


# =========================================================
# DÉTECTION DISTRIBUTION
# =========================================================

def detect_distribution():
    """
    Retourne :
        arch
        debian
        unknown
    """

    if Path("/etc/arch-release").exists():
        return "arch"

    os_release = Path("/etc/os-release")

    if os_release.exists():
        try:
            data = os_release.read_text(
                encoding="utf-8",
                errors="ignore",
            ).lower()

            if (
                "id=cachyos" in data
                or "id=arch" in data
                or "id_like=arch" in data
            ):
                return "arch"

            if (
                "id=ubuntu" in data
                or "id=debian" in data
                or "id_like=debian" in data
            ):
                return "debian"

        except Exception:
            pass

    if command_exists("pacman"):
        return "arch"

    if command_exists("apt-get"):
        return "debian"

    return "unknown"


# =========================================================
# INSTALLATION PACMAN
# =========================================================

def install_arch_packages(packages):
    """
    Installe les paquets Arch/CachyOS manquants.
    """

    if not packages:
        return True

    if not command_exists("pacman"):
        log("[ERROR] pacman est introuvable.")
        return False

    if os.geteuid() == 0:
        pacman_prefix = []
    else:
        if not command_exists("sudo"):
            log("[ERROR] sudo est nécessaire pour installer les paquets.")
            return False

        pacman_prefix = ["sudo"]

    log("")
    log("========================================")
    log(" INSTALLATION DES PAQUETS ARCH/CACHYOS")
    log("========================================")

    log("[PACMAN] Paquets manquants :")
    for package in packages:
        log(f"         - {package}")

    log("")

    # Mise à jour de la base uniquement si nécessaire
    log("[PACMAN] Actualisation de la base des paquets...")

    update_command = pacman_prefix + [
        "pacman",
        "-Sy",
        "--noconfirm",
    ]

    result = run_command(
        update_command,
        capture_output=False,
        check=False,
        timeout=300,
    )

    if result is None or result.returncode != 0:
        log("[WARN] Impossible d'actualiser la base pacman.")

    install_command = pacman_prefix + [
        "pacman",
        "-S",
        "--needed",
        "--noconfirm",
    ] + packages

    log("[PACMAN] Installation...")

    result = run_command(
        install_command,
        capture_output=False,
        check=False,
        timeout=600,
    )

    if result is None or result.returncode != 0:
        log("[ERROR] Échec de l'installation pacman.")
        return False

    log("[PACMAN] Installation terminée.")
    return True


# =========================================================
# VÉRIFICATION D'UNE COMMANDE
# =========================================================

def ensure_system_dependencies():
    """
    Vérifie les dépendances système.

    CachyOS/Arch :
        playerctl
        procps-ng
        appmenu-gtk-module
    """

    distro = detect_distribution()

    log(f"[INIT] Distribution détectée : {distro}")

    if distro != "arch":
        log(
            "[WARN] Ce fichier est principalement prévu "
            "pour CachyOS/Arch Linux."
        )

    missing = []

    # playerctl
    if not command_exists("playerctl"):
        missing.append("playerctl")

    # ps fourni par procps-ng
    if not command_exists("ps"):
        missing.append("procps-ng")

    # Module GTK demandé
    #
    # On ne peut pas toujours vérifier directement si le module
    # est chargé, donc on vérifie simplement le paquet avec pacman.
    if distro == "arch" and command_exists("pacman"):
        result = run_command(
            [
                "pacman",
                "-Q",
                "appmenu-gtk-module",
            ],
            capture_output=True,
            check=False,
        )

        if result is None or result.returncode != 0:
            missing.append("appmenu-gtk-module")

    if not missing:
        log("[INIT] Dépendances système : OK")
        return True

    if not AUTO_INSTALL:
        log("[ERROR] Dépendances manquantes.")
        for package in missing:
            log(f"        - {package}")
        return False

    if distro == "arch":
        return install_arch_packages(missing)

    log(
        "[ERROR] Distribution non supportée pour "
        "l'installation automatique."
    )

    return False


# =========================================================
# PYTHON / VENV
# =========================================================

def inside_virtualenv():
    return (
        hasattr(sys, "real_prefix")
        or sys.prefix != getattr(sys, "base_prefix", sys.prefix)
    )


def python_module_available(module_name):
    try:
        return importlib.util.find_spec(module_name) is not None
    except Exception:
        return False


def python_dependencies_missing():
    missing = []

    if not python_module_available("pystray"):
        missing.append("pystray")

    if not python_module_available("PIL"):
        missing.append("Pillow")

    return missing


def create_virtualenv():
    """
    Crée le venv Auto Spotify.
    """

    APP_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    if VENV_DIR.exists():
        return True

    log("")
    log("========================================")
    log(" CRÉATION DE L'ENVIRONNEMENT PYTHON")
    log("========================================")

    log(f"[PYTHON] Venv : {VENV_DIR}")

    result = run_command(
        [
            sys.executable,
            "-m",
            "venv",
            str(VENV_DIR),
        ],
        capture_output=False,
        check=False,
        timeout=300,
    )

    if result is None or result.returncode != 0:
        log("[ERROR] Impossible de créer le venv.")
        return False

    log("[PYTHON] Venv créé.")
    return True


def venv_python():
    if os.name == "nt":
        return VENV_DIR / "Scripts" / "python.exe"

    return VENV_DIR / "bin" / "python"


def install_python_packages(python_executable, packages):
    if not packages:
        return True

    log("")
    log("========================================")
    log(" INSTALLATION DES MODULES PYTHON")
    log("========================================")

    log("[PYTHON] Modules :")

    for package in packages:
        log(f"         - {package}")

    log("")

    # Mettre pip à jour si possible
    run_command(
        [
            str(python_executable),
            "-m",
            "pip",
            "install",
            "--upgrade",
            "pip",
        ],
        capture_output=False,
        check=False,
        timeout=300,
    )

    result = run_command(
        [
            str(python_executable),
            "-m",
            "pip",
            "install",
            *packages,
        ],
        capture_output=False,
        check=False,
        timeout=600,
    )

    if result is None or result.returncode != 0:
        log("[ERROR] Échec de l'installation Python.")
        return False

    log("[PYTHON] Modules installés.")
    return True


def ensure_python_dependencies():
    """
    Sur CachyOS/Arch, on utilise un venv afin d'éviter les problèmes
    PEP 668 / externally-managed-environment.
    """

    missing = python_dependencies_missing()

    if not missing:
        log("[INIT] Modules Python : OK")
        return True

    log("[INIT] Modules Python manquants :")
    for module in missing:
        log(f"       - {module}")

    if not AUTO_INSTALL:
        return False

    # Si on est déjà dans le venv, installation directe
    if inside_virtualenv():
        return install_python_packages(
            Path(sys.executable),
            missing,
        )

    # Création du venv
    if not create_virtualenv():
        return False

    python_exec = venv_python()

    if not python_exec.exists():
        log("[ERROR] Python du venv introuvable.")
        return False

    # Installation dans le venv
    if not install_python_packages(
        python_exec,
        missing,
    ):
        return False

    # Relancer le script dans le venv
    log("")
    log("[PYTHON] Redémarrage d'Auto Spotify dans le venv...")
    log("")

    try:
        os.execv(
            str(python_exec),
            [
                str(python_exec),
                str(Path(__file__).resolve()),
                *sys.argv[1:],
            ],
        )
    except Exception as exc:
        log(f"[ERROR] Impossible de relancer le script : {exc}")
        return False

    return True


# =========================================================
# IMPORTS OPTIONNELS APRÈS INSTALLATION
# =========================================================

def load_tray_modules():
    try:
        import pystray
        from PIL import Image, ImageDraw

        return pystray, Image, ImageDraw

    except ImportError:
        return None, None, None


# =========================================================
# PROCESSUS
# =========================================================

def get_process_list():
    """
    Retourne une liste :

        [
            {
                pid,
                ppid,
                pgid,
                command,
            }
        ]
    """

    result = run_command(
        [
            "ps",
            "-eo",
            "pid=,ppid=,pgid=,args=",
        ],
        capture_output=True,
        check=False,
        timeout=5,
    )

    if result is None or result.returncode != 0:
        return []

    processes = []

    for line in result.stdout.splitlines():
        line = line.strip()

        if not line:
            continue

        parts = line.split(None, 3)

        if len(parts) < 4:
            continue

        try:
            pid = int(parts[0])
            ppid = int(parts[1])
            pgid = int(parts[2])
            command = parts[3]
        except ValueError:
            continue

        processes.append(
            {
                "pid": pid,
                "ppid": ppid,
                "pgid": pgid,
                "command": command,
            }
        )

    return processes


def is_real_spotify_process(command):
    """
    Détecte uniquement le processus principal Spotify.

    Les processus Electron/Chromium enfants utilisent également
    le binaire spotify, mais contiennent généralement :

        --type=renderer
        --type=gpu-process
        --type=utility
        --type=zygote
        etc.

    Ils ne doivent PAS être comptés comme des instances.
    """

    if not command:
        return False

    command_lower = command.lower()

    # Le dernier exécutable du début de la ligne
    executable = command.split()[0]

    executable_name = os.path.basename(executable)

    if executable_name != "spotify":
        return False

    # Processus Electron enfants
    child_markers = [
        "--type=",
        "--utility-sub-type=",
        "--renderer-client-id=",
        "--gpu-preferences=",
        "--shared-files",
    ]

    for marker in child_markers:
        if marker in command_lower:
            return False

    return True


def get_spotify_main_processes():
    processes = get_process_list()

    result = []

    for process in processes:
        if is_real_spotify_process(
            process["command"]
        ):
            result.append(process)

    return sorted(
        result,
        key=lambda item: item["pid"],
    )


def get_process_tree(root_pid):
    """
    Retourne tous les descendants du PID.
    """

    processes = get_process_list()

    children = {}

    for process in processes:
        children.setdefault(
            process["ppid"],
            [],
        ).append(process)

    result = []
    queue = [root_pid]
    visited = set()

    while queue:
        pid = queue.pop(0)

        if pid in visited:
            continue

        visited.add(pid)

        for child in children.get(pid, []):
            result.append(child)
            queue.append(child["pid"])

    return result


def process_exists(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except Exception:
        return False


def terminate_pid(pid, name="processus"):
    if not process_exists(pid):
        return

    log(
        f"[PROCESS] Fermeture {name} PID={pid}"
    )

    try:
        os.kill(pid, signal.SIGTERM)
    except Exception as exc:
        log(
            f"[WARN] SIGTERM PID={pid}: {exc}"
        )


def kill_pid(pid):
    if not process_exists(pid):
        return

    try:
        os.kill(pid, signal.SIGKILL)
    except Exception:
        pass


def terminate_process_tree(root_pid):
    """
    Ferme les descendants puis le processus principal.
    """

    descendants = get_process_tree(root_pid)

    # Fermer les enfants d'abord
    for process in reversed(descendants):
        terminate_pid(
            process["pid"],
            "processus Spotify enfant",
        )

    terminate_pid(
        root_pid,
        "instance Spotify",
    )

    deadline = time.time() + 3.0

    while time.time() < deadline:
        if not process_exists(root_pid):
            return

        time.sleep(0.1)

    if process_exists(root_pid):
        log(
            f"[PROCESS] PID {root_pid} encore présent -> SIGKILL"
        )

        # Kill descendants
        descendants = get_process_tree(root_pid)

        for process in descendants:
            kill_pid(process["pid"])

        kill_pid(root_pid)


# =========================================================
# GESTION DES INSTANCES
# =========================================================

def choose_instance_to_keep(instances):
    if not instances:
        return None

    # Si une instance correspond au lecteur MPRIS actuel,
    # on essaie de conserver son PID.
    if spotify_pid:
        for process in instances:
            if process["pid"] == spotify_pid:
                return process

    # Sinon, conserver la première instance.
    return instances[0]


def close_extra_spotify_instances():
    global spotify_pid

    instances = get_spotify_main_processes()

    if not instances:
        spotify_pid = None
        return None

    log(
        f"[SPOTIFY] {len(instances)} instance(s) principale(s) détectée(s)."
    )

    keep = choose_instance_to_keep(instances)

    if keep is None:
        return None

    spotify_pid = keep["pid"]

    log(
        f"[SPOTIFY] Instance conservée : "
        f"PID {spotify_pid}"
    )

    for process in instances:
        if process["pid"] == keep["pid"]:
            continue

        log(
            "[INSTANCE] Fermeture de l'instance "
            f"supplémentaire PID={process['pid']}"
        )

        terminate_process_tree(
            process["pid"]
        )

    return spotify_pid


def kill_all_spotify_instances():
    global spotify_pid

    instances = get_spotify_main_processes()

    if not instances:
        spotify_pid = None
        return

    log(
        f"[SPOTIFY] Fermeture de "
        f"{len(instances)} instance(s)."
    )

    for process in instances:
        terminate_process_tree(
            process["pid"]
        )

    spotify_pid = None


# =========================================================
# RECHERCHE DE SPOTIFY
# =========================================================

def find_spotify_binary():
    candidates = []

    # PATH
    spotify_path = shutil.which("spotify")

    if spotify_path:
        candidates.append(
            Path(spotify_path)
        )

    # Spotify Launcher
    candidates.extend(
        [
            Path.home()
            / ".local/share/spotify-launcher/install/usr/share/spotify/spotify",

            Path.home()
            / ".local/share/spotify-launcher/install/usr/bin/spotify",

            Path.home()
            / ".local/bin/spotify",

            Path("/opt/spotify/spotify"),

            Path("/usr/share/spotify/spotify"),

            Path("/usr/lib/spotify/spotify"),
        ]
    )

    for candidate in candidates:
        try:
            if candidate.is_file() and os.access(
                candidate,
                os.X_OK,
            ):
                return str(candidate)
        except Exception:
            pass

    return None


def find_spotify_launcher():
    candidates = [
        shutil.which("spotify-launcher"),
        str(
            Path.home()
            / ".local/bin/spotify-launcher"
        ),
    ]

    for candidate in candidates:
        if not candidate:
            continue

        path = Path(candidate)

        if path.exists() and os.access(
            path,
            os.X_OK,
        ):
            return str(path)

    return None


def detect_spotify_installation():
    """
    Retourne :

        (type_installation, commande)

    """

    # Binaire Spotify
    binary = find_spotify_binary()

    if binary:
        return "binary", binary

    # spotify-launcher
    launcher = find_spotify_launcher()

    if launcher:
        return "launcher", launcher

    # Snap
    if command_exists("snap"):
        result = run_command(
            [
                "snap",
                "list",
                "spotify",
            ],
            capture_output=True,
            check=False,
        )

        if result and result.returncode == 0:
            return "snap", "spotify"

    # Flatpak
    if command_exists("flatpak"):
        result = run_command(
            [
                "flatpak",
                "info",
                "com.spotify.Client",
            ],
            capture_output=True,
            check=False,
        )

        if result and result.returncode == 0:
            return "flatpak", "com.spotify.Client"

    return None, None


# =========================================================
# LANCEMENT SPOTIFY
# =========================================================

def launch_spotify():
    global spotify_pid

    installation, command = (
        detect_spotify_installation()
    )

    if not command:
        log(
            "[ERROR] Spotify introuvable."
        )

        log(
            "[INFO] Installations recherchées :"
        )
        log(
            "       - Spotify natif"
        )
        log(
            "       - spotify-launcher"
        )
        log(
            "       - Snap"
        )
        log(
            "       - Flatpak"
        )

        return False

    log(
        f"[SPOTIFY] Installation : "
        f"{installation}"
    )

    log(
        f"[SPOTIFY] Commande : "
        f"{command}"
    )

    for attempt in range(
        1,
        LAUNCH_RETRIES + 1,
    ):
        log(
            f"[SPOTIFY] Lancement "
            f"{attempt}/{LAUNCH_RETRIES}..."
        )

        try:
            if installation == "flatpak":
                process = subprocess.Popen(
                    [
                        "flatpak",
                        "run",
                        command,
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )

            elif installation == "snap":
                process = subprocess.Popen(
                    [
                        "snap",
                        "run",
                        "spotify",
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )

            else:
                process = subprocess.Popen(
                    [command],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )

            time.sleep(LAUNCH_WAIT)

            # Rechercher le vrai processus Spotify
            instances = (
                get_spotify_main_processes()
            )

            if instances:
                keep = choose_instance_to_keep(
                    instances
                )

                if keep:
                    spotify_pid = keep["pid"]

                    log(
                        f"[SPOTIFY] PID principal : "
                        f"{spotify_pid}"
                    )

                    close_extra_spotify_instances()

                    return True

            # Le processus lancé existe peut-être
            if process.poll() is None:
                log(
                    "[SPOTIFY] Processus lancé, "
                    "attente de l'initialisation..."
                )

        except Exception as exc:
            log(
                f"[ERROR] Lancement Spotify : "
                f"{exc}"
            )

        time.sleep(1)

    log(
        "[ERROR] Impossible de lancer Spotify."
    )

    return False


def ensure_spotify_running():
    global spotify_pid

    instances = get_spotify_main_processes()

    if instances:
        spotify_pid = (
            close_extra_spotify_instances()
        )

        return spotify_pid is not None

    spotify_pid = None

    return launch_spotify()


# =========================================================
# MPRIS / PLAYERCTL
# =========================================================

def get_player_list():
    output = command_output(
        [
            "playerctl",
            "-l",
        ]
    )

    if not output:
        return []

    return [
        line.strip()
        for line in output.splitlines()
        if line.strip()
    ]


def find_mpris_spotify():
    players = get_player_list()

    if not players:
        return None

    # Priorité à un nom exactement spotify
    for player in players:
        if player.lower() == "spotify":
            return player

    # Puis spotify.instance-xxxx
    for player in players:
        if "spotify" in player.lower():
            return player

    return None


def wait_for_mpris(timeout=PLAYER_TIMEOUT):
    global spotify_player

    start = time.time()

    while time.time() - start < timeout:
        player = find_mpris_spotify()

        if player:
            spotify_player = player

            log(
                f"[MPRIS] Lecteur détecté : "
                f"{spotify_player}"
            )

            return player

        time.sleep(0.5)

    log(
        "[MPRIS] Aucun lecteur Spotify détecté."
    )

    return None


def playerctl_command(arguments):
    global spotify_player

    player = spotify_player

    # Si le lecteur actuel n'existe plus,
    # recherche dynamique.
    if not player:
        player = find_mpris_spotify()

    if not player:
        return None

    result = run_command(
        [
            "playerctl",
            "-p",
            player,
            *arguments,
        ],
        capture_output=True,
        check=False,
        timeout=5,
    )

    if result is None:
        return None

    if result.returncode != 0:
        # Le lecteur a peut-être changé de nom.
        new_player = find_mpris_spotify()

        if new_player and new_player != player:
            spotify_player = new_player

            result = run_command(
                [
                    "playerctl",
                    "-p",
                    new_player,
                    *arguments,
                ],
                capture_output=True,
                check=False,
                timeout=5,
            )

    return result


def get_status():
    result = playerctl_command(
        [
            "status",
        ]
    )

    if result is None:
        return ""

    if result.returncode != 0:
        return ""

    return result.stdout.strip().lower()


def get_metadata():
    result = playerctl_command(
        [
            "metadata",
            "--format",
            "{{title}}|{{artist}}|{{album}}",
        ]
    )

    if result is None:
        return "", "", ""

    if result.returncode != 0:
        return "", "", ""

    line = result.stdout.strip()

    parts = line.split("|")

    while len(parts) < 3:
        parts.append("")

    title = parts[0].strip()
    artist = parts[1].strip()
    album = parts[2].strip()

    return title, artist, album


def player_play():
    playerctl_command(["play"])


def player_pause():
    playerctl_command(["pause"])


def player_next():
    playerctl_command(["next"])


def player_previous():
    playerctl_command(["previous"])


# =========================================================
# REDÉMARRAGE
# =========================================================

def restart_spotify():
    global spotify_player
    global ad_since

    log("")
    log("========================================")
    log("       REDÉMARRAGE DE SPOTIFY")
    log("========================================")

    ad_since = None

    kill_all_spotify_instances()

    spotify_player = None

    time.sleep(1)

    if not launch_spotify():
        log(
            "[ERROR] Échec du redémarrage."
        )
        return False

    wait_for_mpris()

    time.sleep(NEXT_DELAY)

    player_next()

    time.sleep(0.5)

    player_play()

    log("[SPOTIFY] Redémarrage terminé.")

    return True


# =========================================================
# DÉTECTION DES PUBLICITÉS
# =========================================================

def is_possible_ad(status, title, artist, album):
    """
    Une publicité Spotify peut apparaître avec des métadonnées
    incomplètes.

    On ne considère pas une pause comme une publicité.
    """

    if status != "playing":
        return False

    # Aucun titre -> potentiellement pub
    if not title:
        return True

    # Artiste ou album manquant
    if not artist or not album:
        return True

    return False


def check_for_ad():
    global ad_since
    global last_ad_action

    status = get_status()

    title, artist, album = get_metadata()

    # Affichage debug uniquement si changement
    global last_title
    global last_artist
    global last_album

    if (
        title != last_title
        or artist != last_artist
        or album != last_album
    ):
        last_title = title
        last_artist = artist
        last_album = album

        if status == "playing":
            log(
                "[TRACK] "
                f"{title or '(sans titre)'}"
                " | "
                f"{artist or '(sans artiste)'}"
                " | "
                f"{album or '(sans album)'}"
            )

    if not is_possible_ad(
        status,
        title,
        artist,
        album,
    ):
        ad_since = None
        return False

    now = time.time()

    if ad_since is None:
        ad_since = now

        log(
            "[AD] Métadonnées suspectes détectées..."
        )

        return False

    elapsed = now - ad_since

    if elapsed < AD_CONFIRMATION_TIME:
        return False

    # Éviter une répétition immédiate
    if now - last_ad_action < 5:
        return False

    last_ad_action = now

    log(
        "[AD] Publicité confirmée."
    )

    restart_spotify()

    ad_since = None

    return True


# =========================================================
# SURVEILLANCE DES INSTANCES
# =========================================================

def monitor_instances():
    global spotify_pid

    instances = get_spotify_main_processes()

    if not instances:
        # Spotify peut être momentanément en cours
        # de lancement.
        if spotify_pid is not None:
            log(
                "[SPOTIFY] Instance principale disparue."
            )

            spotify_pid = None

        return

    keep = choose_instance_to_keep(
        instances
    )

    if keep is None:
        return

    if spotify_pid != keep["pid"]:
        spotify_pid = keep["pid"]

    for process in instances:
        if process["pid"] == spotify_pid:
            continue

        log(
            "[INSTANCE] Nouvelle instance "
            f"supplémentaire : PID={process['pid']}"
        )

        terminate_process_tree(
            process["pid"]
        )


# =========================================================
# TRAY
# =========================================================

def create_tray_image():
    pystray, Image, ImageDraw = (
        load_tray_modules()
    )

    if not pystray:
        return None

    image = Image.new(
        "RGB",
        (64, 64),
        "black",
    )

    draw = ImageDraw.Draw(image)

    draw.ellipse(
        (8, 8, 56, 56),
        fill="white",
    )

    draw.rectangle(
        (28, 15, 36, 42),
        fill="black",
    )

    draw.polygon(
        [
            (36, 18),
            (49, 24),
            (36, 30),
        ],
        fill="black",
    )

    return image


def tray_status(icon, item):
    status = get_status()

    if not status:
        status = "indisponible"

    return f"Spotify : {status}"


def tray_play(icon, item):
    player_play()


def tray_pause(icon, item):
    player_pause()


def tray_next(icon, item):
    player_next()


def tray_restart(icon, item):
    restart_spotify()


def tray_quit(icon, item):
    global running

    running = False

    try:
        icon.stop()
    except Exception:
        pass


def start_tray():
    global tray_icon

    pystray, Image, ImageDraw = (
        load_tray_modules()
    )

    if not pystray:
        log(
            "[TRAY] pystray indisponible."
        )
        return

    image = create_tray_image()

    if image is None:
        return

    menu = pystray.Menu(
        pystray.MenuItem(
            "Spotify : statut",
            tray_status,
            enabled=False,
        ),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(
            "Lecture",
            tray_play,
        ),
        pystray.MenuItem(
            "Pause",
            tray_pause,
        ),
        pystray.MenuItem(
            "Suivant",
            tray_next,
        ),
        pystray.MenuItem(
            "Redémarrer Spotify",
            tray_restart,
        ),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(
            "Quitter",
            tray_quit,
        ),
    )

    tray_icon = pystray.Icon(
        APP_NAME,
        image,
        APP_NAME,
        menu,
    )

    log("[TRAY] Icône système activée.")

    tray_icon.run()


# =========================================================
# COMMANDES TERMINAL
# =========================================================

def print_status():
    instances = get_spotify_main_processes()

    print("")
    print("========================================")
    print("             AUTO SPOTIFY")
    print("========================================")
    print(
        f"PID Spotify : "
        f"{spotify_pid or 'aucun'}"
    )
    print(
        f"MPRIS       : "
        f"{spotify_player or 'aucun'}"
    )
    print(
        f"État        : "
        f"{get_status() or 'inconnu'}"
    )

    title, artist, album = get_metadata()

    print(
        f"Titre       : "
        f"{title or '-'}"
    )

    print(
        f"Artiste     : "
        f"{artist or '-'}"
    )

    print(
        f"Album       : "
        f"{album or '-'}"
    )

    print(
        f"Instances   : "
        f"{len(instances)}"
    )

    print("")


def print_instances():
    instances = get_spotify_main_processes()

    print("")
    print("========================================")
    print("        INSTANCES SPOTIFY")
    print("========================================")

    if not instances:
        print("Aucune instance principale.")
        print("")
        return

    for process in instances:
        print(
            f"PID={process['pid']} "
            f"PPID={process['ppid']} "
            f"PGID={process['pgid']}"
        )

        print(
            f"  {process['command']}"
        )

    print("")


def print_tree():
    instances = get_spotify_main_processes()

    print("")
    print("========================================")
    print("          ARBRE SPOTIFY")
    print("========================================")

    if not instances:
        print("Aucune instance Spotify.")
        print("")
        return

    for process in instances:
        root_pid = process["pid"]

        print("")
        print(
            f"Spotify principal PID={root_pid}"
        )

        descendants = get_process_tree(
            root_pid
        )

        if not descendants:
            print("  └── aucun enfant")
            continue

        for child in descendants:
            print(
                f"  ├── PID={child['pid']} "
                f"PPID={child['ppid']} "
                f"{child['command']}"
            )

    print("")


def print_debug():
    print("")
    print("========================================")
    print("              DEBUG")
    print("========================================")

    print(
        f"playerctl : "
        f"{shutil.which('playerctl')}"
    )

    print(
        f"spotify   : "
        f"{find_spotify_binary()}"
    )

    print(
        f"launcher  : "
        f"{find_spotify_launcher()}"
    )

    print(
        f"players MPRIS : "
        f"{get_player_list()}"
    )

    print(
        f"player MPRIS actuel : "
        f"{spotify_player}"
    )

    print(
        f"PID Spotify : "
        f"{spotify_pid}"
    )

    print("")


def terminal_command(command):
    command = command.strip().lower()

    if command == "":
        return True

    if command == "status":
        print_status()
        return True

    if command == "debug":
        print_debug()
        return True

    if command == "instances":
        print_instances()
        return True

    if command == "tree":
        print_tree()
        return True

    if command == "play":
        player_play()
        return True

    if command == "pause":
        player_pause()
        return True

    if command == "next":
        player_next()
        return True

    if command in (
        "previous",
        "prev",
    ):
        player_previous()
        return True

    if command == "restart":
        restart_spotify()
        return True

    if command in (
        "quit",
        "exit",
        "q",
    ):
        return False

    print(
        "[CMD] Commandes : "
        "status, debug, instances, tree, "
        "play, pause, next, previous, "
        "restart, quit"
    )

    return True


def terminal_loop():
    global running

    while running:
        try:
            command = input(
                "\nAuto Spotify > "
            )

        except EOFError:
            break

        except KeyboardInterrupt:
            print("")
            break

        if not terminal_command(command):
            running = False
            break


# =========================================================
# MONITEUR
# =========================================================

def monitor_loop():
    global running
    global spotify_player
    global spotify_pid

    log("[MONITOR] Surveillance démarrée.")

    last_player_check = 0

    while running:
        try:
            now = time.time()

            # Vérification périodique du lecteur MPRIS
            if (
                spotify_player is None
                or now - last_player_check > 5
            ):
                player = find_mpris_spotify()

                if player:
                    spotify_player = player

                last_player_check = now

            # Vérification des instances Spotify
            monitor_instances()

            # Si Spotify n'est plus lancé, le relancer
            instances = get_spotify_main_processes()

            if not instances:
                if spotify_pid is None:
                    log("[MONITOR] Spotify absent.")

                    if launch_spotify():
                        wait_for_mpris()

            # Détection des publicités
            check_for_ad()

            time.sleep(CHECK_INTERVAL)

        except KeyboardInterrupt:
            running = False
            break

        except Exception as exc:
            log(f"[MONITOR] Erreur : {exc}")
            time.sleep(1)

# =========================================================
# SIGNALS
# =========================================================

def signal_handler(signum, frame):
    global running

    log("")
    log(
        "[SYSTEM] Arrêt demandé."
    )

    running = False


# =========================================================
# MAIN
# =========================================================

def main():
    global spotify_pid
    global spotify_player
    global running

    print("")
    print("========================================")
    print("          AUTO SPOTIFY v3")
    print("        CachyOS / Arch Linux")
    print("========================================")
    print("")

    # -----------------------------------------------------
    # Installation système
    # -----------------------------------------------------

    if not ensure_system_dependencies():
        log("")
        log(
            "[ERROR] Les dépendances système "
            "ne sont pas disponibles."
        )
        sys.exit(1)

    # -----------------------------------------------------
    # Installation Python
    # -----------------------------------------------------

    if not ensure_python_dependencies():
        log("")
        log(
            "[ERROR] Les dépendances Python "
            "ne sont pas disponibles."
        )
        sys.exit(1)

    # -----------------------------------------------------
    # Détection Spotify
    # -----------------------------------------------------

    installation, command = (
        detect_spotify_installation()
    )

    if installation is None:
        log(
            "[ERROR] Spotify n'a pas été trouvé."
        )

        log("")
        log(
            "Installe Spotify ou spotify-launcher "
            "puis relance ce script."
        )

        sys.exit(1)

    log(
        f"[INIT] Installation : "
        f"{installation}"
    )

    log(
        f"[INIT] Commande : "
        f"{command}"
    )

    # -----------------------------------------------------
    # Signaux
    # -----------------------------------------------------

    signal.signal(
        signal.SIGINT,
        signal_handler,
    )

    signal.signal(
        signal.SIGTERM,
        signal_handler,
    )

    # -----------------------------------------------------
    # Instances Spotify
    # -----------------------------------------------------

    instances = get_spotify_main_processes()

    log(
        f"[INIT] {len(instances)} "
        f"instance(s) Spotify détectée(s)."
    )

    if instances:
        spotify_pid = (
            close_extra_spotify_instances()
        )

        log(
            f"[INIT] PID conservé : "
            f"{spotify_pid}"
        )

    else:
        log(
            "[INIT] Aucune instance Spotify."
        )

        launch_spotify()

    # -----------------------------------------------------
    # MPRIS
    # -----------------------------------------------------

    wait_for_mpris()

    # -----------------------------------------------------
    # Tray
    # -----------------------------------------------------

    tray_available = (
        python_module_available("pystray")
    )

    if tray_available:
        import threading

        tray_thread = threading.Thread(
            target=start_tray,
            daemon=True,
        )

        tray_thread.start()

    # -----------------------------------------------------
    # Moniteur
    # -----------------------------------------------------

    import threading

    monitor_thread = threading.Thread(
        target=monitor_loop,
        daemon=True,
    )

    monitor_thread.start()

    # -----------------------------------------------------
    # Terminal
    # -----------------------------------------------------

    log("")
    log(
        "Commandes : "
        "status | debug | instances | tree | "
        "play | pause | next | previous | "
        "restart | quit"
    )

    terminal_loop()

    # -----------------------------------------------------
    # Arrêt
    # -----------------------------------------------------

    running = False

    log("")
    log(
        "[SYSTEM] Auto Spotify arrêté."
    )


# =========================================================
# ENTRY POINT
# =========================================================

if __name__ == "__main__":
    main()
