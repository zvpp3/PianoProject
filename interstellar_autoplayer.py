#!/usr/bin/env python3
"""Galaxy-themed Roblox piano autoplayer GUI."""

from __future__ import annotations

import json
import queue
import re
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, scrolledtext, ttk

from pynput import keyboard

DEFAULT_SHEET = """u u
u u u
u u u
u u u
[eup] u u
[rua] u u
u u u
[eup] [rua] [tus]
[rua] [eup] [rua]
[tus] u u
[rua] u u
u u u
[eup] u [uf]
[tus] u u
[rua] u u
u u u
[eup] [uf] [tus]
[rua] [eup] [rua]
[tus] u u
[rua] u u
u u u
[eup] [uf] [tus]
[rua] [eup] [rua]
[tus] u u"""

SETTINGS_FILE = Path("autoplayer_settings.json")
TOKEN_RE = re.compile(r"\[[^\]]+\]|\S+")
VALID_KEY = re.compile(r"^[a-z0-9]$")


class App:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("🌌 Interstellar Roblox Piano Autoplayer")
        self.root.geometry("980x720")
        self.root.configure(bg="#090b1a")

        self.stop_event = threading.Event()
        self.playing = False
        self.msg_queue: queue.Queue[tuple[str, str]] = queue.Queue()

        cfg = self._load_settings()
        self.bpm_var = tk.IntVar(value=cfg.get("bpm", 120))
        self.hold_var = tk.DoubleVar(value=cfg.get("hold", 0.030))
        self.start_delay_var = tk.DoubleVar(value=cfg.get("start_delay", 4.0))
        self.loop_var = tk.BooleanVar(value=cfg.get("loop", False))
        self.start_keybind_var = tk.StringVar(value=cfg.get("start_keybind", "f8"))
        self.cancel_keybind_var = tk.StringVar(value=cfg.get("cancel_keybind", "backspace"))

        self.start_key_entry: ttk.Entry | None = None
        self.cancel_key_entry: ttk.Entry | None = None

        self._build_style()
        self._build_ui(cfg.get("sheet_text", DEFAULT_SHEET))
        self._start_hotkey_listener()
        self._process_ui_queue()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_style(self) -> None:
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Galaxy.TFrame", background="#090b1a")
        style.configure("Card.TFrame", background="#10162e")
        style.configure("Galaxy.TLabel", background="#10162e", foreground="#e8ecff")
        style.configure("Title.TLabel", background="#090b1a", foreground="#90caf9", font=("Segoe UI", 18, "bold"))
        style.configure("Galaxy.TButton", background="#1f2a5a", foreground="white", font=("Segoe UI", 10, "bold"), padding=8)
        style.map("Galaxy.TButton", background=[("active", "#2b3d84")])

    def _build_ui(self, initial_sheet: str) -> None:
        wrap = ttk.Frame(self.root, style="Galaxy.TFrame", padding=16)
        wrap.pack(fill="both", expand=True)
        ttk.Label(wrap, text="Interstellar Piano Bot", style="Title.TLabel").pack(anchor="w")

        top = ttk.Frame(wrap, style="Galaxy.TFrame")
        top.pack(fill="both", expand=True, pady=10)

        left = ttk.Frame(top, style="Card.TFrame", padding=12)
        left.pack(side="left", fill="both", expand=True, padx=(0, 8))
        ttk.Label(left, text="Sheet Input (paste anything in your bracket format)", style="Galaxy.TLabel").pack(anchor="w")
        self.sheet_box = scrolledtext.ScrolledText(left, wrap="word", bg="#0c1230", fg="#dfe7ff", insertbackground="white", font=("Consolas", 11), height=26)
        self.sheet_box.pack(fill="both", expand=True, pady=8)
        self.sheet_box.insert("1.0", initial_sheet)

        right = ttk.Frame(top, style="Card.TFrame", padding=12)
        right.pack(side="left", fill="y")

        ttk.Label(right, text="Tempo (BPM)", style="Galaxy.TLabel").pack(anchor="w")
        tk.Scale(right, from_=10, to=500, resolution=1, orient="horizontal", variable=self.bpm_var, bg="#10162e", fg="#e8ecff", highlightthickness=0, troughcolor="#283862", length=260).pack(pady=(4, 10))

        self._spinbox_row(right, "Hold duration", self.hold_var, 0.01, 0.30, 0.005)
        self._spinbox_row(right, "Start delay", self.start_delay_var, 0.0, 10.0, 0.1)

        ttk.Checkbutton(right, text="Loop song", variable=self.loop_var).pack(anchor="w", pady=(6, 8))

        ttk.Label(right, text="Click box then press start hotkey", style="Galaxy.TLabel").pack(anchor="w")
        self.start_key_entry = ttk.Entry(right, textvariable=self.start_keybind_var, width=20)
        self.start_key_entry.pack(anchor="w", pady=(2, 8))
        self.start_key_entry.bind("<KeyPress>", lambda e: self._capture_entry_key(e, self.start_keybind_var))

        ttk.Label(right, text="Click box then press cancel hotkey", style="Galaxy.TLabel").pack(anchor="w")
        self.cancel_key_entry = ttk.Entry(right, textvariable=self.cancel_keybind_var, width=20)
        self.cancel_key_entry.pack(anchor="w", pady=(2, 12))
        self.cancel_key_entry.bind("<KeyPress>", lambda e: self._capture_entry_key(e, self.cancel_keybind_var))

        ttk.Button(right, text="▶ Start", style="Galaxy.TButton", command=self.start_playback).pack(fill="x", pady=4)
        ttk.Button(right, text="■ Stop", style="Galaxy.TButton", command=self.stop_playback).pack(fill="x", pady=4)
        ttk.Button(right, text="Reset Sheet", style="Galaxy.TButton", command=self.reset_sheet).pack(fill="x", pady=4)

        self.progress = ttk.Progressbar(right, maximum=100, length=260)
        self.progress.pack(pady=(12, 6))
        self.status = ttk.Label(wrap, text="Ready. Focus Roblox and press Start (or start hotkey).", style="Galaxy.TLabel")
        self.status.pack(anchor="w", pady=(8, 0))

    @staticmethod
    def _spinbox_row(parent: ttk.Frame, label: str, var: tk.DoubleVar, low: float, high: float, step: float) -> None:
        ttk.Label(parent, text=label, style="Galaxy.TLabel").pack(anchor="w")
        ttk.Spinbox(parent, from_=low, to=high, increment=step, textvariable=var, width=10).pack(anchor="w", pady=(2, 8))

    @staticmethod
    def _normalize_key_name(raw: str) -> str:
        key = raw.strip().lower()
        aliases = {"return": "enter", "escape": "esc", "prior": "page_up", "next": "page_down"}
        return aliases.get(key, key)

    def _capture_entry_key(self, event: tk.Event, var: tk.StringVar) -> str:
        name = event.keysym.lower()
        if name in {"shift_l", "shift_r", "control_l", "control_r", "alt_l", "alt_r"}:
            return "break"
        normalized = self._normalize_key_name(name)
        var.set(normalized)
        self._save_settings()
        return "break"

    def _parse_sheet(self, sheet_text: str) -> list[list[str]]:
        steps: list[list[str]] = []
        normalized = sheet_text.replace("\\n", "\n")
        for token in TOKEN_RE.findall(normalized):
            if token.startswith("[") and token.endswith("]"):
                keys = [ch for ch in token[1:-1] if not ch.isspace()]
                if keys:
                    steps.append(keys)
            else:
                # Non-bracket token is interpreted as a chain of single key presses,
                # so tokens like "u----" become u,-,-,-,-
                for ch in token:
                    if not ch.isspace():
                        steps.append([ch])
        return [s for s in steps if s]

    def _press_step(self, ctl: keyboard.Controller, keys: list[str], hold: float) -> None:
        for key in keys:
            ctl.press(key)
        time.sleep(hold)
        for key in reversed(keys):
            ctl.release(key)

    def _parse_keybind(self, raw: str):
        key = self._normalize_key_name(raw)
        if not key:
            return None
        if key in keyboard.Key.__members__:
            return keyboard.Key[key]
        if len(key) == 1 and VALID_KEY.match(key):
            return keyboard.KeyCode.from_char(key)
        return None

    def _start_hotkey_listener(self) -> None:
        def on_press(key):
            start_key = self._parse_keybind(self.start_keybind_var.get())
            cancel_key = self._parse_keybind(self.cancel_keybind_var.get())
            if cancel_key is not None and key == cancel_key:
                self.stop_event.set()
                self.msg_queue.put(("status", "Stop key pressed. Cancelling..."))
            if start_key is not None and key == start_key and not self.playing:
                self.msg_queue.put(("start", ""))

        self.hotkey_listener = keyboard.Listener(on_press=on_press)
        self.hotkey_listener.daemon = True
        self.hotkey_listener.start()

    def start_playback(self) -> None:
        if self.playing:
            return
        steps = self._parse_sheet(self.sheet_box.get("1.0", "end").strip())
        if not steps:
            messagebox.showerror("No notes", "Paste a valid sheet first.")
            return

        self._save_settings()
        self.stop_event.clear()
        self.playing = True
        self.status.configure(text=f"Starting in {self.start_delay_var.get():.1f}s...")
        threading.Thread(target=self._play_worker, args=(steps,), daemon=True).start()

    def _play_worker(self, steps: list[list[str]]) -> None:
        ctl = keyboard.Controller()
        time.sleep(max(0.0, self.start_delay_var.get()))
        loops = 0
        while not self.stop_event.is_set():
            loops += 1
            total = len(steps)
            for i, step in enumerate(steps, start=1):
                if self.stop_event.is_set():
                    break
                self._press_step(ctl, step, max(0.001, self.hold_var.get()))
                time.sleep(60.0 / max(10, self.bpm_var.get()))
                pct = int((i / total) * 100)
                self.msg_queue.put(("progress", str(pct)))
                self.msg_queue.put(("status", f"Playing loop {loops} - note {i}/{total} @ {self.bpm_var.get()} BPM"))
            if not self.loop_var.get():
                break
        self.msg_queue.put(("done", "Playback complete." if not self.stop_event.is_set() else "Playback cancelled."))

    def stop_playback(self) -> None:
        self.stop_event.set()

    def reset_sheet(self) -> None:
        self.sheet_box.delete("1.0", "end")
        self.sheet_box.insert("1.0", DEFAULT_SHEET)
        self._save_settings()

    def _process_ui_queue(self) -> None:
        try:
            while True:
                event, value = self.msg_queue.get_nowait()
                if event == "status":
                    self.status.configure(text=value)
                elif event == "progress":
                    self.progress["value"] = int(value)
                elif event == "done":
                    self.status.configure(text=value)
                    self.playing = False
                elif event == "start":
                    self.start_playback()
        except queue.Empty:
            pass
        self.root.after(60, self._process_ui_queue)

    def _load_settings(self) -> dict:
        if not SETTINGS_FILE.exists():
            return {}
        try:
            return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def _save_settings(self) -> None:
        data = {
            "bpm": int(self.bpm_var.get()),
            "hold": float(self.hold_var.get()),
            "start_delay": float(self.start_delay_var.get()),
            "loop": bool(self.loop_var.get()),
            "start_keybind": self.start_keybind_var.get().strip().lower(),
            "cancel_keybind": self.cancel_keybind_var.get().strip().lower(),
            "sheet_text": self.sheet_box.get("1.0", "end").strip(),
        }
        SETTINGS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _on_close(self) -> None:
        self._save_settings()
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
