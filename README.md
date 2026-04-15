# IoT Gesture Controller

Real-time hand gesture, voice, and Spotify control system for Linux-based IoT setups.

This project combines:

- OpenCV + MediaPipe hand tracking
- Arduino serial commands for IoT actions
- Spotify playback control (Web API or local fallback)
- Optional wake-word voice assistant behavior

## Features

- Gesture-to-command mapping for IoT and Spotify modes
- Mode switching between `IOT` and `SPOTIFY`
- Optional voice command listener (toggle at runtime)
- Wake-word support (`jarvis`) and chat-style assistant replies
- Automatic startup checks overlay (mic, Ollama, Spotify, Arduino)
- Safe fallback behavior when Spotify API credentials are not configured

## Project Structure

- `iot_control/gesture.py`: Main camera loop, gesture recognition, mode logic, and voice orchestration
- `iot_control/voice.py`: Background voice listener and wake-word flow
- `iot_control/spotify.py`: Spotify auth and helper actions
- `scripts/run_gesture.py`: Launcher script
- `scripts/serial_command_test.py`: Arduino serial command test utility
- `audios/`: Local sound effects
- `asset/`: Reserved static assets

## Requirements

- Linux
- Python 3.10+
- Webcam
- Microphone (for voice commands)
- Optional Arduino on `/dev/ttyUSB*` or `/dev/ttyACM*`
- Optional Spotify account/app

## Setup

1. Create and activate a virtual environment.
2. Install dependencies:

   ```bash
   pip install -e .
   ```

3. Configure environment variables:

   ```bash
   cp .env.example .env
   ```

4. If using Spotify API control, set:
   - `SPOTIFY_CLIENT_ID`
   - `SPOTIFY_CLIENT_SECRET`
   - `SPOTIFY_REDIRECT_URI` (must match your Spotify app config)

## Run

```bash
iot-gesture
```

Or:

```bash
python scripts/run_gesture.py
```

## Controls

- Press `v` in the camera window to toggle voice mode on/off.
- Press `Esc` to exit.
- When voice mode is on, gesture actions are paused to prevent accidental triggers.

## Environment Variables

See `.env.example` for all supported keys. Important ones:

- Spotify API: `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET`, `SPOTIFY_REDIRECT_URI`
- Cloud AI chat: `OPENAI_API_KEY` or `AI_CHAT_API_KEY`, `AI_CHAT_API_BASE`, `AI_CHAT_MODEL`
- Local AI chat (Ollama): `AI_LOCAL_API_BASE`, `AI_LOCAL_MODEL`, `AI_AUTO_START_OLLAMA`
- Camera selection: `CAMERA_INDEX` (example: `0` or `0,1`)

## Troubleshooting

### Voice hears you but no spoken reply

The app speaks via `spd-say` first, then `espeak` fallback.
Install one of these packages:

```bash
sudo apt install speech-dispatcher espeak
```

### Spotify commands do not respond

- Ensure Spotify desktop/web is running and currently active.
- If API credentials are not set, install local fallback control:

```bash
sudo apt install playerctl
```

### Camera does not open

- Confirm webcam permissions.
- Try setting `CAMERA_INDEX` in `.env`.

### Arduino not detected

- Check cable and board permissions.
- Verify the device appears under `/dev/ttyUSB*` or `/dev/ttyACM*`.
- Use:

```bash
python scripts/serial_command_test.py
```

## Security

- Never commit `.env`.
- Rotate keys immediately if exposed.
- See `SECURITY.md` for reporting guidance.

## Contributing

See `CONTRIBUTING.md`.
