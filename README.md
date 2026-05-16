# 🌌 Interstellar Roblox Piano Autoplayer (GUI)

A galaxy-themed desktop GUI that auto-plays Roblox piano sheets.

## Features
- Paste/copy sheet text directly in a large editor.
- **BPM tempo slider** (10-500, step 1).
- Adjustable hold duration and start delay.
- Start/stop buttons.
- Click keybind boxes and press keys to capture hotkeys live.
- Configurable **start keybind** and **cancel keybind** (default cancel: Backspace).
- Optional loop mode.
- Progress bar + live playback status.
- Settings persist between launches in `autoplayer_settings.json`.

## Install
```bash
python -m pip install pynput
```

## Run
```bash
python interstellar_autoplayer.py
```

## Sheet format
- Single note: `u`
- Chord/simultaneous notes: `[eup]`

## Notes
- Click/focus your Roblox piano window before starting.
- Use only where automation is allowed.
