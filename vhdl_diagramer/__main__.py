import tkinter as tk


from .ui.main_window import VHDLDiagramApp

from .ui.diagram_canvas import DiagramCanvas

def main():
    print("VHDL Diagramer running!")

    root = tk.Tk()
    app = VHDLDiagramApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
