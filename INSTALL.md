# Oracle Chat — Installation Guide

## Requirements

- **Python 3.10+** (tested up to 3.14)
- **pip** (for installing Python packages into a virtualenv)
- **Qt6 libraries** (installed automatically with PySide6)
- **Optional:** LibreOffice (for .docx file uploads), `arecord` + `whisper` (for voice input), `espeak-ng` (for voice output), a SearXNG instance (for web search)

---

## Debian / Ubuntu (22.04+)

```bash
# System dependencies
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git

# Optional: for .docx support and voice
sudo apt install -y libreoffice-common alsa-utils espeak-ng

# Clone and install
git clone https://github.com/mshermancyber/oracle-chat.git
cd oracle-chat
./install.sh
```

The installer creates a virtualenv, installs Python dependencies, registers a `.desktop` entry, and symlinks `oracle` to `~/.local/bin/`.

```bash
# Run
oracle                  # detached (returns terminal)
oracle --foreground     # attached (for debugging)
```

---

## Arch Linux / CachyOS / Manjaro

```bash
# System dependencies
sudo pacman -S python python-pip git

# Optional: for .docx support and voice
sudo pacman -S libreoffice-still alsa-utils espeak-ng

# Clone and install
git clone https://github.com/mshermancyber/oracle-chat.git
cd oracle-chat
./install.sh
```

**Note:** Arch uses PEP 668 by default — `install.sh` handles this by creating a virtualenv. Never use `sudo pip install`.

---

## Fedora (38+)

```bash
# System dependencies
sudo dnf install -y python3 python3-pip git

# Optional: for .docx support and voice
sudo dnf install -y libreoffice-core alsa-utils espeak-ng

# Clone and install
git clone https://github.com/mshermancyber/oracle-chat.git
cd oracle-chat
./install.sh
```

---

## Manual Install (any distro)

If `install.sh` doesn't work for your setup:

```bash
cd oracle-chat
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python oracle.py
```

To create a desktop entry manually:

```bash
# Create the launcher script
mkdir -p ~/.local/bin
cat > ~/.local/bin/oracle << 'EOF'
#!/bin/sh
cd /path/to/oracle-chat
exec .venv/bin/python oracle.py "$@"
EOF
chmod +x ~/.local/bin/oracle

# Desktop entry
cat > ~/.local/share/applications/oracle.desktop << EOF
[Desktop Entry]
Name=Oracle
Comment=AI Chat Client
Exec=$HOME/.local/bin/oracle
Icon=oracle
Terminal=false
Type=Application
Categories=Development;
EOF
```

---

## First Launch

1. Run `oracle` from terminal or your app launcher
2. The Settings dialog opens automatically on first run
3. Pick your authentication mode:
   - **Anthropic API:** paste your `sk-ant-...` key from [console.anthropic.com](https://console.anthropic.com)
   - **Custom Gateway:** pick a provider (Ollama, ChatGPT, Gemini, etc.), fill in URL and API key
4. Click OK — Oracle restarts with your chosen provider
5. Start chatting

See [MODELS.md](MODELS.md) for detailed provider setup.

---

## Update

```bash
cd oracle-chat
git pull
.venv/bin/pip install -r requirements.txt
```

---

## Uninstall

```bash
rm ~/.local/bin/oracle
rm ~/.local/share/applications/oracle.desktop
rm -rf ~/.config/oracle          # settings, prompts, memory, projects
rm -rf ~/.local/share/oracle     # chat history, attachments
rm -rf /path/to/oracle-chat      # source code + venv
```

---

## Troubleshooting

**"No module named PySide6"** — The virtualenv wasn't created properly. Run `.venv/bin/pip install -r requirements.txt`.

**Blank window on Wayland** — Set `QT_QPA_PLATFORM=xcb` before launching: `QT_QPA_PLATFORM=xcb oracle`.

**Icon not showing in taskbar** — Run `update-desktop-database ~/.local/share/applications/` and restart your panel.

**"python3: externally managed environment"** — You're trying to pip install outside a venv. Use `./install.sh` or create a venv manually.
