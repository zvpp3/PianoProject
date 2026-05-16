# Roblox Piano Autoplayer (Interstellar)

Simple Python script that types Roblox piano keys from sheet format like:

- `u` = press `u`
- `[eup]` = press `e`, `u`, `p` together (chord)

## Setup

```bash
python -m pip install pynput
```

## Run

```bash
python interstellar_autoplayer.py
```

It includes your Interstellar sheet by default.

### Use your own sheet file

```bash
python interstellar_autoplayer.py --sheet my_song.txt
```

### Controls

- **Backspace**: cancel playback instantly.
- `--start-delay`: seconds before autoplay starts (default `4.0`)
- `--tempo`: delay between note steps (default `0.07`)
- `--hold`: how long each key/chord is held (default `0.03`)

## Notes

- Run this only where automation is allowed.
- Click the Roblox piano window before playback starts.
