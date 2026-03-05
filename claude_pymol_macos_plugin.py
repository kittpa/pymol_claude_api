"""
Claude AI Plugin for PyMOL  (macOS Qt-native, docked panel)
============================================================
Embeds a Claude chat panel directly inside the PyMOL window.

API key is saved to ~/.claude_pymol_config.json on first use
and loaded automatically on every subsequent startup.

Installation:
1. pip install anthropic
2. Plugin > Plugin Manager > Install New Plugin > choose this file

Commands (PyMOL terminal):
  ai_key YOUR_KEY   – set & save API key permanently
  ai_key_clear      – delete the saved key
  ai <request>      – natural language → PyMOL commands
  ai_chat           – toggle the docked chat panel
  ai_clear          – clear conversation history
  ai_help           – show help
"""

import os
import json
import threading
from pathlib import Path

# ─── Persistent config ────────────────────────────────────────────────────────
_CONFIG_PATH = Path.home() / ".claude_pymol_config.json"

def _load_config() -> dict:
    try:
        if _CONFIG_PATH.exists():
            return json.loads(_CONFIG_PATH.read_text())
    except Exception:
        pass
    return {}

def _save_config(data: dict):
    try:
        _CONFIG_PATH.write_text(json.dumps(data, indent=2))
        _CONFIG_PATH.chmod(0o600)   # owner read/write only — keeps key private
    except Exception as exc:
        print(f"[ClaudePlugin] Could not save config: {exc}")

# Load key at import time: env var wins, then saved file, then empty
_config   = _load_config()
_API_KEY  = os.environ.get("ANTHROPIC_API_KEY", "") or _config.get("api_key", "")

# ─── Anthropic ────────────────────────────────────────────────────────────────
try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

# ─── PyMOL ────────────────────────────────────────────────────────────────────
try:
    from pymol import cmd
    PYMOL_AVAILABLE = True
except ImportError:
    PYMOL_AVAILABLE = False
    print("[ClaudePlugin] Warning: PyMOL not found – running in test mode.")

# ─── Qt ───────────────────────────────────────────────────────────────────────
try:
    from pymol.Qt import QtWidgets, QtCore, QtGui
    QT_AVAILABLE = True
except ImportError:
    QT_AVAILABLE = False
    print("[ClaudePlugin] Warning: pymol.Qt not found – ai_chat unavailable.")

# ─── Conversation history ─────────────────────────────────────────────────────
_HISTORY  = []
_dock     = None

SYSTEM_PROMPT = """You are an expert PyMOL assistant. Translate the user's natural language
description into PyMOL commands.

Rules:
1. Respond ONLY with valid PyMOL commands (pymol.cmd / CLI syntax).
2. One command per line.
3. Add brief # comments explaining each command.
4. Make reasonable assumptions when the request is ambiguous.
5. NO prose, NO markdown code fences – comments only.
6. Useful commands: fetch, load, select, show, hide, color, set, zoom, center,
   cartoon, surface, sticks, spheres, lines, save, png, align, super, cealign,
   create, delete, enable, disable, label, distance, angle, dihedral, spectrum,
   bg_color, set_color, ray, refresh.

Example input : "show protein as cartoon colored by secondary structure"
Example output:
hide everything
show cartoon
color red, ss h       # alpha helices
color yellow, ss s    # beta sheets
color white, ss l+    # loops
zoom
"""

# ─── Palette ──────────────────────────────────────────────────────────────────
BG          = "#0f0f14"
PANEL       = "#1a1a24"
ACCENT      = "#7c5cfc"
TEXT        = "#e8e8f0"
MUTED       = "#6b6b80"
GREEN       = "#a0d468"
CYAN        = "#3ec6c6"
RED         = "#e05c5c"
INPUT_BG    = "#13131e"
USER_BUBBLE = "#2d2250"
USER_TEXT   = "#d4c8ff"
BOT_BUBBLE  = "#0e2a2a"
BOT_TEXT    = "#9ee8e8"
CODE_BUBBLE = "#141f10"
CODE_TEXT   = "#a0d468"
SYS_BUBBLE  = "#1a1a1a"
SYS_TEXT    = "#6b6b80"

# ─── API helpers ──────────────────────────────────────────────────────────────

