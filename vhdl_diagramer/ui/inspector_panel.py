import tkinter as tk
from tkinter import ttk, Menu
from typing import List, Dict, Any, Optional

from vhdl_diagramer.config import SIGNAL_PANEL_WIDTH
from vhdl_diagramer.models import Instance, Port

class InspectorPanel(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, width=SIGNAL_PANEL_WIDTH, bg='#f5f5f5')
        self.app = app
        self.pack_propagate(False)
        
        # Header with toggle
        self.header_frame = tk.Frame(self, bg='#e0e0e0', height=30)
        self.header_frame.pack(fill=tk.X)
        
        self.title_label = tk.Label(self.header_frame, text="Inspector", font=('Arial', 10, 'bold'), bg='#e0e0e0')
        self.title_label.pack(side=tk.LEFT, padx=5)
        
        # Notebook for tabs
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)
        
        # --- Blocks Tab ---
        self.blocks_frame = tk.Frame(self.notebook)
        self.notebook.add(self.blocks_frame, text="Blocks")
        
        self.block_tree = ttk.Treeview(self.blocks_frame, columns=('status'), show='tree headings')
        self.block_tree.heading('status', text='Status')
        self.block_tree.column('status', width=60, anchor='center')
        self.block_tree.column('#0', width=180)
        self.block_tree.pack(fill=tk.BOTH, expand=True)
        
        self.block_tree.bind('<Button-3>', self.on_block_right_click)
        
        # --- Pins Tab ---
        self.pins_frame = tk.Frame(self.notebook)
        self.notebook.add(self.pins_frame, text="Pins")
        self.pins_list = tk.Listbox(self.pins_frame, font=('Courier', 9))
        self.pins_list.pack(fill=tk.BOTH, expand=True)
        self.pins_list.bind('<Button-3>', self.on_pin_right_click)
        
        # --- Signals Tab ---
        self.signals_frame = tk.Frame(self.notebook)
        self.notebook.add(self.signals_frame, text="Signals")
        self.signal_list = tk.Listbox(self.signals_frame, font=('Courier', 9))
        self.signal_list.pack(fill=tk.BOTH, expand=True)
        self.signal_list.bind('<<ListboxSelect>>', self.on_signal_select)
        
        # --- Legend Frame (Bottom) ---
        self.legend_frame = tk.Frame(self, bg='#f5f5f5', height=100)
        self.legend_frame.pack(fill=tk.X, padx=5, pady=5)
        self.create_legend()

    def create_legend(self):
        tk.Label(self.legend_frame, text='Legend:', font=('Arial', 8, 'bold'), bg='#f5f5f5').pack(anchor='w')
        for color, label in [('#4CAF50', 'Signal'), ('#9C27B0', 'Variable'), 
                            ('#FF9800', 'Constant'), ('#607D8B', 'Undeclared'),
                            ('#2196F3', 'Input Port'), ('#F44336', 'Output Port')]:
            item_frame = tk.Frame(self.legend_frame, bg='#f5f5f5')
            item_frame.pack(anchor='w', pady=2)
            tk.Label(item_frame, text='  ', bg=color, width=2).pack(side=tk.LEFT, padx=(0, 4))
            tk.Label(item_frame, text=label, font=('Arial', 8), bg='#f5f5f5').pack(side=tk.LEFT)

    def refresh(self):
        # Update Blocks
        self.block_tree.delete(*self.block_tree.get_children())
        if self.app.canvas and self.app.canvas.instances:
            for inst in self.app.canvas.instances:
                status = "Visible" if inst.visible else "Deleted"
                # Use tag for color?
                node_id = self.block_tree.insert('', 'end', text=inst.name, values=(status,))
                if not inst.visible:
                    self.block_tree.item(node_id, tags=('deleted',))
        
        self.block_tree.tag_configure('deleted', foreground='gray')
        self.block_tree.tag_configure('deleted', foreground='gray')
        
        # Update Pins
        self.pins_list.delete(0, tk.END)
        if self.app.canvas and self.app.canvas.top_level_pins:
            for p in self.app.canvas.top_level_pins:
                self.pins_list.insert(tk.END, f"{p.direction}: {p.name}")
        # Update Signals
        self.update_signal_list()

    def update_signal_list(self):
        self.signal_list.delete(0, tk.END)
        # Using logic from main_window
        if not self.app.canvas: return
        
        # Get used signals
        used_signals = set()
        for inst in self.app.canvas.instances:
            if inst.visible: # Only count visible?
                for port in inst.ports:
                    used_signals.add(port.signal)
        
        # Add Signals
        if self.app.canvas.signals:
            #self.signal_list.insert(tk.END, '--- SIGNALS ---')
            for name in sorted(self.app.canvas.signals.keys()):
                marker = '●' if name in used_signals else '○'
                self.signal_list.insert(tk.END, f'{marker} {name}')

        # Add Variables
        if self.app.canvas.variables:
            #self.signal_list.insert(tk.END, '--- VARIABLES ---')
            for name in sorted(self.app.canvas.variables.keys()):
                marker = '●' if name in used_signals else '○'
                self.signal_list.insert(tk.END, f'{marker} {name}')

    def on_block_right_click(self, event):
        item_id = self.block_tree.identify_row(event.y)
        if item_id:
            self.block_tree.selection_set(item_id)
            inst_name = self.block_tree.item(item_id, 'text')
            
            # Find instance
            inst = next((i for i in self.app.canvas.instances if i.name == inst_name), None)
            if inst:
                m = Menu(self, tearoff=0)
                if not inst.visible:
                    m.add_command(label="Restore Block", command=lambda: self.app.canvas.restore_instance(inst))
                else:
                    m.add_command(label="Delete Block", command=lambda: self.app.canvas.delete_instance(inst))
                m.tk_popup(event.x_root, event.y_root)

    def on_pin_right_click(self, event):
        selection = self.pins_list.nearest(event.y)
        if selection >= 0:
            self.pins_list.selection_clear(0, tk.END)
            self.pins_list.selection_set(selection)
            item_text = self.pins_list.get(selection)
            # Format is "DIR: Name"
            if ": " in item_text:
                pin_name = item_text.split(": ")[1]
                
                pin = next((p for p in self.app.canvas.top_level_pins if p.name == pin_name), None)
                if pin:
                    m = Menu(self, tearoff=0)
                    m.add_command(label="Edit Font...", command=lambda: self.app.canvas.edit_font(pin))
                    m.add_command(label="Change Color", command=lambda: self.app.canvas.change_pin_color(pin))
                    m.add_command(label="Delete Pin", command=lambda: self.app.canvas.delete_pin(pin))
                    m.tk_popup(event.x_root, event.y_root)

    def on_signal_select(self, event):
        selection = self.signal_list.curselection()
        if selection:
            idx = selection[0]
            item = self.signal_list.get(idx)
            if item.startswith('---'): return
            parts = item.strip().split()
            if len(parts) >= 2:
                signal_name = parts[1]
                self.app.canvas.highlight_signal = signal_name
                self.app.canvas.draw()
