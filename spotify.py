"""
Spotify integration module. See lessons/lesson_05_spotify_integration.py for the educational version.
"""

import os
from pathlib import Path

import spotipy
from spotipy.oauth2 import SpotifyOAuth


SPOTIFY_SCOPE = "user-modify-playback-state user-read-playback-state user-read-currently-playing"


def _load_env_file():
    project_root = Path(__file__).resolve().parents[0]
    env_path = project_root / ".env"

    if not env_path.exists():
        return

    for raw_line in env_path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def create_spotify_client():
    _load_env_file()

    client_id = os.getenv("SPOTIFY_CLIENT_ID")
    client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
    redirect_uri = os.getenv("SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8888/callback")

    if not client_id or not client_secret:
        print("Spotify is not configured. Add SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET to .env.")
        return None

    try:
        return spotipy.Spotify(
            auth_manager=SpotifyOAuth(
                client_id=client_id,
                client_secret=client_secret,
                redirect_uri=redirect_uri,
                scope=SPOTIFY_SCOPE,
            )
        )
    except Exception as e:
        print("Spotify authentication failed.")
        print(f"Reason: {e}")
        print("Check that your redirect URI in the Spotify dashboard matches SPOTIFY_REDIRECT_URI exactly.")
        return None


def spotify_control(command, sp=None):
    client = sp or create_spotify_client()
    if not client:
        return

    try:
        if command == "next":
            client.next_track()
            print(">>> Skipping to Next Track")
        elif command == "prev":
            client.previous_track()
            print("<<< Going to Previous Track")
        elif command == "pause":
            client.pause_playback()
            print("|| Paused")
        elif command == "play":
            client.start_playback()
            print("> Playing")
    except Exception as e:
        print(f"Spotify Error: {e} (Make sure Spotify is open and active on a device!)")


if __name__ == "__main__":
    sp = create_spotify_client()
    if not sp:
        print("Spotify is not configured. Set SPOTIFY_CLIENT_ID/SECRET.")
        raise SystemExit(1)

    current_track = sp.current_user_playing_track()
    if current_track:
        name = current_track["item"]["name"]
        artist = current_track["item"]["artists"][0]["name"]
        print(f"Currently Playing: {name} by {artist}")
    else:
        print("Nothing is currently playing. Open Spotify and play a song first!")
