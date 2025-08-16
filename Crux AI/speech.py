import os
import logging
import threading
import queue
import time

import speech_recognition as sr

# Optional offline engines
try:
    import whisper
except ImportError:
    whisper = None

try:
    from vosk import Model, KaldiRecognizer
    import json as jsonlib
except ImportError:
    Model = None
    KaldiRecognizer = None
    jsonlib = None


class SpeechEngine:
    """
    Handles microphone input, wake word STT, and recognition
    using online (Google) or offline (Whisper/Vosk) engines.
    """

    def __init__(self, cfg: dict, callback):
        self.cfg = cfg
        self.callback = callback  # function(text) → None
        self.logger = logging.getLogger("crux.speech")

        # Recognizer & mic
        self.recognizer = sr.Recognizer()
        self.recognizer.energy_threshold = cfg["stt"].get("energy_threshold", 300)
        self.recognizer.dynamic_energy_threshold = cfg["stt"].get("dynamic_energy", True)

        self.mic = None
        self.device_index = cfg["stt"].get("device_index", -1)

        # Offline engines
        self.offline_mode = cfg["stt"].get("mode", "offline") == "offline"
        self.offline_engine = cfg["stt"].get("preferred_offline_engine", "whisper")
        self.whisper_model = None
        self.vosk_model = None

        if self.offline_mode:
            if self.offline_engine == "whisper" and whisper:
                model_size = cfg["stt"]["whisper"].get("model", "base")
                self.logger.info("Loading Whisper model: %s", model_size)
                try:
                    self.whisper_model = whisper.load_model(model_size)
                except Exception as e:
                    self.logger.error("Failed to load Whisper: %s", e)
            elif self.offline_engine == "vosk" and Model:
                lang = cfg["app"].get("language_preference", "en")
                model_path = cfg["stt"]["vosk"].get(
                    f"model_path_{'en' if lang == 'en' else 'ta'}",
                    "./models/vosk"
                )
                self.logger.info("Loading Vosk model: %s", model_path)
                if os.path.isdir(model_path):
                    try:
                        self.vosk_model = Model(model_path)
                    except Exception as e:
                        self.logger.error("Failed to load Vosk: %s", e)
                else:
                    self.logger.warning("Vosk model path not found: %s", model_path)

        # Threading
        self.running = False
        self.thread = None

    # ---- Control ----
    def start_listening(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._listen_loop, daemon=True)
        self.thread.start()
        self.logger.info("SpeechEngine started listening.")

    def stop_listening(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)
        self.logger.info("SpeechEngine stopped listening.")

    def shutdown(self):
        self.stop_listening()

    # ---- Main loop ----
    def _listen_loop(self):
        self.logger.debug("Listen loop starting...")
        with sr.Microphone(device_index=self.device_index) as source:
            self.recognizer.adjust_for_ambient_noise(source, duration=1)
            while self.running:
                try:
                    audio = self.recognizer.listen(source, timeout=3, phrase_time_limit=8)
                except sr.WaitTimeoutError:
                    continue
                except Exception as e:
                    self.logger.error("Mic error: %s", e)
                    continue

                # Process recognition
                try:
                    text = self.recognize(audio)
                    if text:
                        self.logger.debug("Recognized: %s", text)
                        self.callback(text)
                except Exception as e:
                    self.logger.error("Recognition failed: %s", e)

    # ---- Recognition ----
    def recognize(self, audio) -> str:
        lang = self.cfg["app"].get("language_preference", "en")

        if self.offline_mode:
            if self.offline_engine == "whisper" and self.whisper_model:
                wav = audio.get_wav_data()
                import tempfile, numpy as np, io
                import soundfile as sf

                # Convert to numpy for Whisper
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                    tmp.write(wav)
                    tmp_path = tmp.name
                try:
                    result = self.whisper_model.transcribe(tmp_path, language=None if lang == "ta" else "en")
                    return result.get("text", "").strip()
                finally:
                    try:
                        os.remove(tmp_path)
                    except OSError:
                        pass

            elif self.offline_engine == "vosk" and self.vosk_model:
                rec = KaldiRecognizer(self.vosk_model, audio.sample_rate)
                rec.AcceptWaveform(audio.get_raw_data())
                result = rec.Result()
                if jsonlib:
                    j = jsonlib.loads(result)
                    return j.get("text", "").strip()
                return ""

            else:
                self.logger.warning("No offline STT engine available, falling back to Google.")
                return self._recognize_google(audio, lang)

        else:
            return self._recognize_google(audio, lang)

    def _recognize_google(self, audio, lang: str) -> str:
        try:
            if lang == "ta":
                return self.recognizer.recognize_google(audio, language="ta-IN")
            return self.recognizer.recognize_google(audio, language="en-US")
        except sr.UnknownValueError:
            return ""
        except sr.RequestError as e:
            self.logger.error("Google STT request failed: %s", e)
            return ""


