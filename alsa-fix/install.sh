#!/bin/sh
# install.sh — One-time setup for Sound Blaster G8 ALSA fixes
# Run with: sudo ./install.sh
# Uninstall with: sudo ./install.sh --uninstall
#
# What this does:
#   1. Installs a small script that fixes ALSA mixer defaults for the G8
#   2. Installs a udev rule that runs the script automatically when the G8 is detected
#   That's it. No services, no daemons, no cron jobs.

set -e

SCRIPT_SRC="soundblaster-g8-alsa-fix.sh"
RULES_SRC="95-soundblaster-g8-alsa.rules"
SCRIPT_DEST="/usr/local/bin/soundblaster-g8-alsa-fix.sh"
RULES_DEST="/etc/udev/rules.d/95-soundblaster-g8-alsa.rules"

# --- Helpers ---

die() { echo "ERROR: $1" >&2; exit 1; }

check_root() {
    if [ "$(id -u)" -ne 0 ]; then
        die "This script must be run as root (sudo ./install.sh)"
    fi
}

check_deps() {
    for cmd in amixer udevadm; do
        if ! command -v "$cmd" > /dev/null 2>&1; then
            die "Required command '$cmd' not found. Please install alsa-utils."
        fi
    done
}

card_present() {
    for usbid_file in /proc/asound/card*/usbid; do
        [ -r "$usbid_file" ] || continue
        [ "$(cat "$usbid_file" 2>/dev/null)" = "041e:329b" ] && return 0
    done
    return 1
}

# --- Install ---

do_install() {
    check_deps

    SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

    [ -f "$SCRIPT_DIR/$SCRIPT_SRC" ] || die "Cannot find $SCRIPT_SRC in $SCRIPT_DIR"
    [ -f "$SCRIPT_DIR/$RULES_SRC" ] || die "Cannot find $RULES_SRC in $SCRIPT_DIR"

    echo "Installing Sound Blaster G8 ALSA fix..."

    # Install the fix script
    install -m 755 "$SCRIPT_DIR/$SCRIPT_SRC" "$SCRIPT_DEST"
    echo "  ✓ Installed $SCRIPT_DEST"

    # Install the udev rule
    install -m 644 "$SCRIPT_DIR/$RULES_SRC" "$RULES_DEST"
    echo "  ✓ Installed $RULES_DEST"

    # Reload udev rules
    udevadm control --reload-rules
    echo "  ✓ Reloaded udev rules"

    echo ""
    echo "Done! The fix will apply automatically whenever the G8 is plugged in."
    echo ""

    # If the G8 is currently connected, offer to apply the fix now
    if card_present; then
        echo "G8 detected — applying fix now..."
        "$SCRIPT_DEST"
        echo "  ✓ Fix applied to current session"
    else
        echo "Plug in your G8 and it'll be configured automatically."
    fi
}

# --- Uninstall ---

uninstall() {
    echo "Uninstalling Sound Blaster G8 ALSA fix..."

    [ -f "$SCRIPT_DEST" ] && rm -f "$SCRIPT_DEST" && echo "  ✓ Removed $SCRIPT_DEST"
    [ -f "$RULES_DEST" ] && rm -f "$RULES_DEST" && echo "  ✓ Removed $RULES_DEST"

    udevadm control --reload-rules 2>/dev/null
    echo "  ✓ Reloaded udev rules"
    echo ""
    echo "Done! ALSA fix has been removed."
}

# --- Main ---

check_root

case "${1:-}" in
    --uninstall|-u)
        uninstall
        ;;
    --help|-h)
        echo "Usage: sudo ./install.sh [--uninstall]"
        echo ""
        echo "Installs a udev rule + script that automatically fixes ALSA"
        echo "mixer defaults for the Sound Blaster G8 whenever it's plugged in."
        ;;
    *)
        do_install
        ;;
esac
