import tkinter as tk

import heapq

import math

from tkinter import filedialog, messagebox

from typing import List, Dict, Tuple, Optional, Set

from ..models import Instance, Port
from ..parser import VHDLParser

from ..config import GRID_OPTIONS, DEFAULT_GRID_LABEL, SIGNAL_PANEL_WIDTH, MIN_BLOCK_WIDTH, MIN_BLOCK_HEIGHT, GRID_STEP

from vhdl_diagramer.utils import compress_polyline


from .diagram_canvas import DiagramCanvas


class VHDLDiagramApp:
    def __init__(self, root):
        self.root = root
        self.root.title('VHDL Instance Diagramer - Enhanced')
        self.root.geometry('1600x900')
        self.instances: List[Instance] = []
        self.signals: Dict[str, str] = {}
        self.variables: Dict[str, str] = {}
        self.constants: Dict[str, str] = {}

        # Menu Bar
        self.menubar = tk.Menu(root)
        root.config(menu=self.menubar)
        
        # File Menu
        file_menu = tk.Menu(self.menubar, tearoff=0)
        file_menu.add_command(label="Load VHDL File", command=self.load_file)
        file_menu.add_command(label="Parse Text", command=self.parse_text)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=root.quit)
        self.menubar.add_cascade(label="File", menu=file_menu)
        
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
                                  
        self.show_top_var = tk.BooleanVar(value=False)
        view_menu.add_checkbutton(label="Show Top Pins", onvalue=True, offvalue=False,
                                  variable=self.show_top_var, command=self.toggle_top_level)
                                  
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
        self.canvas = DiagramCanvas(canvas_frame, [], {}, {}, {}, [], [], bg='white', cursor='hand2')
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas_frame = canvas_frame # Store canvas_frame for later use in parse_vhdl
        
        # Signal/Variable list panel on the right
        panel_frame = tk.Frame(main_container, bg='#f5f5f5', width=SIGNAL_PANEL_WIDTH)
        panel_frame.pack(side=tk.RIGHT, fill=tk.BOTH, padx=(6, 0))
        panel_frame.pack_propagate(False)
        
        tk.Label(panel_frame, text='Signals & Variables', font=('Arial', 10, 'bold'), 
                bg='#f5f5f5').pack(pady=8)
        
        # Create scrollable listbox
        list_frame = tk.Frame(panel_frame)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)
        
        scrollbar = tk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.signal_listbox = tk.Listbox(list_frame, yscrollcommand=scrollbar.set, 
                                        font=('Courier', 9), selectmode=tk.SINGLE,
                                        activestyle='none')
        self.signal_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.signal_listbox.yview)
        
        self.signal_listbox.bind('<<ListboxSelect>>', self.on_signal_select)
        
        # Legend
        legend_frame = tk.Frame(panel_frame, bg='#f5f5f5')
        legend_frame.pack(fill=tk.X, padx=6, pady=6)
        tk.Label(legend_frame, text='Legend:', font=('Arial', 8, 'bold'), bg='#f5f5f5').pack(anchor='w')
        
        for color, label in [('#4CAF50', 'Signal'), ('#9C27B0', 'Variable'), 
                            ('#FF9800', 'Constant'), ('#607D8B', 'Undeclared')]:
            item_frame = tk.Frame(legend_frame, bg='#f5f5f5')
            item_frame.pack(anchor='w', pady=2)
            tk.Label(item_frame, text='  ', bg=color, width=2).pack(side=tk.LEFT, padx=(0, 4))
            tk.Label(item_frame, text=label, font=('Arial', 8), bg='#f5f5f5').pack(side=tk.LEFT)
        
        # Status info
        self.status_label = tk.Label(panel_frame, text='● = used in connections\n○ = declared but unused', 
                                     font=('Arial', 7), bg='#f5f5f5', fg='#666', justify=tk.LEFT)
        self.status_label.pack(pady=4)

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

    def on_signal_select(self, event):
        selection = self.signal_listbox.curselection()
        if selection:
            idx = selection[0]
            item = self.signal_listbox.get(idx)
            # Skip header lines
            if item.startswith('===') or not item.strip():
                return
            # Extract signal name (between marker and colon)
            parts = item.strip().split()
            if len(parts) >= 2:
                signal_name = parts[1].rstrip(':')
                self.canvas.highlight_signal = signal_name
                self.canvas.draw()

    def load_file(self):
        file_path = filedialog.askopenfilename(filetypes=[('VHDL files', '*.vhdl *.vhd'), ('All files', '*.*')])
        if file_path:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                text = f.read()
            self.parse_vhdl(text)

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
        
        # Populate signal list
        self.update_signal_list()
        
        msg = f'Found {len(self.instances)} instances, {len(self.signals)} signals, '
        msg += f'{len(self.variables)} variables, {len(self.constants)} constants.'
        messagebox.showinfo('Success', msg)
    
    def update_signal_list(self):
        '''Update the signal/variable listbox with all declarations.'''
        self.signal_listbox.delete(0, tk.END)
        
        # Get all signals used in connections
        used_signals = set()
        for inst in self.instances:
            for port in inst.ports:
                used_signals.add(port.signal)
        
        # Add signals
        if self.signals:
            self.signal_listbox.insert(tk.END, '=== SIGNALS ===')
            for name in sorted(self.signals.keys()):
                type_info = self.signals[name]
                marker = '●' if name in used_signals else '○'
                # Truncate long type names
                if len(type_info) > 25:
                    type_info = type_info[:22] + '...'
                self.signal_listbox.insert(tk.END, f'  {marker} {name}: {type_info}')
        
        # Add variables
        if self.variables:
            if self.signals:
                self.signal_listbox.insert(tk.END, '')
            self.signal_listbox.insert(tk.END, '=== VARIABLES ===')
            for name in sorted(self.variables.keys()):
                type_info = self.variables[name]
                marker = '●' if name in used_signals else '○'
                if len(type_info) > 25:
                    type_info = type_info[:22] + '...'
                self.signal_listbox.insert(tk.END, f'  {marker} {name}: {type_info}')
        
        # Add constants
        if self.constants:
            if self.signals or self.variables:
                self.signal_listbox.insert(tk.END, '')
            self.signal_listbox.insert(tk.END, '=== CONSTANTS ===')
            for name in sorted(self.constants.keys()):
                type_info = self.constants[name]
                marker = '●' if name in used_signals else '○'
                if len(type_info) > 25:
                    type_info = type_info[:22] + '...'
                self.signal_listbox.insert(tk.END, f'  {marker} {name}: {type_info}')
