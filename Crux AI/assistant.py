import os
import openai
import logging
import threading
import json
from datetime import datetime
# Local modules (we'll create them next)
import speech
import tts
import commands
from openai import OpenAI
client = OpenAI(api_key="")

class Assistant:
    """
    Central brain of Crux.
    Handles speech recognition, wake word, command routing,
    GPT Q&A, and TTS response.
    """

    def __init__(self, cfg: dict, event_cb=None):
        self.cfg = cfg
        self.event_cb = event_cb or (lambda e: None)
        self.running = False
        self.listening = False
        self.lock = threading.Lock()

        # Logging setup
        self.logger = logging.getLogger("crux.assistant")

        # STT + TTS engines
        self.stt_engine = speech.SpeechEngine(cfg, self.on_stt_result)
        self.tts_engine = tts.TTSEngine(cfg)

        # GPT
        self.gpt_cfg = cfg.get("gpt", {})
        if self.gpt_cfg.get("enabled") and openai:
            api_key = self.gpt_cfg.get("api_key") or os.environ.get(
                self.gpt_cfg.get("env_api_key", "OPENAI_API_KEY"), ""
            )
            if api_key:
                openai.api_key = api_key
                self.gpt_enabled = True
            else:
                self.logger.warning("GPT enabled but no API key set.")
                self.gpt_enabled = False
        else:
            self.gpt_enabled = False

        # Logging JSONL
        self.jsonl_path = getattr(logging, "CRUX_JSONL_PATH", None)

        self.logger.info("Assistant initialized. GPT enabled: %s", self.gpt_enabled)

    # ---- Public control ----
    def start_listening(self):
        with self.lock:
            if self.listening:
                return
            self.listening = True
        self.stt_engine.start_listening()
        self.emit({"type": "status", "message": "Listening..."})
        self.logger.info("Assistant started listening.")

    def stop_listening(self):
        with self.lock:
            if not self.listening:
                return
            self.listening = False
        self.stt_engine.stop_listening()
        self.emit({"type": "status", "message": "Mic muted"})
        self.logger.info("Assistant stopped listening.")

    def shutdown(self):
        self.stop_listening()
        self.stt_engine.shutdown()
        self.tts_engine.shutdown()
        self.logger.info("Assistant shutdown complete.")

    # ---- STT callback ----
    def on_stt_result(self, text: str):
        """Handle recognized speech text."""
        if not text:
            return
        self.logger.debug("STT result: %s", text)
        text_lower = text.strip().lower()

        # Wake word check
        wake_word = self.cfg.get("app", {}).get("wake_word", "crux").lower()
        if wake_word in text_lower:
            self.emit({"type": "log", "message": f"Heard wake word: {wake_word}"})
            # remove wake word for further processing
            text_lower = text_lower.replace(wake_word, "").strip()
            if not text_lower:
                return

        self.handle_user_text(text_lower)

    # ---- User text (typed or spoken) ----
    def handle_user_text(self, text: str):
        self.emit({"type": "transcript", "role": "user", "text": text})
        self.log_jsonl("user", text)

        response = self.route_command(text)

        if response:
            self.speak(response)
            self.emit({"type": "transcript", "role": "assistant", "text": response})
            self.log_jsonl("assistant", response)

    # ---- Command routing ----
    def route_command(self, text: str) -> str:
        # System/app/media commands
        handled, resp = commands.handle_command(text, self.cfg)
        if handled:
            return resp

        # GPT Q&A
        if self.gpt_enabled:
            try:
                return self.query_gpt(text)
            except Exception as e:
                self.logger.exception("GPT query failed: %s", e)
                return "Sorry, I couldn’t reach GPT right now."

        # Fallback
        return "I don’t understand. Please try again."

    def query_gpt(self, text: str) -> str:
        system_prompt = self.gpt_cfg.get("system_prompt", "You are Crux, a helpful assistant.")
        model = self.gpt_cfg.get("model", "gpt-5")
        max_tokens = self.gpt_cfg.get("max_tokens", 500)
        temp = self.gpt_cfg.get("temperature", 0.7)

        self.logger.debug("Sending GPT request: %s", text)

        resp = openai.ChatCompletion.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ],
            max_tokens=max_tokens,
            temperature=temp,
        )

        answer = resp["choices"][0]["message"]["content"].strip()
        return answer

    # ---- Speaking ----
    def speak(self, text: str):
        try:
            self.tts_engine.say(text)
        except Exception as e:
            self.logger.exception("TTS failed: %s", e)

    # ---- Logging ----
    def log_jsonl(self, role: str, text: str):
        if not self.jsonl_path:
            return
        entry = {
            "ts": datetime.utcnow().isoformat(),
            "role": role,
            "text": text,
        }
        try:
            with open(self.jsonl_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            self.logger.warning("Failed to log JSONL: %s", e)

    # ---- Events ----
    def emit(self, event: dict):
        try:
            self.event_cb(event)
        except Exception:
            self.logger.exception("Event callback failed.")