def _get_client():
    if not ANTHROPIC_AVAILABLE:
        print("[ClaudePlugin] anthropic not installed. Run: pip install anthropic")
        return None
    key = _API_KEY or os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        print("[ClaudePlugin] No API key. Run: ai_key YOUR_KEY")
        return None
    return anthropic.Anthropic(api_key=key)


def _ask_claude(user_text: str, use_history: bool = False) -> str:
    client = _get_client()
    if not client:
        return ""
    if use_history:
        _HISTORY.append({"role": "user", "content": user_text})
        messages = list(_HISTORY)
    else:
        messages = [{"role": "user", "content": user_text}]
    try:
        resp = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=messages,
        )
        result = resp.content[0].text.strip()
        if use_history:
            _HISTORY.append({"role": "assistant", "content": result})
        return result
    except Exception as exc:
        print(f"[ClaudePlugin] API error: {exc}")
        return ""


def _execute_commands(commands: str):
    if not commands:
        return []
    executed = []
    for line in commands.strip().splitlines():
        code = line.split("#")[0].strip()
        if not code:
            continue
        print(f"[ClaudePlugin] > {line}")
        if PYMOL_AVAILABLE:
            try:
                cmd.do(code)
                executed.append(line)
            except Exception as exc:
                print(f"[ClaudePlugin] Error executing '{code}': {exc}")
        else:
            executed.append(line)
    return executed

# ─── PyMOL CLI commands ───────────────────────────────────────────────────────

def ai(query: str):
    """Natural language → PyMOL commands.  Usage: ai show protein as surface"""
    if not query.strip():
        print("[ClaudePlugin] Usage: ai <your request>")
        return
    print(f"\n[ClaudePlugin] Asking Claude: '{query}' …")
    cmds = _ask_claude(query)
    if cmds:
        print(f"\n[ClaudePlugin] Executing:\n{'-'*40}\n{cmds}\n{'-'*40}")
        _execute_commands(cmds)
    else:
        print("[ClaudePlugin] No commands received.")


def ai_key(key: str):
    """
    Set AND save the Anthropic API key.
    Saved to ~/.claude_pymol_config.json — loaded automatically next startup.
    Usage: ai_key sk-ant-...
    """
    global _API_KEY
    _API_KEY = key.strip()
    cfg = _load_config()
    cfg["api_key"] = _API_KEY
    _save_config(cfg)
    print(f"[ClaudePlugin] API key saved to {_CONFIG_PATH}")


def ai_key_clear():
    """Delete the saved API key from disk."""
    global _API_KEY
    _API_KEY = ""
    cfg = _load_config()
    cfg.pop("api_key", None)
    _save_config(cfg)
    print(f"[ClaudePlugin] Saved API key removed from {_CONFIG_PATH}")


def ai_clear():
    """Clear conversation history."""
    global _HISTORY
    _HISTORY.clear()
    print("[ClaudePlugin] History cleared.")


def ai_chat():
    """Toggle the docked Claude chat panel."""
    if not QT_AVAILABLE:
        print("[ClaudePlugin] Qt not available – use 'ai <query>' instead.")
        return
    _toggle_dock()


def ai_help():
    key_status = (
        f"saved in {_CONFIG_PATH}" if _config.get("api_key")
        else "not set – run: ai_key YOUR_KEY"
    )
    print(f"""
╔══════════════════════════════════════════════════════════╗
║         Claude AI Plugin for PyMOL  –  Help              ║
╠══════════════════════════════════════════════════════════╣
║  API key : {key_status:<46}║
╠══════════════════════════════════════════════════════════╣
║  Setup:                                                  ║
║    ai_key YOUR_KEY   Save key (persists across restarts) ║
║    ai_key_clear      Delete the saved key                ║
║                                                          ║
║  Commands:                                               ║
║    ai <query>        Natural language → PyMOL commands   ║
║    ai_chat           Toggle docked chat panel            ║
║    ai_clear          Clear conversation history          ║
║    ai_help           Show this help                      ║
║                                                          ║
║  Panel tips:                                             ║
║    ↑ / ↓             Navigate input history              ║
║    Drag title bar    Dock to any edge                    ║
║    Double-click      Float as separate window            ║
╚══════════════════════════════════════════════════════════╝
""")

# ─── Chat bubble helper ───────────────────────────────────────────────────────

