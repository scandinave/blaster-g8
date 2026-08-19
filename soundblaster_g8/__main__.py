"""
Entry point for the Sound Blaster G8 Control application.
Launches the Tkinter GUI.
"""

import ctypes
import sys
from tkinter import ttk, messagebox
import tkinter as tk

#: ``mallopt`` option number for ``M_ARENA_MAX`` (see ``malloc.h``).
_M_ARENA_MAX = -8


def _cap_malloc_arenas() -> None:
    """Makes every thread share glibc's main malloc arena.

    Hardware commands run on a worker thread (see ``controller.submit``);
    without this, glibc reserves a 64 MB arena per thread on top of its 8 MB
    stack. That address space is virtual - it barely dents RSS - but it
    inflates the VIRT column of every system monitor and is never handed
    back. Together with the shared worker, this keeps VIRT flat around
    70-80 MB where it used to climb past 200 MB with no ceiling.

    The cost is that the worker and the Tk thread contend for one arena
    lock. Irrelevant at this scale: the worker allocates a 65-byte frame per
    command, and it spends its time blocked on USB, not in malloc.

    Only affects arenas created afterwards, hence the call before any thread
    starts.
    """
    try:
        ctypes.CDLL("libc.so.6").mallopt(_M_ARENA_MAX, 1)
    except (OSError, AttributeError):
        pass  # not glibc (musl, macOS): nothing to cap


def _set_process_name() -> None:
    """Renames the process from ``python3`` to ``soundblaster-g8``.

    Without this, ``/proc/pid/comm`` and the visible command line stay tied
    to the Python interpreter, so system monitors (e.g. COSMIC's) show a bare
    "python3.12" process instead of the app. The name must match
    ``Exec``/``StartupWMClass`` in ``packaging/soundblaster-g8.desktop`` for
    monitors that correlate processes with installed desktop entries.
    """
    try:
        import setproctitle

        setproctitle.setproctitle("soundblaster-g8")
    except (ImportError, OSError):
        pass  # optional dependency missing, or platform doesn't support it


def main():
    """Main function that launches the application."""
    _set_process_name()
    _cap_malloc_arenas()

    from soundblaster_g8.gui import MainWindow
    from soundblaster_g8.gui import i18n

    app = MainWindow()

    # Set up clean application shutdown
    def on_closing():
        """Handles application shutdown."""
        if messagebox.askokcancel(i18n._("Quit"), i18n._("Do you want to quit the application?")):
            app.destroy()
            sys.exit(0)

    app.protocol("WM_DELETE_WINDOW", on_closing)

    # Run the main loop
    app.mainloop()


if __name__ == "__main__":
    main()
