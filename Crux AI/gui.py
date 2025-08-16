import sys
from datetime import datetime

from PyQt5 import QtCore, QtGui, QtWidgets


class UISignals(QtCore.QObject):
    # Emitted when user toggles mic from the UI (True = on / False = off)
    mic_toggle = QtCore.pyqtSignal(bool)
    # Emitted when user submits a text command via the input box
    text_submitted = QtCore.pyqtSignal(str)
    # Emitted when the user chooses Quit (tray menu or File > Quit)
    quit_requested = QtCore.pyqtSignal()


class CruxMainWindow(QtWidgets.QMainWindow):
    """
    Main Window for Crux AI Assistant.
    - Left: Transcript (chat-style)
    - Bottom: Command input + Send button
    - Right: Logs panel (toggleable)
    - Top: Toolbar with Mic toggle and indicators
    - Bottom: Status bar
    """

    def __init__(self, cfg: dict, assistant=None, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.assistant = assistant
        self.signals = UISignals()

        self.setWindowTitle(self.cfg.get("app", {}).get("name", "Crux"))
        wcfg = self.cfg.get("gui", {}).get("window", {})
        width = int(wcfg.get("width", 1000))
        height = int(wcfg.get("height", 680))
        self.resize(width, height)
        if wcfg.get("start_centered", True):
            self._center_on_screen()

        # High DPI friendly text rendering
        QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps, True)

        # Build UI
        self._create_actions()
        self._create_toolbar()
        self._create_body()
        self._create_statusbar()
        self._apply_theme()

        # Tray
        if self.cfg.get("gui", {}).get("tray", {}).get("enabled", True):
            self._create_tray_icon()

        # Start mic state from config
        mic_muted = bool(self.cfg.get("gui", {}).get("mic_start_muted", False))
        self._set_mic_ui(not mic_muted)
        # If starting unmuted, emit request to start listening
        if not mic_muted:
            QtCore.QTimer.singleShot(200, lambda: self.signals.mic_toggle.emit(True))

    # -----------------------
    # UI Construction
    # -----------------------
    def _create_actions(self):
        self.act_toggle_mic = QtWidgets.QAction("Mic On/Off", self)
        self.act_toggle_mic.setCheckable(True)
        self.act_toggle_mic.setShortcut("Ctrl+M")
        self.act_toggle_mic.triggered.connect(self._toggle_mic_from_action)

        self.act_quit = QtWidgets.QAction("Quit", self)
        self.act_quit.setShortcut("Ctrl+Q")
        self.act_quit.triggered.connect(self._request_quit)

        self.act_clear_transcript = QtWidgets.QAction("Clear Transcript", self)
        self.act_clear_transcript.triggered.connect(self._clear_transcript)

        self.act_clear_logs = QtWidgets.QAction("Clear Logs", self)
        self.act_clear_logs.triggered.connect(self._clear_logs)

        self.act_toggle_logs_panel = QtWidgets.QAction("Show Logs Panel", self, checkable=True)
        self.act_toggle_logs_panel.setChecked(bool(self.cfg.get("gui", {}).get("show_logs_panel", True)))
        self.act_toggle_logs_panel.toggled.connect(self._toggle_logs_panel)

    def _create_toolbar(self):
        tb = QtWidgets.QToolBar("Main")
        tb.setMovable(False)
        tb.setIconSize(QtCore.QSize(20, 20))
        self.addToolBar(QtCore.Qt.TopToolBarArea, tb)

        # Mic toggle button (visual)
        self.mic_btn = QtWidgets.QToolButton(self)
        self.mic_btn.setText("🎙️ Mic")
        self.mic_btn.setCheckable(True)
        self.mic_btn.clicked.connect(self._toggle_mic_from_button)
        tb.addWidget(self.mic_btn)

        tb.addSeparator()

        # STT/TTS mode indicators
        stt_mode = self.cfg.get("stt", {}).get("mode", "offline").capitalize()
        tts_mode = self.cfg.get("tts", {}).get("mode", "offline").capitalize()
        self.lbl_modes = QtWidgets.QLabel(f"STT: {stt_mode} • TTS: {tts_mode}")
        tb.addWidget(self.lbl_modes)

        tb.addSeparator()

        # Language indicator
        lang = self.cfg.get("app", {}).get("language_preference", "en").upper()
        self.lbl_lang = QtWidgets.QLabel(f"Lang: {lang}")
        tb.addWidget(self.lbl_lang)

        tb.addSeparator()
        tb.addAction(self.act_toggle_logs_panel)
        tb.addAction(self.act_clear_transcript)
        tb.addAction(self.act_clear_logs)
        tb.addSeparator()
        tb.addAction(self.act_quit)

    def _create_body(self):
        central = QtWidgets.QWidget(self)
        self.setCentralWidget(central)

        main_layout = QtWidgets.QVBoxLayout(central)
        main_layout.setContentsMargins(12, 10, 12, 10)
        main_layout.setSpacing(10)

        # Splitter: left (transcript) | right (logs)
        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal, self)

        # Transcript panel
        left_panel = QtWidgets.QWidget(self)
        left_layout = QtWidgets.QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)

        title = QtWidgets.QLabel("Transcript")
        title.setObjectName("sectionTitle")
        left_layout.addWidget(title)

        self.transcript = QtWidgets.QTextEdit(self)
        self.transcript.setReadOnly(True)
        self.transcript.setObjectName("transcript")
        self.transcript.setLineWrapMode(QtWidgets.QTextEdit.WidgetWidth)
        left_layout.addWidget(self.transcript, 1)

        # Input row
        input_row = QtWidgets.QHBoxLayout()
        self.input = QtWidgets.QLineEdit(self)
        self.input.setPlaceholderText("Type a command or question…")
        self.input.returnPressed.connect(self._submit_text)
        input_row.addWidget(self.input, 1)

        self.btn_send = QtWidgets.QPushButton("Send")
        self.btn_send.clicked.connect(self._submit_text)
        input_row.addWidget(self.btn_send)

        left_layout.addLayout(input_row)

        # Logs panel (right)
        right_panel = QtWidgets.QWidget(self)
        right_layout = QtWidgets.QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        logs_title = QtWidgets.QLabel("Logs")
        logs_title.setObjectName("sectionTitle")
        right_layout.addWidget(logs_title)

        self.logs = QtWidgets.QPlainTextEdit(self)
        self.logs.setReadOnly(True)
        self.logs.setObjectName("logs")
        right_layout.addWidget(self.logs, 1)

        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        # Show/hide logs panel based on config
        if not self.cfg.get("gui", {}).get("show_logs_panel", True):
            right_panel.hide()

        main_layout.addWidget(splitter, 1)

    def _create_statusbar(self):
        sb = self.statusBar()
        sb.setSizeGripEnabled(False)
        self.status_label = QtWidgets.QLabel("Ready")
        sb.addPermanentWidget(self.status_label)

    # -----------------------
    # Theming
    # -----------------------
    def _apply_theme(self):
        gui = self.cfg.get("gui", {})
        theme = gui.get("theme", "light").lower()
        accent = gui.get("accent_color", "#4F46E5")

        # Basic modern QSS
        base_bg = "#0f172a" if theme == "dark" else "#ffffff"
        base_fg = "#e2e8f0" if theme == "dark" else "#111827"
        panel_bg = "#111827" if theme == "dark" else "#f8fafc"
        border = "#1f2937" if theme == "dark" else "#e5e7eb"
        subtle = "#94a3b8" if theme == "dark" else "#6b7280"

        qss = f"""
        QMainWindow {{
            background: {base_bg};
            color: {base_fg};
        }}
        QLabel#sectionTitle {{
            font-weight: 600;
            color: {base_fg};
        }}
        QTextEdit#transcript, QPlainTextEdit#logs {{
            background: {panel_bg};
            color: {base_fg};
            border: 1px solid {border};
            border-radius: 8px;
            padding: 8px;
        }}
        QLineEdit {{
            background: {panel_bg};
            color: {base_fg};
            border: 1px solid {border};
            border-radius: 8px;
            padding: 8px;
            selection-background-color: {accent};
        }}
        QPushButton {{
            background: {accent};
            color: white;
            border: none;
            border-radius: 8px;
            padding: 8px 14px;
            font-weight: 600;
        }}
        QPushButton:hover {{
            filter: brightness(1.05);
        }}
        QToolBar {{
            background: {panel_bg};
            border-bottom: 1px solid {border};
            spacing: 8px;
        }}
        QToolButton {{
            background: {panel_bg};
            color: {base_fg};
            padding: 6px 10px;
            border: 1px solid {border};
            border-radius: 8px;
        }}
        QToolButton:checked {{
            background: {accent};
            color: white;
            border-color: {accent};
        }}
        QStatusBar {{
            background: {panel_bg};
            color: {subtle};
            border-top: 1px solid {border};
        }}
        """
        self.setStyleSheet(qss)

    # -----------------------
    # System Tray
    # -----------------------
    def _create_tray_icon(self):
        self.tray = QtWidgets.QSystemTrayIcon(self)
        # Simple emoji icon as a placeholder
        pix = QtGui.QPixmap(64, 64)
        pix.fill(QtCore.Qt.transparent)
        p = QtGui.QPainter(pix)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        p.setBrush(QtGui.QBrush(QtGui.QColor(self.cfg.get("gui", {}).get("accent_color", "#4F46E5"))))
        p.setPen(QtCore.Qt.NoPen)
        p.drawEllipse(4, 4, 56, 56)
        p.end()
        self.tray.setIcon(QtGui.QIcon(pix))
        self.tray.setToolTip(self.cfg.get("app", {}).get("name", "Crux"))

        menu = QtWidgets.QMenu()
        act_show = menu.addAction("Show")
        act_show.triggered.connect(self._tray_show)
        act_mic = menu.addAction("Mic On" if not self.mic_btn.isChecked() else "Mic Off")
        act_mic.triggered.connect(lambda: self.mic_btn.click())
        menu.addSeparator()
        act_quit = menu.addAction("Quit")
        act_quit.triggered.connect(self._request_quit)

        self._tray_mic_action = act_mic  # keep a reference to rename later
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._tray_activated)
        self.tray.show()

    def _tray_show(self):
        self.showNormal()
        self.activateWindow()
        self.raise_()

    def _tray_activated(self, reason):
        if reason == QtWidgets.QSystemTrayIcon.Trigger:  # single click
            self._tray_show()

    # -----------------------
    # Slots / UI Logic
    # -----------------------
    def _center_on_screen(self):
        geo = self.frameGeometry()
        screen = QtWidgets.QApplication.desktop().screenNumber(QtWidgets.QApplication.desktop().cursor().pos())
        center = QtWidgets.QApplication.desktop().screenGeometry(screen).center()
        geo.moveCenter(center)
        self.move(geo.topLeft())

    def _toggle_mic_from_button(self, checked: bool):
        self._set_mic_ui(checked)
        self.signals.mic_toggle.emit(checked)

    def _toggle_mic_from_action(self, checked: bool):
        # Synchronize toolbar button
        self.mic_btn.setChecked(checked)
        self._set_mic_ui(checked)
        self.signals.mic_toggle.emit(checked)

    def _set_mic_ui(self, enabled: bool):
        if enabled:
            self.mic_btn.setChecked(True)
            self.mic_btn.setText("🎙️ Mic ON")
            self.set_status("Listening…")
            if hasattr(self, "_tray_mic_action"):
                self._tray_mic_action.setText("Mic Off")
        else:
            self.mic_btn.setChecked(False)
            self.mic_btn.setText("🎙️ Mic OFF")
            self.set_status("Mic muted")
            if hasattr(self, "_tray_mic_action"):
                self._tray_mic_action.setText("Mic On")

        # Keep the menu action state in sync
        self.act_toggle_mic.setChecked(enabled)

    def _submit_text(self):
        text = self.input.text().strip()
        if not text:
            return
        self.input.clear()
        # Emit to controller/assistant
        self.signals.text_submitted.emit(text)

    def _clear_transcript(self):
        self.transcript.clear()

    def _clear_logs(self):
        self.logs.clear()

    def _toggle_logs_panel(self, show: bool):
        # Find the right panel by object name
        # Our layout: central -> splitter -> [left_panel, right_panel]
        splitter = self.centralWidget().findChild(QtWidgets.QSplitter)
        if not splitter:
            return
        # Right widget is index 1
        right = splitter.widget(1)
        if right:
            right.setVisible(show)

    def _request_quit(self):
        # Confirm if configured
        if self.cfg.get("gui", {}).get("tray", {}).get("quit_confirms", True):
            reply = QtWidgets.QMessageBox.question(
                self, "Quit Crux", "Are you sure you want to quit?",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.No
            )
            if reply != QtWidgets.QMessageBox.Yes:
                return
        self.signals.quit_requested.emit()

    # -----------------------
    # API for Controller
    # -----------------------
    def append_log(self, message: str):
        if not message:
            return
        ts = datetime.now().strftime("%H:%M:%S")
        self.logs.appendPlainText(f"[{ts}] {message}")
        # Auto-scroll
        self.logs.verticalScrollBar().setValue(self.logs.verticalScrollBar().maximum())

    def append_transcript(self, role: str, text: str):
        if not text:
            return
        ts = datetime.now().strftime("%H:%M")
        role = (role or "assistant").strip().lower()
        color_user = "#16a34a"  # green
        color_asst = "#2563eb"  # blue
        if role == "user":
            html = f'<div style="margin:6px 0;"><b style="color:{color_user};">You</b> <span style="color:#6b7280;">[{ts}]</span><br>{self._html_escape(text)}</div>'
        else:
            html = f'<div style="margin:6px 0;"><b style="color:{color_asst};">Crux</b> <span style="color:#6b7280;">[{ts}]</span><br>{self._html_escape(text)}</div>'
        self.transcript.append(html)
        # Auto-scroll
        self.transcript.verticalScrollBar().setValue(self.transcript.verticalScrollBar().maximum())

    def set_status(self, message: str):
        self.status_label.setText(message or "")

    # -----------------------
    # Window events
    # -----------------------
    def closeEvent(self, event: QtGui.QCloseEvent):
        # If tray enabled, minimize to tray instead of exiting
        tray_cfg = self.cfg.get("gui", {}).get("tray", {})
        if tray_cfg.get("enabled", True):
            event.ignore()
            self.hide()
            if hasattr(self, "tray"):
                self.tray.showMessage(
                    self.cfg.get("app", {}).get("name", "Crux"),
                    "Crux is still running here in the tray.",
                    QtWidgets.QSystemTrayIcon.Information,
                    2500
                )
        else:
            super().closeEvent(event)

    # -----------------------
    # Utils
    # -----------------------
    @staticmethod
    def _html_escape(text: str) -> str:
        return (
            text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace("\n", "<br>")
        )
