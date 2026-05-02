"""
JARVIS Gesture + Voice Controller

Teaching path (small, focused scripts):
- Lesson 01: `lessons/lesson_01_open_camera.py`
- Lesson 02: `lessons/lesson_02_count_fingers.py`
- Lesson 03: `lessons/lesson_03_two_finger_screenshot.py`
"""

import glob
import ast
import json
import math
import random
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import warnings
from pathlib import Path
from datetime import datetime

import cv2
import mediapipe as mp
import numpy as np
import pygame
import requests

try:
    import sounddevice as sd
except Exception:
    sd = None

from jarvis_control.spotify import create_spotify_client
from jarvis_control.voice import VoiceCommandListener


ROOT_DIR = Path(__file__).resolve().parents[1]
AUDIO_DIR = ROOT_DIR / "audios"
PROFILE_CONFIG_PATH = ROOT_DIR / "profiles.json"

DEFAULT_PROFILE_CONFIG = {
    "active_profile": "default",
    "profiles": {
        "default": {
            "display_name": "Default",
            "gesture_mode_gestures": {
                "pinch": {"label": "PINCH/SPARKLE"},
                "2": {"label": "SCREENSHOT", "screenshot": True},
                "5": {"label": "JARVIS", "jarvis": True},
            },
            "spotify_gestures": {
                "1": "play",
                "2": "pause",
                "3": "previous",
                "4": "next",
            },
            "volume": {
                "up_start": 60,
                "down_start": 40,
                "step": 10,
            },
        }
    },
}


warnings.filterwarnings(
    "ignore",
    message=r"SymbolDatabase.GetPrototype\(\) is deprecated",
    category=UserWarning,
)


def load_sound(filename):
    path = AUDIO_DIR / filename
    if not path.exists():
        print(f"Audio file not found: {path}")
        return None
    try:
        return pygame.mixer.Sound(str(path))
    except Exception as e:
        print(f"Failed to load {path}: {e}")
        return None


