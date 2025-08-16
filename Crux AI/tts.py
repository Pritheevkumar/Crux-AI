import os
import io
import time
import logging
import threading
import tempfile
from datetime import datetime

from gtts import gTTS
from playsound import playsound

try:
    import pyttsx3
except ImportError:
    pyttsx3 = None


class TTSEngine:
    """
    Unified TTS wrapper for:
      - Offline: pyttsx3 (Windows SAPI5)
      - Online: gTTS (MP3 cached + playsound)

    Respects language preference (en/ta) from config.
    """

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.logger = logging.getLogger("crux.tts")

        self.mode = cfg.get("tts", {}).get("mode", "offline")
        self.lang_pref = cfg.get("app", {}).get("language_preference", "en")

        # pyttsx3
        self.engine = None
        self._engine_lock = threading.Lock()

        # Cache dirs
        paths = cfg.get("paths", {})
        self.tts_cache_dir = os.path.expanduser(cfg.get("paths", {}).get("tts_cache_dir", "./runtime/tts_cache"))
        os.makedirs(self.tts_cache_dir, exist_ok=True)

        # Settings
        self.rate = int(cfg.get("tts", {}).get("rate", 175))
        self.volume = float(cfg.get("tts", {}).get("volume", 1.0))
        self.voice_filters = cfg.get("tts", {}).get("voices", {"en": "", "ta": ""})
        self.gtts_lang_map = cfg.get("tts", {}).get("gtts", {}).get("lang_map", {"en": "en", "ta": "ta"})

        if self.mode == "offline" and pyttsx3:
            try:
                self.engine = pyttsx3.init()  # SAPI5 on Windows by default
                self.engine.setProperty("rate", self.rate)
                self.engine.setProperty("volume", self.volume)
                self._pick_voice(self.lang_pref)
                self.logger.info("pyttsx3 initialized for offline TTS.")
            except Exception as e:
                self.logger.error("Failed to initialize pyttsx3: %s", e)
                self.engine = None
                self.mode = "online"  # failover to gTTS
        elif self.mode == "offline" and not pyttsx3:
            self.logger.warning("pyttsx3 not installed; falling back to gTTS online.")
            self.mode = "online"

        # Playback thread to avoid blocking GUI
        self._play_lock = threading.Lock()

    # ---- Voice selection for pyttsx3 ----
    def _pick_voice(self, lang: str):
        if not self.engine:
            return
        try:
            voices = self.engine.getProperty("voices") or []
            target_filter = (self.voice_filters or {}).get(lang, "").lower().strip()
            selected = None

            # Prefer voices whose name/language matches the target
            for v in voices:
                name = (getattr(v, "name", "") or "").lower()
                languages = getattr(v, "languages", []) or []
                lang_tags = [str(l).lower() for l in languages]
                if target_filter and target_filter in name:
                    selected = v
                    break
                # Basic heuristic: "en" in languages for English, "ta" for Tamil
                if not target_filter:
                    if lang == "en" and any("en" in t for t in lang_tags):
                        selected = v
                        break
                    if lang == "ta" and any("ta" in t for t in lang_tags):
                        selected = v
                        break

            # Fallback to the first available
            if not selected and voices:
                selected = voices[0]
            if selected:
                self.engine.setProperty("voice", selected.id)
                self.logger.debug("Selected pyttsx3 voice: %s", getattr(selected, "name", selected.id))
        except Exception as e:
            self.logger.warning("Voice selection failed: %s", e)

    # ---- Public API ----
    def say(self, text: str):
        """
        Speak text using configured TTS mode.
        For gTTS, stream via cached MP3 and playsound.
        """
        if not text:
            return

        if self.mode == "offline" and self.engine:
            self._say_offline(text)
        else:
            self._say_online(text)

    def shutdown(self):
        try:
            if self.engine:
                with self._engine_lock:
                    self.engine.stop()
        except Exception:
            pass

    # ---- Offline (pyttsx3) ----
    def _say_offline(self, text: str):
        with self._engine_lock:
            try:
                # Adjust voice if language changed at runtime
                current_lang = self.cfg.get("app", {}).get("language_preference", self.lang_pref)
                if current_lang != self.lang_pref:
                    self.lang_pref = current_lang
                    self._pick_voice(self.lang_pref)

                self.engine.say(text)
                self.engine.runAndWait()
            except RuntimeError:
                # Some systems need engine re-init if SAPI glitches
                self.logger.warning("pyttsx3 runtime error; reinitializing engine.")
                try:
                    self.engine = pyttsx3.init()
                    self.engine.setProperty("rate", self.rate)
                    self.engine.setProperty("volume", self.volume)
                    self._pick_voice(self.lang_pref)
                    self.engine.say(text)
                    self.engine.runAndWait()
                except Exception as e:
                    self.logger.error("pyttsx3 failed after reinit: %s", e)
                    # fallback to online
                    self._say_online(text)
            except Exception as e:
                self.logger.error("pyttsx3 failed: %s", e)
                self._say_online(text)

    # ---- Online (gTTS) ----
    def _say_online(self, text: str):
        lang_code = self.gtts_lang_code(self.lang_pref)

        # Key for cache file
        key = f"{lang_code}_{abs(hash(text))}.mp3"
        mp3_path = os.path.join(self.tts_cache_dir, key)

        if not os.path.exists(mp3_path):
            try:
                tts = gTTS(text=text, lang=lang_code)
                tts.save(mp3_path)
            except Exception as e:
                self.logger.error("gTTS synth failed: %s", e)
                return

        # Non-blocking playback (avoid overlapping)
        def _play():
            with self._play_lock:
                try:
                    playsound(mp3_path)
                except Exception as e:
                    self.logger.error("playsound error: %s", e)

        th = threading.Thread(target=_play, daemon=True)
        th.start()

    def gtts_lang_code(self, lang_pref: str) -> str:
        # Map en/ta to gTTS codes
        try:
            return self.gtts_lang_map.get(lang_pref, "en")
        except Exception:
            return "en"
