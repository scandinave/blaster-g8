"""
Point d'entrée pour l'application Sound Blaster G8 Control.
Lance l'interface GUI avec Tkinter.
"""

import sys
from tkinter import ttk, messagebox
import tkinter as tk


def main():
    """Fonction principale qui lance l'application."""
    from soundblaster_g8.gui import MainWindow

    app = MainWindow()

    # Configurer la fermeture propre de l'application
    def on_closing():
        """Gère la fermeture de l'application."""
        if messagebox.askokcancel("Quitter", "Voulez-vous quitter l'application ?"):
            app.destroy()
            sys.exit(0)

    app.protocol("WM_DELETE_WINDOW", on_closing)

    # Lancer la boucle principale
    app.mainloop()


if __name__ == "__main__":
    main()