if QT_AVAILABLE:

    def _bubble(text, bg, fg, label="", label_color=MUTED,
                align="left", mono=False):
        font_style = ("font-family:'Courier New',monospace;" if mono
                      else "font-family:system-ui,sans-serif;")
        escaped = (text.replace("&", "&amp;")
                       .replace("<", "&lt;")
                       .replace(">", "&gt;")
                       .replace("\n", "<br>"))
        bubble_td = (
            f"<td style='background:{bg}; color:{fg}; "
            f"padding:7px 10px; border-radius:8px; "
            f"{font_style} font-size:11px; white-space:pre-wrap;'>"
            f"{escaped}</td>")
        spacer = "<td style='min-width:30px;'></td>"
        label_td = (
            f"<td style='color:{label_color}; font-size:9px; "
            f"font-family:\"Courier New\",monospace; "
            f"vertical-align:top; padding-top:8px; white-space:nowrap;'>"
            f"{label}</td>")
        cells = (f"{spacer}{bubble_td}{label_td}" if align == "right"
                 else f"{label_td}{bubble_td}{spacer}")
        return (f"<table width='100%' cellspacing='0' cellpadding='2' "
                f"style='margin:3px 0;'><tr>{cells}</tr></table>")

# ─── Docked chat widget ───────────────────────────────────────────────────────

