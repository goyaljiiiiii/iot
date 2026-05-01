import os
# Force xcb platform to fix blank/invisible OpenCV windows on Wayland
if os.environ.get("XDG_SESSION_TYPE") == "wayland":
    os.environ["QT_QPA_PLATFORM"] = "xcb"

# Camera index can be selected via CAMERA_INDEX env var (e.g. 0, 1, or "0,1").
# Do not force a default here; jarvis_control will auto-scan if unset.

from jarvis_control.gesture import main


if __name__ == "__main__":
    main()
