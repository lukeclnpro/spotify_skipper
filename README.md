# Spotify Skipper

Petit script qui surveille Spotify (via `playerctl`), détecte les publicités
et redémarre l'application pour les "skipper", avec relance automatique de
la lecture. Une icône dans la barre d'état système permet aussi de
contrôler Spotify (lecture, pause, suivant, précédent, redémarrer, quitter).

## 1. Installation du projet :
### 1. sur ARCH :

```bash
git clone https://github.com/lukeclnpro/spotify_skipper.git
cd spotify_skipper
mkdir -p ~/.local/share/applications; printf '%s\n' '[Desktop Entry]' 'Name=Spotify Skipper' 'Comment=Lancer Spotify Skipper' 'Exec=python3 /home/luke_cln/spotify_skipper/spotify_auto.py' 'Icon=spotify' 'Terminal=false' 'Type=Application' 'Categories=AudioVideo;Audio;' > ~/.local/share/applications/spotify-skipper.desktop
update-desktop-database ~/.local/share/applications 2>/dev/null || true

```
