#!/usr/bin/env python3
"""
🌌 Interstellar Roblox Piano Autoplayer v10 Hybrid

Matches your exact piano layout:

- Uppercase letters in sheet (E, Q, W...) = Shift + key
- Lowercase letters = plain key press (no Shift)
- Only symbols that actually appear on your piano are supported (! @ $ % ^ * ( etc.)
- Removed "|" and other unnecessary special keys
- Accurate BPM timing + seek + all previous features
- Uses hybrid input: Windows SendInput first, pynput fallback if needed
- New lines in the sheet add a small configurable pause
"""

from __future__ import annotations

import json
import queue
import threading
import time
import ctypes
from ctypes import wintypes
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

from pynput import keyboard

SETTINGS_FILE = Path("autoplayer_settings.json")

DEFAULT_SHEET = "u u u\n[EUP] u u\n--\n{qu} q q\n[^q] ^e"

# Only symbols that appear on YOUR piano layout
SHIFT_CHAR_MAP: dict[str, str] = {
    "!": "1",
    "@": "2",
    "$": "4",
    "%": "5",
    "^": "6",
    "*": "8",
    "(": "9",
    ")": "0",
}

# Windows scan-code input is used for playback because Roblox piano scripts
# often read physical KeyCode-style events more reliably than text-like input.
SCAN_CODES: dict[str, int] = {
    "1": 0x02, "2": 0x03, "3": 0x04, "4": 0x05, "5": 0x06,
    "6": 0x07, "7": 0x08, "8": 0x09, "9": 0x0A, "0": 0x0B,

    "q": 0x10, "w": 0x11, "e": 0x12, "r": 0x13, "t": 0x14,
    "y": 0x15, "u": 0x16, "i": 0x17, "o": 0x18, "p": 0x19,

    "a": 0x1E, "s": 0x1F, "d": 0x20, "f": 0x21, "g": 0x22,
    "h": 0x23, "j": 0x24, "k": 0x25, "l": 0x26,

    "z": 0x2C, "x": 0x2D, "c": 0x2E, "v": 0x2F, "b": 0x30,
    "n": 0x31, "m": 0x32,
}

SHIFT_SC = 0x2A
CTRL_SC = 0x1D

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008


# Correct 64-bit-safe SendInput structures. The INPUT union must include mouse and
# hardware variants so ctypes.sizeof(INPUT) matches what Windows expects.
ULONG_PTR = wintypes.WPARAM


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class INPUT_UNION(ctypes.Union):
    _fields_ = [
        ("mi", MOUSEINPUT),
        ("ki", KEYBDINPUT),
        ("hi", HARDWAREINPUT),
    ]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [
        ("type", wintypes.DWORD),
        ("u", INPUT_UNION),
    ]


SendInput = ctypes.windll.user32.SendInput
SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
SendInput.restype = wintypes.UINT


def send_scan(scancode: int, key_up: bool = False) -> bool:
    """Send a hardware-like scan-code event. Returns True if Windows accepts it."""
    flags = KEYEVENTF_SCANCODE | (KEYEVENTF_KEYUP if key_up else 0)
    inp = INPUT(
        type=INPUT_KEYBOARD,
        ki=KEYBDINPUT(
            wVk=0,
            wScan=scancode,
            dwFlags=flags,
            time=0,
            dwExtraInfo=0,
        ),
    )
    return SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT)) == 1


@dataclass
class Step:
    keys: list[str]
    raw: str
    start: str
    end: str
    delay_beats: float = 1.0
    delay_seconds: float = 0.0


