# Crux – Windows AI Voice Assistant (English & Tamil)
Wake word **“Crux”**, dual STT (Google online / Whisper or Vosk offline), dual TTS (pyttsx3 / gTTS), PyQt5 GUI, command routing, and optional GPT integration.

---

## Features
- **Wake word:** “Crux” (phrase-based)
- **Speech-to-Text (STT):**
  - **Online:** Google (SpeechRecognition)
  - **Offline:** Whisper **or** Vosk (English + Tamil)
- **Text-to-Speech (TTS):**
  - **Offline:** pyttsx3 (Windows SAPI5)
  - **Online:** gTTS (with MP3 caching)
- **Commands (English & Tamil):**
  - Open apps (Notepad, Chrome, VS Code…)
  - Web search
  - Volume up/down/mute, Brightness up/down
  - Shutdown/Restart/Sleep (config-gated)
  - Play latest music/video from folders
  - “Write code …” (built-ins + GPT fallback)
  - General Q&A via **GPT** (optional)
- **GUI:** PyQt5 modern look, mic on/off, transcript, logs, status, tray
- **Logging:** `logs/crux.log` (human) & `logs/crux.jsonl` (structured)

---

## Project Structure
