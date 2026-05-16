**Here is a clean, professional `README.md` ready for your GitHub repository:**

```markdown
# 🌌 Interstellar Roblox Piano Autoplayer

A powerful, beautiful, and highly customizable Roblox piano autoplayer with a space/galaxy theme.

![Demo](https://i.imgur.com/placeholder.png) <!-- Replace with actual screenshot -->

## ✨ Features

- **Accurate Playback** – Supports chords `[ ]`, fast sequences `{ }`, pauses `-` / `--`, and newlines
- **Smart Key Handling** – Uppercase letters = **Shift + key**, lowercase = normal key (matches most Roblox pianos)
- **Ctrl Support** – `^q` for underlined/extra keys
- **Precise Timing** – BPM accurately reflects notes per minute (up to 500 BPM)
- **Seek Controls** – Reset, skip ±8 steps while playing or paused
- **Auto Newline Pause** – Configurable pause between lines for natural phrasing
- **Hotkeys** – Start/Stop with customizable global hotkeys (default: F8 / Backspace)
- **Settings Persistence** – Remembers BPM, hold time, sheet, etc.
- **Galaxy UI** – Stunning space-themed interface

## 🎹 Supported Sheet Syntax

| Syntax              | Meaning                              | Example                  |
|---------------------|--------------------------------------|--------------------------|
| `e`                 | Normal key                           | `q w e r t y`            |
| `E`                 | **Shift + e** (uppercase pitch)      | `E e E e`                |
| `[EUP]`             | Chord (all at once)                  | `[EUP] [ASD]`            |
| `{abc}`             | Fast sequence (half delay)           | `{asdf}`                 |
| `-`                 | Short pause                          | `abc - def`              |
| `--`                | Long pause                           | `abc -- def`             |
| `^q`                | Ctrl + q (underlined keys)           | `^q ^w ^e`               |
| New line            | Slight pause (configurable)          | `Line1\nLine2`           |

## 📥 Installation

1. **Clone the repo**
   ```bash
   git clone https://github.com/yourusername/interstellar-roblox-piano-autoplayer.git
   cd interstellar-roblox-piano-autoplayer
   ```

2. **Install dependencies**
   ```bash
   pip install pynput
   ```

3. **Run the autoplayer**
   ```bash
   python interstellar_autoplayer.py
   ```

> **Note:** Run as Administrator if you have issues with key registration in Roblox.

## 🎮 How to Use

1. Paste your piano sheet into the big text box
2. Adjust **BPM**, **Hold duration**, and **Newline pause**
3. Click **▶ Start** or press **F8**
4. Focus Roblox window (Alt+Tab after start delay)
5. Press **Backspace** to stop anytime

### Controls

- **F8** → Start playback (customizable)
- **Backspace** → Stop playback
- Seek buttons: Reset, -8 steps, +8 steps

## ⚙️ Settings

- **BPM**: 10 – 500 (accurate note onset rate)
- **Hold duration**: Usually **0.020** seconds (adjust if notes drop)
- **Newline pause**: Default **0.15** seconds
- **Start delay**: Time before playback begins

## 📸 Screenshots

![Main Interface](https://i.imgur.com/placeholder.png)

*(Add your actual screenshots here)*

## 🛠️ Requirements

- Python 3.8+
- `pynput` library
- Windows (best compatibility with Roblox)

## 📝 Changelog

- **v12+** – Automatic newline pauses, improved Shift handling
- **v11** – More reliable uppercase (Shift) key registration
- **v7+** – Cleaned symbol map to match your piano layout
- Full history in the code

## 🤝 Contributing

Pull requests are welcome! Feel free to improve the UI, add new features (velocity, MIDI import, etc.), or optimize timing.

## 📄 License

This project is open-source under the **MIT License**.

---

**Made with ❤️ for the Roblox piano community**

Star the repo if you find it useful!
```
