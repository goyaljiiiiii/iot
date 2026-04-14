import glob
import math
import random
import subprocess
import sys
import time
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np
import pygame
import serial

from iot_control.spotify import create_spotify_client


ROOT_DIR = Path(__file__).resolve().parents[1]
AUDIO_DIR = ROOT_DIR / "audios"


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
        if not sp:
            print("Spotify is not configured or failed to authenticate. Check your .env and redirect URI.")
            return
        try:
            playback = sp.current_playback()
            is_playing = bool(playback and playback.get("is_playing"))
            if is_playing:
                sp.pause_playback()
                print("Spotify: Paused")
            else:
                sp.start_playback()
                print("Spotify: Playing")
        except Exception as e:
            print(f"Spotify Error: {e} (Make sure Spotify is open and active on a device!)")

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

    cap = cv2.VideoCapture(0)

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
            ["spotify"],
            ["flatpak", "run", "com.spotify.Client"],
            ["snap", "run", "spotify"],
            ["xdg-open", "spotify:"],
        ]

        for command in candidates:
            try:
                subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                print(f"Launching Spotify with: {' '.join(command)}")
                return True
            except Exception:
                continue

        print("Could not launch Spotify automatically. Open it manually once and keep it running.")
        return False

    def set_mode(mode):
        nonlocal current_mode, spotify_trigger_time, spotify_exit_start_time, last_sent, last_volume_level, last_spotify_gesture, spotify_launch_attempted

        if current_mode == mode:
            return

        current_mode = mode
        spotify_trigger_time = 0
        spotify_exit_start_time = 0
        last_sent = ""
        last_volume_level = None
        last_spotify_gesture = None
        spotify_launch_attempted = False
        print(f"Mode switched to {current_mode}")

        if current_mode == "IOT":
            send_arduino("G")

    if current_mode == "IOT":
        send_arduino("G")

    while True:
        ret, frame = cap.read()
        if not ret:
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

            if current_mode == "IOT":
                if detected_count != 0 and must_release_fist_after_spotify:
                    must_release_fist_after_spotify = False

                if detected_count == 4:
                    if spotify_trigger_time == 0:
                        spotify_trigger_time = time.time()
                        if not spotify_launch_attempted:
                            spotify_launch_attempted = True
                            launch_spotify_app()
                    elapsed = time.time() - spotify_trigger_time
                    remaining = max(0.0, 2.0 - elapsed)
                    switch_countdown = remaining
                    gesture_name = "SWITCHING..."
                    if elapsed >= 2.0:
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
                    elif detected_count == 5:
                        gesture_name = "JARVIS ACTIVE"
                        cmd = "5"
                        jarvis_active = True
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

            if current_mode == "SPOTIFY":
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

                    if elapsed >= 3.0:
                        must_release_fist_after_spotify = True
                        fist_start_time = 0
                        set_mode("IOT")
                        display_mode = current_mode
                        last_spotify_gesture = None
                        spotify_exit_start_time = 0
                else:
                    spotify_exit_start_time = 0

                    if detected_count == 1:
                        gesture_name = "PLAY/PAUSE"
                        if last_spotify_gesture != "play_pause":
                            toggle_spotify_playback()
                        last_spotify_gesture = "play_pause"
                    elif detected_count == 2:
                        gesture_name = "NEXT TRACK"
                        if last_spotify_gesture != "next":
                            safe_spotify_call(lambda: sp.next_track() if sp else None, "Spotify: Next track")
                        last_spotify_gesture = "next"
                    elif detected_count == 3:
                        gesture_name = "PREVIOUS TRACK"
                        if last_spotify_gesture != "prev":
                            safe_spotify_call(lambda: sp.previous_track() if sp else None, "Spotify: Previous track")
                        last_spotify_gesture = "prev"
                    elif detected_count == 5:
                        gesture_name = "SPOTIFY VOLUME"
                        volume_level = int(np.interp(wrist[1], [h, 0], [0, 100]))
                        volume_level = max(0, min(100, volume_level))

                        if last_volume_level is None or abs(volume_level - last_volume_level) >= 5:
                            safe_spotify_call(
                                lambda level=volume_level: sp.volume(level) if sp else None,
                                f"Spotify Volume: {volume_level}%",
                            )
                            last_volume_level = volume_level
                        last_spotify_gesture = "volume"
                    else:
                        gesture_name = "SPOTIFY READY"
                        last_spotify_gesture = None

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

        if current_mode == "IOT":
            send_arduino(cmd)

        canvas = cv2.subtract(canvas, (15, 15, 15, 0))
        frame = cv2.add(frame, canvas)

        mode_color = (0, 255, 0) if current_mode == "IOT" else (0, 200, 255)
        color = (0, 255, 0) if gesture_name != "FIST" else (0, 0, 255)

        cv2.putText(frame, f"MODE: {display_mode} MODE", (20, 40), 1, 2, mode_color, 3)
        cv2.putText(frame, f"GESTURE: {gesture_name}", (20, 80), 1, 2.4, color, 3)

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

        if cv2.waitKey(1) & 0xFF == 27:
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
