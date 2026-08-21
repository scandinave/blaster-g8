#!/bin/sh
# install.sh — One-time setup for Sound Blaster G8 ALSA fixes
# Run with: sudo ./install.sh
# Uninstall with: sudo ./install.sh --uninstall
#
# What this does:
#   1. Installs an ALSA card profile that gives the G8 a microphone port, so
#      PipeWire/PulseAudio selects "External Mic" itself instead of Line In
#   2. Installs a small script that fixes ALSA mixer defaults for the G8
#   3. Installs a udev rule that runs the script automatically when the G8 is detected
#   4. Optionally excludes the G8 from `alsactl restore` (needed for Direct Mode)
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

# ALSA card profile (ACP). PipeWire and PulseAudio read profile sets and mixer
# paths from fixed directories under /usr/share, with no per-user or /etc
# override, so these two go there. Both file names are our own - no package
# owns them, so a pipewire update neither removes nor overwrites them.
ACP_DIR="/usr/share/alsa-card-profile/mixer"
ACP_PATH_SRC="acp/analog-input-external-mic.conf"
ACP_PATH_DEST="$ACP_DIR/paths/analog-input-external-mic.conf"
ACP_PROFILE_SRC="acp/soundblaster-g8.conf"
ACP_PROFILE_DEST="$ACP_DIR/profile-sets/soundblaster-g8.conf"
ACP_RULES_SRC="91-soundblaster-g8-acp.rules"
ACP_RULES_DEST="/etc/udev/rules.d/91-soundblaster-g8-acp.rules"

# Step 4 is opt-in because it shadows a file owned by alsa-utils. Marker line
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

    install_card_profile "$SCRIPT_DIR"

    install_restore_override "$SCRIPT_DIR"

    # Reload udev rules
    udevadm control --reload-rules
    echo "  ✓ Reloaded udev rules"
    # Re-run the rules against the card that is already there, so
    # ACP_PROFILE_SET lands in its udev database without a replug. Harmless
    # when no G8 is connected.
    udevadm trigger --subsystem-match=sound --action=change 2>/dev/null || true

    echo ""
    echo "Done! The fix will apply automatically whenever the G8 is plugged in."
    echo ""

    # If the G8 is currently connected, offer to apply the fix now. --now skips
    # the settling delay: the card has clearly been up for a while already.
    if card_present; then
        echo "G8 detected — applying fix now..."
        "$SCRIPT_DEST" --now
        echo "  ✓ Fix applied to current session"
        if [ -f "$ACP_PROFILE_DEST" ]; then
            echo ""
            echo "  The sound server only rebuilds the card on startup. To pick up"
            echo "  the new microphone port without replugging the G8, run as your"
            echo "  own user (not root):"
            echo ""
            echo "      systemctl --user restart wireplumber"
            echo ""
            echo "  then select 'Microphone' as the G8's input in your sound"
            echo "  settings if it isn't already."
        fi
    else
        echo "Plug in your G8 and it'll be configured automatically."
    fi
}

# --- The microphone port: teaching the sound server about "External Mic" ---

# The stock ALSA card profile has no port for the G8's microphone: its
# paths/analog-input-mic.conf only maps the "Mic" and "Mic-In/Mic Array" items
# of the "PCM Capture Source" enumeration, and the G8's item is named
# "External Mic". Line In *is* mapped, so it becomes the card's only analog
# input port, and the sound server writes "PCM Capture Source" back to
# "Line In" every time it applies that route - undoing the fix script.
#
# These two files add the missing port. They are only useful to a sound server
# that reads ACP configuration (PipeWire, PulseAudio); on a system without
# one, $ACP_DIR does not exist and the fix script alone does the job.
install_card_profile() {
    src_dir="$1"

    if [ ! -d "$ACP_DIR/paths" ] || [ ! -d "$ACP_DIR/profile-sets" ]; then
        echo "  · No ALSA card profile directory ($ACP_DIR) — microphone port skipped"
        echo "    (PipeWire/PulseAudio not installed; the fix script still applies)"
        return 0
    fi

    [ -f "$src_dir/$ACP_PATH_SRC" ] || die "Cannot find $ACP_PATH_SRC in $src_dir"
    [ -f "$src_dir/$ACP_PROFILE_SRC" ] || die "Cannot find $ACP_PROFILE_SRC in $src_dir"
    [ -f "$src_dir/$ACP_RULES_SRC" ] || die "Cannot find $ACP_RULES_SRC in $src_dir"

    install -m 644 "$src_dir/$ACP_PATH_SRC" "$ACP_PATH_DEST"
    echo "  ✓ Installed $ACP_PATH_DEST"
    install -m 644 "$src_dir/$ACP_PROFILE_SRC" "$ACP_PROFILE_DEST"
    echo "  ✓ Installed $ACP_PROFILE_DEST"
    install -m 644 "$src_dir/$ACP_RULES_SRC" "$ACP_RULES_DEST"
    echo "  ✓ Installed $ACP_RULES_DEST"
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

    # ALSA card profile. Removing the udev rule alone would be enough to stop
    # using it, but leaving orphan files in /usr/share is not our style.
    for acp_file in "$ACP_RULES_DEST" "$ACP_PROFILE_DEST" "$ACP_PATH_DEST"; do
        [ -f "$acp_file" ] && rm -f "$acp_file" && echo "  ✓ Removed $acp_file"
    done

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
        echo "Installs an ALSA card profile that gives the Sound Blaster G8 a"
        echo "microphone port, plus a udev rule + script that fix its ALSA mixer"
        echo "defaults whenever it's plugged in."
        ;;
    *)
        do_install
        ;;
esac
