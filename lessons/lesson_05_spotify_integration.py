"""
Lesson 05: Spotify Integration

Goal:
- Learn how to control music playback on Spotify
- Understand OAuth authentication
- Control playback (play, pause, next, previous)
- Integrate with gesture or voice commands

Concepts:
- OAuth2 authentication with Spotify API
- Environment variables for credentials
- API client library (spotipy)
- Fallback to local playerctl control
- Error handling and graceful degradation

Run:
- . .venv/bin/activate
- python lessons/lesson_05_spotify_integration.py
"""

import os
import subprocess
import shutil
from pathlib import Path

import spotipy
from spotipy.oauth2 import SpotifyOAuth


# Spotify API permissions we need
SPOTIFY_SCOPE = "user-modify-playback-state user-read-playback-state user-read-currently-playing"


def _load_env_file():
    """
    Load environment variables from .env file.
    
    This allows us to keep sensitive credentials (Client ID, Secret) 
    out of version control and environment variables.
    """
    project_root = Path(__file__).resolve().parents[1]
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
    """
    Create and authenticate a Spotify client.
    
    Steps:
    1. Load credentials from .env file
    2. Use OAuth2 to authenticate with Spotify
    3. Return an authenticated client
    
    Returns:
        A spotipy.Spotify client or None if authentication fails
    """
    # Load credentials from .env
    _load_env_file()

    client_id = os.getenv("SPOTIFY_CLIENT_ID")
    client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
    redirect_uri = os.getenv("SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8888/callback")

    # Check if credentials are configured
    if not client_id or not client_secret:
        print("Spotify is not configured. Add SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET to .env.")
        return None

    try:
        # Create OAuth2 authenticator
        # This will open a browser for the user to login first time
        client = spotipy.Spotify(
            auth_manager=SpotifyOAuth(
                client_id=client_id,
                client_secret=client_secret,
                redirect_uri=redirect_uri,
                scope=SPOTIFY_SCOPE,
            )
        )
        return client
    except Exception as e:
        print("Spotify authentication failed.")
        print(f"Reason: {e}")
        print("Check that your redirect URI in Spotify dashboard matches SPOTIFY_REDIRECT_URI exactly.")
        return None


def spotify_control(command, sp=None):
    """
    Execute a Spotify playback control command.
    
    Args:
        command: One of 'play', 'pause', 'next', 'prev'
        sp: Optional pre-authenticated Spotify client
    """
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


def detect_spotify_player():
    """
    Detect if Spotify is running using playerctl.
    
    This is useful for falling back to local control if web API
    authentication isn't available.
    
    Returns:
        The player name if found, None otherwise
    """
    if not shutil.which("playerctl"):
        print("playerctl not found. Install with: sudo apt install playerctl")
        return None

    result = subprocess.run(
        ["playerctl", "-l"],
        capture_output=True,
        text=True,
        check=False,
    )

    players = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    
    # Look for Spotify player
    if "spotify" in players:
        return "spotify"
    
    # Look for Spotify-like players
    for player in players:
        if "spotify" in player.lower():
            return player
    
    return None


def local_spotify_control(command):
    """
    Control Spotify using playerctl (local fallback).
    
    This works even if Spotify API authentication fails,
    as long as Spotify is running.
    
    Args:
        command: 'play', 'pause', 'next', or 'prev'
    """
    player = detect_spotify_player()
    if not player:
        print("Spotify player not detected. Start playing a song in Spotify first.")
        return

    cmd = ["playerctl", "--player", player, command]
    result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    
    if result.returncode == 0:
        print(f"✓ Executed: {command}")
    else:
        print(f"✗ Failed to execute: {command}")


def get_current_track(sp):
    """
    Get the currently playing track information.
    
    Args:
        sp: Authenticated Spotify client
    
    Returns:
        Dict with track info or None
    """
    try:
        playback = sp.current_playback()
        if not playback or not playback.get("item"):
            return None
        
        item = playback["item"]
        return {
            "name": item.get("name"),
            "artist": item["artists"][0].get("name") if item.get("artists") else "Unknown",
            "is_playing": playback.get("is_playing"),
        }
    except Exception as e:
        print(f"Error fetching current track: {e}")
        return None


def demo_spotify():
    """Demo: Control Spotify playback"""
    
    print("=== Spotify Control Demo ===\n")
    
    # Try to authenticate with Spotify API
    sp = create_spotify_client()
    
    if sp:
        print("✓ Spotify API authenticated\n")
        
        # Get current track
        current = get_current_track(sp)
        if current:
            status = "▶" if current["is_playing"] else "⏸"
            print(f"{status} Currently: {current['name']} by {current['artist']}\n")
        
        # Demo controls
        commands = ["pause", "play", "next", "prev"]
        for cmd in commands:
            print(f"Execute: {cmd}")
            spotify_control(cmd, sp)
            print()
    else:
        print("✗ Spotify API authentication failed\n")
        print("Trying local control with playerctl...\n")
        
        local_spotify_control("play-pause")


if __name__ == "__main__":
    demo_spotify()
