# Setup Guide — JARVIS Gesture + Voice Controller

This guide walks you through installing Python, creating a virtual environment,
installing all dependencies, configuring environment variables, and running the project.

---

## Prerequisites

- Linux (Ubuntu / Debian recommended)
- A webcam
- A microphone (required for voice commands)
- Python 3.10 or higher

---

## 1. Install Python

Check your current Python version:

```bash
python3 --version
```

You already have **Python 3.12.3** — no installation needed. If for some reason it is missing:

```bash
sudo apt update
sudo apt install python3.12 python3.12-venv python3.12-dev
```

Verify the installation:

```bash
python3 --version
# Python 3.12.3
```

---

## 2. Install System Dependencies

These packages are needed for text-to-speech (voice output) and local Spotify control.

```bash
sudo apt install espeak speech-dispatcher playerctl
```

| Package            | Purpose                                      |
|--------------------|----------------------------------------------|
| `espeak`           | TTS fallback for spoken replies              |
| `speech-dispatcher`| Primary TTS backend (`spd-say`)              |
| `playerctl`        | Local Spotify control when API keys not set  |

---

## 3. Create a Virtual Environment

Navigate to the project root and create a `.venv`:

```bash
cd /path/to/Auto_bot_x
python3 -m venv .venv
```

Activate it:

```bash
source .venv/bin/activate
```

Your prompt should now show `(.venv)`. To deactivate later:

```bash
deactivate
```

---

## 4. Upgrade pip

```bash
pip install --upgrade pip
```

---

## 5. Install Dependencies

Install all pinned packages from `requirements.txt`:

```bash
pip install -r requirements.txt
```

Then install the project itself in editable mode so the `jarvis-gesture` command becomes available:

```bash
pip install -e .
```

Verify the entry point works:

```bash
jarvis-gesture --help
```

---

## 6. Configure Environment Variables

Copy the example file:

```bash
cp .env.example .env
```

Open `.env` in your editor and fill in the values you need:

```bash
nano .env
```

### Spotify (required for Spotify mode)

```env
SPOTIFY_CLIENT_ID=your_client_id
SPOTIFY_CLIENT_SECRET=your_client_secret
SPOTIFY_REDIRECT_URI=http://127.0.0.1:8888/callback
```

> Get these from [Spotify Developer Dashboard](https://developer.spotify.com/dashboard).
> Add `http://127.0.0.1:8888/callback` as a Redirect URI in your app settings.

### AI Chat — Cloud (optional)

```env
AI_CHAT_API_KEY=your_openai_or_compatible_key
AI_CHAT_API_BASE=https://api.openai.com/v1
AI_CHAT_MODEL=gpt-4o-mini
```

### AI Chat — Local via Ollama (optional)

```env
AI_LOCAL_API_BASE=http://127.0.0.1:11434
AI_LOCAL_MODEL=llama3.2:3b
AI_AUTO_START_OLLAMA=true
```

Install Ollama separately from [ollama.com](https://ollama.com) and pull your model:

```bash
ollama pull llama3.2:3b
```

### Google Tasks (optional)

```env
GOOGLE_TASKS_CLIENT_ID=your_client_id
GOOGLE_TASKS_CLIENT_SECRET=your_client_secret
GOOGLE_TASKS_REFRESH_TOKEN=your_refresh_token
GOOGLE_TASK_LIST_NAME=My Tasks
```

### Camera Selection (optional)

```env
CAMERA_INDEX=0
```

Leave blank to let the app auto-scan for an available camera.

---

## 7. Run the App

### Main app (gesture + voice controller)

```bash
jarvis-gesture
```

Or using the launcher script:

```bash
python scripts/run_gesture.py
```

### Runtime Controls

| Key   | Action                          |
|-------|---------------------------------|
| `v`   | Toggle voice mode on / off      |
| `Esc` | Exit the app                    |

---

## 8. Run Lesson Scripts

These are small focused scripts for learning the building blocks:

```bash
# Lesson 01 — Open camera and display frames
python lessons/lesson_01_open_camera.py

# Lesson 02 — Detect hands and count fingers
python lessons/lesson_02_count_fingers.py

# Lesson 03 — Take a screenshot on 2-finger gesture
python lessons/lesson_03_two_finger_screenshot.py
```

---

## 9. Test Individual Modules

### Test Spotify connection

```bash
python -m jarvis_control.spotify
```

### Test voice listener (runs standalone loop)

```bash
python -c "
from jarvis_control.voice import VoiceCommandListener
v = VoiceCommandListener(on_command=print)
v.set_enabled(True)
v.start()
import time; time.sleep(10)
v.stop()
"
```

---

## 10. Troubleshooting

### Voice hears you but no spoken reply

```bash
sudo apt install espeak speech-dispatcher
```

### Spotify commands do nothing

- Make sure Spotify desktop or web player is open and **actively playing**.
- Double-check `SPOTIFY_CLIENT_ID` and `SPOTIFY_CLIENT_SECRET` in `.env`.
- The `SPOTIFY_REDIRECT_URI` must match exactly what is set in your Spotify app dashboard.

### Camera does not open

```bash
# List available cameras
ls /dev/video*

# Set the correct index in .env
CAMERA_INDEX=0
```

### Blank / invisible window on Wayland

The app sets `QT_QPA_PLATFORM=xcb` automatically when it detects Wayland.
If the window still does not appear, force it manually:

```bash
QT_QPA_PLATFORM=xcb jarvis-gesture
```

### Dependency install fails (mediapipe / opencv)

```bash
sudo apt install build-essential libgl1 libglib2.0-0
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
```
