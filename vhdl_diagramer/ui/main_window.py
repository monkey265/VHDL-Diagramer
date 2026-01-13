import tkinter as tk
import json
import os
import dataclasses

import heapq

import math

from tkinter import filedialog, messagebox

from typing import List, Dict, Tuple, Optional, Set

from ..models import Instance, Port
from ..parser import VHDLParser

from ..config import GRID_OPTIONS, DEFAULT_GRID_LABEL, SIGNAL_PANEL_WIDTH, MIN_BLOCK_WIDTH, MIN_BLOCK_HEIGHT, GRID_STEP

from vhdl_diagramer.utils import compress_polyline



from .diagram_canvas import DiagramCanvas
from .inspector_panel import InspectorPanel

RECENT_FILES_FILE = os.path.expanduser("~/.vhdl_diagrammer_config.json")

class VHDLDiagramApp:
    def __init__(self, root):
        self.root = root
        self.root.title('VHDL Instance Diagramer - Enhanced')
        self.root.geometry('1600x900')
        self.instances: List[Instance] = []
        self.signals: Dict[str, str] = {}
        self.variables: Dict[str, str] = {}
        self.constants: Dict[str, str] = {}

        self.root.bind('f', lambda e: self.canvas.zoom_to_fit())
        self.root.bind('F', lambda e: self.canvas.zoom_to_fit())
        self.root.bind('<Control-g>', lambda e: self.canvas.create_group_from_selection())
        self.root.bind('<Control-G>', lambda e: self.canvas.ungroup_selection())
        
        # Menu Bar
        self.menubar = tk.Menu(root)
        root.config(menu=self.menubar)
        
        file_menu = tk.Menu(self.menubar, tearoff=0)
        file_menu.add_command(label="Load VHDL File", command=self.load_file)
        file_menu.add_command(label="Save Schematic", command=self.save_schematic)
        file_menu.add_command(label="Load Schematic", command=self.load_schematic)
        file_menu.add_separator()
        
        # Recent Files Submenu
        self.recent_menu = tk.Menu(file_menu, tearoff=0)
        file_menu.add_cascade(label="Open Recent", menu=self.recent_menu)
        self.recent_files: List[str] = []
        self.load_recent_files()

        file_menu.add_command(label="Parse Text", command=self.parse_text)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=root.quit)
        self.menubar.add_cascade(label="File", menu=file_menu)
        
        # Create Menu
        create_menu = tk.Menu(self.menubar, tearoff=0)
        create_menu.add_command(label="Group Selection", accelerator="Ctrl+G", 
                              command=lambda: self.canvas.create_group_from_selection())
        create_menu.add_command(label="Create Empty Group", 
                              command=lambda: self.canvas.create_empty_group())
        create_menu.add_command(label="Ungroup Selection", accelerator="Ctrl+Shift+G", 
                              command=lambda: self.canvas.ungroup_selection())
        self.menubar.add_cascade(label="Create", menu=create_menu)
        
        # Wire Menu
        wire_menu = tk.Menu(self.menubar, tearoff=0)
        wire_menu.add_command(label="Toggle Bus Style", command=lambda: self.canvas.toggle_bus_style_selection())
        wire_menu.add_command(label="Delete Connection", command=lambda: self.canvas.delete_selected_connection())
        self.menubar.add_cascade(label="Wire", menu=wire_menu)
        
        # View Menu
        view_menu = tk.Menu(self.menubar, tearoff=0)
        
        # Grid submenu or checkbutton?
        # User asked for grid options in view
        
        self.show_grid_var = tk.BooleanVar(value=False)
        view_menu.add_checkbutton(label="Show Grid", onvalue=True, offvalue=False, 
                                  variable=self.show_grid_var, command=self.toggle_grid)
                                  
        grid_size_menu = tk.Menu(view_menu, tearoff=0)
        self.grid_size_var = tk.StringVar(value=DEFAULT_GRID_LABEL)
        for label, val in GRID_OPTIONS.items():
            grid_size_menu.add_radiobutton(label=label, value=label, variable=self.grid_size_var,
                                          command=lambda: self.on_grid_change(self.grid_size_var.get()))
        view_menu.add_cascade(label="Grid Size", menu=grid_size_menu)
        
        view_menu.add_separator()
        
        self.show_signals_var = tk.BooleanVar(value=True)
        view_menu.add_checkbutton(label="Show Signal Names", onvalue=True, offvalue=False,
                                  variable=self.show_signals_var, command=self.toggle_signal_names)
                                  
        self.show_top_var = tk.BooleanVar(value=True)
        view_menu.add_checkbutton(label="Show Top Pins", onvalue=True, offvalue=False,
                                  variable=self.show_top_var, command=self.toggle_top_level)
                                  
        self.show_inspector_var = tk.BooleanVar(value=True)
        view_menu.add_checkbutton(label="Show Inspector", onvalue=True, offvalue=False,
                                  variable=self.show_inspector_var, command=self.toggle_inspector)
        
        self.menubar.add_cascade(label="View", menu=view_menu)

        # Toolbar
        toolbar_frame = tk.Frame(root, bg='#e0e0e0', height=36)
        toolbar_frame.pack(fill=tk.X, padx=0, pady=0)
        toolbar_frame.pack_propagate(False)

        # Helper to make styled buttons
        def add_tool_btn(text, cmd, bg='#f0f0f0'):
            btn = tk.Button(toolbar_frame, text=text, command=cmd, bg=bg, relief='flat', padx=8, pady=2)
            btn.pack(side=tk.LEFT, padx=2, pady=2)
            return btn
        
        # Undo / Redo
        add_tool_btn("↶ Undo", lambda: self.canvas.undo())
        add_tool_btn("↷ Redo", lambda: self.canvas.redo())
        
        tk.Label(toolbar_frame, text=" | ", bg='#e0e0e0').pack(side=tk.LEFT)
        
        # Zoom
        add_tool_btn("🔍+", lambda: self.canvas.zoom(1.2))
        add_tool_btn("🔍-", lambda: self.canvas.zoom(0.8))
        add_tool_btn("Scale to Fit", lambda: self.canvas.zoom_to_fit())

        # Right side info
        tk.Label(toolbar_frame, text='Scroll: Zoom | Drag: Pan | Right-Click: Context Menu  ',
                 font=('Arial', 9), bg='#e0e0e0').pack(side=tk.RIGHT)

        # Main container with canvas and signal list panel
        main_container = tk.Frame(root)
        main_container.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)
        
        # Canvas on the left
        canvas_frame = tk.Frame(main_container)
        canvas_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        # Canvas is now initialized in parse_vhdl, but we need a placeholder or initial canvas
        # for the buttons to call methods on before parsing.
        # Let's keep a minimal canvas initialization here and update it in parse_vhdl.
        # Inspector Panel on the right
        self.inspector = InspectorPanel(main_container, self)
        self.inspector.pack(side=tk.RIGHT, fill=tk.BOTH, padx=(6, 0))
        
        # Init canvas with callback
        self.canvas = DiagramCanvas(canvas_frame, [], {}, {}, {}, [], [], 
                                   on_update=lambda: self.inspector.refresh(),
                                   on_selection_change=self.update_status,
                                   bg='white', cursor='hand2')
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # Status Bar
        self.status_bar_path = tk.StringVar()
        self.status_bar_path.set("Ready")
        
        self.status_bar = tk.Label(self.root, textvariable=self.status_bar_path, 
                                 bd=1, relief=tk.SUNKEN, anchor=tk.W, font=('Arial', 9))
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    def update_status(self, message: str):
        self.status_bar_path.set(message)

    def toggle_grid(self):
        self.canvas.toggle_grid()
        # State synced via variable
    
    def toggle_signal_names(self):
        self.canvas.toggle_signal_names()

    def toggle_top_level(self):
        self.canvas.toggle_top_level()

    def on_grid_change(self, choice):
        if choice in GRID_OPTIONS:
            self.canvas.set_grid_label(choice)

    def toggle_inspector(self):
        if self.show_inspector_var.get():
            self.inspector.pack(side=tk.RIGHT, fill=tk.BOTH, padx=(6, 0))
        else:
            self.inspector.pack_forget()

    def load_file(self):
        file_path = filedialog.askopenfilename(filetypes=[('VHDL files', '*.vhdl *.vhd'), ('All files', '*.*')])
        if file_path:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                text = f.read()
            self.parse_vhdl(text)
            
            # Update Recent Files
            if file_path in self.recent_files:
                self.recent_files.remove(file_path)
            self.recent_files.insert(0, file_path)
            # Keep only last 10
            if len(self.recent_files) > 10:
                self.recent_files = self.recent_files[:10]
            self.save_recent_files()
            self.update_recent_menu()

    def parse_text(self):
        tw = tk.Toplevel(self.root)
        tw.title('Paste VHDL Code')
        tw.geometry('700x450')
        frame = tk.Frame(tw)
        frame.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)
        txt = tk.Text(frame, font=('Courier', 10))
        txt.pack(fill=tk.BOTH, expand=True)
        def do_parse():
            vhdl_text = txt.get('1.0', tk.END)
            self.parse_vhdl(vhdl_text)
            tw.destroy()
        tk.Button(tw, text='Parse', command=do_parse, bg='#4CAF50', fg='white', padx=18, pady=6).pack(pady=6)

    def parse_vhdl(self, vhdl_text: str):
        parser = VHDLParser(vhdl_text)
        parser.parse()
        self.instances = parser.instances
        self.signals = parser.signals
        self.variables = parser.variables
        self.constants = parser.constants
        
        if not self.instances:
            messagebox.showwarning('No Instances', 'No instances found in the VHDL code.')
            return
        
        self.canvas.instances = self.instances
        self.canvas.signals = self.signals
        self.canvas.variables = self.variables
        self.canvas.constants = self.constants
        self.canvas.top_level_pins = parser.top_level_ports
        self.canvas.assignments = parser.assignments
        self.canvas.draw()
        
        # Populate inspector logic
        self.inspector.refresh()
        
        msg = f'Found {len(self.instances)} instances, {len(self.signals)} signals, '
        msg += f'{len(self.variables)} variables, {len(self.constants)} constants.'
        messagebox.showinfo('Success', msg)

    def load_recent_files(self):
        self.recent_files = []
        if os.path.exists(RECENT_FILES_FILE):
            try:
                with open(RECENT_FILES_FILE, 'r') as f:
                    data = json.load(f)
                    self.recent_files = data.get('recent_files', [])
            except Exception as e:
                print(f"Error loading recent files: {e}")
        self.update_recent_menu()

    def save_recent_files(self):
        data = {'recent_files': self.recent_files}
        try:
            with open(RECENT_FILES_FILE, 'w') as f:
                json.dump(data, f)
        except Exception as e:
            print(f"Error saving recent files: {e}")

    def update_recent_menu(self):
        self.recent_menu.delete(0, tk.END)
        for file_path in self.recent_files:
            def load_this(path=file_path):
                try:
                    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                        text = f.read()
                    self.parse_vhdl(text)
                    
                    # Move to top
                    if path in self.recent_files:
                        self.recent_files.remove(path)
                    self.recent_files.insert(0, path)
                    self.save_recent_files()
                    self.update_recent_menu()
                except Exception as e:
                    messagebox.showerror("Error", f"Could not load file: {path}\n{e}")
                    
            self.recent_menu.add_command(label=file_path, command=load_this)
            
        self.recent_menu.add_separator()
        self.recent_menu.add_command(label="Clear Menu", command=self.clear_recent_files)

    def clear_recent_files(self):
        self.recent_files = []
        self.save_recent_files()
        self.update_recent_menu()
    
    def save_schematic(self):
        if not self.canvas.instances:
            messagebox.showinfo("Info", "Nothing to save.")
            return

        filename = filedialog.asksaveasfilename(defaultextension=".json",
                                                filetypes=[("JSON files", "*.json")])
        if not filename:
            return

        data = {
            "instances": [dataclasses.asdict(i) for i in self.canvas.instances],
            "top_level_pins": [dataclasses.asdict(p) for p in self.canvas.top_level_pins],
            "top_pin_positions": self.canvas.top_pin_positions,
            "pin_colors": self.canvas.pin_colors,
            "grid_size": self.canvas.grid_label,
            "signals": self.canvas.signals,
            "variables": self.canvas.variables,
            "constants": self.canvas.constants,
            "assignments": self.canvas.assignments
        }

        try:
            with open(filename, 'w') as f:
                json.dump(data, f, indent=2)
            messagebox.showinfo("Success", "Schematic saved successfully.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save schematic: {e}")

    def load_schematic(self):
        filename = filedialog.askopenfilename(filetypes=[("JSON files", "*.json")])
        if not filename:
            return

        try:
            with open(filename, 'r') as f:
                data = json.load(f)

            # Reconstruct Instances
            instances = []
            for idata in data.get("instances", []):
                # Reconstruct Ports
                ports = []
                for pdata in idata.get("ports", []):
                    ports.append(Port(**pdata))
                orig_ports = []
                for pdata in idata.get("original_ports", []):
                    orig_ports.append(Port(**pdata))
                
                idata["ports"] = ports
                idata["original_ports"] = orig_ports
                instances.append(Instance(**idata))

            # Reconstruct Top Level Pins
            top_pins = []
            for pdata in data.get("top_level_pins", []):
                top_pins.append(Port(**pdata))
            
            self.canvas.instances = instances
            self.canvas.top_level_pins = top_pins
            self.canvas.top_pin_positions = data.get("top_pin_positions", {})
            self.canvas.pin_colors = data.get("pin_colors", {})
            
            # Simple fields
            self.canvas.signals = data.get("signals", {})
            self.canvas.variables = data.get("variables", {})
            self.canvas.constants = data.get("constants", {})
            self.canvas.assignments = data.get("assignments", [])

            # Formatting
            grid_label = data.get("grid_size", DEFAULT_GRID_LABEL)
            if grid_label in GRID_OPTIONS:
                self.canvas.set_grid_label(grid_label)
                self.grid_size_var.set(grid_label)

            self.canvas.draw()
            self.inspector.refresh()
            messagebox.showinfo("Success", "Schematic loaded successfully.")

        except Exception as e:
            messagebox.showerror("Error", f"Failed to load schematic: {e}")
    

