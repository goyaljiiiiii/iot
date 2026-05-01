import threading
import time
import re

import numpy as np
import sounddevice as sd
import speech_recognition as sr


class VoiceCommandListener:
    def __init__(
        self,
        on_command,
        on_wake=None,
        on_heard=None,
        on_state=None,
        on_error=None,
        sample_rate=16000,
        phrase_seconds=4.0,
        cooldown_seconds=0.25,
        wake_word="jarvis",
        wake_window_seconds=8.0,
        callback_suppress_seconds=1.2,
        require_wake_word=False,
    ):
        self.on_command = on_command
        self.on_wake = on_wake or (lambda: None)
        self.on_heard = on_heard or (lambda _raw, _normalized: None)
        self.on_state = on_state or (lambda _state: None)
        self.on_error = on_error or (lambda message: None)
        self.sample_rate = sample_rate
        self.phrase_seconds = phrase_seconds
        self.cooldown_seconds = cooldown_seconds
        self.wake_word = wake_word.lower().strip()
        self.wake_window_seconds = wake_window_seconds
        self.callback_suppress_seconds = callback_suppress_seconds
        self.require_wake_word = require_wake_word
        self.recognizer = sr.Recognizer()
        self._enabled = False
        self._wake_until = 0.0
        self._suppress_until = 0.0
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._started = False

    @property
    def enabled(self):
        return self._enabled

    def start(self):
        if self._started:
            return

        self._started = True
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        try:
            sd.stop()
        except Exception:
            pass
        if self._started and self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def set_enabled(self, enabled):
        self._enabled = enabled

    def _loop(self):
        while not self._stop_event.is_set():
            if not self._enabled:
                self.on_state("voice_off")
                time.sleep(0.2)
                continue

            if time.time() < self._suppress_until:
                self.on_state("suppressing")
                time.sleep(0.05)
                continue

            try:
                frames = int(self.sample_rate * self.phrase_seconds)
                recording = sd.rec(frames, samplerate=self.sample_rate, channels=1, dtype="int16")
                sd.wait()

                samples = np.asarray(recording).reshape(-1)
                if not np.any(samples):
                    time.sleep(0.1)
                    continue

                audio = sr.AudioData(samples.tobytes(), self.sample_rate, 2)
                try:
                    text = self.recognizer.recognize_google(audio).strip().lower()
                except sr.RequestError:
                    # Fallback to offline speech recognition if internet/DNS is unavailable
                    text = self.recognizer.recognize_sphinx(audio).strip().lower()

                if text:
                    now = time.time()
                    normalized = re.sub(r"[^a-z0-9\s]", " ", text)
                    normalized = " ".join(normalized.split())
                    self.on_heard(text, normalized)
                    wake_pattern = rf"\b{re.escape(self.wake_word)}\b"
                    contains_wake_word = re.search(wake_pattern, normalized) is not None

                    if contains_wake_word:
                        remaining = re.sub(wake_pattern, " ", normalized)
                        remaining = " ".join(remaining.split())
                        self._wake_until = now + self.wake_window_seconds

                        if remaining:
                            self.on_command(remaining)
                            self._suppress_until = time.time() + self.callback_suppress_seconds
                        else:
                            self.on_wake()
                            # Do not suppress after wake-only phrase; user usually continues speaking immediately.
                            self._suppress_until = 0.0
                        continue

                    if not self.require_wake_word:
                        self.on_state("listening")
                        self.on_command(normalized)
                        self._suppress_until = time.time() + self.callback_suppress_seconds
                    elif now <= self._wake_until:
                        self.on_state("wake_window")
                        self.on_command(normalized)
                        self._suppress_until = time.time() + self.callback_suppress_seconds
                    else:
                        self.on_state("waiting_wake")

                time.sleep(self.cooldown_seconds)
            except sr.UnknownValueError:
                continue
            except sr.RequestError as exc:
                self.on_error(f"Voice recognition unavailable: {exc}")
                time.sleep(2.0)
            except Exception as exc:
                self.on_error(f"Voice input error: {exc}")
                time.sleep(1.0)