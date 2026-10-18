# ReaLocalizer - Game Memory & Binary Localization Suite

A professional localization and binary string patching engine engineered with reverse engineering (REA) principles, targeting Call of Duty: Black Ops Cold War (T8 Engine) and IW engine releases.

---

## 🚀 Features

- **Text & String Studio:** High-performance string searching, in-line string replacement, and font glyph encoding presets (UTF-8, Safe-ASCII, CP-1254).
- **Hex & Offset Inspector:** Real-time 16-byte hexadecimal inspector (`0x004A...`), glyph viewer, and memory offset mapping for game packages (`.xpak`, `.ff`).
- **Live Byte Budget & Overflow Protection:** Real-time visual gauge preventing buffer overflows by strictly enforcing in-place memory boundary constraints.
- **Package & Backup Manager:** Inspect package sizes, string counts, and perform one-click restores from original `.bak` archives.
- **Process & Anti-Cheat Watcher:** Monitors target game executables to prevent concurrent memory access conflicts.

---

## ✨ Enhancements & Modifications by @xavierlayne

- **Unified Rea Architecture:** Restructured legacy tools into a clean, modular REA suite.
- **Developer Attribution:** Prominent developer credits for [@xavierlayne](https://github.com/xavierlayne) across HUD messages, console output, and window titles.

---

## 🛠️ Usage

```bash
git clone https://github.com/xavierlayne/ReaLocalizer.git
cd ReaLocalizer
python -m pip install -r requirements.txt
python main.py
```

---

## 📄 License & Maintainer

Distributed under the [MIT License](LICENSE).

- **Developer:** [@xavierlayne](https://github.com/xavierlayne)
