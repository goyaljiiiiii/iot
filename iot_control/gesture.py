import glob
import ast
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
    jarvis_distance_scale = 1.0
    jarvis_height_factor = 1.0

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

            if any(phrase in lowered_text for phrase in ["who are you", "what are you", "your name", "who is this"]):
                return "I am JARVIS, your IoT and voice assistant."

            if any(phrase in lowered_text for phrase in ["what time", "current time", "time now"]):
                return f"Current time is {now_dt.strftime('%I:%M %p')}"

            if any(phrase in lowered_text for phrase in ["what date", "today date", "which date", "today is"]):
                return f"Today is {now_dt.strftime('%A, %d %B %Y')}"

            if any(phrase in lowered_text for phrase in ["what can you do", "help", "commands", "capabilities"]):
                return (
                    "I can control Spotify, switch I O T and Spotify modes, adjust volume, "
                    "and answer short questions."
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
        palm_center = None
        jarvis_angle = 0
        jarvis_render_targets = []

        if results.multi_hand_landmarks:
            for hl_all in results.multi_hand_landmarks:
                mp_draw.draw_landmarks(frame, hl_all, mp_hands.HAND_CONNECTIONS)
                lm_all = hl_all.landmark

                detected_count_all = count_raised_fingers(lm_all)

                if current_mode == "IOT" and not voice_enabled and detected_count_all == 5:
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

        if current_mode == "IOT" and not voice_enabled:
            jarvis_active = bool(jarvis_render_targets)

        if gesture_name != "FIST":
            fist_start_time = 0
            try:
                if sound_count:
                    sound_count.stop()
            except Exception:
                pass

        if current_mode == "IOT" and jarvis_active and jarvis_render_targets:
            sorted_targets = sorted(jarvis_render_targets, key=lambda item: item[0][0])

            if len(sorted_targets) >= 2:
                left_center = sorted_targets[0][0]
                right_center = sorted_targets[1][0]
                bridge_overlay = frame.copy()
                bridge_len = max(1.0, math.hypot(right_center[0] - left_center[0], right_center[1] - left_center[1]))
                bridge_strength = max(0.2, min(1.0, bridge_len / max(1, w * 0.62)))
                bridge_phase = time.time() * 6.0

                for strand in range(4):
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
                for n in range(3):
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

                steps = 10
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

                if idx % 2 == 0:
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
                cv2.circle(frame, center, mid_r, (120, 140, 170) if idx % 2 == 0 else (130, 180, 215), 2)
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

                for i in range(0, 360, 10):
                    ang = math.radians(i + sweep * 0.35)
                    x1 = int(center[0] + (inner_r + 8) * math.cos(ang))
                    y1 = int(center[1] + (inner_r + 8) * math.sin(ang))
                    x2 = int(center[0] + (mid_r - 8) * math.cos(ang))
                    y2 = int(center[1] + (mid_r - 8) * math.sin(ang))
                    cv2.line(frame, (x1, y1), (x2, y2), (95, 105, 122), 1)

                # Rotating segmented arcs for a more premium scanner look.
                arc_sets = [
                    (outer_r - 10, sweep, 58, neon_ring, 2),
                    (outer_r - 10, sweep + 165, 42, (200, 165, 65) if idx % 2 == 0 else (115, 195, 230), 2),
                    (mid_r - 8, -sweep * 1.2, 68, neon_core, 2),
                    (mid_r - 8, -sweep * 1.2 + 205, 34, (190, 145, 55) if idx % 2 == 0 else (90, 170, 210), 2),
                    (inner_r - 8, sweep * 1.6, 85, (255, 235, 120) if idx % 2 == 0 else (175, 245, 255), 2),
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
                    (140, 175, 230) if idx % 2 == 0 else (120, 220, 255),
                    1,
                )
                cv2.ellipse(
                    frame,
                    center,
                    (mid_r - 18, mid_r - 18),
                    -sweep * 0.75,
                    0,
                    260,
                    (255, 210, 110) if idx % 2 == 0 else (135, 230, 255),
                    1,
                )
                cv2.ellipse(
                    frame,
                    center,
                    (inner_r - 14, inner_r - 14),
                    sweep * 1.2,
                    80,
                    360,
                    (255, 240, 150) if idx % 2 == 0 else (190, 250, 255),
                    1,
                )

                # Orbiting glints for depth.
                glint_r = mid_r + 6
                for offset in (0, 120, 240):
                    ang = math.radians(sweep * 1.25 + offset)
                    gx = int(center[0] + glint_r * math.cos(ang))
                    gy = int(center[1] + glint_r * math.sin(ang))
                    glow_size = 3 if (offset == 0 and twinkle > 0.65) else 2
                    cv2.circle(frame, (gx, gy), glow_size, (255, 235, 150) if idx % 2 == 0 else (190, 245, 255), -1)

                # Sweep beam accent.
                beam_ang = math.radians(sweep)
                bx = int(center[0] + (outer_r - 14) * math.cos(beam_ang))
                by = int(center[1] + (outer_r - 14) * math.sin(beam_ang))
                cv2.line(frame, center, (bx, by), (255, 230, 120) if idx % 2 == 0 else (150, 240, 255), 2)
                cv2.circle(frame, (bx, by), 5, (255, 235, 145) if idx % 2 == 0 else (205, 250, 255), -1)

                # Beam trail for more cinematic motion.
                for trail_idx in range(1, 4):
                    trail_ang = math.radians(sweep - trail_idx * 8)
                    tx = int(center[0] + (outer_r - 18 - trail_idx * 3) * math.cos(trail_ang))
                    ty = int(center[1] + (outer_r - 18 - trail_idx * 3) * math.sin(trail_ang))
                    if idx % 2 == 0:
                        trail_color = (210 - trail_idx * 30, 180 - trail_idx * 20, 110 - trail_idx * 15)
                    else:
                        trail_color = (130 - trail_idx * 14, 210 - trail_idx * 22, 235 - trail_idx * 20)
                    cv2.line(frame, center, (tx, ty), trail_color, 1)

                core_outer = int((39 + 3 * pulse) * dynamic_scale)
                core_inner = int((18 + 2 * pulse) * dynamic_scale)
                cv2.circle(frame, center, core_outer, neon_ring, 2)
                cv2.circle(frame, center, core_inner + 8, (255, 245, 185) if idx % 2 == 0 else (205, 250, 255), -1)
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
                cv2.polylines(frame, [np.array(tri_pts, np.int32)], True, (255, 225, 120) if idx % 2 == 0 else (170, 245, 255), 1)

                brace_r = inner_r - 18
                for angle_offset in (45, 135, 225, 315):
                    a = math.radians(angle_offset + sweep * 0.4)
                    bx1 = int(center[0] + brace_r * math.cos(a))
                    by1 = int(center[1] + brace_r * math.sin(a))
                    bx2 = int(center[0] + (brace_r + 10) * math.cos(a))
                    by2 = int(center[1] + (brace_r + 10) * math.sin(a))
                    cv2.line(frame, (bx1, by1), (bx2, by2), (210, 175, 90) if idx % 2 == 0 else (120, 210, 245), 2)

                hex_pts = []
                for i in range(6):
                    ang = math.radians(i * 60 + sweep * 0.9)
                    x = int(center[0] + (core_inner + 14) * math.cos(ang))
                    y = int(center[1] + (core_inner + 14) * math.sin(ang))
                    hex_pts.append([x, y])
                cv2.polylines(frame, [np.array(hex_pts, np.int32)], True, (255, 220, 95) if idx % 2 == 0 else (150, 240, 255), 2)

                for i in range(12):
                    ang = math.radians(i * 30 + sweep * 0.55)
                    r = outer_r - 2
                    x = int(center[0] + r * math.cos(ang))
                    y = int(center[1] + r * math.sin(ang))
                    size = 2 if i % 2 == 0 else 3
                    cv2.circle(frame, (x, y), size, (230, 195, 85) if idx % 2 == 0 else (130, 220, 250), -1)

                # Micro particles that shimmer near the outer ring.
                particle_count = int(6 + 6 * twinkle)
                for i in range(particle_count):
                    p_ang = math.radians((sweep * 1.6 + i * (360 / max(1, particle_count))) % 360)
                    p_r = outer_r + 8 + (i % 3) * 3
                    px = int(center[0] + p_r * math.cos(p_ang))
                    py = int(center[1] + p_r * math.sin(p_ang))
                    cv2.circle(frame, (px, py), 1, (255, 240, 170) if idx % 2 == 0 else (190, 248, 255), -1)

                # Cinematic wave shell and rotating chevrons.
                shell_overlay = frame.copy()
                shell_r = outer_r + 18
                for band in range(3):
                    start_ang = (sweep * (1.2 + band * 0.18) + band * 80) % 360
                    span = 52 + band * 16
                    shell_color = (145 + band * 30, 170 + band * 18, 245 - band * 20) if idx % 2 else (250 - band * 22, 205 - band * 14, 120 - band * 12)
                    cv2.ellipse(shell_overlay, center, (shell_r + band * 8, shell_r + band * 8), 0, start_ang, start_ang + span, shell_color, 2)
                cv2.addWeighted(shell_overlay, 0.20, frame, 0.80, 0, frame)

                for k in range(8):
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
                    cv2.polylines(frame, [np.array([p1, p2, p3], np.int32)], True, (245, 220, 140) if idx % 2 == 0 else (170, 245, 255), 1)

                # Radial flicker lines to amplify reactor energy.
                for ray in range(16):
                    a = math.radians(ray * 22.5 + sweep * 0.55)
                    r1 = core_inner + 6
                    r2 = inner_r - 6
                    rx1 = int(center[0] + r1 * math.cos(a))
                    ry1 = int(center[1] + r1 * math.sin(a))
                    rx2 = int(center[0] + r2 * math.cos(a))
                    ry2 = int(center[1] + r2 * math.sin(a))
                    if ray % 2 == 0:
                        cv2.line(frame, (rx1, ry1), (rx2, ry2), (180, 175, 130) if idx % 2 == 0 else (140, 210, 230), 1)

                # Trailing afterimage for faster perceived motion.
                trail_overlay = frame.copy()
                for trail in range(1, 4):
                    ta = math.radians(sweep - trail * 14)
                    tr = outer_r - 24
                    tx = int(center[0] + tr * math.cos(ta))
                    ty = int(center[1] + tr * math.sin(ta))
                    cv2.circle(trail_overlay, (tx, ty), max(2, 6 - trail), (255, 230, 150) if idx % 2 == 0 else (180, 245, 255), -1)
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
                    segments = 13
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

                    thread_color = (255, 220, 120) if idx % 2 == 0 else (160, 245, 255)
                    glow_color = (210, 175, 90) if idx % 2 == 0 else (115, 205, 240)
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
                    (250, 230, 150),
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

        overlay = frame.copy()
        cv2.rectangle(overlay, (0, 0), (w, 280), (20, 24, 32), -1)
        cv2.rectangle(overlay, (0, h - 60), (w, h), (16, 20, 28), -1)
        cv2.addWeighted(overlay, 0.34, frame, 0.66, 0, frame)

        cv2.putText(frame, "JARVIS CONTROL HUD", (18, 30), 1, 1.0, (240, 240, 255), 2)
        cv2.line(frame, (18, 36), (260, 36), (90, 140, 255), 2)

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

        panel_x = max(20, w - 306)
        panel_y = 18
        panel_w = 286
        panel_h = 168
        cv2.rectangle(frame, (panel_x, panel_y), (panel_x + panel_w, panel_y + panel_h), (22, 28, 38), -1)
        cv2.rectangle(frame, (panel_x, panel_y), (panel_x + panel_w, panel_y + panel_h), (88, 116, 170), 1)
        cv2.putText(frame, "SYSTEM CHECKS", (panel_x + 12, panel_y + 28), 1, 1.0, (240, 240, 255), 2)

        check_items = ["MIC", "OLLAMA", "SPOTIFY", "ARDUINO"]
        for index, key in enumerate(check_items):
            ok = bool(startup_checks.get(key))
            label = "OK" if ok else "MISSING"
            status_color = (0, 220, 0) if ok else (0, 0, 255)
            y = panel_y + 56 + index * 25
            cv2.putText(frame, f"{key}", (panel_x + 14, y), 1, 0.9, (220, 220, 220), 2)
            cv2.putText(frame, ":", (panel_x + 124, y), 1, 0.9, (140, 140, 140), 2)
            cv2.putText(frame, label, (panel_x + 150, y), 1, 0.9, status_color, 2)

        bottom_hint = "Press V: Voice Toggle   Esc: Exit"
        cv2.putText(frame, bottom_hint, (18, h - 22), 1, 0.8, (185, 200, 240), 2)

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
