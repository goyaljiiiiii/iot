import os
# Force xcb platform to fix blank/invisible OpenCV windows on Wayland
if os.environ.get("XDG_SESSION_TYPE") == "wayland":
    os.environ["QT_QPA_PLATFORM"] = "xcb"

# Use external webcam (index 2 corresponds to /dev/video2)
os.environ["CAMERA_INDEX"] = "2"

from iot_control.gesture import main


if __name__ == "__main__":
    main()
