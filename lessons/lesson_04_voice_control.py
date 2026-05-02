"""
Lesson 04: Voice Command Recognition

Goal:
- Learn how to listen for voice commands using a microphone
- Understand wake word detection
- Recognize and process spoken commands

Concepts:
- Real-time audio input from the microphone
- Speech recognition APIs (Google Speech Recognition)
- Thread-based event loop for continuous listening
- Wake word pattern matching

Run:
- . .venv/bin/activate
- python lessons/lesson_04_voice_control.py
"""

import threading
import time
import re

import numpy as np
import sounddevice as sd
import speech_recognition as sr


class VoiceCommandListener:
    """
    Listen for voice commands in real-time.
    
    This class runs in a background thread and continuously:
    1. Records audio from the microphone
    2. Converts speech to text using Google Speech Recognition
    3. Detects if a wake word (like "Jarvis") is mentioned
    4. Triggers callbacks when commands are heard
    """
    
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
        """
        Initialize voice listener.
        
        Args:
            on_command: Callback when a command is recognized
            on_wake: Callback when wake word is detected
            on_heard: Callback when any speech is recognized
            on_state: Callback for state changes (listening, waiting, etc.)
            on_error: Callback for errors
            sample_rate: Audio sample rate (Hz) - 16000 is standard
            phrase_seconds: How long to listen for (4 seconds per phrase)
            cooldown_seconds: Wait time between recordings
            wake_word: The word to listen for (e.g., "jarvis")
            wake_window_seconds: Time window to accept commands after wake word
            callback_suppress_seconds: Suppress callbacks to avoid rapid re-triggers
            require_wake_word: If True, only respond after hearing wake word
        """
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
        
        # Google Speech Recognizer - converts audio to text
        self.recognizer = sr.Recognizer()
        
        # Internal state tracking
        self._enabled = False
        self._wake_until = 0.0  # Timestamp when wake window expires
        self._suppress_until = 0.0  # Suppress rapid callbacks
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._started = False

    @property
    def enabled(self):
        """Check if voice listening is currently active."""
        return self._enabled

    def start(self):
        """Start the voice listener thread."""
        if self._started:
            return
        self._started = True
        self._thread.start()

    def stop(self):
        """Stop the voice listener thread gracefully."""
        self._stop_event.set()
        try:
            sd.stop()
        except Exception:
            pass
        if self._started and self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def set_enabled(self, enabled):
        """Enable or disable voice listening."""
        self._enabled = enabled

    def _loop(self):
        """
        Main listening loop (runs in background thread).
        
        This continuously:
        1. Records audio from microphone
        2. Uses Google Speech Recognition to convert to text
        3. Checks if wake word is present
        4. Triggers appropriate callbacks
        """
        while not self._stop_event.is_set():
            # Skip if voice is disabled
            if not self._enabled:
                self.on_state("voice_off")
                time.sleep(0.2)
                continue

            # Skip if we're suppressing rapid callbacks
            if time.time() < self._suppress_until:
                self.on_state("suppressing")
                time.sleep(0.05)
                continue

            try:
                # Step 1: Record audio from microphone for X seconds
                frames = int(self.sample_rate * self.phrase_seconds)
                recording = sd.rec(frames, samplerate=self.sample_rate, channels=1, dtype="int16")
                sd.wait()  # Wait for recording to complete

                # Convert numpy array to raw bytes
                samples = np.asarray(recording).reshape(-1)
                if not np.any(samples):
                    # Silence detected, skip
                    time.sleep(0.1)
                    continue

                # Step 2: Convert audio to text using Google Speech Recognition
                audio = sr.AudioData(samples.tobytes(), self.sample_rate, 2)
                try:
                    text = self.recognizer.recognize_google(audio).strip().lower()
                except sr.RequestError:
                    # Fallback: No internet? Use offline Sphinx recognizer
                    text = self.recognizer.recognize_sphinx(audio).strip().lower()

                if text:
                    now = time.time()
                    # Normalize text: remove special characters, extra spaces
                    normalized = re.sub(r"[^a-z0-9\s]", " ", text)
                    normalized = " ".join(normalized.split())
                    
                    # Trigger on_heard callback with both raw and normalized text
                    self.on_heard(text, normalized)
                    
                    # Step 3: Check if wake word is in the text
                    wake_pattern = rf"\b{re.escape(self.wake_word)}\b"
                    contains_wake_word = re.search(wake_pattern, normalized) is not None

                    if contains_wake_word:
                        # Wake word found! Extract the rest of the command
                        remaining = re.sub(wake_pattern, " ", normalized)
                        remaining = " ".join(remaining.split())
                        
                        # Set wake window timer - accept commands for next N seconds
                        self._wake_until = now + self.wake_window_seconds

                        if remaining:
                            # There's a command after the wake word
                            self.on_command(remaining)
                            self._suppress_until = time.time() + self.callback_suppress_seconds
                        else:
                            # Just the wake word, no command yet
                            self.on_wake()
                            # Don't suppress - user will continue speaking
                            self._suppress_until = 0.0
                        continue

                    # Wake word not found
                    if not self.require_wake_word:
                        # If we don't require wake word, accept any command
                        self.on_state("listening")
                        self.on_command(normalized)
                        self._suppress_until = time.time() + self.callback_suppress_seconds
                    elif now <= self._wake_until:
                        # We're in the wake window, accept commands
                        self.on_state("wake_window")
                        self.on_command(normalized)
                        self._suppress_until = time.time() + self.callback_suppress_seconds
                    else:
                        # Not in wake window, waiting for wake word
                        self.on_state("waiting_wake")

                time.sleep(self.cooldown_seconds)
                
            except sr.UnknownValueError:
                # Audio was recorded but couldn't be understood
                continue
            except sr.RequestError as exc:
                # Network error or service unavailable
                self.on_error(f"Voice recognition unavailable: {exc}")
                time.sleep(2.0)
            except Exception as exc:
                # Other errors
                self.on_error(f"Voice input error: {exc}")
                time.sleep(1.0)


def demo_voice_listener():
    """Demo: Listen for voice commands with wake word 'jarvis'"""
    
    def on_command(cmd):
        print(f"✓ Command: {cmd}")
    
    def on_wake():
        print("🎤 Wake word detected!")
    
    def on_heard(raw, normalized):
        print(f"📢 Heard: '{raw}' → normalized: '{normalized}'")
    
    def on_state(state):
        print(f"  State: {state}")
    
    def on_error(msg):
        print(f"❌ Error: {msg}")
    
    listener = VoiceCommandListener(
        on_command=on_command,
        on_wake=on_wake,
        on_heard=on_heard,
        on_state=on_state,
        on_error=on_error,
        wake_word="jarvis",
        require_wake_word=True
    )
    
    listener.set_enabled(True)
    listener.start()
    
    print("🎙️ Voice listener started. Say 'Jarvis' followed by a command.")
    print("Press Ctrl+C to stop.")
    
    try:
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\nStopping...")
        listener.stop()


if __name__ == "__main__":
    demo_voice_listener()
