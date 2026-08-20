#!/bin/sh
# install.sh — One-time setup for Sound Blaster G8 ALSA fixes
# Run with: sudo ./install.sh
# Uninstall with: sudo ./install.sh --uninstall
#
# What this does:
#   1. Installs a small script that fixes ALSA mixer defaults for the G8
#   2. Installs a udev rule that runs the script automatically when the G8 is detected
#   3. Optionally excludes the G8 from `alsactl restore` (needed for Direct Mode)
#   That's it. No services, no daemons, no cron jobs.

set -e

SCRIPT_SRC="soundblaster-g8-alsa-fix.sh"
RULES_SRC="95-soundblaster-g8-alsa.rules"
# Own directory rather than a shared /usr/local/bin: this script is executed
# as root by udev on every plug, so its integrity must not depend on the
# permissions /usr/local/bin happens to carry (some setups make it
# group-writable). The directory is created explicitly root:root 0755 below.
SCRIPT_DIR_DEST="/usr/local/lib/soundblaster-g8"
SCRIPT_DEST="$SCRIPT_DIR_DEST/soundblaster-g8-alsa-fix.sh"
RULES_DEST="/etc/udev/rules.d/95-soundblaster-g8-alsa.rules"

# Step 3 is opt-in because it shadows a file owned by alsa-utils. Marker line
# used to make sure --uninstall only ever removes a copy we installed.
RESTORE_SRC="90-alsa-restore.rules"
RESTORE_DEST="/etc/udev/rules.d/90-alsa-restore.rules"
RESTORE_MARKER="Overrides alsa-utils"

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
    install -d -o root -g root -m 755 "$SCRIPT_DIR_DEST"
    install -m 755 "$SCRIPT_DIR/$SCRIPT_SRC" "$SCRIPT_DEST"
    echo "  ✓ Installed $SCRIPT_DEST"

    # Install the udev rule
    install -m 644 "$SCRIPT_DIR/$RULES_SRC" "$RULES_DEST"
    echo "  ✓ Installed $RULES_DEST"

    install_restore_override "$SCRIPT_DIR"

    # Reload udev rules
    udevadm control --reload-rules
    echo "  ✓ Reloaded udev rules"

    echo ""
    echo "Done! The fix will apply automatically whenever the G8 is plugged in."
    echo ""

    # If the G8 is currently connected, offer to apply the fix now. --now skips
    # the settling delay: the card has clearly been up for a while already.
    if card_present; then
        echo "G8 detected — applying fix now..."
        "$SCRIPT_DEST" --now
        echo "  ✓ Fix applied to current session"
    else
        echo "Plug in your G8 and it'll be configured automatically."
    fi
}

# --- Direct Mode: excluding the G8 from alsactl restore ---

install_restore_override() {
    src_dir="$1"

    if [ -e "$RESTORE_DEST" ]; then
        # Ours: refresh it, that is what re-running the installer is for.
        # Anyone else's: not our file, leave it alone and say so.
        if grep -q "$RESTORE_MARKER" "$RESTORE_DEST" 2>/dev/null; then
            install -m 644 "$src_dir/$RESTORE_SRC" "$RESTORE_DEST"
            echo "  ✓ Updated $RESTORE_DEST"
        else
            echo "  · $RESTORE_DEST exists and is not ours — left untouched"
        fi
        return 0
    fi

    cat <<'EOF'

--------------------------------------------------------------------------
Direct Mode support (optional)

Writing to the G8's ALSA mixer within a few seconds of it re-enumerating
knocks it out of Direct Mode. Toggling Direct Mode *is* a re-enumeration, so
`alsactl restore` — which rewrites the card's whole saved mixer state the
moment it registers — makes Direct Mode revert on its own every time, whether
you toggle it from the app or from the card's physical button.

Unlike our own script, alsactl cannot be delayed: udev runs RUN+= programs
unconditionally. The only fix is to shadow alsa-utils' rule file with a copy
that skips this one card:

    /etc/udev/rules.d/90-alsa-restore.rules   (ours, skips 041e:329b)
  shadows
    /usr/lib/udev/rules.d/90-alsa-restore.rules   (alsa-utils)

Every other sound card keeps its normal behaviour. The G8's mixer levels will
no longer be restored at boot by ALSA — on a desktop, PipeWire owns those.

Re-check this copy if alsa-utils ever updates its own rule.
Undo at any time with: sudo ./install.sh --uninstall
--------------------------------------------------------------------------

EOF

    printf "Install it? Direct Mode will not hold without it. [y/N] "
    read -r answer
    case "$answer" in
        [yY]|[yY][eE][sS])
            install -m 644 "$src_dir/$RESTORE_SRC" "$RESTORE_DEST"
            echo "  ✓ Installed $RESTORE_DEST"
            ;;
        *)
            echo "  · Skipped — Direct Mode will revert on its own"
            ;;
    esac
}

# --- Uninstall ---

uninstall() {
    echo "Uninstalling Sound Blaster G8 ALSA fix..."

    [ -f "$SCRIPT_DEST" ] && rm -f "$SCRIPT_DEST" && echo "  ✓ Removed $SCRIPT_DEST"
    # Fails harmlessly if anything else was put there.
    [ -d "$SCRIPT_DIR_DEST" ] && rmdir "$SCRIPT_DIR_DEST" 2>/dev/null \
        && echo "  ✓ Removed $SCRIPT_DIR_DEST"
    [ -f "$RULES_DEST" ] && rm -f "$RULES_DEST" && echo "  ✓ Removed $RULES_DEST"

    # Only remove the alsa-restore override if it is the one we installed:
    # anything else at that path is the user's own and none of our business.
    if [ -f "$RESTORE_DEST" ]; then
        if grep -q "$RESTORE_MARKER" "$RESTORE_DEST" 2>/dev/null; then
            rm -f "$RESTORE_DEST"
            echo "  ✓ Removed $RESTORE_DEST (alsa-utils' own rule applies again)"
        else
            echo "  · Left $RESTORE_DEST alone — not installed by this script"
        fi
    fi

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
