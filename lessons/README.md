# JARVIS Lessons - Building a Gesture + Voice Recognition System

These lessons teach you how to build **JARVIS**, a complete hand gesture and voice recognition system. Each lesson builds on the previous one, starting with basics and moving to advanced features.

## Learning Path

Run each lesson with the virtualenv activated:

```bash
. .venv/bin/activate
python lessons/lesson_XX_name.py
```

### Level 1: Camera Fundamentals

#### **Lesson 01: Open Camera** 
- **Goal**: Learn to access the webcam with OpenCV
- **Topics**: Video capture, frame reading, real-time display
- **Skills**: Setting up camera input for vision tasks
```bash
CAMERA_INDEX=0 python lessons/lesson_01_open_camera.py
```

### Level 2: Hand Detection & Gesture Recognition

#### **Lesson 02: Count Fingers**
- **Goal**: Detect hands and count raised fingers
- **Topics**: MediaPipe hand detection, landmark analysis, gesture detection
- **Skills**: ML-based hand tracking, geometric calculations
```bash
python lessons/lesson_02_count_fingers.py
```

#### **Lesson 03: Two Finger Screenshot**
- **Goal**: Take screenshots using a hand gesture
- **Topics**: Gesture triggering, screen capture, state management
- **Skills**: Combining gesture detection with system commands
```bash
python lessons/lesson_03_two_finger_screenshot.py
```

### Level 3: Voice & Audio Integration

#### **Lesson 04: Voice Command Recognition**
- **Goal**: Listen for and recognize voice commands
- **Topics**: Real-time audio capture, speech-to-text, wake word detection
- **Skills**: Voice processing, threading, callbacks
```bash
python lessons/lesson_04_voice_control.py
```

### Level 4: External Service Integration

#### **Lesson 05: Spotify Integration**
- **Goal**: Control music playback with Python
- **Topics**: OAuth authentication, API integration, error handling
- **Skills**: Working with APIs, credential management, graceful degradation
```bash
python lessons/lesson_05_spotify_integration.py
```

### Level 5: Complete System

#### **Lesson 06: Full JARVIS System**
- **Goal**: Combine all features into one powerful application
- **Topics**: Multi-modal input, event architecture, real-time processing
- **Skills**: System integration, performance optimization, user experience
```bash
CAMERA_INDEX=0 python lessons/lesson_06_gesture_recognition_full.py
```

Or use the main entry point:
```bash
CAMERA_INDEX=0 python gesture.py
```

**Controls:**
- Raise fingers to trigger actions
- Press `V` to toggle voice recognition
- Press `M` to switch between gesture and music modes
- Press `ESC` to quit

## What You'll Learn

✅ Real-time computer vision with OpenCV  
✅ Machine learning models (MediaPipe)  
✅ Audio processing and speech recognition  
✅ API authentication and integration  
✅ Multi-threaded applications  
✅ Event-driven architectures  
✅ Professional code structure and documentation  

## Setup Instructions

1. **Create virtual environment:**
   ```bash
   python3 -m venv .venv
   . .venv/bin/activate
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure Spotify (optional):**
   - Create a Spotify Developer account
   - Create a `.env` file in the project root:
   ```
   SPOTIFY_CLIENT_ID=your_client_id
   SPOTIFY_CLIENT_SECRET=your_client_secret
   SPOTIFY_REDIRECT_URI=http://127.0.0.1:8888/callback
   ```

4. **Install optional system dependencies:**
   ```bash
   # For local Spotify control (fallback)
   sudo apt install playerctl
   
   # For text-to-speech
   sudo apt install speech-dispatcher espeak
   
   # For local AI models (advanced)
   curl -fsSL https://ollama.ai/install.sh | sh
   ```

## Educational Use

These lessons are designed for learning. Each file contains:
- Clear comments explaining what's happening
- Well-structured code following best practices
- Modular functions that can be adapted
- Demo/test functions to verify learning

**Planned exercises for students:**
- Delete certain code sections and re-implement them
- Modify gesture triggers to do different actions
- Add new voice commands
- Integrate different external APIs
- Optimize performance for different hardware

## Tips for Learning

1. **Start with Lesson 01** - Understand the fundamentals
2. **Run each lesson independently** - Don't skip around
3. **Read the code comments** - They explain the "why"
4. **Modify and experiment** - Change parameters, try new things
5. **Use the print statements** - Debug output helps understanding
6. **Progress gradually** - Complex concepts build on simpler ones

---

**Happy learning!** 🎓


