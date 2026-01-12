import tkinter as tk


from .ui.main_window import VHDLDiagramApp

from .ui.diagram_canvas import DiagramCanvas

from . import config
import argparse
import sys

def main():
    parser = argparse.ArgumentParser(description='VHDL Diagrammer')
    parser.add_argument('--debug', action='store_true', help='Enable debug output')
    args = parser.parse_args()
    
    if args.debug:
        config.DEBUG = True
        print("Debug mode enabled")

    print("VHDL Diagramer running!")

    root = tk.Tk()
    app = VHDLDiagramApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
