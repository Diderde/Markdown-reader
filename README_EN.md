# Markdown Reader

[简体中文](README.md) | English

A Markdown reader with side-by-side editing and live rendering, adaptive for desktop and mobile.
Tested only on Windows 11 desktop so far.

## Run

```powershell
python -m venv .venv
.venv\Scripts\pip install -e .
.venv\Scripts\python main.py        # desktop window
```

**One-click start (recommended)**: double-click `run.bat` — it checks the environment and, when
dependencies are missing, asks before creating `.venv` and installing them.
`--yes` skips the prompt; `--narrow` forces the mobile layout.

Other ways:

- **Desktop**: `python main.py` (or `flet run`)
- **Web**: `flet run --web` — open the URL on your phone (same LAN) for the mobile layout
- **Mobile**: `flet run --android` / `--ios` (requires Flet CLI), or package an APK

## Features

- Wide screens (≥900px): source | preview panes; narrow screens: "source / preview" tabs
- Adaptive debounce (120ms ~ 2s); parsing and control building run off the UI thread,
  stale results are discarded
- Hand-written CommonMark-style parser: headings (ATX/Setext), paragraphs, fenced & indented
  code, quotes, lists (incl. task lists), GFM tables (alignment + `\|` escapes), link reference definitions
- Inline syntax: **bold**, *italic*, ~~strikethrough~~, ==highlight== (built-in extension),
  inline code, links/images/autolinks/email, backslash escapes, hard/soft breaks
- Lightweight syntax highlighting: Python / JavaScript / JSON / HTML / CSS / Bash
- Open .md files (UTF-8 / GB18030 auto-detect), sample document, clear, toggle source pane
- Status bar: file, characters, parse time, blocks/nodes, error count
- Anti-freeze: bounded forward scans, recursion depth cap, inline scan budget;
  render failures keep the last good render and show a notice

## License

Copyright © 2026 Diderde

This project is open source under [GPL-2.0-or-later](LICENSE): redistributed derivatives must likewise be licensed GPL-2.0-or-later with the copyright notice intact.
