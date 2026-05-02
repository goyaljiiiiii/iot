# JARVIS Command Reference

All voice commands require voice mode to be **on** (press `v` in the camera window).
Say **"jarvis"** first to wake JARVIS, then speak your command within 8 seconds.

---

## Keyboard Shortcuts

| Key   | Action                    |
|-------|---------------------------|
| `v`   | Toggle voice mode on / off |
| `Esc` | Exit the app              |

---

## Gestures

### GESTURE Mode (default)

| Fingers | Action                  |
|---------|-------------------------|
| Pinch   | Sparkle effect          |
| 2       | Take a screenshot       |
| 5       | JARVIS animation        |

### SPOTIFY Mode

| Fingers | Action          |
|---------|-----------------|
| 1       | Play            |
| 2       | Pause           |
| 3       | Previous track  |
| 4       | Next track      |

> Switch modes by voice or by gesture (hold 5 fingers in GESTURE mode to trigger JARVIS).

---

## Voice Commands

### Wake & Control

| Say                                              | What happens                        |
|--------------------------------------------------|-------------------------------------|
| `jarvis`                                         | Wake JARVIS ("Yes?")                |
| `jarvis on` / `activate jarvis`                  | Activate JARVIS                     |
| `jarvis off` / `deactivate jarvis`               | Deactivate JARVIS                   |
| `voice off` / `stop voice` / `disable voice`     | Turn voice input off                |

---

### Mode Switching

| Say                                              | What happens                        |
|--------------------------------------------------|-------------------------------------|
| `gesture mode` / `go to gesture` / `control mode` | Switch to GESTURE mode             |
| `spotify mode` / `go to spotify`                 | Switch to SPOTIFY mode              |

---

### Music / Spotify

| Say                                              | What happens                        |
|--------------------------------------------------|-------------------------------------|
| `play` / `resume` / `play music`                 | Resume playback                     |
| `pause` / `stop playback` / `pause music`        | Pause playback                      |
| `next` / `next track` / `skip`                   | Skip to next track                  |
| `previous` / `prev` / `back`                     | Go to previous track                |
| `volume up` / `raise volume` / `louder`          | Increase volume by one step         |
| `volume down` / `lower volume` / `softer`        | Decrease volume by one step         |
| `set volume to 70` / `volume 50`                 | Set volume to exact level (0–100)   |
| `mute` / `toggle mute` / `mute audio`            | Toggle mute                         |

---

### Open Apps

| Say                   | Opens                              |
|-----------------------|------------------------------------|
| `open chrome`         | Google Chrome / Chromium           |
| `open firefox`        | Firefox                            |
| `open terminal`       | Terminal emulator                  |
| `open files`          | File manager (Nautilus / Thunar)   |
| `open spotify`        | Spotify                            |
| `open vscode`         | VS Code                            |
| `open calculator`     | Calculator                         |
| `open settings`       | System settings                    |
| `open <any app name>` | Tries to run that app directly     |

---

### System Info

| Say                                              | What happens                              |
|--------------------------------------------------|-------------------------------------------|
| `battery` / `how much battery` / `power level`  | Speaks battery % and charging status      |
| `cpu usage` / `cpu load` / `processor usage`    | Speaks current CPU usage %                |
| `ram usage` / `memory usage` / `how much ram`   | Speaks RAM used / total and percent       |

---

### Timer

| Say                          | What happens                              |
|------------------------------|-------------------------------------------|
| `set timer for 5 minutes`    | Starts a 5-minute countdown               |
| `timer for 30 seconds`       | Starts a 30-second countdown              |
| `set timer for 1 minute`     | Starts a 1-minute countdown               |

JARVIS speaks aloud when the timer finishes. Multiple timers can run at the same time.

---

### Clipboard

| Say                                                        | What happens                         |
|------------------------------------------------------------|--------------------------------------|
| `read clipboard` / `show clipboard` / `what's in clipboard` | Reads out the current clipboard text |

> Requires `xclip` or `xsel`: `sudo apt install xclip`

---

### Google Tasks

> Requires `GOOGLE_TASKS_CLIENT_ID`, `GOOGLE_TASKS_CLIENT_SECRET`, and `GOOGLE_TASKS_REFRESH_TOKEN` in `.env`.

| Say                                    | What happens                       |
|----------------------------------------|------------------------------------|
| `list my tasks` / `show tasks`         | Reads out your top 5 pending tasks |
| `add task buy milk`                    | Creates a new task                 |
| `create task finish report`            | Creates a new task                 |
| `complete task buy milk`               | Marks a task as done               |
| `finish task buy milk`                 | Marks a task as done               |
| `delete task buy milk`                 | Deletes a task                     |
| `update task buy milk to buy oat milk` | Renames a task                     |

---

### Profiles

| Say                                          | What happens                                |
|----------------------------------------------|---------------------------------------------|
| `list profiles` / `show profiles`            | Lists all saved profiles                    |
| `switch to <name>` / `use profile <name>`    | Switches to an existing profile             |
| `my name is aakash` / `i am aakash`          | Creates a profile for that name and activates it |

---

### Built-in Chat (no internet needed)

These work offline without Ollama:

| Say                          | Reply                                      |
|------------------------------|--------------------------------------------|
| `hello` / `hi` / `hey`       | "Hello. I am online and listening."        |
| `how are you` / `what's up`  | "I am running well and ready to help."     |
| `who are you` / `your name`  | "I am JARVIS, your voice assistant."       |
| `what time is it`            | Current time                               |
| `what date is today`         | Today's date                               |
| `what can you do` / `help`   | Brief capabilities summary                 |
| `status` / `are you online`  | Current mode and voice state               |
| `what is 12 times 8`         | Math answer (supports +, −, ×, ÷, ^, mod) |
| `weather in London`          | Live weather via wttr.in                   |

---

### Free Chat with Ollama (AI replies spoken aloud)

Any phrase that doesn't match a command above is sent to **Ollama** (local LLM) and the reply is spoken by JARVIS.

**Requirements:**
- Ollama installed and running (`ollama serve`)
- A model pulled: `ollama pull llama3.2:3b`
- Or set `AI_AUTO_START_OLLAMA=true` in `.env` to auto-start

**Examples:**

```
jarvis tell me a joke
jarvis explain black holes in simple words
jarvis write a short poem about the ocean
jarvis what should I have for dinner
```

Chat history is kept for context (last 16 messages by default).
Set `MAX_CHAT_HISTORY_MESSAGES` in `.env` to change the window.

---

## Environment Variables (quick reference)

| Variable                  | Purpose                                    | Default                        |
|---------------------------|--------------------------------------------|--------------------------------|
| `AI_LOCAL_MODEL`          | Ollama model to use                        | auto-detected                  |
| `AI_AUTO_START_OLLAMA`    | Auto-start Ollama if not running           | `true`                         |
| `VOICE_PHRASE_SECONDS`    | How long JARVIS listens per phrase         | `4.0`                          |
| `VOICE_WAKE_WINDOW_SECONDS` | Seconds stay awake after wake word       | `8.0`                          |
| `MAX_CHAT_HISTORY_MESSAGES` | How many messages to keep for AI context | `16`                           |
| `CAMERA_INDEX`            | Which camera to use (0, 1, …)             | auto-scan                      |
| `JARVIS_THEME`            | Visual theme (`auto`, `amber`, `cyan`)     | `auto`                         |
| `RENDER_QUALITY`          | HUD quality (`performance`, `balanced`, `ultra`) | `balanced`               |
| `SHOW_FPS`                | Show FPS counter in HUD                    | `true`                         |
