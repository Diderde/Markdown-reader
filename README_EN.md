# Markdown Reader

[简体中文](README.md) | English

A Markdown reader with side-by-side editing and live rendering, adaptive for desktop and mobile.

## Run

```powershell
cd markdown-reader
python -m venv .venv
.venv\Scripts\pip install -e .
.venv\Scripts\python main.py        # desktop window
```

**One-click start**: double-click `run.bat` — it checks the environment; when dependencies are missing it asks in the console and, on confirmation, creates a `.venv` and installs them (get-pip.py is fetched only from the official PyPA endpoint, behind a host whitelist and restricted-address validation). `--yes` skips the prompt; `--narrow` forces the mobile layout.

- **Desktop**: `python main.py` (or `flet run`);
- **Web**: `flet run --web` — open the URL on your phone (same LAN) for the mobile layout;
- **Mobile**: `flet run --android` / `--ios` (requires Flet CLI), or package an APK.

## SSH tunnel access (optional, encrypted)

Prefer not to expose a port on the LAN? Have the app listen on loopback only and reach it from your phone through an SSH tunnel:

1. Install the OpenSSH server on the PC (elevated PowerShell, one-time):
   ```powershell
   Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0
   Start-Service sshd
   Set-Service sshd StartupType Automatic
   New-NetFirewallRule -Name sshd-in -DisplayName 'OpenSSH Server' -Direction Inbound -Protocol TCP -LocalPort 22 -Action Allow
   ```
2. Run `run-web.bat` (binds to `127.0.0.1:8550`, never exposed to the LAN);
3. On the phone, open the tunnel (Termux directly; Termius via Port Forwarding):
   ```
   ssh -N -L 8550:127.0.0.1:8550 user@<pc-ip>
   ```
4. Open `http://127.0.0.1:8550` in the phone's browser.

Traffic is encrypted end-to-end by SSH; the browser talks to the phone's own loopback, so no TLS certificate is needed.

## Features

- Wide screens (≥900px): source | preview panes; narrow screens: "source / preview" tabs
- Adaptive debounce (120ms ~ 2s); parsing and control building run off the UI thread
- Hand-written CommonMark-style parser: headings (ATX/Setext), fenced & indented code,
  quotes, lists (incl. task lists), GFM tables (alignment + `\|` escapes), link reference definitions
- Inline syntax: **bold**, *italic*, ~~strikethrough~~, ==highlight== (built-in extension),
  inline code, links/images/autolinks/email, backslash escapes, hard/soft breaks
- Lightweight syntax highlighting: Python / JavaScript / JSON / HTML / CSS / Bash
- Open .md files (UTF-8 / GB18030 auto-detect), sample document, clear, toggle source pane
- Status bar: file, characters, parse time, blocks/nodes, error count
- Anti-freeze: bounded forward scans, recursion depth cap, inline parse budget;
  render failures keep the last good render and show an error banner

## License

This project is open source under [GPL-2.0-or-later](LICENSE): redistributed derivatives must likewise be licensed GPL-2.0-or-later with the copyright notice intact.
