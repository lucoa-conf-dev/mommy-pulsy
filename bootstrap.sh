#!/bin/sh
set -eu

REPO="lucoa-conf-dev/mommy-pulsy"
API_URL="https://api.github.com/repos/$REPO/releases/latest"

say() {
    printf '\033[1;35m[mommy-pulsy]\033[0m %s\n' "$1"
}

concern() {
    printf '\033[1;35m[mommy-pulsy]\033[0m Hmm... %s\n' "$1" >&2
}

progress() {
    current="$1"
    total="$2"

    percent=$((current * 100 / total))
    filled=$((percent / 5))
    empty=$((20 - filled))

    bar=""

    i=0
    while [ "$i" -lt "$filled" ]; do
        bar="${bar}█"
        i=$((i + 1))
    done

    i=0
    while [ "$i" -lt "$empty" ]; do
        bar="${bar}░"
        i=$((i + 1))
    done

    printf '\r\033[1;35m[mommy-pulsy]\033[0m [%s] %3d%%' "$bar" "$percent"
}

if [ "$(id -u)" -eq 0 ]; then
    concern "Please run me as your normal user, darling."
    exit 1
fi

command -v curl >/dev/null 2>&1 || {
    concern "I couldn't find curl, honey."
    exit 1
}

command -v tar >/dev/null 2>&1 || {
    concern "I couldn't find tar, darling."
    exit 1
}

command -v mktemp >/dev/null 2>&1 || {
    concern "I couldn't find mktemp, sweetheart."
    exit 1
}

TMP_DIR=$(mktemp -d "${TMPDIR:-/tmp}/mommy-pulsy.XXXXXX")

cleanup() {
    rm -rf "$TMP_DIR"
}

trap cleanup EXIT INT TERM

say "Mommy is waking up. ♡"
say "Looking for the latest release..."

RELEASE_JSON="$TMP_DIR/release.json"

curl -fsSL \
    -H "Accept: application/vnd.github+json" \
    "$API_URL" \
    -o "$RELEASE_JSON"

TAG=$(sed -n 's/.*"tag_name": *"\([^"]*\)".*/\1/p' "$RELEASE_JSON" | head -n 1)

if [ -z "$TAG" ]; then
    concern "I couldn't find a valid release, darling."
    exit 1
fi

VERSION="${TAG#v}"

say "Found mommy-pulsy $TAG. ♡"

ARCHIVE="mommy-pulsy-${VERSION}.tar.gz"
DOWNLOAD_URL="https://github.com/$REPO/releases/download/$TAG/$ARCHIVE"

say "Downloading $ARCHIVE..."

curl -fL \
    --progress-bar \
    "$DOWNLOAD_URL" \
    -o "$TMP_DIR/$ARCHIVE"

printf '\n'

say "Download complete. ♡"
say "Unpacking mommy-pulsy..."

mkdir -p "$TMP_DIR/package"

tar -xzf "$TMP_DIR/$ARCHIVE" \
    -C "$TMP_DIR/package" \
    --strip-components=1

say "Package unpacked. ♡"

#
# ─────────────────────────────────────────────
# Mommy-pulsy installation starts here.
# There is NO install.sh.
# ─────────────────────────────────────────────
#

INSTALL_ROOT="$HOME/.local/share/mommy-pulsy"
BIN_DIR="$HOME/.local/bin"
CONFIG_DIR="$HOME/.config/mommy-pulsy"

say "Preparing your little pulse..."

mkdir -p "$INSTALL_ROOT"
mkdir -p "$BIN_DIR"
mkdir -p "$CONFIG_DIR"

say "Installing mommy-pulsy files..."

cp -R "$TMP_DIR/package/." "$INSTALL_ROOT/"

#
# Preserve the user's existing configuration.
#

if [ ! -f "$CONFIG_DIR/mommie.lua" ]; then
    if [ -f "$INSTALL_ROOT/default_config.lua" ]; then
        cp "$INSTALL_ROOT/default_config.lua" "$CONFIG_DIR/mommie.lua"
        say "Created your default configuration. ♡"
    fi
else
    say "Existing configuration found. Mommy will preserve it. ♡"
fi

#
# Create the executable launcher.
#

cat > "$BIN_DIR/mommy-pulsy" <<EOF
#!/bin/sh
exec python3 "$INSTALL_ROOT/mommy_pulsy.py" "\$@"
EOF

chmod +x "$BIN_DIR/mommy-pulsy"

#
# Create snapshots directory.
#

mkdir -p "$CONFIG_DIR/snapshots"

#
# Optional Python environment.
#

if command -v python3 >/dev/null 2>&1; then
    say "Python is here. ♡"

    if [ -f "$INSTALL_ROOT/requirements.txt" ]; then
        say "Installing mommy-pulsy dependencies..."

        python3 -m pip install \
            --user \
            -r "$INSTALL_ROOT/requirements.txt"
    fi
else
    concern "I couldn't find python3, darling."
    concern "The project files were installed, but mommy-pulsy cannot run yet."
    exit 1
fi

#
# Add ~/.local/bin to PATH for the current installation process.
#

case ":${PATH:-}:" in
    *":$BIN_DIR:"*)
        ;;
    *)
        export PATH="$BIN_DIR:$PATH"
        ;;
esac

printf '\n'

say "Finishing everything..."

progress 1 5
sleep 0.05

progress 2 5
sleep 0.05

progress 3 5
sleep 0.05

progress 4 5
sleep 0.05

progress 5 5

printf '\n\n'

say "Mommy-pulsy is installed. ♡"
say "Your little pulse is ready."
say "Installed to: $INSTALL_ROOT"
say "Command: $BIN_DIR/mommy-pulsy"
say "All tucked away. ♡"