if QT_AVAILABLE:

    class ClaudePanelWidget(QtWidgets.QWidget):

        _result_ready = QtCore.Signal(str, str)

        def __init__(self, parent=None):
            super().__init__(parent)
            self.setStyleSheet(f"background:{BG}; color:{TEXT};")
            self._input_history: list = []
            self._hist_idx: int = -1
            self._draft: str = ""
            self._build_ui()
            self._result_ready.connect(self._on_result)

        def _build_ui(self):
            root = QtWidgets.QVBoxLayout(self)
            root.setContentsMargins(0, 0, 0, 0)
            root.setSpacing(0)

            # Chat display
            self.chat = QtWidgets.QTextEdit()
            self.chat.setReadOnly(True)
            self.chat.setStyleSheet(
                f"background:{BG}; color:{TEXT}; border:none; padding:4px;")
            root.addWidget(self.chat, stretch=1)

            line = QtWidgets.QFrame()
            line.setFrameShape(QtWidgets.QFrame.HLine)
            line.setStyleSheet(f"color:{PANEL};")
            root.addWidget(line)

            # Status bar
            self.status = QtWidgets.QLabel("Ready")
            self.status.setStyleSheet(
                f"background:{INPUT_BG}; color:{MUTED}; "
                f"font:9px 'Courier'; padding:3px 10px;")
            root.addWidget(self.status)

            # Input row
            input_row = QtWidgets.QWidget()
            input_row.setStyleSheet(f"background:{INPUT_BG};")
            il = QtWidgets.QHBoxLayout(input_row)
            il.setContentsMargins(8, 6, 8, 6)
            il.setSpacing(6)

            self.input = QtWidgets.QLineEdit()
            self.input.setStyleSheet(
                f"background:{PANEL}; color:{TEXT}; font:10px 'Courier'; "
                f"border:none; border-radius:4px; padding:6px 8px;")
            self.input.setPlaceholderText("Ask Claude about your structure…")
            self.input.returnPressed.connect(self._on_submit)
            self.input.installEventFilter(self)
            il.addWidget(self.input, stretch=1)

            self.send_btn = QtWidgets.QPushButton("Ask ↵")
            self.send_btn.setFixedWidth(56)
            self.send_btn.setStyleSheet(
                f"background:{ACCENT}; color:white; font:bold 9px 'Courier'; "
                f"border:none; padding:6px; border-radius:4px;")
            self.send_btn.clicked.connect(self._on_submit)
            il.addWidget(self.send_btn)
            root.addWidget(input_row)

            # Quick chips
            chips_row = QtWidgets.QWidget()
            chips_row.setStyleSheet(f"background:{BG};")
            cl = QtWidgets.QHBoxLayout(chips_row)
            cl.setContentsMargins(8, 2, 8, 6)
            cl.setSpacing(4)
            for label, example in [
                ("clear ai_chat history",   None),
            ]:
                b = QtWidgets.QPushButton(label)
                b.setStyleSheet(
                    f"background:{PANEL}; color:{MUTED}; font:8px 'Courier'; "
                    f"border:none; padding:3px 8px; border-radius:10px;")
                b.setCursor(QtCore.Qt.PointingHandCursor)
                if example:
                    b.clicked.connect(lambda _, t=example: self._set_example(t))
                else:
                    b.clicked.connect(self._clear_history)
                cl.addWidget(b)
            cl.addStretch()
            root.addWidget(chips_row)

            # Welcome / key status
            if _API_KEY:
                masked = _API_KEY[:12] + "…" + _API_KEY[-4:]
                self._append_system(
                    f"Claude · PyMOL Assistant\n"
                    f"API key loaded: {masked}\n"
                    f"Use ↑ / ↓ to navigate prompt history.")
            else:
                self._append_system(
                    "Claude · PyMOL Assistant\n"
                    "⚠️  No API key found.\n"
                    "Run:  ai_key YOUR_ANTHROPIC_API_KEY")

        # ── bubble helpers ────────────────────────────────────────────────────

        def _append_html(self, html):
            self.chat.moveCursor(QtGui.QTextCursor.End)
            self.chat.insertHtml(html)
            self.chat.moveCursor(QtGui.QTextCursor.End)

        def _append_user(self, text):
            self._append_html(_bubble(text, USER_BUBBLE, USER_TEXT,
                                      "you", ACCENT, "right"))

        def _append_claude(self, text):
            self._append_html(_bubble(text, BOT_BUBBLE, BOT_TEXT,
                                      "claude", CYAN, "left"))

        def _append_code(self, text):
            self._append_html(_bubble(text, CODE_BUBBLE, CODE_TEXT,
                                      "cmd", GREEN, "left", mono=True))

        def _append_system(self, text):
            self._append_html(_bubble(text, SYS_BUBBLE, SYS_TEXT))

        def _append_error(self, text):
            self._append_html(_bubble(text, "#2a0a0a", RED,
                                      "error", RED, "left"))

        # ── history navigation ────────────────────────────────────────────────

        def eventFilter(self, obj, event):
            if obj is self.input and event.type() == QtCore.QEvent.KeyPress:
                if event.key() == QtCore.Qt.Key_Up:
                    self._history_up(); return True
                if event.key() == QtCore.Qt.Key_Down:
                    self._history_down(); return True
            return super().eventFilter(obj, event)

        def _history_up(self):
            if not self._input_history:
                return
            if self._hist_idx == -1:
                self._draft = self.input.text()
            self._hist_idx = min(self._hist_idx + 1,
                                 len(self._input_history) - 1)
            self.input.setText(self._input_history[-(self._hist_idx + 1)])
            self.input.end(False)

        def _history_down(self):
            if self._hist_idx == -1:
                return
            self._hist_idx -= 1
            if self._hist_idx == -1:
                self.input.setText(self._draft)
            else:
                self.input.setText(self._input_history[-(self._hist_idx + 1)])
            self.input.end(False)

        # ── submit ────────────────────────────────────────────────────────────

        def _on_submit(self):
            query = self.input.text().strip()
            if not query:
                return
            if not self._input_history or self._input_history[-1] != query:
                self._input_history.append(query)
            self._hist_idx = -1
            self._draft = ""
            self.input.clear()
            self._append_user(query)
            self.status.setText("Asking Claude…")
            self.send_btn.setEnabled(False)
            threading.Thread(
                target=self._worker, args=(query,), daemon=True).start()

        def _worker(self, query):
            commands = _ask_claude(query, use_history=True)
            self._result_ready.emit("ok" if commands else "error", commands)

        def _on_result(self, status, commands):
            if status == "ok":
                self._append_claude("Here are the commands to execute:")
                self._append_code(commands)
                self.status.setText("Executing…")
                _execute_commands(commands)
                self.status.setText("Done · ready for next command")
            else:
                self._append_error(
                    "No response received.\n"
                    "Check your key with:  ai_key YOUR_KEY")
                self.status.setText("Error · check API key")
            self.send_btn.setEnabled(True)
            self.input.setFocus()

        def _clear_history(self):
            ai_clear()
            self.chat.clear()
            self._append_system("History cleared.")

        def _set_example(self, text):
            self.input.setText(text)
            self.input.setFocus()
            self.input.end(False)

        def focus_input(self):
            self.input.setFocus()

# ─── Dock management ──────────────────────────────────────────────────────────

