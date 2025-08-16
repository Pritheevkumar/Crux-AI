import os
import sys
import json
import signal
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime

import yaml
from PyQt5 import QtWidgets

# --- Local modules (you'll paste these next) ---
# speech.py        -> STT engines + wake word listening
# tts.py           -> TTS engines (pyttsx3 / gTTS)
# commands.py      -> system/app/media/web commands
# assistant.py     -> intent routing, GPT Q&A, logging of conversations
# gui.py           -> PyQt5 main window, signals to/from assistant
try:
    from assistant import Assistant
    from gui import CruxMainWindow
except ImportError:
    # During first run (before you paste other files), keep a friendly message.
    Assistant = None
    CruxMainWindow = None


APP_NAME = "Crux"
DEFAULT_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.yaml")


def ensure_dirs(cfg: dict):
    """Create required directories if they don't exist."""
    paths = cfg.get("paths", {})
    for key in ["models_dir", "runtime_dir", "cache_dir", "tts_cache_dir", "logs_dir"]:
        d = paths.get(key)
        if d:
            os.makedirs(os.path.expanduser(d), exist_ok=True)

    # developer raw audio dir
    dev = cfg.get("developer", {})
    if dev.get("save_raw_audio"):
        raw_dir = dev.get("raw_audio_dir", "./runtime/raw_audio")
        os.makedirs(os.path.expanduser(raw_dir), exist_ok=True)


def setup_logging(cfg: dict):
    """Configure logging to file and console."""
    log_cfg = cfg.get("logging", {})
    level_name = log_cfg.get("level", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    log_file = os.path.expanduser(log_cfg.get("log_file", "./logs/crux.log"))
    jsonl_file = os.path.expanduser(log_cfg.get("jsonl_file", "./logs/crux.jsonl"))

    # Root logger
    logger = logging.getLogger()
    logger.setLevel(level)

    # Console handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(level)
    ch.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s"))
    logger.addHandler(ch)

    # File handler (rotating optional)
    rotate = bool(log_cfg.get("rotate", False))
    if rotate:
        fh = RotatingFileHandler(log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
    else:
        fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(level)
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    logger.addHandler(fh)

    # JSONL handler for structured conversation logs (Assistant will append too)
    if jsonl_file:
        # Create an extra logger for JSONL lines
        json_logger = logging.getLogger("crux.jsonl")
        json_logger.setLevel(level)
        jfh = logging.FileHandler(jsonl_file, encoding="utf-8")
        jfh.setLevel(level)
        jfh.setFormatter(logging.Formatter("%(message)s"))
        json_logger.addHandler(jfh)
        # store path on logging module for easy access elsewhere
        logging.CRUX_JSONL_PATH = jsonl_file

    logging.info(f"{APP_NAME} logging initialized")
    logging.debug("Logging configuration: %s", json.dumps(log_cfg, indent=2))


def load_config(path: str) -> dict:
    if not os.path.exists(path):
        raise FileNotFoundError(f"Config file not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    return cfg


def exception_hook(exc_type, exc_value, exc_traceback):
    """Ensure unhandled exceptions are logged and UI stays clean."""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    logging.exception("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))
    # Show a minimal dialog if GUI is up
    try:
        QtWidgets.QMessageBox.critical(None, f"{APP_NAME} - Error", f"{exc_type.__name__}: {exc_value}")
    except Exception:
        pass


class AppController:
    """
    Wires together configuration, Assistant (brains), and GUI.
    The Assistant exposes methods for starting/stopping mic,
    handling user text commands, and pushing logs/status back to GUI.
    """

    def __init__(self, cfg: dict, app: QtWidgets.QApplication):
        self.cfg = cfg
        self.qt_app = app
        self.assistant = None
        self.window = None

        # Instantiate Assistant
        if Assistant is None:
            logging.warning("Assistant module not found yet. Paste assistant.py to enable full functionality.")
        else:
            self.assistant = Assistant(cfg, self.on_assistant_event)

        # Build GUI
        if CruxMainWindow is None:
            logging.warning("GUI module not found yet. Paste gui.py to enable the interface.")
        else:
            self.window = CruxMainWindow(cfg, self.assistant)

            # Connect GUI → Assistant signals
            if self.assistant:
                self.window.signals.mic_toggle.connect(self.on_gui_mic_toggle)
                self.window.signals.text_submitted.connect(self.on_gui_text_submitted)
                self.window.signals.quit_requested.connect(self.on_gui_quit_requested)

            # Initial status
            self.window.append_log(f"{APP_NAME} started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            lang = cfg.get("app", {}).get("language_preference", "en")
            self.window.set_status(f"Ready • Language: {lang.upper()}")

    # ---- GUI event handlers ----
    def on_gui_mic_toggle(self, enable: bool):
        if not self.assistant:
            logging.error("Mic toggle requested but Assistant is not initialized.")
            return
        if enable:
            self.assistant.start_listening()
        else:
            self.assistant.stop_listening()

    def on_gui_text_submitted(self, text: str):
        if not self.assistant:
            logging.error("Text submitted but Assistant is not initialized.")
            return
        self.assistant.handle_user_text(text)

    def on_gui_quit_requested(self):
        logging.info("Quit requested from GUI.")
        self.shutdown()

    # ---- Assistant → GUI events ----
    def on_assistant_event(self, event: dict):
        """
        Assistant can emit events like:
        { "type": "log", "message": "..." }
        { "type": "status", "message": "..." }
        { "type": "transcript", "role": "user"/"assistant", "text": "..." }
        """
        if not self.window:
            return
        etype = event.get("type")
        if etype == "log":
            self.window.append_log(event.get("message", ""))
        elif etype == "status":
            self.window.set_status(event.get("message", ""))
        elif etype == "transcript":
            role = event.get("role", "assistant")
            text = event.get("text", "")
            self.window.append_transcript(role, text)

    def show(self):
        if self.window:
            self.window.show()
        else:
            # Headless fallback (useful while you paste files)
            logging.info("GUI not available; running headless. Press Ctrl+C to exit.")
            print(f"{APP_NAME} running headless. Paste gui.py to enable the interface.")

    def shutdown(self):
        try:
            if self.assistant:
                self.assistant.shutdown()
        finally:
            self.qt_app.quit()


def install_signal_handlers(controller: AppController):
    """Gracefully close on Ctrl+C / SIGTERM."""
    def handle_sigint(signum, frame):
        logging.info("Received signal %s, shutting down...", signum)
        controller.shutdown()

    signal.signal(signal.SIGINT, handle_sigint)
    try:
        signal.signal(signal.SIGTERM, handle_sigint)
    except Exception:
        # SIGTERM may not be available on some environments
        pass


def main():
    # Ensure stdout uses UTF-8 (Tamil-friendly)
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    # Load config
    cfg_path = os.environ.get("CRUX_CONFIG", DEFAULT_CONFIG_PATH)
    cfg = load_config(cfg_path)

    # Prepare folders & logging
    ensure_dirs(cfg)
    setup_logging(cfg)

    # Qt app
    qt_app = QtWidgets.QApplication(sys.argv)
    qt_app.setApplicationName(APP_NAME)

    # Controller
    controller = AppController(cfg, qt_app)
    install_signal_handlers(controller)
    controller.show()

    # Global exception hook
    sys.excepthook = exception_hook

    # Run
    exit_code = qt_app.exec_()
    logging.info("%s exited with code %s", APP_NAME, exit_code)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
