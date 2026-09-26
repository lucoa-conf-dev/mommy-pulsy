# Installation Documentation

## System Detection and Installation Flows

mommy-pulsy uses reliable system detection to choose the appropriate installation method for your environment.

## Detection Method

The installer detects the operating system and distribution using multiple reliable methods:

1. **Primary method**: Reads `/etc/os-release` (standard on modern Linux distributions)
2. **Secondary method**: Checks for distribution-specific files (e.g., `/etc/arch-release`, `/etc/debian_version`)
3. **Tertiary method**: Checks for package managers (e.g., `pacman` for Arch)

### Detection Priority

The system is considered **Arch-based** if any of these conditions are true:

1. `ID=arch` in `/etc/os-release`
2. `ID_LIKE` contains "arch" in `/etc/os-release`
3. `/etc/arch-release` file exists
4. `pacman` command is available

This multi-method approach ensures reliable detection without false positives.

## Installation Flows

### Arch-based Systems

For Arch Linux and Arch-based distributions:

1. **System Detection**: Confirms Arch-based system
2. **Virtual Environment Creation**: Creates isolated Python venv at `~/.local/share/mommy-pulsy/venv`
3. **Dependency Installation**: Installs all Python dependencies within the venv
4. **Wrapper Script Creation**: Creates command wrapper that activates the venv before running
5. **Application Installation**: Copies application files to `~/.local/share/mommy-pulsy/`
6. **Configuration Preservation**: Never overwrites existing `mommie.lua` or snapshots

**Example Output**:
```
[mommy-pulsy] Let me check what you're running, sweetheart. ♡
[mommy-pulsy] System detected: Arch Linux
[mommy-pulsy] This is Arch-based, so I'll set up an isolated environment.
[mommy-pulsy] Creating virtual environment...
[mommy-pulsy] Virtual environment created. ♪
[mommy-pulsy] Installing dependencies in isolated environment...
[mommy-pulsy] Dependencies installed nicely in the isolated environment. ♪
[mommy-pulsy] Everything is tucked away nicely. ♡
```

### Non-Arch Systems

For Debian, Ubuntu, Fedora, macOS, and other systems:

1. **System Detection**: Identifies the distribution
2. **Global Dependency Installation**: Installs Python dependencies using system pip
3. **Wrapper Script Creation**: Creates command wrapper for the application
4. **Application Installation**: Copies application files to `~/.local/share/mommy-pulsy/`
5. **Configuration Preservation**: Never overwrites existing `mommie.lua` or snapshots

**Example Output**:
```
[mommy-pulsy] Let me see what we have here... ♡
[mommy-pulsy] System detected: Debian/Ubuntu
[mommy-pulsy] This isn't Arch-based, so I'll use the normal installation path.
[mommy-pulsy] Installing dependencies globally...
[mommy-pulsy] Dependencies installed nicely.
```

## Configuration and Snapshot Preservation

The installer **never** modifies or overwrites:

- `~/.config/mommy-pulsy/mommie.lua` (main configuration)
- `~/.config/mommy-pulsy/snapshots/` (configuration snapshots)

If these exist, the installer:
1. Detects them
2. Reports their presence to the user
3. Continues without modification
4. Preserves all existing data

## Virtual Environment Details (Arch-based)

### Location
- **Path**: `~/.local/share/mommy-pulsy/venv`
- **Python**: Uses system Python 3
- **Isolation**: Complete isolation from system Python packages

### Benefits
- No pollution of system Python environment
- Avoids conflicts with system packages
- Easy to remove or update
- Follows Arch Linux best practices

### Wrapper Script
The installed `mommy-pulsy` command automatically:
1. Activates the virtual environment
2. Runs the application
3. Deactivates the environment after execution

## Command Availability

After installation, the `mommy-pulsy` command is available from:

- **Arch-based**: Works via wrapper script that activates venv
- **Other systems**: Works via wrapper script that uses system Python

The command remains available regardless of installation method.

## Installation Methods

### Local Installation (Git)
```bash
git clone <repository>
cd mommy-pulsy
./install.sh
```

### Remote Installation (curl)
```bash
curl -fsSL <installer-url> | sh
```

Both methods use the same system detection and installation flows.

## Supported Systems

### Arch-based
- Arch Linux
- Manjaro
- EndeavourOS
- Garuda Linux
- Any distribution with `ID_LIKE=arch`

### Debian-based
- Debian
- Ubuntu
- Linux Mint
- Pop!_OS
- Any distribution with `ID=debian` or `ID=ubuntu`

### Fedora-based
- Fedora
- RHEL
- CentOS
- Any distribution with `ID=fedora` or `ID=rhel`

### macOS
- macOS (using Homebrew or system Python)

### Unknown Systems
If the system cannot be reliably identified, the installer:
1. Reports the detected information
2. Explains what was found
3. Stops with clear instructions
4. Does not proceed with potentially incorrect installation

## Error Handling

The installer handles common errors:

1. **Missing Python 3**: Clear message to install Python 3 first
2. **Missing pip**: Clear message to install pip first
3. **Missing venv (Arch)**: Clear message to install python-virtualenv
4. **Root user**: Refuses to run as root for security
5. **Unknown system**: Stops with clear information about what was detected

## Manual Intervention

If automatic detection fails, users can:

1. **Report the issue**: Provide `/etc/os-release` contents
2. **Manual installation**: Install dependencies manually
3. **System-specific adjustments**: Modify the installation script for their system

## Security Considerations

1. **No root required**: Installation runs as regular user
2. **No system modification**: Only writes to user directories
3. **Configuration preservation**: Never overwrites user data
4. **Virtual isolation**: Arch systems use isolated venv
5. **Atomic writes**: Configuration uses atomic file operations

## Troubleshooting

### Installation fails on Arch
```bash
# Check venv is available
python3 -m venv --help

# If not available, install it
sudo pacman -S python-virtualenv
```

### Command not found after installation
```bash
# Add to PATH (add to ~/.bashrc or ~/.zshrc)
export PATH="$HOME/.local/bin:$PATH"
```

### Dependencies fail to install
```bash
# Try upgrading pip first
pip install --upgrade pip

# Then retry installation
```

## Update Process

Updating mommy-pulsy preserves:
- User configuration (`mommie.lua`)
- All snapshots
- Virtual environment (Arch-based)
- Command availability

The update process:
1. Detects system (same as initial installation)
2. Updates application files
3. Updates dependencies in venv (Arch-based)
4. Preserves all user data
