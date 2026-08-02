#!/bin/sh
# soundblaster-g8-alsa-fix.sh
# Fixes ALSA mixer defaults for the Creative Sound Blaster G8 on Linux.
# Triggered automatically by udev when the card is detected.
#
# The snd-usb-audio driver doesn't set the correct capture source, so the
# microphone (External Mic) doesn't work out of the box: the card boots with
# "PCM Capture Source" set to "Line In". This script fixes that.
#
# Card discovery uses /proc/asound/card*/usbid (kernel-provided, not
# localized) instead of parsing `aplay -l` text output: the latter is
# localized (e.g. "carte" instead of "card" on French locales) and breaks
# name-based matching entirely on non-English systems.

VENDOR_PRODUCT="041e:329b"
LOG_TAG="soundblaster-g8-alsa-fix"
MAX_RETRIES=10
RETRY_DELAY=1

log() {
    if command -v logger > /dev/null 2>&1; then
        logger -t "$LOG_TAG" "$1"
    fi
}

# Find the card index. Retry because ALSA enumeration may still be settling.
card_index=""
attempt=0
while [ "$attempt" -lt "$MAX_RETRIES" ]; do
    for usbid_file in /proc/asound/card*/usbid; do
        [ -r "$usbid_file" ] || continue
        if [ "$(cat "$usbid_file" 2>/dev/null)" = "$VENDOR_PRODUCT" ]; then
            card_index=$(echo "$usbid_file" | sed -n 's#.*/card\([0-9][0-9]*\)/usbid#\1#p')
            break
        fi
    done
    [ -n "$card_index" ] && break
    attempt=$((attempt + 1))
    sleep "$RETRY_DELAY"
done

if [ -z "$card_index" ]; then
    log "ERROR: Could not find card with usbid $VENDOR_PRODUCT after $MAX_RETRIES attempts"
    exit 1
fi

log "Found Sound Blaster G8 as card $card_index, applying ALSA fix..."

# === THE CRITICAL FIX ===
# Without this, the microphone simply doesn't work on Linux: the card boots
# with "PCM Capture Source" set to "Line In" instead of "External Mic".
# Named-control form (sset), not numid: numids can be renumbered across
# kernel/driver versions, the control name is stable.
if amixer -c "$card_index" -q sset 'PCM Capture Source' 'External Mic' 2>/dev/null; then
    log "Successfully set capture source to 'External Mic' on card $card_index"
else
    log "ERROR: failed to set capture source on card $card_index"
    exit 1
fi
