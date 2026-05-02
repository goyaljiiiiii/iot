"""
JARVIS Main Entry Point

This is the main launcher for the JARVIS gesture and voice control system.
Run this to start the full-featured application with all visualizations.

Educational version: See lessons/lesson_06_gesture_recognition_full.py
"""

import os
import sys
from pathlib import Path

# Force xcb platform to fix blank/invisible OpenCV windows on Wayland
if os.environ.get("XDG_SESSION_TYPE") == "wayland":
    os.environ["QT_QPA_PLATFORM"] = "xcb"

# Add current directory to path
ROOT = Path(__file__).resolve().parents[0]
sys.path.insert(0, str(ROOT))

# Import and run the full JARVIS system
from lessons.lesson_06_gesture_recognition_full import main


if __name__ == "__main__":
    main()