def _get_main_window():
    app = QtWidgets.QApplication.instance()
    if app is None:
        return None
    for w in app.topLevelWidgets():
        if isinstance(w, QtWidgets.QMainWindow):
            return w
    return None


def _toggle_dock():
    global _dock
    main_win = _get_main_window()
    if main_win is None:
        print("[ClaudePlugin] Could not find PyMOL main window.")
        return
    if _dock is not None:
        try:
            if _dock.isVisible():
                _dock.hide()
            else:
                _dock.show()
                _dock.widget().focus_input()
            return
        except RuntimeError:
            _dock = None

    _dock = QtWidgets.QDockWidget("  Claude AI", main_win)
    _dock.setObjectName("ClaudeAIDock")
    _dock.setAllowedAreas(
        QtCore.Qt.LeftDockWidgetArea  |
        QtCore.Qt.RightDockWidgetArea |
        QtCore.Qt.BottomDockWidgetArea)
    _dock.setFeatures(
        QtWidgets.QDockWidget.DockWidgetMovable   |
        QtWidgets.QDockWidget.DockWidgetFloatable |
        QtWidgets.QDockWidget.DockWidgetClosable)
    _dock.setStyleSheet(f"""
        QDockWidget {{
            color: {TEXT};
            font: bold 10px 'Courier';
        }}
        QDockWidget::title {{
            background: {ACCENT};
            padding: 6px 10px;
            text-align: left;
        }}
        QDockWidget::close-button,
        QDockWidget::float-button {{
            background: transparent;
            border: none;
        }}
    """)
    panel = ClaudePanelWidget()
    _dock.setWidget(panel)
    _dock.setMinimumWidth(300)
    main_win.addDockWidget(QtCore.Qt.RightDockWidgetArea, _dock)
    panel.focus_input()

# ─── Plugin entry-point ───────────────────────────────────────────────────────

def __init_plugin__(app=None):
    _register()
    if QT_AVAILABLE:
        try:
            from pymol.plugins import addmenuitemqt
            addmenuitemqt("Claude AI", _toggle_dock)
        except Exception:
            pass
    key_msg = (f"API key loaded from {_CONFIG_PATH}"
               if _API_KEY else "No API key – run: ai_key YOUR_KEY")
    print(f"\n[ClaudePlugin] ✓ Claude AI Plugin loaded!")
    print(f"[ClaudePlugin]   {key_msg}")
    print(f"[ClaudePlugin]   Open panel : ai_chat  (or Plugin > Claude AI)\n")


def _register():
    if PYMOL_AVAILABLE:
        cmd.extend("ai",         ai)
        cmd.extend("ai_key",     ai_key)
        cmd.extend("ai_key_clear", ai_key_clear)
        cmd.extend("ai_clear",   ai_clear)
        cmd.extend("ai_chat",    ai_chat)
        cmd.extend("ai_help",    ai_help)


if PYMOL_AVAILABLE and __name__ != "__main__":
    _register()
    print("\n[ClaudePlugin] ✓ Claude AI commands registered.")
    print(f"[ClaudePlugin]   Config: {_CONFIG_PATH}\n")

# ─── Standalone test ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    print("Standalone test mode…")
    if not ANTHROPIC_AVAILABLE:
        print("Warning: run  pip install anthropic  first.")
    if not _API_KEY:
        key = input("Anthropic API key (Enter to skip): ").strip()
        if key:
            ai_key(key)
    if QT_AVAILABLE:
        app = QtWidgets.QApplication(sys.argv)
        main_win = QtWidgets.QMainWindow()
        main_win.setWindowTitle("PyMOL (test)")
        main_win.resize(1100, 700)
        central = QtWidgets.QLabel("← PyMOL viewport")
        central.setAlignment(QtCore.Qt.AlignCenter)
        central.setStyleSheet(
            f"background:{BG}; color:{MUTED}; font:12px 'Courier';")
        main_win.setCentralWidget(central)
        dock = QtWidgets.QDockWidget("  Claude AI", main_win)
        dock.setWidget(ClaudePanelWidget())
        dock.setMinimumWidth(320)
        main_win.addDockWidget(QtCore.Qt.RightDockWidgetArea, dock)
        main_win.show()
        sys.exit(app.exec_())
    else:
        print("Qt not available.")