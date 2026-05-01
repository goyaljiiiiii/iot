"""
Lesson 01: Open the camera (OpenCV).

Goal:
- Show how to open a webcam with cv2.VideoCapture and display frames.

Run:
- . .venv/bin/activate
- CAMERA_INDEX=0 python lessons/lesson_01_open_camera.py
"""

import os
import cv2


def main():
    camera_index = int(os.getenv("CAMERA_INDEX", "0"))
    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        raise SystemExit(f"Could not open camera index {camera_index}. Try CAMERA_INDEX=1.")

    while True:
        ok, frame = cap.read()
        if not ok:
            break

        cv2.imshow("Lesson 01 - Camera", frame)
        key = cv2.waitKey(1) & 0xFF
        if key == 27:  # Esc
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()