def main():
    sp = create_spotify_client()
    playerctl_available = shutil.which("playerctl") is not None
    pactl_available = shutil.which("pactl") is not None
    spotify_player_name = None
    last_player_scan_time = 0.0
    PLAYER_SCAN_INTERVAL = 1.0

    if not sp:
        if playerctl_available:
            print("Spotify Web API unavailable. Using local Spotify controls via playerctl.")
        else:
            print("Spotify controls are unavailable. Install playerctl or configure Spotify API credentials.")

    audio_available = True
    try:
        pygame.mixer.pre_init(44100, -16, 2, 512)
        pygame.mixer.init()
    except Exception as exc:
        audio_available = False
        try:
            pygame.mixer.quit()
        except Exception:
            pass
        print(f"Audio disabled: {exc}")

    def safe_spotify_call(action, label):
        if not sp:
            print("Spotify is not configured or failed to authenticate. Check your .env and redirect URI.")
            return
        try:
            action()
            print(label)
        except Exception as e:
            print(f"Spotify Error: {e} (Make sure Spotify is open and active on a device!)")

    def toggle_spotify_playback():
        if sp:
            try:
                playback = sp.current_playback()
                is_playing = bool(playback and playback.get("is_playing"))
                if is_playing:
                    sp.pause_playback()
                    print("Spotify: Paused")
                else:
                    sp.start_playback()
                    print("Spotify: Playing")
                return
            except Exception as e:
                print(f"Spotify API Error: {e}. Falling back to local control.")

        if not playerctl_available:
            print("Local Spotify control requires playerctl. Install it: sudo apt install playerctl")
            return

        local_spotify_command(["play-pause"], "Spotify: Toggled play/pause (local)")

    def spotify_play_only():
        if sp:
            safe_spotify_call(lambda: sp.start_playback(), "Spotify: Play")
            return

        local_spotify_command(["play"], "Spotify: Play (local)")

    def spotify_pause_only():
        if sp:
            safe_spotify_call(lambda: sp.pause_playback(), "Spotify: Pause")
            return

        local_spotify_command(["pause"], "Spotify: Pause (local)")

    def detect_spotify_player_name(force=False):
        nonlocal spotify_player_name, last_player_scan_time

        if not playerctl_available:
            return None

        now = time.time()
        if not force and spotify_player_name and (now - last_player_scan_time) < PLAYER_SCAN_INTERVAL:
            return spotify_player_name

        if not force and (now - last_player_scan_time) < PLAYER_SCAN_INTERVAL:
            return spotify_player_name

        last_player_scan_time = now

        result = subprocess.run(
            ["playerctl", "-l"],
            capture_output=True,
            text=True,
            check=False,
        )

        players = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        if not players:
            spotify_player_name = None
            return None

        if "spotify" in players:
            spotify_player_name = "spotify"
            return spotify_player_name

        spotify_like = [p for p in players if "spotify" in p.lower()]
        if spotify_like:
            spotify_player_name = spotify_like[0]
            print(f"Detected Spotify player: {spotify_player_name}")
            return spotify_player_name

        # Browser players can expose Spotify via metadata URL/title.
        for player in players:
            meta = subprocess.run(
                ["playerctl", "--player", player, "metadata"],
                capture_output=True,
                text=True,
                check=False,
            ).stdout.lower()

            if "open.spotify.com" in meta or "spotify" in meta:
                spotify_player_name = player
                print(f"Detected Spotify web player: {spotify_player_name}")
                return spotify_player_name

        spotify_player_name = None

        return spotify_player_name

    def local_spotify_command(args, success_label):
        nonlocal spotify_player_name

        if not playerctl_available:
            print("Local Spotify control requires playerctl. Install it: sudo apt install playerctl")
            return False

        if not spotify_player_name:
            detect_spotify_player_name()

        cmd = ["playerctl"]
        if spotify_player_name:
            cmd.extend(["--player", spotify_player_name])
        cmd.extend(args)

        result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)

        # Quick one-time refresh if player identity changed.
        if result.returncode != 0:
            spotify_player_name = None
            detect_spotify_player_name(force=True)

            retry_cmd = ["playerctl"]
            if spotify_player_name:
                retry_cmd.extend(["--player", spotify_player_name])
            retry_cmd.extend(args)
            result = subprocess.run(retry_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)

        # Ubuntu browser sessions often expose changing player names; try all players.
        if result.returncode != 0:
            fallback_cmd = ["playerctl", "-a", *args]
            result = subprocess.run(fallback_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)

        if result.returncode == 0:
            print(success_label)
            return True

        print("Local Spotify control failed. Start playback once in Spotify desktop/web, then retry gesture.")
        return False

    def spotify_next_track():
        if sp:
            safe_spotify_call(lambda: sp.next_track(), "Spotify: Next track")
        else:
            local_spotify_command(["next"], "Spotify: Next track (local)")

    def spotify_previous_track():
        if sp:
            safe_spotify_call(lambda: sp.previous_track(), "Spotify: Previous track")
        else:
            local_spotify_command(["previous"], "Spotify: Previous track (local)")

    def spotify_set_volume(volume_level):
        if sp:
            safe_spotify_call(
                lambda level=volume_level: sp.volume(level),
                f"Spotify Volume: {volume_level}%",
            )
            return

        if pactl_available:
            result = subprocess.run(
                ["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{volume_level}%"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            if result.returncode == 0:
                print(f"System Volume: {volume_level}%")
                return

        local_volume = max(0.0, min(1.0, volume_level / 100.0))
        local_spotify_command(["volume", f"{local_volume:.2f}"], f"Spotify Volume: {volume_level}% (local)")

    def spotify_toggle_mute():
        if pactl_available:
            result = subprocess.run(
                ["pactl", "set-sink-mute", "@DEFAULT_SINK@", "toggle"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            if result.returncode == 0:
                print("System Mute toggled")
                return True

        print("Mute toggle requires pactl on this setup.")
        return False

    sound_count = load_sound("count.mp3") if audio_available else None
    sound_click = load_sound("click.mp3") if audio_available else None
    sound_sparkle = load_sound("sparkle.mp3") if audio_available else None
    sound_jarvis = load_sound("jarvis.wav") if audio_available else None

    screenshots_dir = Path(os.getenv("SCREENSHOTS_DIR", str(ROOT_DIR / "screenshots"))).expanduser()
    screenshot_cooldown_seconds = float(os.getenv("SCREENSHOT_COOLDOWN_SECONDS", "1.25"))
    last_screenshot_time = 0.0
    screenshot_wait_release = False

    def take_screenshot(_frame_bgr):
        nonlocal last_screenshot_time, screenshot_wait_release

        now_ts = time.time()
        if screenshot_wait_release:
            return None
        if now_ts - last_screenshot_time < screenshot_cooldown_seconds:
            return None

        screenshots_dir.mkdir(parents=True, exist_ok=True)
        filename = datetime.now().strftime("jarvis_%Y%m%d_%H%M%S_%f")[:-3] + ".png"
        out_path = screenshots_dir / filename
        ok = False

        try:
            import mss
            import mss.tools

            with mss.mss() as sct:
                monitor = sct.monitors[0]  # all monitors
                grab = sct.grab(monitor)
                png_bytes = mss.tools.to_png(grab.rgb, grab.size)
                out_path.write_bytes(png_bytes)
                ok = True
        except Exception:
            ok = False

        if not ok:
            return None

        last_screenshot_time = now_ts
        screenshot_wait_release = True
        print(f"Saved screenshot: {out_path}")
        return str(out_path)

    mp_hands = mp.solutions.hands
    mp_draw = mp.solutions.drawing_utils
    hands = mp_hands.Hands(
        model_complexity=0,
        min_detection_confidence=0.7,
        min_tracking_confidence=0.7,
    )

    def open_camera():
        env_index = os.getenv("CAMERA_INDEX", "").strip()
        if env_index:
            parts = [p.strip() for p in env_index.split(",") if p.strip()]
            indices = [int(p) for p in parts if p.isdigit()]
        else:
            indices = list(range(0, 10))

        if not indices:
            indices = [0]

        for index in indices:
            # First try default backend, then explicit V4L2 fallback.
            for backend in (None, cv2.CAP_V4L2, cv2.CAP_ANY):
                try:
                    if backend is None:
                        cap_obj = cv2.VideoCapture(index)
                    else:
                        cap_obj = cv2.VideoCapture(index, backend)
                except Exception:
                    cap_obj = None

                if cap_obj is not None and cap_obj.isOpened():
                    # Confirm at least one frame can be read before accepting.
                    ok, _ = cap_obj.read()
                    if not ok:
                        cap_obj.release()
                        continue
                    print(f"Camera opened on index {index}")
                    return cap_obj, index

                if cap_obj is not None:
                    cap_obj.release()

        return None, None

    cap, camera_index = open_camera()
    if cap is None:
        print("No usable camera found. Check webcam connection/permissions or set CAMERA_INDEX.")
        return

    canvas = None
    fist_start_time = 0
    is_sparkle_playing = False
    is_jarvis_playing = False
    current_mode = "GESTURE"
    spotify_trigger_time = 0
    spotify_exit_start_time = 0
    last_pinch_state = False
    last_volume_level = None
    last_spotify_gesture = None
    must_release_fist_after_spotify = False
    spotify_launch_attempted = False
    spotify_pending_gesture = None
    spotify_pending_since = 0.0
    spotify_last_action_time = 0.0
    spotify_wait_release = False
    SPOTIFY_HOLD_SECONDS = 0.35
    SPOTIFY_COOLDOWN_SECONDS = 0.85
    voice_enabled = False
    voice_last_command = "VOICE OFF"
    voice_last_heard = "-"
    voice_state = "voice_off"
    voice_listener = None
    ollama_autostart_attempted = False
    voice_chat_history = []
    MAX_CHAT_HISTORY_MESSAGES = max(8, int(os.getenv("MAX_CHAT_HISTORY_MESSAGES", "16")))
    VOICE_FAST_MODE = os.getenv("VOICE_FAST_MODE", "true").strip().lower() in {"1", "true", "yes", "on"}
    MODEL_DISCOVERY_CACHE_SECONDS = float(os.getenv("MODEL_DISCOVERY_CACHE_SECONDS", "300"))
    OLLAMA_STATUS_CACHE_SECONDS = float(os.getenv("OLLAMA_STATUS_CACHE_SECONDS", "2.0"))
    cached_local_model_name = ""
    cached_local_model_until = 0.0
    cached_ollama_available = False
    cached_ollama_available_until = 0.0
    startup_checks_last_refresh = 0.0
    startup_checks = {"MIC": False, "OLLAMA": False, "SPOTIFY": False}
    jarvis_distance_scale = 1.0
    jarvis_height_factor = 1.0
    profile_config = {}
    active_profile = "default"
    google_tasks_access_token = None
    google_tasks_token_expiry = 0.0
    google_tasks_list_id = None
    app_build_tag = os.getenv("JARVIS_BUILD_TAG", "v1.0.0").strip() or "v1.0.0"

    visual_theme = os.getenv("JARVIS_THEME", "auto").strip().lower()
    if visual_theme not in {"auto", "amber", "cyan"}:
        visual_theme = "auto"

    render_quality = os.getenv("RENDER_QUALITY", "balanced").strip().lower()
    if render_quality not in {"performance", "balanced", "ultra"}:
        render_quality = "balanced"

    quality_presets = {
        "performance": {
            "bridge_strands": 2,
            "bridge_rings": 2,
            "bridge_steps": 6,
            "tick_step": 18,
            "particles_base": 3,
            "particles_amp": 3,
            "shell_bands": 2,
            "chevrons": 5,
            "rays": 8,
            "trail_layers": 2,
            "thread_segments": 8,
        },
        "balanced": {
            "bridge_strands": 3,
            "bridge_rings": 3,
            "bridge_steps": 8,
            "tick_step": 12,
            "particles_base": 5,
            "particles_amp": 5,
            "shell_bands": 3,
            "chevrons": 7,
            "rays": 12,
            "trail_layers": 3,
            "thread_segments": 11,
        },
        "ultra": {
            "bridge_strands": 4,
            "bridge_rings": 3,
            "bridge_steps": 10,
            "tick_step": 10,
            "particles_base": 6,
            "particles_amp": 6,
            "shell_bands": 3,
            "chevrons": 8,
            "rays": 16,
            "trail_layers": 3,
            "thread_segments": 13,
        },
    }
    render_tuning = quality_presets[render_quality]
    show_fps = os.getenv("SHOW_FPS", "true").strip().lower() in {"1", "true", "yes", "on"}
    fps_counter = 0
    fps_value = 0.0
    fps_last_time = time.time()

    def warm_palette_for_hand(hand_index):
        if visual_theme == "amber":
            return True
        if visual_theme == "cyan":
            return False
        if current_mode == "SPOTIFY" or voice_enabled:
            return False
        return hand_index % 2 == 0

    def load_profile_config():
        config = json.loads(json.dumps(DEFAULT_PROFILE_CONFIG))

        if not PROFILE_CONFIG_PATH.exists():
            return config

        try:
            with PROFILE_CONFIG_PATH.open("r", encoding="utf-8") as f:
                raw = json.load(f)
        except Exception as exc:
            print(f"Failed to read profiles config: {exc}")
            return config

        if not isinstance(raw, dict):
            return config

        profiles = raw.get("profiles")
        if isinstance(profiles, dict):
            for key, value in profiles.items():
                if isinstance(key, str) and isinstance(value, dict):
                    config["profiles"][key] = value

        configured_active = raw.get("active_profile")
        if isinstance(configured_active, str) and configured_active.strip():
            config["active_profile"] = configured_active.strip()

        return config

    def get_active_profile_config():
        profiles = profile_config.get("profiles", {})
        selected = profiles.get(active_profile)
        if isinstance(selected, dict):
            return selected
        return profiles.get("default", DEFAULT_PROFILE_CONFIG["profiles"]["default"])

    def get_active_profile_name():
        profile = get_active_profile_config()
        display_name = profile.get("display_name")
        if isinstance(display_name, str) and display_name.strip():
            return display_name.strip()
        return active_profile

    def resolve_profile_key(requested_text):
        requested = requested_text.strip().lower()
        if not requested:
            return None

        profiles = profile_config.get("profiles", {})
        if requested in profiles:
            return requested

        for key, profile in profiles.items():
            if key.lower() == requested:
                return key

            display_name = profile.get("display_name") if isinstance(profile, dict) else None
            if isinstance(display_name, str) and display_name.strip().lower() == requested:
                return key

        return None

    def switch_profile(profile_key):
        nonlocal active_profile, last_volume_level

        if profile_key == active_profile:
            return False

        active_profile = profile_key
        last_volume_level = None
        print(f"Profile switched to {get_active_profile_name()} ({active_profile})")
        return True

    def normalized_profile_key(raw_name):
        key = re.sub(r"[^a-z0-9]+", "_", raw_name.lower()).strip("_")
        if not key:
            return "user"
        return key[:24]

    def save_profile_config():
        try:
            profile_config["active_profile"] = active_profile
            with PROFILE_CONFIG_PATH.open("w", encoding="utf-8") as f:
                json.dump(profile_config, f, indent=2)
                f.write("\n")
            return True
        except Exception as exc:
            print(f"Failed to save profiles config: {exc}")
            return False

    def ensure_profile_from_name(raw_name):
        clean_name = " ".join(raw_name.strip().split())
        if len(clean_name) < 2:
            return None, "I did not catch your name clearly. Please say it again."

        existing_key = resolve_profile_key(clean_name)
        if existing_key:
            switch_profile(existing_key)
            save_profile_config()
            return False, get_active_profile_name()

        base_key = normalized_profile_key(clean_name)
        key = base_key
        suffix = 2
        profiles = profile_config.setdefault("profiles", {})
        while key in profiles:
            key = f"{base_key}_{suffix}"
            suffix += 1

        default_profile = DEFAULT_PROFILE_CONFIG["profiles"]["default"]
        new_profile = json.loads(json.dumps(default_profile))
        new_profile["display_name"] = clean_name.title()
        profiles[key] = new_profile

        switch_profile(key)
        save_profile_config()
        return True, get_active_profile_name()

    def profile_volume_settings():
        volume = get_active_profile_config().get("volume", {})
        up_start = volume.get("up_start", 60)
        down_start = volume.get("down_start", 40)
        step = volume.get("step", 10)

        try:
            up_start = int(up_start)
        except Exception:
            up_start = 60
        try:
            down_start = int(down_start)
        except Exception:
            down_start = 40
        try:
            step = int(step)
        except Exception:
            step = 10

        return {
            "up_start": max(0, min(100, up_start)),
            "down_start": max(0, min(100, down_start)),
            "step": max(1, min(40, step)),
        }

    def gesture_mode_action_for_detection(detected_count_value, is_pinch):
        gestures = get_active_profile_config().get("gesture_mode_gestures", {})
        key = "pinch" if is_pinch else str(detected_count_value)
        action = gestures.get(key)
        if not isinstance(action, dict):
            return None

        label = action.get("label")
        jarvis = bool(action.get("jarvis", False))
        screenshot = bool(action.get("screenshot", False))

        if not isinstance(label, str) or not label.strip():
            return None

        return {
            "label": label.strip(),
            "jarvis": jarvis,
            "screenshot": screenshot,
        }

    def spotify_action_for_count(detected_count_value):
        spotify_handlers = {
            "play": ("play", "PLAY", spotify_play_only),
            "pause": ("pause", "PAUSE", spotify_pause_only),
            "previous": ("previous", "PREVIOUS TRACK", spotify_previous_track),
            "next": ("next", "NEXT TRACK", spotify_next_track),
        }

        mapping = get_active_profile_config().get("spotify_gestures", {})
        action_name = mapping.get(str(detected_count_value))
        if not isinstance(action_name, str):
            return None

        return spotify_handlers.get(action_name.strip().lower())

    profile_config = load_profile_config()
    requested_profile = os.getenv("ACTIVE_PROFILE", "").strip() or str(profile_config.get("active_profile", "default"))
    resolved_profile = resolve_profile_key(requested_profile)
    if resolved_profile:
        active_profile = resolved_profile
    print(f"Active profile: {get_active_profile_name()} ({active_profile})")

    def resolve_ollama_binary():
        candidates = [
            shutil.which("ollama"),
            "/usr/local/bin/ollama",
            "/usr/bin/ollama",
        ]
        for candidate in candidates:
            if candidate and Path(candidate).exists():
                return candidate
        return None

    def ollama_server_available(local_base):
        try:
            response = requests.get(f"{local_base.rstrip('/')}/api/tags", timeout=2)
            return response.ok
        except Exception:
            return False

    def ensure_ollama_server_running(local_base):
        nonlocal ollama_autostart_attempted

        auto_start = os.getenv("AI_AUTO_START_OLLAMA", "true").strip().lower()
        if auto_start not in {"1", "true", "yes", "on"}:
            return False

        if ollama_server_available(local_base):
            return True

        if ollama_autostart_attempted:
            return False

        ollama_autostart_attempted = True
        binary = resolve_ollama_binary()
        if not binary:
            print("Ollama binary not found. Install Ollama or set AI_CHAT_API_KEY.")
            return False

        try:
            subprocess.Popen([binary, "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            for _ in range(15):
                if ollama_server_available(local_base):
                    print("Ollama server started automatically")
                    return True
                time.sleep(0.3)
        except Exception as exc:
            print(f"Failed to start Ollama server: {exc}")

        print("Ollama server is not reachable.")
        return False

    def microphone_available():
        if sd is None:
            return False
        try:
            devices = sd.query_devices()
            default_input = None
            if hasattr(sd, "default") and hasattr(sd.default, "device"):
                default_input = sd.default.device[0]

            if isinstance(default_input, int) and default_input >= 0:
                if devices[default_input].get("max_input_channels", 0) > 0:
                    return True

            return any(device.get("max_input_channels", 0) > 0 for device in devices)
        except Exception:
            return False

    def collect_startup_checks():
        local_base = os.getenv("AI_LOCAL_API_BASE", "http://127.0.0.1:11434")
        return {
            "MIC": microphone_available(),
            "OLLAMA": ollama_server_available(local_base),
            "SPOTIFY": bool(sp or playerctl_available),
        }

    def google_tasks_configured():
        direct_access = os.getenv("GOOGLE_TASKS_ACCESS_TOKEN", "").strip()
        refresh_token = os.getenv("GOOGLE_TASKS_REFRESH_TOKEN", "").strip()
        client_id = os.getenv("GOOGLE_TASKS_CLIENT_ID", "").strip()
        client_secret = os.getenv("GOOGLE_TASKS_CLIENT_SECRET", "").strip()
        return bool(direct_access or (refresh_token and client_id and client_secret))

    def get_google_tasks_access_token(force_refresh=False):
        nonlocal google_tasks_access_token, google_tasks_token_expiry

        static_token = os.getenv("GOOGLE_TASKS_ACCESS_TOKEN", "").strip()
        if static_token:
            return static_token

        refresh_token = os.getenv("GOOGLE_TASKS_REFRESH_TOKEN", "").strip()
        client_id = os.getenv("GOOGLE_TASKS_CLIENT_ID", "").strip()
        client_secret = os.getenv("GOOGLE_TASKS_CLIENT_SECRET", "").strip()

        if not (refresh_token and client_id and client_secret):
            return None

        now = time.time()
        if not force_refresh and google_tasks_access_token and now < google_tasks_token_expiry - 30:
            return google_tasks_access_token

        try:
            response = requests.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                },
                timeout=8,
            )
            response.raise_for_status()
            payload = response.json()
            token = payload.get("access_token", "").strip()
            expires_in = int(payload.get("expires_in", 3600))
            if not token:
                return None
            google_tasks_access_token = token
            google_tasks_token_expiry = now + max(60, expires_in)
            return google_tasks_access_token
        except Exception as exc:
            print(f"Google Tasks auth error: {exc}")
            return None

    def google_tasks_request(method, endpoint, params=None, payload=None):
        token = get_google_tasks_access_token()
        if not token:
            return None, "Google Tasks is not configured. Set OAuth env vars first."

        base_url = "https://tasks.googleapis.com/tasks/v1"

        def _do_request(access_token):
            return requests.request(
                method,
                f"{base_url}{endpoint}",
                params=params,
                json=payload,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                timeout=10,
            )

        try:
            response = _do_request(token)

            if response.status_code == 401 and not os.getenv("GOOGLE_TASKS_ACCESS_TOKEN", "").strip():
                refreshed = get_google_tasks_access_token(force_refresh=True)
                if refreshed:
                    response = _do_request(refreshed)

            if not response.ok:
                message = f"HTTP {response.status_code}"
                try:
                    err_payload = response.json()
                    message = err_payload.get("error", {}).get("message") or message
                except Exception:
                    pass
                return None, f"Google Tasks API error: {message}"

            if response.text.strip():
                return response.json(), None
            return {}, None
        except Exception as exc:
            return None, f"Google Tasks request failed: {exc}"

    def resolve_google_task_list_id():
        nonlocal google_tasks_list_id

        if google_tasks_list_id:
            return google_tasks_list_id, None

        explicit_list_id = os.getenv("GOOGLE_TASK_LIST_ID", "").strip()
        if explicit_list_id:
            google_tasks_list_id = explicit_list_id
            return google_tasks_list_id, None

        data, error = google_tasks_request("GET", "/users/@me/lists", params={"maxResults": 20})
        if error:
            return None, error

        items = data.get("items", []) if isinstance(data, dict) else []
        if not items:
            return None, "No Google Task lists found on this account."

        preferred_name = os.getenv("GOOGLE_TASK_LIST_NAME", "").strip().lower()
        if preferred_name:
            for item in items:
                title = str(item.get("title", "")).strip().lower()
                if title == preferred_name:
                    google_tasks_list_id = item.get("id")
                    break

        if not google_tasks_list_id:
            google_tasks_list_id = items[0].get("id")

        if not google_tasks_list_id:
            return None, "Could not resolve Google Task list ID."
        return google_tasks_list_id, None

    def normalize_task_text(raw_text):
        text = " ".join(raw_text.split()).strip()
        text = re.sub(r"^[\s:;,.\-]+", "", text)
        text = re.sub(r"[\s:;,.\-]+$", "", text)
        return text

    def list_google_tasks(limit=5):
        task_list_id, error = resolve_google_task_list_id()
        if error:
            return None, error

        data, error = google_tasks_request(
            "GET",
            f"/lists/{task_list_id}/tasks",
            params={
                "maxResults": max(1, min(15, limit)),
                "showCompleted": "false",
                "showHidden": "false",
            },
        )
        if error:
            return None, error

        items = data.get("items", []) if isinstance(data, dict) else []
        readable = [item.get("title", "").strip() for item in items if item.get("title")]
        return readable, None

    def create_google_task(task_title):
        task_list_id, error = resolve_google_task_list_id()
        if error:
            return None, error

        data, error = google_tasks_request(
            "POST",
            f"/lists/{task_list_id}/tasks",
            payload={"title": task_title},
        )
        if error:
            return None, error

        return data.get("title", task_title), None

    def find_google_task_by_title(task_title):
        task_list_id, error = resolve_google_task_list_id()
        if error:
            return None, None, error

        data, error = google_tasks_request(
            "GET",
            f"/lists/{task_list_id}/tasks",
            params={
                "maxResults": 100,
                "showCompleted": "true",
                "showHidden": "true",
            },
        )
        if error:
            return None, None, error

        wanted = task_title.strip().lower()
        items = data.get("items", []) if isinstance(data, dict) else []
        for item in items:
            title = str(item.get("title", "")).strip()
            if title.lower() == wanted:
                return task_list_id, item, None

        for item in items:
            title = str(item.get("title", "")).strip().lower()
            if wanted and wanted in title:
                return task_list_id, item, None

        return task_list_id, None, None

    def delete_google_task(task_title):
        task_list_id, task_item, error = find_google_task_by_title(task_title)
        if error:
            return False, error
        if not task_item:
            return False, "Task not found"

        task_id = task_item.get("id")
        if not task_id:
            return False, "Task ID is missing"

        _, error = google_tasks_request("DELETE", f"/lists/{task_list_id}/tasks/{task_id}")
        if error:
            return False, error

        return True, str(task_item.get("title", task_title)).strip()

    def update_google_task_title(old_title, new_title):
        task_list_id, task_item, error = find_google_task_by_title(old_title)
        if error:
            return False, error
        if not task_item:
            return False, "Task not found"

        task_id = task_item.get("id")
        if not task_id:
            return False, "Task ID is missing"

        _, error = google_tasks_request(
            "PATCH",
            f"/lists/{task_list_id}/tasks/{task_id}",
            params={"fields": "id,title,status"},
            payload={"title": new_title},
        )
        if error:
            return False, error

        return True, str(task_item.get("title", old_title)).strip()

    def complete_google_task(task_title):
        task_list_id, task_item, error = find_google_task_by_title(task_title)
        if error:
            return False, error
        if not task_item:
            return False, "Task not found"

        task_id = task_item.get("id")
        if not task_id:
            return False, "Task ID is missing"

        completed_at = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
        _, error = google_tasks_request(
            "PATCH",
            f"/lists/{task_list_id}/tasks/{task_id}",
            params={"fields": "id,title,status,completed"},
            payload={
                "title": task_item.get("title", task_title),
                "status": "completed",
                "completed": completed_at,
            },
        )
        if error:
            return False, error

        return True, str(task_item.get("title", task_title)).strip()

    def speak(text):
        if shutil.which("spd-say"):
            subprocess.Popen(["spd-say", text], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return

        if shutil.which("espeak"):
            subprocess.Popen(["espeak", text], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return

        print(f"TTS unavailable: {text}")

    def count_raised_fingers(landmarks):
        wrist = landmarks[0]
        palm_width = max(
            0.02,
            math.hypot(landmarks[5].x - landmarks[17].x, landmarks[5].y - landmarks[17].y),
        )

        palm_center_x = (landmarks[0].x + landmarks[5].x + landmarks[9].x + landmarks[13].x + landmarks[17].x) / 5.0
        palm_center_y = (landmarks[0].y + landmarks[5].y + landmarks[9].y + landmarks[13].y + landmarks[17].y) / 5.0

        def dist_from_palm(idx):
            return math.hypot(landmarks[idx].x - palm_center_x, landmarks[idx].y - palm_center_y)

        def dist_from_wrist(idx):
            return math.hypot(landmarks[idx].x - wrist.x, landmarks[idx].y - wrist.y)

        def joint_angle(a_idx, b_idx, c_idx):
            ax, ay = landmarks[a_idx].x, landmarks[a_idx].y
            bx, by = landmarks[b_idx].x, landmarks[b_idx].y
            cx, cy = landmarks[c_idx].x, landmarks[c_idx].y

            v1x, v1y = ax - bx, ay - by
            v2x, v2y = cx - bx, cy - by
            n1 = math.hypot(v1x, v1y)
            n2 = math.hypot(v2x, v2y)
            if n1 < 1e-6 or n2 < 1e-6:
                return 0.0
            cosang = max(-1.0, min(1.0, (v1x * v2x + v1y * v2y) / (n1 * n2)))
            return math.degrees(math.acos(cosang))

        # Thumb extension from palm-radial distance + uncurled angle.
        thumb_tip_far = dist_from_palm(4) > dist_from_palm(3) + 0.12 * palm_width
        thumb_uncurled = joint_angle(2, 3, 4) > 145
        thumb_extended = thumb_tip_far and thumb_uncurled

        count = 1 if thumb_extended else 0

        # Non-thumb fingers: orientation-agnostic using radial + wrist distance, with y-check as bonus.
        for tip, pip, mcp in [(8, 6, 5), (12, 10, 9), (16, 14, 13), (20, 18, 17)]:
            radial_extended = dist_from_palm(tip) > dist_from_palm(pip) + 0.08 * palm_width
            wrist_extended = dist_from_wrist(tip) > dist_from_wrist(mcp) + 0.10 * palm_width
            vertical_extended = landmarks[tip].y < landmarks[pip].y
            if (radial_extended and wrist_extended) or vertical_extended:
                count += 1

        return count

    def launch_spotify_app():
        candidates = [
            ["xdg-open", "https://open.spotify.com/"],
            ["spotify"],
            ["flatpak", "run", "com.spotify.Client"],
            ["snap", "run", "spotify"],
            ["xdg-open", "spotify:"],
        ]

        for command in candidates:
            try:
                subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if "open.spotify.com" in command[-1]:
                    print("Launching Spotify Web in browser")
                else:
                    print(f"Launching Spotify with: {' '.join(command)}")
                return True
            except Exception:
                continue

        print("Could not launch Spotify automatically. Open it manually once and keep it running.")
        return False

    def set_mode(mode):
        nonlocal current_mode, spotify_trigger_time, spotify_exit_start_time, last_volume_level, last_spotify_gesture, spotify_launch_attempted
        nonlocal spotify_pending_gesture, spotify_pending_since, spotify_last_action_time, spotify_wait_release

        if current_mode == mode:
            return

        current_mode = mode
        spotify_trigger_time = 0
        spotify_exit_start_time = 0
        last_volume_level = None
        last_spotify_gesture = None
        spotify_launch_attempted = False
        spotify_pending_gesture = None
        spotify_pending_since = 0.0
        spotify_last_action_time = 0.0
        spotify_wait_release = False
        print(f"Mode switched to {current_mode}")

    def reply(text):
        nonlocal voice_last_command
        voice_last_command = text
        speak(text)

    def chat_reply(user_text):
        nonlocal voice_chat_history
        nonlocal cached_local_model_name, cached_local_model_until
        nonlocal cached_ollama_available, cached_ollama_available_until

        def pick_local_chat_model(local_base_url, preferred_model):
            nonlocal cached_local_model_name, cached_local_model_until

            if preferred_model:
                return preferred_model

            now_ts = time.time()
            if cached_local_model_name and now_ts < cached_local_model_until:
                return cached_local_model_name

            try:
                response = requests.get(f"{local_base_url.rstrip('/')}/api/tags", timeout=3)
                if not response.ok:
                    return "llama3.2:3b"

                payload = response.json()
                items = payload.get("models", []) if isinstance(payload, dict) else []
                installed = [str(item.get("name", "")).strip() for item in items if str(item.get("name", "")).strip()]
                if not installed:
                    return "llama3.2:3b"

                priority = [
                    "qwen2.5:7b",
                    "llama3.1:8b",
                    "mistral:7b",
                    "phi4",
                    "llama3.2:3b",
                ]

                installed_lower = {name.lower(): name for name in installed}
                for candidate in priority:
                    exact = installed_lower.get(candidate.lower())
                    if exact:
                        cached_local_model_name = exact
                        cached_local_model_until = now_ts + MODEL_DISCOVERY_CACHE_SECONDS
                        return exact

                for candidate in priority:
                    for existing in installed:
                        if candidate.lower() in existing.lower():
                            cached_local_model_name = existing
                            cached_local_model_until = now_ts + MODEL_DISCOVERY_CACHE_SECONDS
                            return existing

                cached_local_model_name = installed[0]
                cached_local_model_until = now_ts + MODEL_DISCOVERY_CACHE_SECONDS
                return installed[0]
            except Exception:
                return "llama3.2:3b"

        def fast_ollama_available(local_base_url):
            nonlocal cached_ollama_available, cached_ollama_available_until

            now_ts = time.time()
            if now_ts < cached_ollama_available_until:
                return cached_ollama_available

            available = ollama_server_available(local_base_url)
            cached_ollama_available = available
            cached_ollama_available_until = now_ts + OLLAMA_STATUS_CACHE_SECONDS
            return available

        def safe_eval_math(expression):
            try:
                node = ast.parse(expression, mode="eval")
            except Exception:
                return None

            allowed_binops = {
                ast.Add: lambda a, b: a + b,
                ast.Sub: lambda a, b: a - b,
                ast.Mult: lambda a, b: a * b,
                ast.Div: lambda a, b: a / b,
                ast.Mod: lambda a, b: a % b,
                ast.Pow: lambda a, b: a**b,
            }
            allowed_unary = {
                ast.UAdd: lambda a: +a,
                ast.USub: lambda a: -a,
            }

            def _eval(n):
                if isinstance(n, ast.Expression):
                    return _eval(n.body)

                if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
                    return float(n.value)

                if isinstance(n, ast.UnaryOp) and type(n.op) in allowed_unary:
                    return allowed_unary[type(n.op)](_eval(n.operand))

                if isinstance(n, ast.BinOp) and type(n.op) in allowed_binops:
                    left = _eval(n.left)
                    right = _eval(n.right)
                    if isinstance(n.op, ast.Pow) and abs(right) > 8:
                        raise ValueError("Exponent too large")
                    return allowed_binops[type(n.op)](left, right)

                raise ValueError("Unsupported expression")

            try:
                result = _eval(node)
                if math.isinf(result) or math.isnan(result):
                    return None
                return result
            except Exception:
                return None

        def try_math_reply(text):
            lowered = text.lower()
            lowered = lowered.replace("x", " * ")
            replacements = {
                "plus": " + ",
                "minus": " - ",
                "times": " * ",
                "multiplied by": " * ",
                "into": " * ",
                "divided by": " / ",
                "over": " / ",
                "modulus": " % ",
                "mod": " % ",
                "to the power of": " ** ",
                "power": " ** ",
            }
            for src, dst in replacements.items():
                lowered = lowered.replace(src, dst)

            number_words = {
                "zero": "0",
                "one": "1",
                "two": "2",
                "three": "3",
                "four": "4",
                "five": "5",
                "six": "6",
                "seven": "7",
                "eight": "8",
                "nine": "9",
                "ten": "10",
                "eleven": "11",
                "twelve": "12",
                "thirteen": "13",
                "fourteen": "14",
                "fifteen": "15",
                "sixteen": "16",
                "seventeen": "17",
                "eighteen": "18",
                "nineteen": "19",
                "twenty": "20",
            }
            for word, num in number_words.items():
                lowered = re.sub(rf"\b{word}\b", num, lowered)

            lowered = re.sub(r"\b(what is|what's|calculate|compute|solve|equals|equal to|answer)\b", " ", lowered)
            lowered = re.sub(r"[^0-9\+\-\*\/\%\(\)\.\s]", " ", lowered)
            lowered = " ".join(lowered.split())

            if not re.search(r"[\+\-\*\/\%]", lowered):
                return None

            result = safe_eval_math(lowered)
            if result is None:
                return None

            if abs(result - round(result)) < 1e-9:
                return f"The answer is {int(round(result))}."
            return f"The answer is {result:.4f}."

        def extract_city(text):
            match = re.search(r"\bin\s+([a-zA-Z\s]{2,40})", text)
            if not match:
                return ""
            city = " ".join(match.group(1).split()).strip()
            return city

        def weather_context(text):
            lowered = text.lower()
            is_weather_query = any(
                word in lowered
                for word in ["weather", "temperature", "rain", "forecast", "hot", "cold", "humidity"]
            )
            if not is_weather_query:
                return ""

            city = extract_city(text)
            location_path = city.replace(" ", "+") if city else ""

            try:
                response = requests.get(
                    f"https://wttr.in/{location_path}?format=j1",
                    timeout=8,
                )
                response.raise_for_status()
                data = response.json()
                current = data.get("current_condition", [{}])[0]
                nearest = data.get("nearest_area", [{}])[0]
                area_name = (
                    nearest.get("areaName", [{}])[0].get("value")
                    if nearest.get("areaName")
                    else (city or "your location")
                )
                condition = current.get("weatherDesc", [{}])[0].get("value", "Unknown")
                temp_c = current.get("temp_C", "?")
                feels = current.get("FeelsLikeC", "?")
                humidity = current.get("humidity", "?")

                return (
                    f"Live weather data for {area_name}: {condition}, temperature {temp_c}C, "
                    f"feels like {feels}C, humidity {humidity} percent."
                )
            except Exception as exc:
                print(f"Weather fetch error: {exc}")
                return "Live weather data is currently unavailable."

        def local_fallback_reply(raw_text, lowered_text, weather_text):
            now_dt = datetime.now()

            math_reply = try_math_reply(raw_text)
            if math_reply:
                return math_reply

            if weather_text:
                return weather_text

            if any(word in lowered_text for word in ["hello", "hi", "hey", "yo"]):
                return "Hello. I am online and listening."

            if any(word in lowered_text for word in ["thanks", "thank you", "thx"]):
                return "You are welcome."

            if any(phrase in lowered_text for phrase in ["how are you", "how are u", "what's up", "whats up"]):
                return "I am running well and ready to help."

            if any(
                phrase in lowered_text
                for phrase in [
                    "how is your day",
                    "how's your day",
                    "how is the day going",
                    "how's the day going",
                    "how are things",
                    "how is it going",
                ]
            ):
                return "My day is going great. I am here with you and ready for anything you need. How is your day going?"

            if any(phrase in lowered_text for phrase in ["good morning", "good afternoon", "good evening"]):
                return "Great to hear from you. Hope your day is going smoothly."

            if any(phrase in lowered_text for phrase in ["who are you", "what are you", "your name", "who is this"]):
                return "I am JARVIS, your voice assistant."

            if any(phrase in lowered_text for phrase in ["what time", "current time", "time now"]):
                return f"Current time is {now_dt.strftime('%I:%M %p')}"

            if any(phrase in lowered_text for phrase in ["what date", "today date", "which date", "today is"]):
                return f"Today is {now_dt.strftime('%A, %d %B %Y')}"

            if any(phrase in lowered_text for phrase in ["what can you do", "help", "commands", "capabilities"]):
                return (
                    "I can control Spotify, switch I O T and Spotify modes, adjust volume, "
                    "manage Google Tasks, and answer short questions."
                )

            if any(phrase in lowered_text for phrase in ["status", "system status", "are you online"]):
                return f"Mode is {current_mode}. Voice is {'on' if voice_enabled else 'off'}."

            if lowered_text.endswith("?"):
                topic_words = [
                    word
                    for word in re.findall(r"[a-zA-Z]{3,}", raw_text.lower())
                    if word not in {"what", "when", "where", "which", "who", "how", "why", "can", "you", "the"}
                ]
                if topic_words:
                    topic = topic_words[0]
                    return (
                        f"I heard your question about {topic}. "
                        "I can give short answers and also run voice commands for music and I O T."
                    )
                return "Good question. I can answer short queries and execute your voice commands."

            return "I am listening. You can ask a question or give a command."

        local_base = os.getenv("AI_LOCAL_API_BASE", "http://127.0.0.1:11434")
        configured_local_model = os.getenv("AI_LOCAL_MODEL", "").strip()
        local_model = pick_local_chat_model(local_base, configured_local_model)
        api_key = os.getenv("AI_CHAT_API_KEY") or os.getenv("OPENAI_API_KEY")
        api_base = os.getenv("AI_CHAT_API_BASE", "https://api.openai.com/v1")
        model = os.getenv("AI_CHAT_MODEL", "gpt-4o-mini")
        weather_info = weather_context(user_text)
        now_text = datetime.now().strftime("%Y-%m-%d %H:%M")

        system_prompt = (
            "You are JARVIS, warm, natural, and concise. "
            "Reply in 1-3 short conversational lines. "
            "For chit-chat, sound friendly and human, not robotic. "
            "Use provided weather context exactly and do not invent weather values. "
            f"Current local datetime is {now_text}."
        )

        prompt_text = user_text if not weather_info else f"{user_text}\n\nContext: {weather_info}"
        local_available = fast_ollama_available(local_base)
        if not local_available:
            local_available = ensure_ollama_server_running(local_base)

        history_window = 8 if VOICE_FAST_MODE else MAX_CHAT_HISTORY_MESSAGES
        chat_context = voice_chat_history[-history_window:]
        messages = [{"role": "system", "content": system_prompt}] + chat_context + [
            {"role": "user", "content": prompt_text}
        ]

        # Prefer free local chat via Ollama if available.
        if local_available:
            try:
                response = requests.post(
                    f"{local_base.rstrip('/')}/api/chat",
                    json={
                        "model": local_model,
                        "messages": messages,
                        "stream": False,
                    },
                    timeout=12,
                )
                if response.ok:
                    data = response.json()
                    content = data.get("message", {}).get("content", "").strip()
                    if content:
                        voice_chat_history.extend(
                            [
                                {"role": "user", "content": prompt_text},
                                {"role": "assistant", "content": content},
                            ]
                        )
                        voice_chat_history = voice_chat_history[-MAX_CHAT_HISTORY_MESSAGES:]
                        return content
            except Exception as exc:
                print(f"Local Ollama chat error: {exc}")

        if api_key:
            try:
                response = requests.post(
                    f"{api_base.rstrip('/')}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model,
                        "messages": messages,
                        "temperature": 0.6,
                        "max_tokens": 120 if VOICE_FAST_MODE else 180,
                    },
                    timeout=20,
                )
                response.raise_for_status()
                data = response.json()
                content = data["choices"][0]["message"]["content"].strip()
                if content:
                    voice_chat_history.extend(
                        [
                            {"role": "user", "content": prompt_text},
                            {"role": "assistant", "content": content},
                        ]
                    )
                    voice_chat_history = voice_chat_history[-MAX_CHAT_HISTORY_MESSAGES:]
                return content
            except Exception as exc:
                print(f"Voice chat API error: {exc}")

        lower = user_text.lower().strip()
        return local_fallback_reply(user_text, lower, weather_info)

    def handle_voice_wake():
        reply("Yes?")

    def handle_voice_heard(_raw_text, normalized_text):
        nonlocal voice_last_heard
        voice_last_heard = normalized_text[:50] if normalized_text else "-"

    def handle_voice_state(state):
        nonlocal voice_state
        voice_state = state

    def handle_voice_command(text):
        nonlocal voice_last_command, voice_enabled, last_volume_level, voice_listener

        raw_command = re.sub(r"^\s*jarvis\b[\s,.:;-]*", "", text.strip(), flags=re.IGNORECASE).strip()
        command = raw_command.lower()
        print(f"Voice command: {command}")

        if not command:
            reply("Yes?")
            return

        if command in {"voice off", "stop voice", "disable voice", "mute voice input"}:
            voice_enabled = False
            if voice_listener:
                voice_listener.set_enabled(False)
            reply("Voice control off")
            print("Voice control disabled")
            return

        if "jarvis off" in command or "deactivate jarvis" in command:
            reply("JARVIS off")
            return

        if "jarvis on" in command or "activate jarvis" in command or command == "jarvis":
            reply("JARVIS on")
            return

        if "gesture mode" in command or "go to gesture" in command or "control mode" in command:
            set_mode("GESTURE")
            reply("Gesture mode")
            return

        if "spotify mode" in command or "go to spotify" in command:
            set_mode("SPOTIFY")
            reply("Spotify mode")
            return

        if command in {"list profiles", "show profiles", "available profiles"}:
            names = ", ".join(sorted(profile_config.get("profiles", {}).keys()))
            reply(f"Available profiles are {names}. Active profile is {get_active_profile_name()}.")
            return

        name_match = re.search(r"(?:^|\b)(?:my\s+name\s+is|i\s+am|i\'m|this\s+is)\s+(.+)$", command)
        if name_match:
            captured_name = name_match.group(1)
            captured_name = re.sub(r"[^a-z0-9_\-\s]", " ", captured_name.lower())
            captured_name = " ".join(captured_name.split())
            created, profile_name = ensure_profile_from_name(captured_name)
            if created is None:
                reply(profile_name)
            elif created:
                reply(f"Nice to meet you {profile_name}. Your profile is ready.")
            else:
                reply(f"Welcome back {profile_name}. Profile activated.")
            return

        profile_match = re.search(r"(?:switch to|use|set)\s+(?:profile\s+)?([a-z0-9_\- ]{2,30})$", command)
        if profile_match:
            requested = profile_match.group(1).strip()
            profile_key = resolve_profile_key(requested)
            if profile_key:
                changed = switch_profile(profile_key)
                if changed:
                    reply(f"Switched to {get_active_profile_name()} profile")
                else:
                    reply(f"{get_active_profile_name()} profile is already active")
            else:
                reply("Profile not found")
            return

        if re.search(r"^(?:list|show)\s+(?:my\s+)?(?:google\s+)?tasks\b", command):
            if not google_tasks_configured():
                reply("Google Tasks is not configured")
                return

            tasks, error = list_google_tasks(limit=5)
            if error:
                reply(error)
                return
            if not tasks:
                reply("No pending tasks")
                return
            reply("Top tasks: " + ", ".join(tasks[:3]))
            return

        add_task_match = re.search(
            r"^(?:add|create|new)\s+(?:a\s+)?(?:google\s+)?task\b[:\s\-]*(.+)$",
            raw_command,
            re.IGNORECASE,
        )
        if add_task_match:
            if not google_tasks_configured():
                reply("Google Tasks is not configured")
                return

            task_title = normalize_task_text(add_task_match.group(1))
            if not task_title:
                reply("Please say the task title")
                return

            created_title, error = create_google_task(task_title)
            if error:
                reply(error)
            else:
                reply(f"Task added: {created_title}")
            return

        delete_task_match = re.search(
            r"^(?:delete|del|remove)\s+(?:the\s+)?(?:google\s+)?task\b[:\s\-]*(.+)$",
            raw_command,
            re.IGNORECASE,
        )
        if delete_task_match:
            if not google_tasks_configured():
                reply("Google Tasks is not configured")
                return

            task_title = normalize_task_text(delete_task_match.group(1))
            if not task_title:
                reply("Please say which task to delete")
                return

            deleted, info = delete_google_task(task_title)
            if deleted:
                reply(f"Task deleted: {info}")
            else:
                reply(info)
            return

        update_task_match = re.search(
            r"^(?:update|edit|rename)\s+(?:the\s+)?(?:google\s+)?task\b[:\s\-]*(.+?)\s+(?:to|as)\s+(.+)$",
            raw_command,
            re.IGNORECASE,
        )
        if update_task_match:
            if not google_tasks_configured():
                reply("Google Tasks is not configured")
                return

            old_title = normalize_task_text(update_task_match.group(1))
            new_title = normalize_task_text(update_task_match.group(2))
            if not old_title or not new_title:
                reply("Please say old and new task titles")
                return

            updated, info = update_google_task_title(old_title, new_title)
            if updated:
                reply(f"Task updated: {old_title} to {new_title}")
            else:
                reply(info)
            return

        complete_task_match = re.search(
            r"^(?:complete|finish|done|mark)\s+(?:the\s+)?(?:google\s+)?task\b[:\s\-]*(.+)$",
            raw_command,
            re.IGNORECASE,
        )
        if complete_task_match:
            if not google_tasks_configured():
                reply("Google Tasks is not configured")
                return

            task_title = normalize_task_text(complete_task_match.group(1))
            if not task_title:
                reply("Please say which task to complete")
                return

            completed, info = complete_google_task(task_title)
            if completed:
                reply(f"Task completed: {info}")
            else:
                reply(info)
            return

        if command in {"play", "resume", "start playback"} or "play music" in command:
            if current_mode != "SPOTIFY":
                set_mode("SPOTIFY")
            spotify_play_only()
            reply("Playing music")
            return

        if command in {"pause", "stop playback"} or "pause music" in command:
            if current_mode != "SPOTIFY":
                set_mode("SPOTIFY")
            spotify_pause_only()
            reply("Music paused")
            return

        if command in {"next", "next track", "skip"}:
            if current_mode != "SPOTIFY":
                set_mode("SPOTIFY")
            spotify_next_track()
            reply("Next track")
            return

        if command in {"previous", "prev", "previous track", "back"}:
            if current_mode != "SPOTIFY":
                set_mode("SPOTIFY")
            spotify_previous_track()
            reply("Previous track")
            return

        if "volume up" in command or "raise volume" in command or "louder" in command:
            volume_cfg = profile_volume_settings()
            level = volume_cfg["up_start"] if last_volume_level is None else min(100, last_volume_level + volume_cfg["step"])
            last_volume_level = level
            spotify_set_volume(level)
            reply(f"Volume {level} percent")
            return

        if "volume down" in command or "lower volume" in command or "softer" in command:
            volume_cfg = profile_volume_settings()
            level = volume_cfg["down_start"] if last_volume_level is None else max(0, last_volume_level - volume_cfg["step"])
            last_volume_level = level
            spotify_set_volume(level)
            reply(f"Volume {level} percent")
            return

        if command in {"mute", "toggle mute", "mute audio"}:
            if spotify_toggle_mute():
                reply("Mute toggled")
            else:
                reply("Mute is unavailable on this setup")
            return

        volume_hint = any(tag in command for tag in ["volume", "vol", "voue", "volum", "audio"])
        volume_match = re.search(r"(?:set\s+)?(?:volume|vol|voue|volum)(?:\s+to)?\s+(\d{1,3})", command)
        if not volume_match and volume_hint:
            number_match = re.search(r"(\d{1,3})", command)
            if number_match:
                volume_match = number_match

        if volume_match:
            level = max(0, min(100, int(volume_match.group(1))))
            last_volume_level = level
            spotify_set_volume(level)
            reply(f"Volume {level} percent")
            return

        # ── Feature: Open app by voice ────────────────────────────────────
        open_match = re.match(r"^open\s+(.+)$", command)
        if open_match:
            app_name = open_match.group(1).strip()
            app_map = {
                "chrome":      ["google-chrome", "chromium-browser", "chromium"],
                "firefox":     ["firefox"],
                "terminal":    ["gnome-terminal", "xterm", "konsole", "xfce4-terminal"],
                "files":       ["nautilus", "thunar", "dolphin"],
                "spotify":     ["spotify"],
                "vscode":      ["code"],
                "calculator":  ["gnome-calculator", "kcalc"],
                "settings":    ["gnome-control-center", "systemsettings5"],
            }
            candidates = app_map.get(app_name)
            if not candidates:
                for key, cmds in app_map.items():
                    if key in app_name or app_name in key:
                        candidates = cmds
                        break
            if not candidates:
                candidates = [app_name]
            launched = False
            for cmd in candidates:
                if shutil.which(cmd):
                    subprocess.Popen([cmd], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    reply(f"Opening {app_name}")
                    launched = True
                    break
            if not launched:
                reply(f"Could not find {app_name} on this system")
            return

        # ── Feature: System info ──────────────────────────────────────────
        if any(w in command for w in ["battery", "power level", "how much battery"]):
            try:
                capacity = Path("/sys/class/power_supply/BAT0/capacity").read_text().strip()
                status = Path("/sys/class/power_supply/BAT0/status").read_text().strip()
                reply(f"Battery is at {capacity} percent and {status.lower()}")
            except Exception:
                reply("Battery information is not available on this device")
            return

        if any(w in command for w in ["cpu usage", "cpu load", "processor usage"]):
            try:
                result = subprocess.run(["top", "-bn1"], capture_output=True, text=True, timeout=5)
                for line in result.stdout.splitlines():
                    if "Cpu(s)" in line or "%Cpu" in line:
                        idle_match = re.search(r"(\d+\.?\d*)\s*(?:id|idle)", line)
                        if idle_match:
                            usage = round(100 - float(idle_match.group(1)), 1)
                            reply(f"CPU usage is {usage} percent")
                            return
                reply("Could not read CPU usage")
            except Exception:
                reply("CPU information is not available")
            return

        if any(w in command for w in ["ram usage", "memory usage", "how much ram", "memory left"]):
            try:
                result = subprocess.run(["free", "-m"], capture_output=True, text=True, timeout=3)
                for line in result.stdout.splitlines():
                    if line.startswith("Mem:"):
                        parts = line.split()
                        total, used = int(parts[1]), int(parts[2])
                        pct = round(used / total * 100)
                        reply(f"RAM is {used} of {total} megabytes used, {pct} percent")
                        return
                reply("Could not read memory info")
            except Exception:
                reply("Memory information is not available")
            return

        # ── Feature: Voice timer ──────────────────────────────────────────
        timer_match = re.search(
            r"(?:set\s+)?timer\s+(?:for\s+)?(\d+)\s*(minute|minutes|second|seconds|min|sec|m|s)\b",
            command,
        )
        if timer_match:
            amount = int(timer_match.group(1))
            unit = timer_match.group(2).lower()
            seconds = amount * 60 if unit.startswith("m") else amount
            label = f"{amount} {'minute' if unit.startswith('m') else 'second'}{'s' if amount != 1 else ''}"

            def _timer(secs, lbl):
                time.sleep(secs)
                speak(f"Timer done. {lbl} is up.")

            threading.Thread(target=_timer, args=(seconds, label), daemon=True).start()
            reply(f"Timer set for {label}")
            return

        # ── Feature: Read clipboard ───────────────────────────────────────
        if any(w in command for w in ["read clipboard", "what's in clipboard", "whats in clipboard", "show clipboard"]):
            clipboard_tools = [
                ["xclip", "-selection", "clipboard", "-o"],
                ["xsel", "--clipboard", "--output"],
            ]
            for tool in clipboard_tools:
                if shutil.which(tool[0]):
                    try:
                        result = subprocess.run(tool, capture_output=True, text=True, timeout=3)
                        text_clip = result.stdout.strip()
                        if text_clip:
                            reply(f"Clipboard says: {text_clip[:120]}")
                        else:
                            reply("Clipboard is empty")
                        return
                    except Exception:
                        pass
            reply("Clipboard tool not found. Install xclip with: sudo apt install xclip")
            return

        reply(chat_reply(command))

    voice_phrase_seconds = float(os.getenv("VOICE_PHRASE_SECONDS", "4.0"))
    voice_cooldown_seconds = float(os.getenv("VOICE_COOLDOWN_SECONDS", "0.35"))
    voice_suppress_seconds = float(os.getenv("VOICE_SUPPRESS_SECONDS", "1.2"))
    voice_wake_window_seconds = float(os.getenv("VOICE_WAKE_WINDOW_SECONDS", "8.0"))

    voice_listener = VoiceCommandListener(
        on_command=handle_voice_command,
        on_wake=handle_voice_wake,
        on_heard=handle_voice_heard,
        on_state=handle_voice_state,
        on_error=lambda message: print(message),
        phrase_seconds=voice_phrase_seconds,
        cooldown_seconds=voice_cooldown_seconds,
        callback_suppress_seconds=voice_suppress_seconds,
        wake_window_seconds=voice_wake_window_seconds,
        require_wake_word=False,
    )
    voice_listener.start()

    # Warm up local LLM server once at startup so first query is fast.
    ensure_ollama_server_running(os.getenv("AI_LOCAL_API_BASE", "http://127.0.0.1:11434"))
    startup_checks = collect_startup_checks()
    startup_checks_last_refresh = time.time()

    while True:
        ret, frame = cap.read()
        if not ret:
            print(f"Camera read failed on index {camera_index}. Closing app.")
            break

        fps_counter += 1
        fps_now = time.time()
        fps_elapsed = fps_now - fps_last_time
        if fps_elapsed >= 0.5:
            fps_value = fps_counter / fps_elapsed
            fps_counter = 0
            fps_last_time = fps_now

        frame = cv2.flip(frame, 1)
        h, w, _ = frame.shape

        if canvas is None:
            canvas = np.zeros((h, w, 3), np.uint8)

        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = hands.process(rgb_frame)

        gesture_name = "NONE"
        pinch_active = False
        jarvis_active = False
        switch_countdown = None
        display_mode = current_mode

        detected_count = None
        pinch_detected = False
        palm_center = None
        jarvis_angle = 0
        jarvis_render_targets = []

        if results.multi_hand_landmarks:
            for hand_index, hl_all in enumerate(results.multi_hand_landmarks):
                warm_theme = warm_palette_for_hand(hand_index)
                landmark_color = (120, 220, 255) if warm_theme else (255, 220, 120)
                connector_color = (95, 175, 235) if warm_theme else (210, 170, 70)
                landmark_style = mp_draw.DrawingSpec(color=landmark_color, thickness=2, circle_radius=2)
                connector_style = mp_draw.DrawingSpec(color=connector_color, thickness=2, circle_radius=1)
                mp_draw.draw_landmarks(
                    frame,
                    hl_all,
                    mp_hands.HAND_CONNECTIONS,
                    landmark_style,
                    connector_style,
                )
                lm_all = hl_all.landmark

                detected_count_all = count_raised_fingers(lm_all)

                if current_mode == "GESTURE" and not voice_enabled and detected_count_all == 5:
                    palm_points_all = [0, 1, 5, 9, 13, 17]
                    base_center_x_all = sum(lm_all[idx].x for idx in palm_points_all) / len(palm_points_all)
                    base_center_y_all = sum(lm_all[idx].y for idx in palm_points_all) / len(palm_points_all)
                    dir_x_all = lm_all[9].x - lm_all[0].x
                    dir_y_all = lm_all[9].y - lm_all[0].y
                    lift_factor_all = 0.34
                    palm_center_all = (
                        int((base_center_x_all + dir_x_all * lift_factor_all) * w),
                        int((base_center_y_all + dir_y_all * lift_factor_all) * h),
                    )
                    index_base_all = (int(lm_all[5].x * w), int(lm_all[5].y * h))
                    dx_all = index_base_all[0] - palm_center_all[0]
                    dy_all = index_base_all[1] - palm_center_all[1]
                    jarvis_angle_all = math.degrees(math.atan2(dy_all, dx_all)) + 90
                    hand_ys_all = [point.y for point in lm_all]
                    hand_height_all = max(0.06, max(hand_ys_all) - min(hand_ys_all))
                    per_hand_scale = max(0.82, min(1.28, 0.76 + hand_height_all * 1.4))
                    per_hand_height = max(0.0, min(1.0, 1.0 - (palm_center_all[1] / max(1, h))))
                    fingertip_points_all = [
                        (int(lm_all[idx].x * w), int(lm_all[idx].y * h))
                        for idx in (4, 8, 12, 16, 20)
                    ]
                    jarvis_render_targets.append(
                        (palm_center_all, jarvis_angle_all, per_hand_scale, per_hand_height, fingertip_points_all)
                    )

            hl = results.multi_hand_landmarks[0]
            lm = hl.landmark

            detected_count = count_raised_fingers(lm)

            cx, cy = int(lm[8].x * w), int(lm[8].y * h)
            tx, ty = int(lm[4].x * w), int(lm[4].y * h)
            pinch_dist = math.hypot(cx - tx, cy - ty)
            pinch_detected = pinch_dist < 45 and detected_count <= 2

            palm_points = [0, 1, 5, 9, 13, 17]
            base_center_x = sum(lm[idx].x for idx in palm_points) / len(palm_points)
            base_center_y = sum(lm[idx].y for idx in palm_points) / len(palm_points)

            # Lift effect anchor toward fingers using hand direction (wrist -> middle MCP).
            dir_x = lm[9].x - lm[0].x
            dir_y = lm[9].y - lm[0].y
            lift_factor = 0.34
            palm_center = (
                int((base_center_x + dir_x * lift_factor) * w),
                int((base_center_y + dir_y * lift_factor) * h),
            )

            hand_xs = [point.x for point in lm]
            hand_ys = [point.y for point in lm]
            hand_height_norm = max(0.06, max(hand_ys) - min(hand_ys))
            target_distance_scale = max(0.82, min(1.25, 0.76 + hand_height_norm * 1.35))
            jarvis_distance_scale = 0.84 * jarvis_distance_scale + 0.16 * target_distance_scale

            palm_height_norm = max(0.0, min(1.0, 1.0 - (palm_center[1] / max(1, h))))
            target_height_factor = 0.90 + 0.26 * palm_height_norm
            jarvis_height_factor = 0.86 * jarvis_height_factor + 0.14 * target_height_factor

            index_base = (int(lm[5].x * w), int(lm[5].y * h))
            dx = index_base[0] - palm_center[0]
            dy = index_base[1] - palm_center[1]
            jarvis_angle = math.degrees(math.atan2(dy, dx)) + 90

            if current_mode == "GESTURE" and not voice_enabled:
                if detected_count != 0 and must_release_fist_after_spotify:
                    must_release_fist_after_spotify = False

                if detected_count == 4:
                    if spotify_trigger_time == 0:
                        spotify_trigger_time = time.time()
                    elapsed = time.time() - spotify_trigger_time
                    remaining = max(0.0, 2.0 - elapsed)
                    switch_countdown = remaining
                    gesture_name = "SWITCHING..."
                    if elapsed >= 2.0:
                        if not spotify_launch_attempted:
                            spotify_launch_attempted = True
                            launch_spotify_app()
                        set_mode("SPOTIFY")
                        display_mode = current_mode
                        gesture_name = "SPOTIFY MODE"
                else:
                    spotify_trigger_time = 0
                    spotify_launch_attempted = False

                if current_mode == "GESTURE":
                    if detected_count == 0:
                        if must_release_fist_after_spotify:
                            gesture_name = "RELEASE FIST"
                            fist_start_time = 0
                            try:
                                if sound_count:
                                    sound_count.stop()
                            except Exception:
                                pass
                        else:
                            gesture_name = "FIST"
                            if fist_start_time == 0:
                                fist_start_time = time.time()
                                try:
                                    if sound_count:
                                        sound_count.play()
                                except Exception:
                                    pass

                            if time.time() - fist_start_time > 3:
                                print("SHUTDOWN")
                                pygame.mixer.stop()
                                sys.exit()
                    elif pinch_detected:
                        pinch_action = gesture_mode_action_for_detection(detected_count, True)
                        if pinch_action:
                            gesture_name = pinch_action["label"]
                        else:
                            gesture_name = "PINCH/SPARKLE"
                        pinch_active = True

                        for _ in range(3):
                            cv2.circle(
                                canvas,
                                (
                                    cx + random.randint(-10, 10),
                                    cy + random.randint(-10, 10),
                                ),
                                3,
                                (0, 255, 255),
                                -1,
                            )
                    else:
                        gesture_action = gesture_mode_action_for_detection(detected_count, False)
                        if gesture_action:
                            gesture_name = gesture_action["label"]
                            jarvis_active = bool(gesture_action["jarvis"])
                            if gesture_action.get("screenshot"):
                                saved_path = take_screenshot(frame)
                                if saved_path:
                                    gesture_name = "SCREENSHOT SAVED"

            if current_mode == "SPOTIFY" and not voice_enabled:
                display_mode = current_mode
                spotify_trigger_time = 0
                jarvis_active = False
                pinch_active = False

                if detected_count == 0:
                    if spotify_exit_start_time == 0:
                        spotify_exit_start_time = time.time()
                    elapsed = time.time() - spotify_exit_start_time
                    switch_countdown = max(0.0, 3.0 - elapsed)
                    gesture_name = "EXITING TO GESTURE"
                    spotify_wait_release = False
                    spotify_pending_gesture = None

                    if elapsed >= 3.0:
                        must_release_fist_after_spotify = True
                        fist_start_time = 0
                        set_mode("GESTURE")
                        display_mode = current_mode
                        last_spotify_gesture = None
                        spotify_exit_start_time = 0
                else:
                    spotify_exit_start_time = 0
                    now = time.time()
                    mapped = spotify_action_for_count(detected_count)

                    if not mapped:
                        gesture_name = "SPOTIFY READY"
                        spotify_pending_gesture = None
                        spotify_wait_release = False
                        last_spotify_gesture = None
                    else:
                        gesture_key, gesture_label, action = mapped
                        gesture_name = gesture_label

                        if spotify_wait_release:
                            gesture_name = f"{gesture_label} (RELEASE)"
                            spotify_pending_gesture = None
                        else:
                            if spotify_pending_gesture != gesture_key:
                                spotify_pending_gesture = gesture_key
                                spotify_pending_since = now

                            hold_elapsed = now - spotify_pending_since
                            cooldown_left = max(0.0, SPOTIFY_COOLDOWN_SECONDS - (now - spotify_last_action_time))

                            if hold_elapsed >= SPOTIFY_HOLD_SECONDS and cooldown_left <= 0.0:
                                action()
                                last_spotify_gesture = gesture_key
                                spotify_last_action_time = now
                                spotify_wait_release = True
                                spotify_pending_gesture = None
                            elif hold_elapsed < SPOTIFY_HOLD_SECONDS:
                                gesture_name = f"{gesture_label} ({SPOTIFY_HOLD_SECONDS - hold_elapsed:0.1f}s)"
                            elif cooldown_left > 0.0:
                                gesture_name = f"{gesture_label} ({cooldown_left:0.1f}s)"

        else:
            spotify_trigger_time = 0

        if current_mode == "GESTURE" and not voice_enabled:
            jarvis_active = bool(jarvis_render_targets)

        if screenshot_wait_release and detected_count != 2:
            screenshot_wait_release = False

        if gesture_name != "FIST":
            fist_start_time = 0
            try:
                if sound_count:
                    sound_count.stop()
            except Exception:
                pass

        if current_mode == "GESTURE" and jarvis_active and jarvis_render_targets:
            sorted_targets = sorted(jarvis_render_targets, key=lambda item: item[0][0])

            if len(sorted_targets) >= 2:
                left_center = sorted_targets[0][0]
                right_center = sorted_targets[1][0]
                bridge_overlay = frame.copy()
                bridge_len = max(1.0, math.hypot(right_center[0] - left_center[0], right_center[1] - left_center[1]))
                bridge_strength = max(0.2, min(1.0, bridge_len / max(1, w * 0.62)))
                bridge_phase = time.time() * 6.0

                for strand in range(render_tuning["bridge_strands"]):
                    wave = int((strand - 1.5) * 4 + 8 * math.sin(bridge_phase + strand * 1.1))
                    p1 = (left_center[0], left_center[1] + wave)
                    p2 = (right_center[0], right_center[1] - wave)
                    strand_color = (int(120 + 40 * strand), int(150 + 12 * strand), int(220 - 15 * strand))
                    cv2.line(bridge_overlay, p1, p2, strand_color, 1 + (strand % 2))

                # Dual-hand reactor tunnel ring pulses between palms.
                link_mid = (
                    (left_center[0] + right_center[0]) // 2,
                    (left_center[1] + right_center[1]) // 2,
                )
                for n in range(render_tuning["bridge_rings"]):
                    wave_r = int(22 + n * 16 + 6 * math.sin(bridge_phase + n * 1.3))
                    cv2.ellipse(
                        bridge_overlay,
                        link_mid,
                        (wave_r, int(max(10, wave_r * 0.42))),
                        math.degrees(math.atan2(right_center[1] - left_center[1], right_center[0] - left_center[0])),
                        0,
                        360,
                        (110 + n * 30, 175 + n * 18, 245),
                        1,
                    )

                steps = render_tuning["bridge_steps"]
                for step in range(1, steps):
                    blend = step / steps
                    px = int(left_center[0] * (1 - blend) + right_center[0] * blend)
                    py = int(left_center[1] * (1 - blend) + right_center[1] * blend)
                    sparkle = int(2 + 2 * math.sin(time.time() * 10 + step))
                    cv2.circle(bridge_overlay, (px, py), max(1, sparkle), (255, 240, 180), -1)

                cv2.addWeighted(bridge_overlay, 0.28 + 0.12 * bridge_strength, frame, 0.72 - 0.12 * bridge_strength, 0, frame)

            for idx, (center, render_angle, per_hand_scale, per_hand_height, fingertip_points) in enumerate(sorted_targets):
                t = time.time()
                phase = idx * 0.42
                global_scale = jarvis_distance_scale * (0.90 + 0.22 * jarvis_height_factor)
                hand_scale = per_hand_scale * (0.90 + 0.22 * (0.90 + 0.26 * per_hand_height))
                blended_scale = 0.55 * global_scale + 0.45 * hand_scale
                dynamic_scale = max(0.76, min(1.36, blended_scale))
                pulse_rate = 3.0 + (dynamic_scale - 1.0) * 2.1
                sweep_speed = 88 + (dynamic_scale - 1.0) * 74 + (jarvis_height_factor - 1.0) * 35
                pulse = 0.72 + 0.28 * (0.5 + 0.5 * math.sin((t + phase) * pulse_rate))
                sweep = ((render_angle + phase * 32) * 1.8 + t * sweep_speed) % 360
                twinkle = 0.5 + 0.5 * math.sin((t + phase) * 8.2)

                warm_theme = warm_palette_for_hand(idx)
                if warm_theme:
                    neon_core = (255, 220, 60)
                    neon_ring = (255, 200, 70)
                    neon_soft = (170, 120, 35)
                    steel = (95, 105, 120)
                else:
                    neon_core = (120, 245, 255)
                    neon_ring = (95, 225, 255)
                    neon_soft = (52, 128, 160)
                    steel = (95, 120, 138)

                glow = frame.copy()
                max_r = int((146 + 8 * pulse) * dynamic_scale)
                for radius, color, thickness in [
                    (max_r, (40, 55, 85), -1),
                    (int(max_r * 0.78), (28, 42, 64), -1),
                    (int(max_r * 0.54), (20, 30, 46), -1),
                ]:
                    cv2.circle(glow, center, radius, color, thickness)
                cv2.addWeighted(glow, 0.36, frame, 0.64, 0, frame)

                outer_r = int((130 + 5 * pulse) * dynamic_scale)
                mid_r = int((106 + 4 * pulse) * dynamic_scale)
                inner_r = int((78 + 3 * pulse) * dynamic_scale)

                cv2.circle(frame, center, outer_r, steel, 1)
                cv2.circle(frame, center, mid_r, (120, 140, 170) if warm_theme else (130, 180, 215), 2)
                cv2.circle(frame, center, inner_r, neon_soft, 1)

                # Soft crosshair bloom at center.
                bloom_len = int((62 + 5 * pulse) * dynamic_scale)
                cv2.line(
                    frame,
                    (center[0] - bloom_len, center[1]),
                    (center[0] + bloom_len, center[1]),
                    (120, 110, 85),
                    1,
                )
                cv2.line(
                    frame,
                    (center[0], center[1] - bloom_len),
                    (center[0], center[1] + bloom_len),
                    (120, 110, 85),
                    1,
                )

                for i in range(0, 360, render_tuning["tick_step"]):
                    ang = math.radians(i + sweep * 0.35)
                    x1 = int(center[0] + (inner_r + 8) * math.cos(ang))
                    y1 = int(center[1] + (inner_r + 8) * math.sin(ang))
                    x2 = int(center[0] + (mid_r - 8) * math.cos(ang))
                    y2 = int(center[1] + (mid_r - 8) * math.sin(ang))
                    cv2.line(frame, (x1, y1), (x2, y2), (95, 105, 122), 1)

                # Rotating segmented arcs for a more premium scanner look.
                arc_sets = [
                    (outer_r - 10, sweep, 58, neon_ring, 2),
                    (outer_r - 10, sweep + 165, 42, (200, 165, 65) if warm_theme else (115, 195, 230), 2),
                    (mid_r - 8, -sweep * 1.2, 68, neon_core, 2),
                    (mid_r - 8, -sweep * 1.2 + 205, 34, (190, 145, 55) if warm_theme else (90, 170, 210), 2),
                    (inner_r - 8, sweep * 1.6, 85, (255, 235, 120) if warm_theme else (175, 245, 255), 2),
                ]
                for radius, start, span, color, thick in arc_sets:
                    cv2.ellipse(frame, center, (radius, radius), 0, start, start + span, color, thick)

                # Add layered cinematic rings for arc-reactor style depth.
                cv2.ellipse(
                    frame,
                    center,
                    (outer_r - 22, outer_r - 22),
                    sweep * 0.45,
                    30,
                    310,
                    (140, 175, 230) if warm_theme else (120, 220, 255),
                    1,
                )
                cv2.ellipse(
                    frame,
                    center,
                    (mid_r - 18, mid_r - 18),
                    -sweep * 0.75,
                    0,
                    260,
                    (255, 210, 110) if warm_theme else (135, 230, 255),
                    1,
                )
                cv2.ellipse(
                    frame,
                    center,
                    (inner_r - 14, inner_r - 14),
                    sweep * 1.2,
                    80,
                    360,
                    (255, 240, 150) if warm_theme else (190, 250, 255),
                    1,
                )

                # Orbiting glints for depth.
                glint_r = mid_r + 6
                for offset in (0, 120, 240):
                    ang = math.radians(sweep * 1.25 + offset)
                    gx = int(center[0] + glint_r * math.cos(ang))
                    gy = int(center[1] + glint_r * math.sin(ang))
                    glow_size = 3 if (offset == 0 and twinkle > 0.65) else 2
                    cv2.circle(frame, (gx, gy), glow_size, (255, 235, 150) if warm_theme else (190, 245, 255), -1)

                # Sweep beam accent.
                beam_ang = math.radians(sweep)
                bx = int(center[0] + (outer_r - 14) * math.cos(beam_ang))
                by = int(center[1] + (outer_r - 14) * math.sin(beam_ang))
                cv2.line(frame, center, (bx, by), (255, 230, 120) if warm_theme else (150, 240, 255), 2)
                cv2.circle(frame, (bx, by), 5, (255, 235, 145) if warm_theme else (205, 250, 255), -1)

                # Beam trail for more cinematic motion.
                for trail_idx in range(1, render_tuning["trail_layers"] + 1):
                    trail_ang = math.radians(sweep - trail_idx * 8)
                    tx = int(center[0] + (outer_r - 18 - trail_idx * 3) * math.cos(trail_ang))
                    ty = int(center[1] + (outer_r - 18 - trail_idx * 3) * math.sin(trail_ang))
                    if warm_theme:
                        trail_color = (210 - trail_idx * 30, 180 - trail_idx * 20, 110 - trail_idx * 15)
                    else:
                        trail_color = (130 - trail_idx * 14, 210 - trail_idx * 22, 235 - trail_idx * 20)
                    cv2.line(frame, center, (tx, ty), trail_color, 1)

                core_outer = int((39 + 3 * pulse) * dynamic_scale)
                core_inner = int((18 + 2 * pulse) * dynamic_scale)
                cv2.circle(frame, center, core_outer, neon_ring, 2)
                cv2.circle(frame, center, core_inner + 8, (255, 245, 185) if warm_theme else (205, 250, 255), -1)
                cv2.circle(frame, center, core_inner, (255, 255, 255), -1)

                # Inner rotating triangle and braces for a HUD-like look.
                tri_r = core_inner + 24
                tri_pts = []
                for i in range(3):
                    tri_ang = math.radians(sweep * 1.1 + i * 120)
                    tri_pts.append(
                        [
                            int(center[0] + tri_r * math.cos(tri_ang)),
                            int(center[1] + tri_r * math.sin(tri_ang)),
                        ]
                    )
                cv2.polylines(frame, [np.array(tri_pts, np.int32)], True, (255, 225, 120) if warm_theme else (170, 245, 255), 1)

                brace_r = inner_r - 18
                for angle_offset in (45, 135, 225, 315):
                    a = math.radians(angle_offset + sweep * 0.4)
                    bx1 = int(center[0] + brace_r * math.cos(a))
                    by1 = int(center[1] + brace_r * math.sin(a))
                    bx2 = int(center[0] + (brace_r + 10) * math.cos(a))
                    by2 = int(center[1] + (brace_r + 10) * math.sin(a))
                    cv2.line(frame, (bx1, by1), (bx2, by2), (210, 175, 90) if warm_theme else (120, 210, 245), 2)

                hex_pts = []
                for i in range(6):
                    ang = math.radians(i * 60 + sweep * 0.9)
                    x = int(center[0] + (core_inner + 14) * math.cos(ang))
                    y = int(center[1] + (core_inner + 14) * math.sin(ang))
                    hex_pts.append([x, y])
                cv2.polylines(frame, [np.array(hex_pts, np.int32)], True, (255, 220, 95) if warm_theme else (150, 240, 255), 2)

                for i in range(12):
                    ang = math.radians(i * 30 + sweep * 0.55)
                    r = outer_r - 2
                    x = int(center[0] + r * math.cos(ang))
                    y = int(center[1] + r * math.sin(ang))
                    size = 2 if i % 2 == 0 else 3
                    cv2.circle(frame, (x, y), size, (230, 195, 85) if warm_theme else (130, 220, 250), -1)

                # Micro particles that shimmer near the outer ring.
                particle_count = int(render_tuning["particles_base"] + render_tuning["particles_amp"] * twinkle)
                for i in range(particle_count):
                    p_ang = math.radians((sweep * 1.6 + i * (360 / max(1, particle_count))) % 360)
                    p_r = outer_r + 8 + (i % 3) * 3
                    px = int(center[0] + p_r * math.cos(p_ang))
                    py = int(center[1] + p_r * math.sin(p_ang))
                    cv2.circle(frame, (px, py), 1, (255, 240, 170) if warm_theme else (190, 248, 255), -1)

                # Cinematic wave shell and rotating chevrons.
                shell_overlay = frame.copy()
                shell_r = outer_r + 18
                for band in range(render_tuning["shell_bands"]):
                    start_ang = (sweep * (1.2 + band * 0.18) + band * 80) % 360
                    span = 52 + band * 16
                    shell_color = (145 + band * 30, 170 + band * 18, 245 - band * 20) if not warm_theme else (250 - band * 22, 205 - band * 14, 120 - band * 12)
                    cv2.ellipse(shell_overlay, center, (shell_r + band * 8, shell_r + band * 8), 0, start_ang, start_ang + span, shell_color, 2)
                cv2.addWeighted(shell_overlay, 0.20, frame, 0.80, 0, frame)

                for k in range(render_tuning["chevrons"]):
                    ang = math.radians((sweep * 0.9 + k * 45) % 360)
                    base_r = inner_r + 18
                    p1 = (
                        int(center[0] + base_r * math.cos(ang)),
                        int(center[1] + base_r * math.sin(ang)),
                    )
                    p2 = (
                        int(center[0] + (base_r + 12) * math.cos(ang + 0.08)),
                        int(center[1] + (base_r + 12) * math.sin(ang + 0.08)),
                    )
                    p3 = (
                        int(center[0] + (base_r + 12) * math.cos(ang - 0.08)),
                        int(center[1] + (base_r + 12) * math.sin(ang - 0.08)),
                    )
                    cv2.polylines(frame, [np.array([p1, p2, p3], np.int32)], True, (245, 220, 140) if warm_theme else (170, 245, 255), 1)

                # Radial flicker lines to amplify reactor energy.
                for ray in range(render_tuning["rays"]):
                    a = math.radians(ray * 22.5 + sweep * 0.55)
                    r1 = core_inner + 6
                    r2 = inner_r - 6
                    rx1 = int(center[0] + r1 * math.cos(a))
                    ry1 = int(center[1] + r1 * math.sin(a))
                    rx2 = int(center[0] + r2 * math.cos(a))
                    ry2 = int(center[1] + r2 * math.sin(a))
                    if ray % 2 == 0:
                        cv2.line(frame, (rx1, ry1), (rx2, ry2), (180, 175, 130) if warm_theme else (140, 210, 230), 1)

                # Trailing afterimage for faster perceived motion.
                trail_overlay = frame.copy()
                for trail in range(1, render_tuning["trail_layers"] + 1):
                    ta = math.radians(sweep - trail * 14)
                    tr = outer_r - 24
                    tx = int(center[0] + tr * math.cos(ta))
                    ty = int(center[1] + tr * math.sin(ta))
                    cv2.circle(trail_overlay, (tx, ty), max(2, 6 - trail), (255, 230, 150) if warm_theme else (180, 245, 255), -1)
                cv2.addWeighted(trail_overlay, 0.18, frame, 0.82, 0, frame)

                # Finger energy threads that stretch with palm-to-fingertip distance.
                thread_overlay = frame.copy()
                for finger_i, tip_pt in enumerate(fingertip_points):
                    dx_tip = tip_pt[0] - center[0]
                    dy_tip = tip_pt[1] - center[1]
                    finger_dist = max(1.0, math.hypot(dx_tip, dy_tip))
                    dist_norm = max(0.0, min(1.0, finger_dist / max(1.0, 0.40 * h)))
                    # More stretch -> stronger displacement and brighter strands.
                    stretch_amp = 4 + 9 * dist_norm

                    angle = math.atan2(dy_tip, dx_tip)
                    perp_x = -math.sin(angle)
                    perp_y = math.cos(angle)
                    phase_base = t * (8.0 + finger_i * 0.65) + finger_i * 0.9 + phase

                    points = []
                    segments = render_tuning["thread_segments"]
                    for s in range(segments + 1):
                        u = s / segments
                        bx = center[0] + dx_tip * u
                        by = center[1] + dy_tip * u
                        # Taper wave near center and tip for cleaner anchors.
                        envelope = math.sin(math.pi * u)
                        wave = math.sin(phase_base + u * 9.5) * stretch_amp * envelope
                        px = int(bx + perp_x * wave)
                        py = int(by + perp_y * wave)
                        points.append([px, py])

                    thread_color = (255, 220, 120) if warm_theme else (160, 245, 255)
                    glow_color = (210, 175, 90) if warm_theme else (115, 205, 240)
                    cv2.polylines(thread_overlay, [np.array(points, np.int32)], False, glow_color, 3)
                    cv2.polylines(thread_overlay, [np.array(points, np.int32)], False, thread_color, 1)

                    # Moving plasma pulses along each thread.
                    pulse_u = (0.12 * finger_i + (t * 0.85) % 1.0)
                    pulse_idx = max(0, min(len(points) - 1, int(pulse_u * (len(points) - 1))))
                    pulse_pt = points[pulse_idx]
                    pulse_size = int(2 + 3 * dist_norm)
                    cv2.circle(thread_overlay, tuple(pulse_pt), pulse_size, (255, 245, 190), -1)

                    # Anchor spark at fingertip.
                    cv2.circle(thread_overlay, tip_pt, int(2 + 2 * dist_norm), thread_color, -1)

                cv2.addWeighted(thread_overlay, 0.34, frame, 0.66, 0, frame)

                cv2.putText(
                    frame,
                    "JARVIS",
                    (center[0] - 34, center[1] + outer_r + 22),
                    cv2.FONT_HERSHEY_DUPLEX,
                    0.56,
                    (20, 20, 20),
                    3,
                )
                cv2.putText(
                    frame,
                    "JARVIS",
                    (center[0] - 33, center[1] + outer_r + 21),
                    cv2.FONT_HERSHEY_DUPLEX,
                    0.56,
                    (250, 230, 150) if warm_theme else (185, 245, 255),
                    2,
                )

        if jarvis_active:
            if not is_jarvis_playing:
                try:
                    pygame.mixer.stop()
                    if sound_jarvis:
                        sound_jarvis.play(-1)
                    is_jarvis_playing = True
                except Exception:
                    pass
        else:
            if is_jarvis_playing:
                try:
                    if sound_jarvis:
                        sound_jarvis.stop()
                    is_jarvis_playing = False
                except Exception:
                    pass

        if pinch_active:
            if not is_sparkle_playing:
                try:
                    if sound_sparkle:
                        sound_sparkle.play(-1)
                    is_sparkle_playing = True
                except Exception:
                    pass
        else:
            if is_sparkle_playing:
                try:
                    if sound_sparkle:
                        sound_sparkle.stop()
                    is_sparkle_playing = False
                except Exception:
                    pass

        last_pinch_state = pinch_detected

        canvas = cv2.subtract(canvas, (15, 15, 15, 0))
        frame = cv2.add(frame, canvas)

        mode_color = (0, 255, 0) if current_mode == "GESTURE" else (0, 200, 255)
        color = (0, 255, 0) if gesture_name != "FIST" else (0, 0, 255)

        now = time.time()
        if now - startup_checks_last_refresh >= 2.0:
            startup_checks = collect_startup_checks()
            startup_checks_last_refresh = now

        overlay = frame.copy()
        cv2.rectangle(overlay, (0, 0), (w, 280), (20, 24, 32), -1)
        cv2.rectangle(overlay, (0, h - 60), (w, h), (16, 20, 28), -1)
        cv2.addWeighted(overlay, 0.34, frame, 0.66, 0, frame)

        cv2.putText(frame, "JARVIS CONTROL HUD", (18, 30), 1, 1.0, (240, 240, 255), 2)
        cv2.line(frame, (18, 36), (260, 36), (90, 140, 255), 2)
        cv2.putText(
            frame,
            f"BUILD {app_build_tag}  THEME {visual_theme.upper()}  RENDER {render_quality.upper()}",
            (18, 54),
            1,
            0.64,
            (164, 184, 230),
            1,
        )

        cv2.putText(frame, f"MODE", (20, 68), 1, 0.9, (165, 190, 240), 2)
        cv2.putText(frame, f"{display_mode}", (130, 68), 1, 1.1, mode_color, 2)

        cv2.putText(frame, "GESTURE", (20, 102), 1, 0.9, (165, 190, 240), 2)
        cv2.putText(frame, f"{gesture_name}", (130, 102), 1, 1.1, color, 2)

        voice_color = (0, 220, 110) if voice_enabled else (0, 150, 220)
        cv2.putText(frame, "VOICE", (20, 136), 1, 0.9, (165, 190, 240), 2)
        cv2.putText(frame, "ON" if voice_enabled else "OFF", (130, 136), 1, 1.1, voice_color, 2)

        cv2.putText(frame, "STATE", (20, 170), 1, 0.9, (165, 190, 240), 2)
        cv2.putText(frame, f"{voice_state}", (130, 170), 1, 0.95, (210, 210, 210), 2)

        cv2.putText(frame, "HEARD", (20, 204), 1, 0.9, (165, 190, 240), 2)
        cv2.putText(frame, f"{voice_last_heard[:44]}", (130, 204), 1, 0.9, (190, 190, 190), 2)

        cv2.putText(frame, "REPLY", (20, 238), 1, 0.9, (165, 190, 240), 2)
        cv2.putText(frame, f"{voice_last_command[:48]}", (130, 238), 1, 0.9, (210, 210, 210), 2)

        cv2.putText(frame, "PROFILE", (20, 272), 1, 0.9, (165, 190, 240), 2)
        cv2.putText(frame, f"{get_active_profile_name()}", (130, 272), 1, 0.9, (210, 210, 210), 2)

        panel_x = max(20, w - 306)
        panel_y = 18
        panel_w = 286
        panel_h = 168
        cv2.rectangle(frame, (panel_x, panel_y), (panel_x + panel_w, panel_y + panel_h), (22, 28, 38), -1)
        cv2.rectangle(frame, (panel_x, panel_y), (panel_x + panel_w, panel_y + panel_h), (88, 116, 170), 1)
        cv2.putText(frame, "SYSTEM CHECKS", (panel_x + 12, panel_y + 28), 1, 1.0, (240, 240, 255), 2)

        check_items = ["MIC", "OLLAMA", "SPOTIFY"]
        for index, key in enumerate(check_items):
            ok = bool(startup_checks.get(key))
            label = "OK" if ok else "MISSING"
            status_color = (0, 220, 0) if ok else (0, 0, 255)
            y = panel_y + 56 + index * 25
            cv2.putText(frame, f"{key}", (panel_x + 14, y), 1, 0.9, (220, 220, 220), 2)
            cv2.putText(frame, ":", (panel_x + 124, y), 1, 0.9, (140, 140, 140), 2)
            cv2.putText(frame, label, (panel_x + 150, y), 1, 0.9, status_color, 2)

        if show_fps:
            fps_text = f"FPS {fps_value:0.1f}"
            cv2.putText(frame, fps_text, (panel_x + 176, panel_y + panel_h + 24), 1, 0.85, (145, 220, 255), 2)

        bottom_hint = "Press V: Voice Toggle   Esc: Exit"
        cv2.putText(frame, bottom_hint, (18, h - 22), 1, 0.8, (185, 200, 240), 2)

        if switch_countdown is not None and current_mode == "GESTURE":
            cv2.putText(frame, "Switching...", (w // 2 - 170, h // 2 - 30), 1, 2.2, (0, 200, 255), 4)
            cv2.putText(
                frame,
                f"{switch_countdown:0.1f}s",
                (w // 2 - 70, h // 2 + 35),
                1,
                3,
                (0, 200, 255),
                4,
            )

        if fist_start_time > 0 and current_mode == "GESTURE":
            cd = 3 - int(time.time() - fist_start_time)
            cv2.putText(frame, str(max(0, cd)), (w // 2 - 50, h // 2), 1, 12, (0, 0, 255), 15)

        cv2.imshow("JARVIS Interface", frame)

        key = cv2.waitKey(1) & 0xFF

        if key == ord("v"):
            voice_enabled = not voice_enabled
            voice_listener.set_enabled(voice_enabled)
            voice_last_command = "VOICE ON" if voice_enabled else "VOICE OFF"
            print(f"Voice control {'enabled' if voice_enabled else 'disabled'}")

        if key == 27:
            break

    cap.release()
    if voice_listener:
        voice_listener.stop()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
