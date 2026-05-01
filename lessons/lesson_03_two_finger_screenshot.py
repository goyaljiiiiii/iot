"""
Lesson 03: Take a screenshot when 2 fingers are raised.

Goal:
- Combine finger counting + saving a full desktop screenshot.
- Add a simple "release" gate so it only saves once per gesture.

Run:
- . .venv/bin/activate
- CAMERA_INDEX=0 python lessons/lesson_03_two_finger_screenshot.py
"""

import math
import os
import time
from datetime import datetime
from pathlib import Path

import cv2
import mediapipe as mp


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

    thumb_tip_far = dist_from_palm(4) > dist_from_palm(3) + 0.12 * palm_width
    thumb_uncurled = joint_angle(2, 3, 4) > 145
    thumb_extended = thumb_tip_far and thumb_uncurled

    count = 1 if thumb_extended else 0

    for tip, pip, mcp in [(8, 6, 5), (12, 10, 9), (16, 14, 13), (20, 18, 17)]:
        radial_extended = dist_from_palm(tip) > dist_from_palm(pip) + 0.08 * palm_width
        wrist_extended = dist_from_wrist(tip) > dist_from_wrist(mcp) + 0.10 * palm_width
        vertical_extended = landmarks[tip].y < landmarks[pip].y
        if (radial_extended and wrist_extended) or vertical_extended:
            count += 1

    return count


def main():
    camera_index = int(os.getenv("CAMERA_INDEX", "0"))
    screenshots_dir = Path(os.getenv("SCREENSHOTS_DIR", "screenshots")).expanduser()
    cooldown = float(os.getenv("SCREENSHOT_COOLDOWN_SECONDS", "1.25"))

    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        raise SystemExit(f"Could not open camera index {camera_index}. Try CAMERA_INDEX=1.")

    mp_hands = mp.solutions.hands
    hands = mp_hands.Hands(model_complexity=0, min_detection_confidence=0.7, min_tracking_confidence=0.7)
    mp_draw = mp.solutions.drawing_utils

    last_shot = 0.0
    wait_release = False
    status = "READY"

    while True:
        ok, frame = cap.read()
        if not ok:
            break

        frame = cv2.flip(frame, 1)
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = hands.process(rgb)

        count = None
        if results.multi_hand_landmarks:
            hl = results.multi_hand_landmarks[0]
            mp_draw.draw_landmarks(frame, hl, mp_hands.HAND_CONNECTIONS)
            count = count_raised_fingers(hl.landmark)

        if wait_release and count != 2:
            wait_release = False
            status = "READY"

        now = time.time()
        if count == 2 and not wait_release and (now - last_shot) >= cooldown:
            screenshots_dir.mkdir(parents=True, exist_ok=True)
            filename = datetime.now().strftime("lesson03_%Y%m%d_%H%M%S_%f")[:-3] + ".png"
            out_path = screenshots_dir / filename
            try:
                import mss
                import mss.tools

                with mss.mss() as sct:
                    monitor = sct.monitors[0]
                    grab = sct.grab(monitor)
                    png_bytes = mss.tools.to_png(grab.rgb, grab.size)
                    out_path.write_bytes(png_bytes)
                last_shot = now
                wait_release = True
                status = f"SAVED {out_path}"
            except Exception as exc:
                status = f"Install mss for desktop screenshots ({exc})"

        cv2.putText(frame, f"FINGERS: {count if count is not None else '-'}", (20, 40), 1, 1.2, (0, 255, 0), 2)
        cv2.putText(frame, f"STATUS: {status[:54]}", (20, 80), 1, 0.8, (200, 220, 255), 2)
        cv2.imshow("Lesson 03 - 2 finger screenshot", frame)
        key = cv2.waitKey(1) & 0xFF
        if key == 27:
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()

