# Building a .deb package

A native Debian source package (`debian/`) is provided, built with
`dh-python`/`pybuild` against the system Python (no PyInstaller
involved: the package depends on `python3-hid`, which ships the `hid`
and `hidraw` modules on Debian/Ubuntu, and `python3-tk`):

```bash
sudo apt install debhelper dh-python pybuild-plugin-pyproject \
    python3-all python3-setuptools gettext
dpkg-buildpackage -us -uc -b
```

This produces `../soundblaster-g8_0.1.0-1_all.deb`. Install it with:

```bash
sudo apt install ../soundblaster-g8_0.1.0-1_all.deb
```

The package installs the application (`soundblaster-g8` on `$PATH`), a
menu entry with icon, and the HID udev rule
(`udev/99-soundblaster-g8.rules`, see
[linux-setup.md](linux-setup.md#access-rights-udev)) - so, unlike the
manual install, no `sudo cp` / `udevadm trigger` step is needed for the
card to be accessible without root. The optional ALSA fix
(`alsa-fix/install.sh`) is not part of the package and still needs to be
installed separately if desired (the app re-applies the same fix at every
startup regardless, see
[linux-setup.md](linux-setup.md#microphone-disabled-at-startup-alsa-capture-source)).
