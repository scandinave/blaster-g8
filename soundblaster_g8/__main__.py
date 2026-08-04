"""
Entry point for the Sound Blaster G8 Control application.
Launches the Tkinter GUI.
"""

import sys
from tkinter import ttk, messagebox
import tkinter as tk


def main():
    """Main function that launches the application."""
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