class InterstellarPianoAutoplayer:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("🌌 Interstellar Roblox Piano Autoplayer v10 Hybrid")
        self.root.geometry("1120x820")
        self.root.minsize(980, 720)

        self.stop_event = threading.Event()
        self.playing = False
        self.msg_queue: queue.Queue[tuple[str, object]] = queue.Queue()

        self.current_steps: list[Step] = []
        self.playback_index = 0

        cfg = self._load_settings()
        self.bpm_var = tk.IntVar(value=cfg.get("bpm", 120))
        self.hold_var = tk.DoubleVar(value=cfg.get("hold", 0.045))
        self.start_delay_var = tk.DoubleVar(value=cfg.get("start_delay", 3.0))
        self.newline_pause_var = tk.DoubleVar(value=cfg.get("newline_pause", 0.18))
        self.loop_var = tk.BooleanVar(value=cfg.get("loop", False))
        self.top_var = tk.BooleanVar(value=cfg.get("always_on_top", False))
        self.start_hotkey_var = tk.StringVar(value=cfg.get("start_hotkey", "f8"))
        self.stop_hotkey_var = tk.StringVar(value=cfg.get("stop_hotkey", "backspace"))
        self.scancode_var = tk.BooleanVar(value=cfg.get("use_scancode", True))

        self._build_style()
        self._build_ui(cfg.get("sheet_text", DEFAULT_SHEET))
        self._bind_traces()

        self.root.attributes("-topmost", self.top_var.get())
        self._start_hotkey_listener()
        self._process_queue()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # --------------------------- UI ---------------------------

    def _build_style(self) -> None:
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Galaxy.TFrame", background="#0a0f2e")
        style.configure("Panel.TFrame", background="#12183c")
        style.configure("Galaxy.TLabel", background="#12183c", foreground="#c8d6ff", font=("Segoe UI", 10))
        style.configure("Title.TLabel", background="#090d25", foreground="#7ed0ff", font=("Segoe UI", 20, "bold"))
        style.configure("Subtitle.TLabel", background="#0a0f2e", foreground="#9ab8ff", font=("Segoe UI", 9))
        style.configure("Galaxy.TCheckbutton", background="#12183c", foreground="#c8d6ff")
        style.map("Galaxy.TCheckbutton", background=[("active", "#1a234f")], foreground=[("active", "#ffffff")])
        style.configure("Galaxy.TButton", background="#2a3a7a", foreground="#e0f0ff", borderwidth=0, padding=(8, 5))
        style.map("Galaxy.TButton", background=[("active", "#3d52b0")])
        style.configure("Accent.TButton", background="#4a6fd4", foreground="white", font=("Segoe UI", 10, "bold"))
        style.map("Accent.TButton", background=[("active", "#5f8cff")])

    def _draw_galaxy_bg(self, canvas: tk.Canvas) -> None:
        w, h = 1120, 820
        for y in range(h):
            r = int(5 + (y / h) * 16)
            g = int(9 + (y / h) * 22)
            b = int(30 + (y / h) * 42)
            canvas.create_line(0, y, w, y, fill=f"#{r:02x}{g:02x}{b:02x}")

        import random
        random.seed(42)
        for _ in range(450):
            x = random.randint(0, w)
            y = random.randint(0, h)
            size = random.choice([1, 1, 2, 2, 3])
            color = random.choice(["#e8f0ff", "#c8d8ff", "#a8c4ff", "#f0e8ff", "#ffffff"])
            canvas.create_oval(x, y, x + size, y + size, fill=color, outline="")

        for x, y, rw, rh, c1, c2 in [
            (620, 60, 380, 310, "#1a2a5e", "#14234d"),
            (780, 150, 280, 230, "#2a3a6e", "#1f2f5a"),
            (90, 450, 420, 370, "#2f2a55", "#25204a"),
            (860, 490, 290, 250, "#3a2a6a", "#2a1f55"),
        ]:
            canvas.create_oval(x, y, x + rw, y + rh, fill=c1, outline="")
            canvas.create_oval(x + 28, y + 20, x + rw - 38, y + rh - 30, fill=c2, outline="")

        canvas.create_oval(930, 25, 1190, 195, fill="#1c2a55", outline="")
        canvas.create_oval(970, 55, 1130, 165, fill="#2a3f7a", outline="")

    def _build_ui(self, initial_sheet: str) -> None:
        bg = tk.Canvas(self.root, highlightthickness=0)
        bg.place(relx=0, rely=0, relwidth=1, relheight=1)
        self._draw_galaxy_bg(bg)

        wrap = ttk.Frame(self.root, style="Galaxy.TFrame", padding=16)
        wrap.place(relx=0.015, rely=0.02, relwidth=0.97, relheight=0.96)

        header = ttk.Frame(wrap, style="Galaxy.TFrame")
        header.pack(fill="x", pady=(0, 8))
        ttk.Label(header, text="🌌 INTERSTELLAR", style="Title.TLabel").pack(side="left")
        ttk.Label(header, text="ROBLOX PIANO AUTOPLAYER v10  •  Hybrid playback", style="Subtitle.TLabel").pack(side="left", padx=12, pady=5)

        main = ttk.Frame(wrap, style="Galaxy.TFrame")
        main.pack(fill="both", expand=True)

        left = ttk.Frame(main, style="Panel.TFrame", padding=12)
        left.pack(side="left", fill="both", expand=True, padx=(0, 10))

        rules = (
            "Your layout rules:\n"
            "• Capital letters (E, Q, W...) = Shift + key\n"
            "• Lowercase letters = plain key (no Shift)\n"
            "• [EUP] = chord with Shift+E, Shift+U, Shift+P\n"
            "• ^q = Ctrl + q   •   New lines add a small pause"
        )
        ttk.Label(left, text=rules, style="Galaxy.TLabel", justify="left", wraplength=620).pack(anchor="w", pady=(0, 4))

        self.sheet_box = scrolledtext.ScrolledText(
            left, wrap="word", bg="#0a1235", fg="#e0e8ff", insertbackground="#7ed0ff",
            selectbackground="#3a4f9f", font=("Consolas", 11), height=26, relief="flat", borderwidth=0, padx=6, pady=4
        )
        self.sheet_box.pack(fill="both", expand=True)
        self.sheet_box.insert("1.0", initial_sheet)
        self.sheet_box.tag_configure("playing", background="#ffd54f", foreground="#1a1a1a", font=("Consolas", 11, "bold"))

        btnbar = ttk.Frame(left, style="Panel.TFrame")
        btnbar.pack(fill="x", pady=6)
        ttk.Button(btnbar, text="📂 Import", command=self._import_sheet, style="Galaxy.TButton").pack(side="left", padx=3)
        ttk.Button(btnbar, text="💾 Export", command=self._export_sheet, style="Galaxy.TButton").pack(side="left", padx=3)
        ttk.Button(btnbar, text="🗑 Clear", command=lambda: self.sheet_box.delete("1.0", "end"), style="Galaxy.TButton").pack(side="left", padx=3)
        ttk.Button(btnbar, text="📋 Example", command=self._load_example, style="Galaxy.TButton").pack(side="left", padx=3)

        right = ttk.Frame(main, style="Panel.TFrame", padding=12)
        right.pack(side="left", fill="y")

        ttk.Label(right, text="▶ PLAYBACK SPEED", style="Galaxy.TLabel", font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(0, 4))

        ttk.Label(right, text="BPM (notes per minute)", style="Galaxy.TLabel").pack(anchor="w")
        bpmf = ttk.Frame(right, style="Panel.TFrame")
        bpmf.pack(anchor="w", pady=2)

        tk.Scale(bpmf, from_=10, to=500, resolution=1, orient="horizontal",
                 variable=self.bpm_var, bg="#131c3f", fg="#c8d6ff", troughcolor="#2a3a7a",
                 highlightthickness=0, length=230, showvalue=True).pack(side="left")

        qf = ttk.Frame(right, style="Panel.TFrame")
        qf.pack(anchor="w", pady=(0, 6))
        for v in (60, 120, 180, 240, 360, 480):
            ttk.Button(qf, text=str(v), width=5,
                       command=lambda val=v: self.bpm_var.set(val),
                       style="Galaxy.TButton").pack(side="left", padx=2)

        self._spin(right, "Key hold time (s)", self.hold_var, 0.005, 0.12, 0.005)
        self._spin(right, "Line break pause (s)", self.newline_pause_var, 0.0, 2.0, 0.05)
        self._spin(right, "Start delay (s)", self.start_delay_var, 0.0, 10, 0.5)

        ttk.Checkbutton(right, text="🔁 Loop playback", variable=self.loop_var, style="Galaxy.TCheckbutton").pack(anchor="w", pady=4)
        ttk.Checkbutton(right, text="📌 Always on top", variable=self.top_var,
                        command=self._toggle_top, style="Galaxy.TCheckbutton").pack(anchor="w")
        ttk.Checkbutton(right, text="⌨️ Use scan-code input", variable=self.scancode_var,
                        style="Galaxy.TCheckbutton").pack(anchor="w")

        ttk.Label(right, text="⏩ SEEK", style="Galaxy.TLabel", font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(12, 4))
        seekf = ttk.Frame(right, style="Panel.TFrame")
        seekf.pack(anchor="w")
        ttk.Button(seekf, text="⏮ Reset", command=self._seek_reset, style="Galaxy.TButton", width=8).pack(side="left", padx=2)
        ttk.Button(seekf, text="⏪ -8", command=lambda: self._seek_delta(-8), style="Galaxy.TButton", width=6).pack(side="left", padx=2)
        ttk.Button(seekf, text="+8 ⏩", command=lambda: self._seek_delta(8), style="Galaxy.TButton", width=6).pack(side="left", padx=2)

        self.progress = ttk.Progressbar(right, maximum=100, length=260, mode="determinate")
        self.progress.pack(pady=(10, 4))
        self.countdown = ttk.Label(right, text="Countdown: —", style="Galaxy.TLabel")
        self.countdown.pack(anchor="w")

        ttk.Label(right, text="⌨️ HOTKEYS", style="Galaxy.TLabel", font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(14, 4))
        ttk.Label(right, text="Start hotkey", style="Galaxy.TLabel").pack(anchor="w")
        se = ttk.Entry(right, textvariable=self.start_hotkey_var, width=16)
        se.pack(anchor="w", pady=1)
        se.bind("<KeyPress>", lambda e: self._capture_hotkey(e, self.start_hotkey_var))

        ttk.Label(right, text="Stop hotkey", style="Galaxy.TLabel").pack(anchor="w")
        ce = ttk.Entry(right, textvariable=self.stop_hotkey_var, width=16)
        ce.pack(anchor="w", pady=1)
        ce.bind("<KeyPress>", lambda e: self._capture_hotkey(e, self.stop_hotkey_var))

        ttk.Button(right, text="▶ START", command=self.start_playback, style="Accent.TButton").pack(fill="x", pady=(14, 4))
        ttk.Button(right, text="■ STOP", command=self.stop_playback, style="Galaxy.TButton").pack(fill="x")

        self.status = ttk.Label(wrap, text="Ready. Uppercase letters = Shift + key. New lines add a small pause.",
                                style="Subtitle.TLabel")
        self.status.pack(anchor="w", pady=(10, 0))

    def _spin(self, parent, label, var, lo, hi, inc):
        ttk.Label(parent, text=label, style="Galaxy.TLabel").pack(anchor="w", pady=(6, 0))
        ttk.Spinbox(parent, from_=lo, to=hi, increment=inc, textvariable=var, width=9).pack(anchor="w")

    def _bind_traces(self):
        for var in (self.bpm_var, self.hold_var, self.start_delay_var, self.newline_pause_var, self.loop_var, self.top_var, self.scancode_var):
            var.trace_add("write", lambda *_: self._save_settings())

    # --------------------------- Hotkeys & Settings ---------------------------

    @staticmethod
    def _normalize(name: str) -> str:
        aliases = {"return": "enter", "escape": "esc", "prior": "page_up", "next": "page_down"}
        return aliases.get(name.strip().lower(), name.strip().lower())

    def _capture_hotkey(self, event, var):
        var.set(self._normalize(event.keysym))
        self._save_settings()
        return "break"

    def _toggle_top(self):
        self.root.attributes("-topmost", self.top_var.get())
        self._save_settings()

    def _parse_hotkey(self, raw: str):
        raw = self._normalize(raw)
        if len(raw) == 1:
            return keyboard.KeyCode.from_char(raw)
        return keyboard.Key[raw] if raw in keyboard.Key.__members__ else None

    def _start_hotkey_listener(self):
        def on_press(key):
            try:
                if self._parse_hotkey(self.stop_hotkey_var.get()) == key:
                    self.stop_event.set()
                if self._parse_hotkey(self.start_hotkey_var.get()) == key and not self.playing:
                    self.msg_queue.put(("start", None))
            except Exception:
                pass
        l = keyboard.Listener(on_press=on_press)
        l.daemon = True
        l.start()
        self.listener = l

    # --------------------------- Parsing ---------------------------

    def _split_key_tokens(self, inner: str) -> list[str]:
        tokens, i = [], 0
        while i < len(inner):
            if inner[i].isspace():
                i += 1
                continue
            if inner[i] in "^+" and i + 1 < len(inner) and not inner[i + 1].isspace():
                tokens.append(inner[i] + inner[i + 1])
                i += 2
            else:
                tokens.append(inner[i])
                i += 1
        return tokens

    def _append_step(self, steps, raw, start, end, chord=False, fast=False):
        if chord:
            t = self._split_key_tokens(raw[1:-1])
            if t:
                steps.append(Step(t, raw, start, end, 1.0))
            return
        if fast:
            for tok in self._split_key_tokens(raw[1:-1]):
                steps.append(Step([tok], raw, start, end, 0.5))
            return
        steps.append(Step([] if raw == "-" else [raw], raw, start, end, 1.0))

    def _parse_sheet(self, text: str) -> list[Step]:
        steps, i, idx = [], 0, "1.0"
        text = text.replace("\\n", "\n")
        while i < len(text):
            ch = text[i]
            start = idx
            if ch == "\n":
                endi = self.sheet_box.index(f"{start}+1c")
                pause = max(0.0, float(self.newline_pause_var.get()))
                if pause > 0:
                    steps.append(Step([], "\n", start, endi, 0.0, pause))
                i += 1
                idx = endi
                continue

            if ch.isspace():
                i += 1
                idx = self.sheet_box.index(f"{idx}+1c")
                continue
            if ch == "[":
                j = text.find("]", i + 1)
                if j == -1:
                    self._append_step(steps, ch, start, idx)
                    i += 1
                    idx = self.sheet_box.index(f"{idx}+1c")
                    continue
                raw = text[i:j+1]
                endi = self.sheet_box.index(f"{start}+{len(raw)}c")
                self._append_step(steps, raw, start, endi, chord=True)
                i, idx = j + 1, endi
                continue
            if ch == "{":
                j = text.find("}", i + 1)
                if j == -1:
                    self._append_step(steps, ch, start, idx)
                    i += 1
                    idx = self.sheet_box.index(f"{idx}+1c")
                    continue
                raw = text[i:j+1]
                endi = self.sheet_box.index(f"{start}+{len(raw)}c")
                self._append_step(steps, raw, start, endi, fast=True)
                i, idx = j + 1, endi
                continue
            if ch in "^+" and i + 1 < len(text) and not text[i+1].isspace():
                tok = ch + text[i+1]
                endi = self.sheet_box.index(f"{start}+2c")
                self._append_step(steps, tok, start, endi)
                i += 2
                idx = endi
                continue
            endi = self.sheet_box.index(f"{start}+1c")
            self._append_step(steps, ch, start, endi)
            i += 1
            idx = endi
        return steps

    # --------------------------- Key Simulation (Uppercase = Shift) ---------------------------

    def _token_to_scan_combo(self, token: str):
        """Convert one sheet token into scan-code modifiers + base scan code."""
        if not token:
            return None

        mods: list[int] = []
        base = token

        # Explicit prefixes from the sheet syntax.
        if base.startswith("+"):
            mods.append(SHIFT_SC)
            base = base[1:]
        if base.startswith("^"):
            mods.append(CTRL_SC)
            base = base[1:]

        if not base:
            return None

        # Uppercase sheet letters must be sent as real Shift + lowercase scan code.
        if len(base) == 1 and base.isalpha():
            if base.isupper():
                mods.append(SHIFT_SC)
            base = base.lower()

        # Supported piano symbols are also sent as Shift + number scan code.
        elif len(base) == 1 and base in SHIFT_CHAR_MAP:
            mods.append(SHIFT_SC)
            base = SHIFT_CHAR_MAP[base]

        else:
            base = base.lower()

        scancode = SCAN_CODES.get(base)
        return (mods, scancode) if scancode else None

    @staticmethod
    def _scan_to_pynput_key(scancode: int):
        reverse = {v: k for k, v in SCAN_CODES.items()}
        ch = reverse.get(scancode)
        return keyboard.KeyCode.from_char(ch) if ch else None

    def _to_pynput_combo(self, token: str):
        """Fallback path using pynput, similar to the original v7 behavior."""
        if not token:
            return None

        mods, base = [], token

        if base.startswith("+"):
            mods.append(keyboard.Key.shift)
            base = base[1:]
        if base.startswith("^"):
            mods.append(keyboard.Key.ctrl)
            base = base[1:]

        if not base:
            return None

        if len(base) == 1 and base.isalpha():
            if base.isupper():
                mods.append(keyboard.Key.shift)
                base = base.lower()
            return mods, keyboard.KeyCode.from_char(base)

        if len(base) == 1 and base in SHIFT_CHAR_MAP:
            mods.append(keyboard.Key.shift)
            return mods, keyboard.KeyCode.from_char(SHIFT_CHAR_MAP[base])

        if len(base) == 1:
            return mods, keyboard.KeyCode.from_char(base)

        name = base.lower()
        return (mods, keyboard.Key[name]) if name in keyboard.Key.__members__ else None

    def _press_step_pynput(self, ctl: keyboard.Controller, key_tokens: list[str], hold: float):
        combos = [c for c in (self._to_pynput_combo(t) for t in key_tokens) if c]
        if not combos:
            return

        active_mods, active_keys = [], []
        active_mod_set = set()

        try:
            for modlist, key in combos:
                for mod in modlist:
                    if mod not in active_mod_set:
                        ctl.press(mod)
                        active_mods.append(mod)
                        active_mod_set.add(mod)
                ctl.press(key)
                active_keys.append(key)

            time.sleep(max(0.001, hold))

        finally:
            for key in reversed(active_keys):
                ctl.release(key)
            for mod in reversed(active_mods):
                ctl.release(mod)

    def _press_step_scancode(self, key_tokens: list[str], hold: float) -> bool:
        combos = [c for c in (self._token_to_scan_combo(t) for t in key_tokens) if c]
        if not combos:
            return True

        active_mods: list[int] = []
        active_mod_set: set[int] = set()
        active_keys: list[int] = []
        ok = True

        try:
            for modlist, key_sc in combos:
                for mod_sc in modlist:
                    if mod_sc not in active_mod_set:
                        ok = send_scan(mod_sc) and ok
                        active_mods.append(mod_sc)
                        active_mod_set.add(mod_sc)

                ok = send_scan(key_sc) and ok
                active_keys.append(key_sc)

            time.sleep(max(0.001, hold))

        finally:
            for key_sc in reversed(active_keys):
                ok = send_scan(key_sc, key_up=True) and ok
            for mod_sc in reversed(active_mods):
                ok = send_scan(mod_sc, key_up=True) and ok

        return ok

    def _press_step(self, ctl: keyboard.Controller, key_tokens: list[str], hold: float):
        # Try hardware-like scan codes first. If Windows rejects them, fall back to pynput
        # so the program still types instead of doing nothing.
        if self.scancode_var.get():
            if self._press_step_scancode(key_tokens, hold):
                return
            self.msg_queue.put(("status", "Scan-code input failed; using pynput fallback."))

        self._press_step_pynput(ctl, key_tokens, hold)

    # --------------------------- Playback ---------------------------

    def _play_worker(self, steps: list[Step]):
        ctl = keyboard.Controller()
        delay = max(0.0, self.start_delay_var.get())
        t0 = time.perf_counter()

        while not self.stop_event.is_set() and (time.perf_counter() - t0) < delay:
            rem = delay - (time.perf_counter() - t0)
            self.msg_queue.put(("countdown", f"Countdown: {rem:.1f}s"))
            time.sleep(0.04)
        self.msg_queue.put(("countdown", "Countdown: 0.0s"))

        self.playback_index = 0
        total = len(steps)
        next_onset = time.perf_counter()

        while not self.stop_event.is_set():
            with threading.Lock():
                idx = self.playback_index

            if idx >= total:
                if not self.loop_var.get():
                    break
                self.playback_index = 0
                idx = 0
                next_onset = time.perf_counter()

            st = steps[idx]

            while (rem := next_onset - time.perf_counter()) > 0 and not self.stop_event.is_set():
                time.sleep(min(rem, 0.002))

            if self.stop_event.is_set():
                break

            self.msg_queue.put(("highlight", (st.start, st.end)))
            self.msg_queue.put(("status", f"Playing {idx+1}/{total}"))
            self._press_step(ctl, st.keys, max(0.001, self.hold_var.get()))

            beat = 60.0 / max(10, int(self.bpm_var.get()))
            next_onset += (beat * st.delay_beats) + st.delay_seconds

            self.msg_queue.put(("progress", int((idx + 1) * 100 / total)))

            with threading.Lock():
                if self.playback_index == idx:
                    self.playback_index = idx + 1

        msg = "Playback cancelled." if self.stop_event.is_set() else "Playback complete."
        self.msg_queue.put(("done", msg))

    def start_playback(self):
        if self.playing:
            return
        text = self.sheet_box.get("1.0", "end-1c")
        steps = self._parse_sheet(text)
        if not steps:
            messagebox.showerror("No notes", "Paste a valid sheet first.")
            return
        self.sheet_box.tag_remove("playing", "1.0", "end")
        self.stop_event.clear()
        self.playing = True
        self.current_steps = steps
        self.playback_index = 0
        self._save_settings()
        threading.Thread(target=self._play_worker, args=(steps,), daemon=True).start()

    def stop_playback(self):
        self.stop_event.set()

    def _seek_reset(self):
        self.playback_index = 0
        self.progress["value"] = 0
        self.status.configure(text="Position reset to start.")

    def _seek_delta(self, delta: int):
        if not self.current_steps:
            return
        new_idx = max(0, min(self.playback_index + delta, len(self.current_steps) - 1))
        self.playback_index = new_idx
        pct = int((new_idx + 1) * 100 / len(self.current_steps)) if self.current_steps else 0
        self.progress["value"] = pct
        self.status.configure(text=f"Skipped to step {new_idx + 1}")

    def _process_queue(self):
        try:
            while True:
                event, payload = self.msg_queue.get_nowait()
                if event == "countdown":
                    self.countdown.configure(text=str(payload))
                elif event == "progress":
                    self.progress["value"] = int(payload)
                elif event == "status":
                    self.status.configure(text=str(payload))
                elif event == "highlight":
                    s, e = payload
                    self.sheet_box.tag_remove("playing", "1.0", "end")
                    self.sheet_box.tag_add("playing", s, e)
                    self.sheet_box.see(s)
                elif event == "done":
                    self.status.configure(text=str(payload))
                    self.playing = False
                    self.sheet_box.tag_remove("playing", "1.0", "end")
                    self.progress["value"] = 0
                elif event == "start":
                    self.start_playback()
        except queue.Empty:
            pass
        self.root.after(35, self._process_queue)

    def _import_sheet(self):
        p = filedialog.askopenfilename(title="Import sheet", filetypes=[("Text", "*.txt"), ("All", "*.*")])
        if p:
            try:
                self.sheet_box.delete("1.0", "end")
                self.sheet_box.insert("1.0", Path(p).read_text(encoding="utf-8"))
            except Exception as e:
                messagebox.showerror("Import failed", str(e))

    def _export_sheet(self):
        p = filedialog.asksaveasfilename(title="Export sheet", defaultextension=".txt")
        if p:
            Path(p).write_text(self.sheet_box.get("1.0", "end-1c"), encoding="utf-8")

    def _load_example(self):
        self.sheet_box.delete("1.0", "end")
        self.sheet_box.insert("1.0", DEFAULT_SHEET)

    def _load_settings(self):
        try:
            if SETTINGS_FILE.exists():
                return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
        return {}

    def _save_settings(self):
        data = {
            "bpm": int(self.bpm_var.get()),
            "hold": float(self.hold_var.get()),
            "start_delay": float(self.start_delay_var.get()),
            "newline_pause": float(self.newline_pause_var.get()),
            "loop": bool(self.loop_var.get()),
            "always_on_top": bool(self.top_var.get()),
            "start_hotkey": self.start_hotkey_var.get().strip().lower(),
            "stop_hotkey": self.stop_hotkey_var.get().strip().lower(),
            "use_scancode": bool(self.scancode_var.get()),
            "sheet_text": self.sheet_box.get("1.0", "end-1c"),
        }
        try:
            SETTINGS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _on_close(self):
        self._save_settings()
        self.root.destroy()


def main():
    root = tk.Tk()
    InterstellarPianoAutoplayer(root)
    root.mainloop()


if __name__ == "__main__":
    main()