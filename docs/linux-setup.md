# Linux setup details

## hidapi backend: hidraw or libusb

`pip install hidapi` installs **two** Python modules on Linux:

| Module | Backend | `usage_page` listed | Kernel driver |
|---|---|---|---|
| `hid` | **libusb** (the one from the binary wheels, so the default) | ❌ always `0` | detaches `usbhid` during access |
| `hidraw` | **hidraw** | ✅ read from sysfs | kept |

`soundblaster_g8/hidbackend.py` **prefers `hidraw`** and falls back to `hid`
(libusb). The selected backend is logged on startup and shown by:

```bash
python tools/g8_probe.py --backend
```

To get the `hidraw` module, hidapi must be compiled locally:

```bash
sudo apt install libudev-dev libusb-1.0-0-dev   # or your distro's equivalent
HIDAPI_WITH_HIDRAW=1 pip install --no-binary :all: hidapi
```

Consequences of the libusb backend:

- `hid_enumerate()` doesn't populate `usage_page`: the control interface is
  selected on `interface_number == 4` (the **normal** path in this case, not
  a degraded mode).
- libusb **detaches the kernel driver** `usbhid` from the interface for the
  duration of the access: the card's media keys may stop responding during
  that time, and access requires the parent USB device (see the udev rule).

## Access rights (udev)

```bash
sudo cp udev/99-soundblaster-g8.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules && sudo udevadm trigger
```

The `KERNEL=="hidraw*"` rule covers the hidraw backend, the
`SUBSYSTEM=="usb"` rule is **mandatory for libusb** (usbfs access + kernel
driver detachment). `TAG+="uaccess"` is enough for a local session;
`GROUP="plugdev"` is simply ignored on distributions without that group
(Fedora, Arch...).

⚠️ **Race with udev**: after the USB reset triggered by a Direct Mode
toggle, the new `/dev/hidrawN` can appear before udev has applied
permissions. The driver therefore retries the open (`PermissionError`
treated as transient) for 12 seconds.

⚠️ **`uaccess` isn't always reliable on hotplug**: on some sessions
(observed under COSMIC/Wayland), the `uaccess` ACL is only applied by
`systemd-logind` for devices already present when the session opens - not
for ones that appear afterward (USB reset, replug). In that case, the 12
seconds of retries above are never enough: *every* state read times out
(including on the app's very first startup), and reconnection after a
Direct Mode toggle systematically fails. If you observe this symptom,
explicitly add yourself to the `plugdev` group (independent of `uaccess`,
applied synchronously by the udev rule):

```bash
sudo usermod -aG plugdev "$USER"
# then log out/back in (or: newgrp plugdev / sg plugdev -c ...)
```

## Microphone disabled at startup (ALSA capture source)

The `snd-usb-audio` kernel driver initializes the ALSA "PCM Capture
Source" control to `Line In` instead of `External Mic`: the microphone
therefore picks up nothing until the source is changed manually, on every
restart of the card.

The application re-applies this fix on every startup
(`soundblaster_g8/alsa_fix.py`). For the microphone to work even without
launching the app (e.g. right after plugging in the card), also install the
system-level fix:

```bash
sudo alsa-fix/install.sh
```

See [`alsa-fix/README.md`](../alsa-fix/README.md) for details (udev rule +
script, uninstallation).
