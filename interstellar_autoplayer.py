#!/usr/bin/env python3
"""Galaxy-themed Roblox piano autoplayer GUI."""

from __future__ import annotations

import json
import queue
import re
import threading
import time
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import messagebox, scrolledtext, ttk

from pynput import keyboard

DEFAULT_SHEET = "u u u\n[eup] u u"
SETTINGS_FILE = Path("autoplayer_settings.json")
TOKEN_RE = re.compile(r"\[[^\]]*\]|\s+|.", re.DOTALL)


@dataclass
class Step:
    keys: list[str]
    raw: str


class App:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("🌌 Interstellar Roblox Piano Autoplayer")
        self.root.geometry("1000x760")
        self.root.configure(bg="#090b1a")
        self.stop_event = threading.Event()
        self.playing = False
        self.msg_queue: queue.Queue[tuple[str, str]] = queue.Queue()

        cfg = self._load_settings()
        self.bpm_var = tk.IntVar(value=cfg.get("bpm", 120))
        self.hold_var = tk.DoubleVar(value=cfg.get("hold", 0.022))
        self.start_delay_var = tk.DoubleVar(value=cfg.get("start_delay", 4.0))
        self.loop_var = tk.BooleanVar(value=cfg.get("loop", False))
        self.always_on_top_var = tk.BooleanVar(value=cfg.get("always_on_top", False))
        self.start_keybind_var = tk.StringVar(value=cfg.get("start_keybind", "f8"))
        self.cancel_keybind_var = tk.StringVar(value=cfg.get("cancel_keybind", "backspace"))

        self._build_ui(cfg.get("sheet_text", DEFAULT_SHEET))
        self.root.attributes("-topmost", self.always_on_top_var.get())
        self._start_hotkey_listener()
        self._process_ui_queue()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self, initial_sheet: str) -> None:
        wrap = ttk.Frame(self.root, padding=16)
        wrap.pack(fill="both", expand=True)
        ttk.Label(wrap, text="Interstellar Piano Bot", font=("Segoe UI", 18, "bold")).pack(anchor="w")
        top = ttk.Frame(wrap)
        top.pack(fill="both", expand=True, pady=10)
        left = ttk.Frame(top, padding=12)
        left.pack(side="left", fill="both", expand=True, padx=(0, 8))
        ttk.Label(left, text="Sheet Input (keys outside [] play one-by-one; keys inside [] play simultaneously, e.g. [DFK])").pack(anchor="w")
        self.sheet_box = scrolledtext.ScrolledText(left, wrap="word", font=("Consolas", 11), height=28)
        self.sheet_box.pack(fill="both", expand=True, pady=8)
        self.sheet_box.insert("1.0", initial_sheet)

        right = ttk.Frame(top, padding=12)
        right.pack(side="left", fill="y")
        ttk.Label(right, text="Tempo (BPM)").pack(anchor="w")
        bpm_row = ttk.Frame(right); bpm_row.pack(anchor="w", pady=(4, 10))
        tk.Scale(bpm_row, from_=10, to=500, resolution=1, orient="horizontal", variable=self.bpm_var, length=220).pack(side="left")
        col = ttk.Frame(bpm_row); col.pack(side="left", padx=(6, 0))
        ttk.Button(col, text="▲", width=3, command=lambda: self._bpm_step(1)).pack(pady=(0, 3))
        ttk.Button(col, text="▼", width=3, command=lambda: self._bpm_step(-1)).pack()

        self._spinbox_row(right, "Hold duration", self.hold_var, 0.001, 0.30, 0.001)
        self._spinbox_row(right, "Start delay", self.start_delay_var, 0.0, 10.0, 0.1)
        ttk.Checkbutton(right, text="Loop song", variable=self.loop_var).pack(anchor="w")
        ttk.Checkbutton(right, text="Always on top", variable=self.always_on_top_var, command=self._apply_topmost).pack(anchor="w", pady=(0, 8))

        s=ttk.Entry(right, textvariable=self.start_keybind_var, width=20); s.pack(anchor="w", pady=(2, 8)); s.bind("<KeyPress>", lambda e: self._capture_entry_key(e, self.start_keybind_var))
        c=ttk.Entry(right, textvariable=self.cancel_keybind_var, width=20); c.pack(anchor="w", pady=(2, 12)); c.bind("<KeyPress>", lambda e: self._capture_entry_key(e, self.cancel_keybind_var))

        ttk.Button(right, text="▶ Start", command=self.start_playback).pack(fill="x", pady=4)
        ttk.Button(right, text="■ Stop", command=self.stop_playback).pack(fill="x", pady=4)
        self.progress = ttk.Progressbar(right, maximum=100, length=260); self.progress.pack(pady=(10, 6))
        self.countdown_label = ttk.Label(right, text="Countdown: -"); self.countdown_label.pack(anchor="w")
        self.now_playing_label = ttk.Label(right, text="Now Playing: -"); self.now_playing_label.pack(anchor="w", pady=(4,0))
        self.status = ttk.Label(wrap, text="Ready."); self.status.pack(anchor="w", pady=(8,0))

    @staticmethod
    def _spinbox_row(parent, label, var, low, high, step):
        ttk.Label(parent, text=label).pack(anchor="w")
        ttk.Spinbox(parent, from_=low, to=high, increment=step, textvariable=var, width=10).pack(anchor="w", pady=(2, 8))

    def _parse_sheet(self, sheet_text: str) -> list[Step]:
        steps: list[Step] = []
        text = sheet_text.replace("\\n", "\n")
        for tok in TOKEN_RE.findall(text):
            if tok.startswith("[") and tok.endswith("]"):
                inside = tok[1:-1]
                keys = [ch for ch in inside if not ch.isspace()]
                if keys:
                    steps.append(Step(keys=keys, raw=tok))
            elif tok.isspace():
                continue
            else:
                steps.append(Step(keys=[tok], raw=tok))
        return steps

    @staticmethod
    def _normalize_key_name(raw: str) -> str:
        aliases = {"return": "enter", "escape": "esc", "prior": "page_up", "next": "page_down"}
        return aliases.get(raw.strip().lower(), raw.strip().lower())

    def _key_to_pressable(self, raw: str):
        key = self._normalize_key_name(raw)
        if key == "ctrl": return keyboard.Key.ctrl
        if key == "shift": return keyboard.Key.shift
        if key == "alt": return keyboard.Key.alt
        if len(raw) == 1:
            return keyboard.KeyCode.from_char(raw)
        if key in keyboard.Key.__members__:
            return keyboard.Key[key]
        return None

    def _press_step(self, ctl: keyboard.Controller, keys: list[str], hold: float) -> None:
        pressables = [self._key_to_pressable(k) for k in keys]
        pressables = [p for p in pressables if p is not None]
        for p in pressables: ctl.press(p)
        time.sleep(hold)
        for p in reversed(pressables): ctl.release(p)

    def _parse_hotkey(self, raw: str):
        k = self._normalize_key_name(raw)
        if len(k) == 1: return keyboard.KeyCode.from_char(k)
        if k in keyboard.Key.__members__: return keyboard.Key[k]
        return None

    def _play_worker(self, steps: list[Step]) -> None:
        ctl = keyboard.Controller()
        delay = max(0.0, self.start_delay_var.get())
        start = time.perf_counter()
        while not self.stop_event.is_set() and (time.perf_counter() - start) < delay:
            self.msg_queue.put(("countdown", f"Countdown: {delay-(time.perf_counter()-start):.1f}s"))
            time.sleep(0.05)
        self.msg_queue.put(("countdown", "Countdown: 0.0s"))

        step_seconds = 60.0 / max(10, int(self.bpm_var.get()))
        loops = 0
        while not self.stop_event.is_set():
            loops += 1
            next_tick = time.perf_counter()
            total = len(steps)
            for i, st in enumerate(steps, 1):
                if self.stop_event.is_set(): break
                self.msg_queue.put(("playing", f"Now Playing: {st.raw}"))
                self._press_step(ctl, st.keys, max(0.001, self.hold_var.get()))
                next_tick += step_seconds
                while (rem := next_tick - time.perf_counter()) > 0: time.sleep(min(rem, 0.002))
                self.msg_queue.put(("progress", str(int(i * 100 / total))))
            if not self.loop_var.get(): break
        self.msg_queue.put(("done", "Playback complete." if not self.stop_event.is_set() else "Playback cancelled."))

    def start_playback(self):
        if self.playing: return
        steps = self._parse_sheet(self.sheet_box.get("1.0", "end").strip())
        if not steps: return messagebox.showerror("No notes", "Paste a valid sheet first.")
        self._save_settings(); self.stop_event.clear(); self.playing=True
        threading.Thread(target=self._play_worker, args=(steps,), daemon=True).start()

    def stop_playback(self): self.stop_event.set()
    def _bpm_step(self, d:int): self.bpm_var.set(max(10,min(500,int(self.bpm_var.get())+d))); self._save_settings()
    def _apply_topmost(self): self.root.attributes("-topmost", self.always_on_top_var.get()); self._save_settings()
    def _capture_entry_key(self, event: tk.Event, var: tk.StringVar): var.set(self._normalize_key_name(event.keysym)); self._save_settings(); return "break"

    def _start_hotkey_listener(self):
        def on_press(key):
            s=self._parse_hotkey(self.start_keybind_var.get()); c=self._parse_hotkey(self.cancel_keybind_var.get())
            if c is not None and key == c: self.stop_event.set(); self.msg_queue.put(("status","Stop key pressed. Cancelling..."))
            if s is not None and key == s and not self.playing: self.msg_queue.put(("start",""))
        self.hotkey_listener = keyboard.Listener(on_press=on_press); self.hotkey_listener.daemon=True; self.hotkey_listener.start()

    def _process_ui_queue(self):
        try:
            while True:
                e,v=self.msg_queue.get_nowait()
                if e=="status": self.status.configure(text=v)
                elif e=="progress": self.progress["value"]=int(v)
                elif e=="countdown": self.countdown_label.configure(text=v)
                elif e=="playing": self.now_playing_label.configure(text=v)
                elif e=="done": self.status.configure(text=v); self.playing=False
                elif e=="start": self.start_playback()
        except queue.Empty: pass
        self.root.after(40, self._process_ui_queue)

    def _load_settings(self):
        try: return json.loads(SETTINGS_FILE.read_text(encoding="utf-8")) if SETTINGS_FILE.exists() else {}
        except Exception: return {}
    def _save_settings(self):
        SETTINGS_FILE.write_text(json.dumps({"bpm":int(self.bpm_var.get()),"hold":float(self.hold_var.get()),"start_delay":float(self.start_delay_var.get()),"loop":bool(self.loop_var.get()),"always_on_top":bool(self.always_on_top_var.get()),"start_keybind":self.start_keybind_var.get().strip().lower(),"cancel_keybind":self.cancel_keybind_var.get().strip().lower(),"sheet_text":self.sheet_box.get("1.0","end").strip()}, indent=2), encoding="utf-8")
    def _on_close(self): self._save_settings(); self.root.destroy()


def main() -> None:
    root = tk.Tk(); App(root); root.mainloop()


if __name__ == "__main__":
    main()
