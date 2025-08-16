import os
import subprocess
import webbrowser
import pyttsx3
from gtts import gTTS
from playsound import playsound
import tempfile
import openai

# Ensure OpenAI API key is set
openai.api_key = os.getenv("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")    
try:
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    import ctypes
except Exception:
    AudioUtilities = None
    IAudioEndpointVolume = None

try:
    import screen_brightness_control as sbc
except Exception:
    sbc = None



def speak(text, cfg):
    """Use TTS (offline pyttsx3 or online gTTS)."""
    if cfg.get("tts", {}).get("engine") == "gtts":
        tts = gTTS(text=text, lang=cfg.get("language", "en"))
        with tempfile.NamedTemporaryFile(delete=True, suffix=".mp3") as fp:
            tts.save(fp.name)
            playsound(fp.name)
    else:
        engine = pyttsx3.init()
        engine.say(text)
        engine.runAndWait()


def handle_command(command, cfg):
    """Main command handler with safety checks."""
    command = command.lower()

    # --- Open apps ---
    if command.startswith("open "):
        app = command.replace("open ", "")
        if app in cfg.get("apps", {}):
            subprocess.Popen(cfg["apps"][app], shell=True)
            return True, f"Opening {app}."
        return True, f"App {app} not found in config."

    # --- Web search ---
    if command.startswith("search "):
        query = command.replace("search ", "")
        webbrowser.open(f"https://www.google.com/search?q={query}")
        return True, f"Searching the web for {query}."

    # --- Volume control ---
    if "volume" in command and AudioUtilities:
        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        volume = ctypes.cast(interface, ctypes.POINTER(IAudioEndpointVolume))
        cur = volume.GetMasterVolumeLevelScalar()

        if "up" in command:
            volume.SetMasterVolumeLevelScalar(min(cur + 0.1, 1.0), None)
            return True, "Volume increased."
        elif "down" in command:
            volume.SetMasterVolumeLevelScalar(max(cur - 0.1, 0.0), None)
            return True, "Volume decreased."

    # --- Brightness control ---
    if "brightness" in command and sbc:
        try:
            if "up" in command:
                sbc.set_brightness("+10")
                return True, "Brightness increased."
            elif "down" in command:
                sbc.set_brightness("-10")
                return True, "Brightness decreased."
        except Exception as e:
            return True, f"Brightness control error: {e}"

    # --- Safe shutdown / restart ---
    if "shutdown" in command or "restart" in command:
        if not cfg.get("allow_shutdown", False):
            return True, "Shutdown and restart are disabled in config."
        
        if "confirm" not in command:
            return True, "Say 'confirm shutdown' or 'confirm restart' to proceed."

        if "shutdown" in command:
            os.system("shutdown /s /t 1")
            return True, "Shutting down system..."
        elif "restart" in command:
            os.system("shutdown /r /t 1")
            return True, "Restarting system..."

    # --- Play music/videos ---
    if "play music" in command:
        music_path = cfg.get("music_path", "")
        if music_path and os.path.exists(music_path):
            os.startfile(music_path)
            return True, "Playing music."
        return True, "Music path not configured."

    # --- Code writing ---
    if command.startswith("crux write"):
        if "bubble sort" in command:
            code = (
                "def bubble_sort(arr):\n"
                "    n = len(arr)\n"
                "    for i in range(n):\n"
                "        for j in range(0, n-i-1):\n"
                "            if arr[j] > arr[j+1]:\n"
                "                arr[j], arr[j+1] = arr[j+1], arr[j]\n"
                "    return arr\n"
                "print(bubble_sort([64, 34, 25, 12, 22, 11, 90]))"
            )
            return True, code
    
    return False, "Command not recognized."
