#!/bin/bash
set -euo pipefail

say() { printf '[mommy-pulsy] %s\n' "$1"; }
success() { printf '[mommy-pulsy] %s ♪\n' "$1"; }
concern() { printf '[mommy-pulsy] Hmm... %s\n' "$1" >&2; }

if [[ ${EUID:-$(id -u)} -eq 0 ]]; then
    concern "Please don't run me as root, darling. I install into your user account."
    exit 1
fi

SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/mommy-pulsy"
CONFIG_FILE="$CONFIG_DIR/mommie.lua"
SNAPSHOTS_DIR="$CONFIG_DIR/snapshots"
DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/mommy-pulsy"
APP_DIR="$DATA_DIR/app"
VENV_DIR="$DATA_DIR/venv"
BIN_DIR="${HOME}/.local/bin"

say "Let me check what you're running, sweetheart. ♡"
OS_ID="unknown"
OS_LIKE=""
if [[ -r /etc/os-release ]]; then
    # shellcheck disable=SC1091
    . /etc/os-release
    OS_ID="${ID:-unknown}"
    OS_LIKE="${ID_LIKE:-}"
fi

IS_LINUX=false
IS_ARCH_BASED=false
[[ "${OSTYPE:-}" == linux* ]] && IS_LINUX=true
if [[ "$OS_ID" == "arch" || " $OS_LIKE " == *" arch "* || -e /etc/arch-release ]]; then
    IS_ARCH_BASED=true
fi

say "System detected: ${PRETTY_NAME:-$OS_ID}"

command -v python3 >/dev/null 2>&1 || { concern "I couldn't find Python 3, honey."; exit 1; }
python3 -m pip --version >/dev/null 2>&1 || { concern "Python's pip module isn't available, darling."; exit 1; }
python3 -m venv --help >/dev/null 2>&1 || { concern "Python's venv module isn't available, honey."; exit 1; }

if [[ -f "$CONFIG_FILE" ]]; then
    say "I found your mommie.lua. Don't worry, I won't touch it. ♡"
fi
if [[ -d "$SNAPSHOTS_DIR" ]]; then
    count=$(find "$SNAPSHOTS_DIR" -maxdepth 1 -type f -name '*.lua' | wc -l)
    [[ "$count" -gt 0 ]] && say "I found $count snapshot(s). Those stay safe too. ♡"
fi

if [[ "$IS_ARCH_BASED" == true ]]; then
    say "This is Arch-based. I'll make an isolated Python environment for you."
    if ! command -v pactl >/dev/null 2>&1 && ! command -v pw-cat >/dev/null 2>&1; then
        say "I couldn't find PipeWire/PulseAudio tools yet. You may need:"
        say "  sudo pacman -S pipewire pipewire-pulse libpulse"
    fi
    mkdir -p "$DATA_DIR" "$BIN_DIR"
    python3 -m venv "$VENV_DIR"
    "$VENV_DIR/bin/python" -m pip install --upgrade pip >/dev/null
    "$VENV_DIR/bin/python" -m pip install -r "$SOURCE_DIR/requirements.txt"
    PYTHON_BIN="$VENV_DIR/bin/python"
    success "The isolated environment is ready. ♡"
else
    say "This isn't Arch-based, so I'll use the normal user-level Python installation."
    python3 -m pip install --user -r "$SOURCE_DIR/requirements.txt"
    PYTHON_BIN="python3"
fi

say "Installing mommy-pulsy files..."
mkdir -p "$APP_DIR" "$CONFIG_DIR" "$SNAPSHOTS_DIR" "$BIN_DIR"
rm -rf "$APP_DIR/src"
cp -a "$SOURCE_DIR/src" "$APP_DIR/"
cp "$SOURCE_DIR/mommy_pulsy.py" "$APP_DIR/"
cp "$SOURCE_DIR/default_config.lua" "$APP_DIR/"
chmod +x "$APP_DIR/mommy_pulsy.py"

cat > "$BIN_DIR/mommy-pulsy" <<EOF
#!/bin/sh
exec "$PYTHON_BIN" "$APP_DIR/mommy_pulsy.py" "\$@"
EOF
chmod +x "$BIN_DIR/mommy-pulsy"

if [[ ! -f "$CONFIG_FILE" ]]; then
    cp "$SOURCE_DIR/default_config.lua" "$CONFIG_FILE"
    success "I made you a default mommie.lua. ♡"
else
    success "Your existing mommie.lua is staying exactly where it is."
fi

if [[ ":${PATH}:" != *":$BIN_DIR:"* ]]; then
    concern "$BIN_DIR isn't in your PATH yet, darling."
    printf '  export PATH="$HOME/.local/bin:$PATH"\n'
fi

success "Installation complete! Run 'mommy-pulsy --audio-info' to check system playback."
