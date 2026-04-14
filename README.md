# IoT Gesture Controller

Hand gesture interface for controlling an Arduino-connected IoT setup and Spotify playback.

## Project Structure

- `iot_control/gesture.py`: Main vision + gesture control loop
- `iot_control/spotify.py`: Spotify authentication and helper commands
- `audios/`: Audio effects and prompts
- `asset/`: Reserved for non-audio static assets
- `scripts/run_gesture.py`: Convenience launcher

## Setup

1. Create/activate a virtual environment.
2. Install dependencies:
   `pip install -e .`
3. Configure Spotify credentials:
   - Copy `.env.example` to `.env`
   - Set `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET`, and optional `SPOTIFY_REDIRECT_URI`

## Run

Use either command:

- `iot-gesture`
- `python scripts/run_gesture.py`

## Notes

- Arduino port auto-detect checks `/dev/ttyUSB*` and `/dev/ttyACM*`.
- Audio files are loaded from `audios/`.
- If Spotify credentials are missing, Spotify controls are skipped safely.
