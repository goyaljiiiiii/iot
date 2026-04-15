import glob
import math
import random
import os
import re
import shutil
import subprocess
import sys
import time
import warnings
from pathlib import Path
from datetime import datetime

import cv2
import mediapipe as mp
import numpy as np
import pygame
import requests
import serial

try:
    import sounddevice as sd
except Exception:
    sd = None

from iot_control.spotify import create_spotify_client
from iot_control.voice import VoiceCommandListener


ROOT_DIR = Path(__file__).resolve().parents[1]
AUDIO_DIR = ROOT_DIR / "audios"


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

    pygame.mixer.pre_init(44100, -16, 2, 512)
    pygame.mixer.init()

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

    sound_count = load_sound("count.mp3")
    sound_click = load_sound("click.mp3")
    sound_sparkle = load_sound("sparkle.mp3")
    sound_jarvis = load_sound("jarvis.wav")

    ports = glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*")
    arduino = serial.Serial(ports[0], 9600, timeout=0) if ports else None

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
    last_sent = ""
    fist_start_time = 0
    is_sparkle_playing = False
    is_jarvis_playing = False
    current_mode = "IOT"
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
    MAX_CHAT_HISTORY_MESSAGES = 8
    startup_checks_last_refresh = 0.0
    startup_checks = {
        "MIC": False,
        "OLLAMA": False,
        "SPOTIFY": False,
        "ARDUINO": False,
    }

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
            "ARDUINO": arduino is not None,
        }

    def speak(text):
        if shutil.which("spd-say"):
            subprocess.Popen(["spd-say", text], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return

        if shutil.which("espeak"):
            subprocess.Popen(["espeak", text], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return

        print(f"TTS unavailable: {text}")

    def send_arduino(command):
        nonlocal last_sent

        if not arduino or not command:
            return

        if command == last_sent:
            return

        try:
            arduino.write(command.encode())
            last_sent = command
            print(f"Sent to Arduino: {command}")
            if command != "0" and sound_click:
                sound_click.play()
        except Exception as e:
            print(f"Arduino Error: {e}")

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
        nonlocal current_mode, spotify_trigger_time, spotify_exit_start_time, last_sent, last_volume_level, last_spotify_gesture, spotify_launch_attempted
        nonlocal spotify_pending_gesture, spotify_pending_since, spotify_last_action_time, spotify_wait_release

        if current_mode == mode:
            return

        current_mode = mode
        spotify_trigger_time = 0
        spotify_exit_start_time = 0
        last_sent = ""
        last_volume_level = None
        last_spotify_gesture = None
        spotify_launch_attempted = False
        spotify_pending_gesture = None
        spotify_pending_since = 0.0
        spotify_last_action_time = 0.0
        spotify_wait_release = False
        print(f"Mode switched to {current_mode}")

        if current_mode == "IOT":
            send_arduino("G")

    def reply(text):
        nonlocal voice_last_command
        voice_last_command = text
        speak(text)

    def chat_reply(user_text):
        nonlocal voice_chat_history

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

        local_base = os.getenv("AI_LOCAL_API_BASE", "http://127.0.0.1:11434")
        local_model = os.getenv("AI_LOCAL_MODEL", "llama3.2:3b")
        api_key = os.getenv("AI_CHAT_API_KEY") or os.getenv("OPENAI_API_KEY")
        api_base = os.getenv("AI_CHAT_API_BASE", "https://api.openai.com/v1")
        model = os.getenv("AI_CHAT_MODEL", "gpt-4o-mini")
        weather_info = weather_context(user_text)
        now_text = datetime.now().strftime("%Y-%m-%d %H:%M")

        system_prompt = (
            "You are JARVIS: concise, helpful, and speak in short replies. "
            "If live weather context is provided, use it directly and do not invent weather values. "
            f"Current local datetime is {now_text}."
        )

        prompt_text = user_text if not weather_info else f"{user_text}\n\nContext: {weather_info}"
        local_available = ensure_ollama_server_running(local_base)
        messages = [{"role": "system", "content": system_prompt}] + voice_chat_history + [
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
                        "temperature": 0.7,
                        "max_tokens": 120,
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
        if any(phrase in lower for phrase in ["how are you", "how are u", "what's up", "whats up"]):
            return "I am ready and listening."
        if any(phrase in lower for phrase in ["who are you", "what are you"]):
            return "I am JARVIS, your voice assistant."
        if any(phrase in lower for phrase in ["your name", "who am i talking", "who is this"]):
            return "I am JARVIS, your AI assistant."
        if weather_info:
            return weather_info
        if lower.endswith("?"):
            return "I can answer that. If my local model is offline, I may give shorter fallback replies."
        return "I am here. Ask me anything or give a command."

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

        command = text.strip().lower()
        command = re.sub(r"^\s*jarvis\b[\s,.:;-]*", "", command).strip()
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

        if "iot mode" in command or "go to iot" in command:
            set_mode("IOT")
            reply("I O T mode")
            return

        if "spotify mode" in command or "go to spotify" in command:
            set_mode("SPOTIFY")
            reply("Spotify mode")
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
            level = 60 if last_volume_level is None else min(100, last_volume_level + 10)
            last_volume_level = level
            spotify_set_volume(level)
            reply(f"Volume {level} percent")
            return

        if "volume down" in command or "lower volume" in command or "softer" in command:
            level = 40 if last_volume_level is None else max(0, last_volume_level - 10)
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

        reply(chat_reply(command))

    voice_listener = VoiceCommandListener(
        on_command=handle_voice_command,
        on_wake=handle_voice_wake,
        on_heard=handle_voice_heard,
        on_state=handle_voice_state,
        on_error=lambda message: print(message),
        require_wake_word=False,
    )
    voice_listener.start()

    # Warm up local LLM server once at startup so first query is fast.
    ensure_ollama_server_running(os.getenv("AI_LOCAL_API_BASE", "http://127.0.0.1:11434"))
    startup_checks = collect_startup_checks()
    startup_checks_last_refresh = time.time()

    if current_mode == "IOT":
        send_arduino("G")

    while True:
        ret, frame = cap.read()
        if not ret:
            print(f"Camera read failed on index {camera_index}. Closing app.")
            break

        frame = cv2.flip(frame, 1)
        h, w, _ = frame.shape

        if canvas is None:
            canvas = np.zeros((h, w, 3), np.uint8)

        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = hands.process(rgb_frame)

        cmd = "0"
        gesture_name = "NONE"
        pinch_active = False
        jarvis_active = False
        switch_countdown = None
        display_mode = current_mode

        detected_count = None
        pinch_detected = False
        wrist = None
        jarvis_angle = 0

        if results.multi_hand_landmarks:
            hl = results.multi_hand_landmarks[0]
            mp_draw.draw_landmarks(frame, hl, mp_hands.HAND_CONNECTIONS)
            lm = hl.landmark

            fingers = []
            if lm[4].x > lm[3].x:
                fingers.append(1)

            for tip, pip in [(8, 6), (12, 10), (16, 14), (20, 18)]:
                if lm[tip].y < lm[pip].y:
                    fingers.append(1)

            detected_count = len(fingers)

            cx, cy = int(lm[8].x * w), int(lm[8].y * h)
            tx, ty = int(lm[4].x * w), int(lm[4].y * h)
            pinch_dist = math.hypot(cx - tx, cy - ty)
            pinch_detected = pinch_dist < 45 and detected_count <= 2

            wrist = (
                int((lm[0].x + lm[9].x) / 2 * w),
                int((lm[0].y + lm[9].y) / 2 * h),
            )
            index_base = (int(lm[5].x * w), int(lm[5].y * h))
            dx = index_base[0] - wrist[0]
            dy = index_base[1] - wrist[1]
            jarvis_angle = math.degrees(math.atan2(dy, dx)) + 90

            if current_mode == "IOT" and not voice_enabled:
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

                if current_mode == "IOT":
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
                        gesture_name = "PINCH/SPARKLE"
                        cmd = "P"
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
                    elif detected_count == 1:
                        gesture_name, cmd = "ONE", "1"
                    elif detected_count == 2:
                        gesture_name, cmd = "TWO", "2"
                    elif detected_count == 3:
                        gesture_name, cmd = "THREE", "3"
                    elif detected_count == 5:
                        gesture_name = "JARVIS"
                        jarvis_active = True

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
                    gesture_name = "EXITING TO IOT"
                    spotify_wait_release = False
                    spotify_pending_gesture = None

                    if elapsed >= 3.0:
                        must_release_fist_after_spotify = True
                        fist_start_time = 0
                        set_mode("IOT")
                        display_mode = current_mode
                        last_spotify_gesture = None
                        spotify_exit_start_time = 0
                else:
                    spotify_exit_start_time = 0
                    now = time.time()
                    gesture_map = {
                        1: ("play", "PLAY", spotify_play_only),
                        2: ("pause", "PAUSE", spotify_pause_only),
                        3: ("prev", "PREVIOUS TRACK", spotify_previous_track),
                        4: ("next", "NEXT TRACK", spotify_next_track),
                    }
                    mapped = gesture_map.get(detected_count)

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

        if gesture_name != "FIST":
            fist_start_time = 0
            try:
                if sound_count:
                    sound_count.stop()
            except Exception:
                pass

        if current_mode == "IOT" and jarvis_active and wrist is not None:
            center = wrist
            jarvis_blue = (255, 255, 0)

            cv2.circle(frame, center, 170, (60, 60, 60), 1)
            cv2.circle(frame, center, 150, (90, 90, 90), 2)
            cv2.circle(frame, center, 130, jarvis_blue, 2)

            for i in range(0, 360, 12):
                angle = math.radians(i + jarvis_angle * 0.4)
                x1 = int(center[0] + 120 * math.cos(angle))
                y1 = int(center[1] + 120 * math.sin(angle))
                x2 = int(center[0] + 150 * math.cos(angle))
                y2 = int(center[1] + 150 * math.sin(angle))
                cv2.line(frame, (x1, y1), (x2, y2), (80, 80, 80), 1)

            cv2.ellipse(frame, center, (110, 110), jarvis_angle, 0, 360, jarvis_blue, 2)
            cv2.ellipse(frame, center, (90, 90), -jarvis_angle * 1.2, 0, 300, (180, 180, 180), 1)
            cv2.ellipse(frame, center, (70, 70), jarvis_angle * 1.6, 90, 360, jarvis_blue, 2)

            cv2.circle(frame, center, 45, jarvis_blue, 3)
            cv2.circle(frame, center, 25, (255, 255, 255), -1)

            for i in range(8):
                ang = math.radians(jarvis_angle * 2 + i * 45)
                x = int(center[0] + 120 * math.cos(ang))
                y = int(center[1] + 120 * math.sin(ang))
                cv2.circle(frame, (x, y), 5, jarvis_blue, -1)

            hex_pts = []
            for i in range(6):
                ang = math.radians(i * 60 + jarvis_angle)
                x = int(center[0] + 30 * math.cos(ang))
                y = int(center[1] + 30 * math.sin(ang))
                hex_pts.append([x, y])

            cv2.polylines(frame, [np.array(hex_pts, np.int32)], True, jarvis_blue, 2)

            cv2.line(frame, (center[0] - 40, center[1]), (center[0] - 90, center[1]), jarvis_blue, 2)
            cv2.line(frame, (center[0] + 40, center[1]), (center[0] + 90, center[1]), jarvis_blue, 2)
            cv2.line(frame, (center[0], center[1] - 40), (center[0], center[1] - 90), jarvis_blue, 2)
            cv2.line(frame, (center[0], center[1] + 40), (center[0], center[1] + 90), jarvis_blue, 2)

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

        if current_mode == "IOT" and not voice_enabled:
            send_arduino(cmd)

        canvas = cv2.subtract(canvas, (15, 15, 15, 0))
        frame = cv2.add(frame, canvas)

        mode_color = (0, 255, 0) if current_mode == "IOT" else (0, 200, 255)
        color = (0, 255, 0) if gesture_name != "FIST" else (0, 0, 255)

        now = time.time()
        if now - startup_checks_last_refresh >= 2.0:
            startup_checks = collect_startup_checks()
            startup_checks_last_refresh = now

        cv2.putText(frame, f"MODE: {display_mode} MODE", (20, 40), 1, 2, mode_color, 3)
        cv2.putText(frame, f"GESTURE: {gesture_name}", (20, 80), 1, 2.4, color, 3)
        cv2.putText(frame, f"VOICE: {'ON' if voice_enabled else 'OFF'}", (20, 120), 1, 2.0, (255, 255, 0), 2)
        cv2.putText(frame, f"VOICE STATE: {voice_state}", (20, 160), 1, 1.4, (200, 200, 200), 2)
        cv2.putText(frame, f"HEARD: {voice_last_heard}", (20, 195), 1, 1.2, (170, 170, 170), 2)
        cv2.putText(frame, f"VOICE REPLY: {voice_last_command}", (20, 230), 1, 1.2, (200, 200, 200), 2)

        panel_x = max(20, w - 290)
        panel_y = 20
        panel_w = 260
        panel_h = 150
        cv2.rectangle(frame, (panel_x, panel_y), (panel_x + panel_w, panel_y + panel_h), (35, 35, 35), -1)
        cv2.rectangle(frame, (panel_x, panel_y), (panel_x + panel_w, panel_y + panel_h), (90, 90, 90), 1)
        cv2.putText(frame, "STARTUP CHECKS", (panel_x + 10, panel_y + 28), 1, 1.0, (255, 255, 255), 2)

        check_items = ["MIC", "OLLAMA", "SPOTIFY", "ARDUINO"]
        for index, key in enumerate(check_items):
            ok = bool(startup_checks.get(key))
            label = "OK" if ok else "MISSING"
            status_color = (0, 220, 0) if ok else (0, 0, 255)
            y = panel_y + 56 + index * 22
            cv2.putText(frame, f"{key}:", (panel_x + 10, y), 1, 0.9, (220, 220, 220), 2)
            cv2.putText(frame, label, (panel_x + 145, y), 1, 0.9, status_color, 2)

        if switch_countdown is not None and current_mode == "IOT":
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

        if fist_start_time > 0 and current_mode == "IOT":
            cd = 3 - int(time.time() - fist_start_time)
            cv2.putText(frame, str(max(0, cd)), (w // 2 - 50, h // 2), 1, 12, (0, 0, 255), 15)

        cv2.imshow("IoT Interface Final", frame)

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
