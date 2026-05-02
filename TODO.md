# Project TODO

## Done

### Core Features
- [x] OpenCV camera loop with MediaPipe hand tracking
- [x] Finger counting and gesture-to-command mapping
- [x] Mode switching: `GESTURE` mode and `SPOTIFY` mode
- [x] Screenshot on 2-finger gesture
- [x] Pinch / sparkle effect gesture
- [x] Volume up/down via finger count thresholds

### Voice
- [x] Background voice listener (`jarvis_control/voice.py`)
- [x] Wake-word support (`jarvis`)
- [x] Wake-window: commands heard within N seconds of wake word
- [x] Toggle voice on/off with `v` key at runtime
- [x] TTS output via `spd-say` with `espeak` fallback

### AI Chat
- [x] Cloud AI chat (OpenAI-compatible API via `AI_CHAT_API_KEY` / `AI_CHAT_API_BASE`)
- [x] Local AI chat via Ollama (`AI_LOCAL_MODEL`, `AI_LOCAL_API_BASE`)
- [x] Auto-start Ollama server if `AI_AUTO_START_OLLAMA=true`
- [x] Math expression evaluation (offline, no API needed)
- [x] Weather query support (live via wttr.in)
- [x] Local fallback replies when no AI is available

### Spotify
- [x] Spotify Web API control (play, pause, next, prev) via `spotipy`
- [x] Local Spotify fallback via `playerctl` when API keys are not set
- [x] Gesture-to-Spotify mapping (finger count → action)
- [x] Spotify app auto-launch if not running

### Google Tasks
- [x] Voice CRUD: add, list, update, complete, delete tasks
- [x] OAuth token refresh (uses `GOOGLE_TASKS_REFRESH_TOKEN`)
- [x] Task list auto-resolution (by name or ID)

### Profiles
- [x] Multi-profile gesture config system (`profiles.json`)
- [x] Voice command to switch profiles (`switch profile <name>`)
- [x] Runtime profile creation by voice

### UX / Visuals
- [x] Startup check overlay (mic, Ollama, Spotify status)
- [x] JARVIS HUD with mode display and FPS counter
- [x] Warm color palette per hand
- [x] Audio feedback on gestures (pygame sound effects)
- [x] Wayland fix (`QT_QPA_PLATFORM=xcb` auto-set)
- [x] Camera auto-scan when `CAMERA_INDEX` is not set

### Project Setup
- [x] `requirements.txt` with pinned versions
- [x] `pyproject.toml` with `jarvis-gesture` CLI entrypoint
- [x] `.env.example` with all supported config vars
- [x] `.gitignore`, `CONTRIBUTING.md`, `SECURITY.md`, `LICENSE`
- [x] GitHub Actions CI workflow
- [x] Lesson scripts: `lesson_01_open_camera.py`, `lesson_02_count_fingers.py`, `lesson_03_two_finger_screenshot.py`

---

## TODO

### High Priority
- [ ] **Tests** — no test suite exists; add `pytest` tests for voice parsing, Google Tasks helpers, and gesture mapping logic
- [ ] **Google Tasks OAuth setup guide** — getting `GOOGLE_TASKS_REFRESH_TOKEN` is a manual, undocumented step; add a helper script or instructions
- [ ] **`asset/` directory** — currently empty (only `.gitkeep`); add planned static assets (icons, overlay images, etc.)
- [ ] **`profiles.json` default file** — the file is generated at runtime but never committed; add a `profiles.example.json` so users know the format

### Features
- [ ] **Multi-hand support** — currently only the first detected hand is used; add dual-hand gestures
- [ ] **Gesture recording / custom mapping UI** — let users bind new gestures without editing `profiles.json` by hand
- [ ] **Spotify search by voice** — `play <song name>` command (API search + playback)
- [ ] **Volume sync** — reflect system or Spotify volume in the HUD in real time
- [ ] **Google Calendar integration** — `.env.example` has no Calendar vars yet but it's a natural next step given Tasks support
- [ ] **Lesson 04+** — extend the teaching path (e.g., voice integration, gesture recording)

### Code Quality
- [ ] **`gesture.py` in repo root** — thin stub that just calls `jarvis_control.gesture.main()`; consider removing and keeping only `scripts/run_gesture.py`
- [ ] **`scripts/camera_cleanup_stub.py`** — placeholder stub with no real content; promote to a real utility or delete
- [ ] **Type hints** — `jarvis_control/gesture.py` has none; add at least to public function signatures
- [ ] **Split `jarvis_control/gesture.py`** — the file is very large; break out AI chat, Google Tasks, and profile logic into separate modules

### Packaging / Distribution
- [ ] **Docker / container support** — tricky with camera/mic but useful for CI and headless testing
- [ ] **`setup.sh` for macOS** — current `setup.sh` has Linux-only system-package checks; add macOS (`brew`) equivalents
- [ ] **Publish to PyPI** — `pyproject.toml` is ready; just need a release workflow
