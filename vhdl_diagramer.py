import tkinter as tk
from tkinter import filedialog, messagebox
import re
from dataclasses import dataclass
from typing import List, Dict, Tuple, Set
import math

@dataclass
class Port:
    name: str
    direction: str  # IN, OUT, INOUT
    signal: str

@dataclass
class Instance:
    name: str
    entity: str
    ports: List[Port]
    x: float = 0
    y: float = 0
    width: float = 0
    height: float = 0

class VHDLParser:
    def __init__(self, vhdl_text: str):
        self.text = vhdl_text
        self.instances: List[Instance] = []
    
    def parse(self):
        # Find all instance blocks more carefully
        # Match: instance_name : ENTITY work.entity_name [GENERIC MAP (...)] PORT MAP (...)
        instance_pattern = r'(\w+)\s*:\s*ENTITY\s+work\.(\w+)(.*?)PORT\s+MAP\s*\((.*?)\)\s*;'
        
        matches = re.finditer(instance_pattern, self.text, re.DOTALL | re.IGNORECASE)
        
        for match in matches:
            inst_name = match.group(1)
            entity_name = match.group(2)
            port_map_text = match.group(4)  # The content inside PORT MAP (...)
            
            print(f"\n=== Parsing Instance: {inst_name} ===")
            print(f"Entity: {entity_name}")
            print(f"Raw PORT MAP content:\n{port_map_text}")
            
            ports = self._parse_port_map(port_map_text)
            
            print(f"Parsed {len(ports)} ports:")
            for port in ports:
                print(f"  - {port.name} ({port.direction}) => {port.signal}")
            
            self.instances.append(Instance(
                name=inst_name,
                entity=entity_name,
                ports=ports
            ))
    
    def _parse_port_map(self, port_map_text: str) -> List[Port]:
        ports = []
        # Remove comments (-- to end of line)
        port_map_text = re.sub(r'--.*?(\n|$)', '\n', port_map_text)
        # Split by comma, but not inside parentheses
        port_entries = re.split(r',(?![^()]*\))', port_map_text)
        
        print(f"Split into {len(port_entries)} entries:")
        
        for i, entry in enumerate(port_entries):
            entry = entry.strip()
            print(f"  Entry {i}: '{entry}'")
            
            if not entry or '=>' not in entry:
                print(f"    -> Skipped (no '=>')")
                continue
            
            # Format: port_name => signal_name
            parts = entry.split('=>')
            if len(parts) == 2:
                port_name = parts[0].strip()
                signal_name = parts[1].strip()
                # Clean up signal name (remove trailing semicolons, parentheses, whitespace)
                signal_name = re.sub(r'[;)\s]+', '', signal_name)
                
                print(f"    -> Port: '{port_name}' => Signal: '{signal_name}'")
                
                # Guess direction based on common patterns
                direction = self._guess_direction(port_name, signal_name)
                print(f"    -> Direction: {direction}")
                
                ports.append(Port(
                    name=port_name,
                    direction=direction,
                    signal=signal_name
                ))
        
        return ports
    
    def _guess_direction(self, port_name: str, signal_name: str) -> str:
        port_lower = port_name.lower()
        
        # Common output patterns
        if any(x in port_lower for x in ['out', 'result', 'data_out', 'dout', 'do']):
            return 'OUT'
        # Common input patterns
        elif any(x in port_lower for x in ['in', 'data_in', 'din', 'di', 'clk', 'rstn', 'aresetn']):
            return 'IN'
        
        return 'INOUT'

class DiagramCanvas(tk.Canvas):
    def __init__(self, parent, instances: List[Instance], **kwargs):
        super().__init__(parent, **kwargs)
        self.instances = instances
        self.port_height = 18
        self.min_block_width = 180
        self.padding = 15
        self.bind("<MouseWheel>", self.on_mousewheel)
        self.bind("<Button-4>", self.on_mousewheel)
        self.bind("<Button-5>", self.on_mousewheel)
        self.bind("<Button-1>", self.on_click)
        self.bind("<B1-Motion>", self.on_drag)
        self.bind("<Motion>", self.on_motion)
        self.bind("<Leave>", self.on_leave)
        self.pan_data = None
        self.highlight_instance = None
        self.connection_cache = {}
        self.highlight_connection = None
        self.lines = []  # Store line info for hit detection
    
    def on_mousewheel(self, event):
        scale = 1.1 if event.num == 5 or event.delta < 0 else 0.9
        self.scale("all", event.x, event.y, scale, scale)
    
    def on_click(self, event):
        self.pan_data = (event.x, event.y)
    
    def on_drag(self, event):
        if self.pan_data:
            dx = event.x - self.pan_data[0]
            dy = event.y - self.pan_data[1]
            self.scan_dragto(event.x - self.pan_data[0], event.y - self.pan_data[1], gain=1)
            self.pan_data = (event.x, event.y)
    
    def on_motion(self, event):
        # Highlight instance on hover
        for inst in self.instances:
            if (inst.x <= event.x <= inst.x + inst.width and
                inst.y <= event.y <= inst.y + inst.height):
                if self.highlight_instance != inst.name:
                    self.highlight_instance = inst.name
                    self.highlight_connection = None
                    self.draw()
                return
        
        # Check if hovering over a line
        for line_info in self.lines:
            src_inst, src_port, dst_inst, dst_port = line_info
            if self.is_point_near_line(event.x, event.y, src_inst, src_port, dst_inst, dst_port, tolerance=10):
                connection_key = (src_inst.name, src_port.name, dst_inst.name, dst_port.name)
                if self.highlight_connection != connection_key:
                    self.highlight_connection = connection_key
                    self.highlight_instance = None
                    self.draw()
                return
        
        if self.highlight_instance is not None or self.highlight_connection is not None:
            self.highlight_instance = None
            self.highlight_connection = None
            self.draw()
    
    def on_leave(self, event):
        """Reset highlights when mouse leaves canvas"""
        if self.highlight_instance is not None or self.highlight_connection is not None:
            self.highlight_instance = None
            self.highlight_connection = None
            self.draw()
    
    def is_point_near_line(self, px, py, src_inst, src_port, dst_inst, dst_port, tolerance=5):
        """Check if point (px, py) is near the line connecting src to dst"""
        src_out_ports = [p for p in src_inst.ports if p.direction == 'OUT']
        src_port_idx = src_out_ports.index(src_port) if src_port in src_out_ports else 0
        src_y = src_inst.y + 50 + src_port_idx * self.port_height
        src_x = src_inst.x + src_inst.width
        
        dst_in_ports = [p for p in dst_inst.ports if p.direction == 'IN']
        dst_port_idx = dst_in_ports.index(dst_port) if dst_port in dst_in_ports else 0
        dst_y = dst_inst.y + 50 + dst_port_idx * self.port_height
        dst_x = dst_inst.x
        
        offset_x = 20 + src_port_idx * 5
        mid_x = src_x + offset_x
        
        # Check segments: horizontal1, vertical, horizontal2
        segments = [
            ((src_x, src_y), (mid_x, src_y)),
            ((mid_x, src_y), (mid_x, dst_y)),
            ((mid_x, dst_y), (dst_x, dst_y))
        ]
        
        for (x1, y1), (x2, y2) in segments:
            if self.distance_point_to_segment(px, py, x1, y1, x2, y2) < tolerance:
                return True
        return False
    
    def distance_point_to_segment(self, px, py, x1, y1, x2, y2):
        """Calculate perpendicular distance from point to line segment"""
        dx = x2 - x1
        dy = y2 - y1
        if dx == 0 and dy == 0:
            return ((px - x1)**2 + (py - y1)**2)**0.5
        
        t = max(0, min(1, ((px - x1) * dx + (py - y1) * dy) / (dx**2 + dy**2)))
        closest_x = x1 + t * dx
        closest_y = y1 + t * dy
        return ((px - closest_x)**2 + (py - closest_y)**2)**0.5
    
    def highlight_unconnected_input(self, inst: Instance, port: Port):
        """Draw a red circle on unconnected input ports"""
        in_ports = [p for p in inst.ports if p.direction == 'IN']
        port_idx = in_ports.index(port) if port in in_ports else 0
        py = inst.y + 50 + port_idx * self.port_height
        px = inst.x
        
        # Draw red warning circle around the port
        self.create_oval(px - 10, py - 10, px + 10, py + 10, 
                        outline='#F44336', width=2, fill='')
    
    def calculate_block_size(self, inst: Instance) -> Tuple[float, float]:
        """Calculate block size based on number of ports"""
        in_ports = [p for p in inst.ports if p.direction == 'IN']
        out_ports = [p for p in inst.ports if p.direction == 'OUT']
        
        max_ports = max(len(in_ports), len(out_ports))
        height = max(80, max_ports * self.port_height + self.padding * 2 + 40)
        
        # Calculate width based on longest port name (use 8 pixels per character for better fit)
        max_port_name_len = max([len(p.name) for p in inst.ports], default=0)
        # Add extra space for both sides and padding
        width = max(self.min_block_width, max_port_name_len * 8 + self.padding * 4 + 40)
        
        return width, height
    
    def arrange_grid(self):
        """Arrange instances in a grid layout"""
        # Calculate sizes first
        for inst in self.instances:
            inst.width, inst.height = self.calculate_block_size(inst)
        
        # Arrange in grid
        cols = math.ceil(math.sqrt(len(self.instances)))
        max_width = 0
        row_heights = {}
        
        for i, inst in enumerate(self.instances):
            row = i // cols
            col = i % cols
            
            if row not in row_heights:
                row_heights[row] = 0
            row_heights[row] = max(row_heights[row], inst.height)
            max_width = max(max_width, inst.width)
        
        y_offset = 50
        for i, inst in enumerate(self.instances):
            row = i // cols
            col = i % cols
            
            inst.x = col * (max_width + 150) + 50
            inst.y = y_offset + sum(row_heights.get(r, 0) + 100 for r in range(row))
    
    def build_connection_map(self) -> Dict[str, Tuple[Instance, Port]]:
        """Build a map of signal names to their source (output) port"""
        signal_map = {}
        for inst in self.instances:
            for port in inst.ports:
                if port.direction == 'OUT':
                    signal_map[port.signal] = (inst, port)
        return signal_map
    
    def draw(self):
        self.delete("all")
        self.arrange_grid()
        self.lines = []  # Reset lines list
        
        # Draw connections first (behind blocks)
        signal_map = self.build_connection_map()
        self.draw_connections(signal_map)
        
        # Draw instances on top
        for inst in self.instances:
            self.draw_instance(inst)
    
    def draw_connections(self, signal_map: Dict[str, Tuple[Instance, Port]]):
        """Draw lines connecting output ports to input ports"""
        drawn_connections = set()
        for inst in self.instances:
            for port in inst.ports:
                if port.direction == 'IN':
                    # Find the source of this signal
                    if port.signal in signal_map:
                        source_inst, source_port = signal_map[port.signal]
                        conn_key = (source_inst.name, source_port.name, inst.name, port.name)
                        if conn_key not in drawn_connections:
                            self.draw_connection_line(source_inst, source_port, inst, port)
                            drawn_connections.add(conn_key)
                    else:
                        # Signal not found - highlight port as unconnected
                        self.highlight_unconnected_input(inst, port)
    
    def draw_connection_line(self, src_inst: Instance, src_port: Port, 
                            dst_inst: Instance, dst_port: Port):
        """Draw a line with 90-degree angles from source output to destination input"""
        # Get port positions - these are the exact pin locations
        src_out_ports = [p for p in src_inst.ports if p.direction == 'OUT']
        src_port_idx = src_out_ports.index(src_port) if src_port in src_out_ports else 0
        src_y = src_inst.y + 50 + src_port_idx * self.port_height
        src_x = src_inst.x + src_inst.width
        
        dst_in_ports = [p for p in dst_inst.ports if p.direction == 'IN']
        dst_port_idx = dst_in_ports.index(dst_port) if dst_port in dst_in_ports else 0
        dst_y = dst_inst.y + 50 + dst_port_idx * self.port_height
        dst_x = dst_inst.x
        
        # Calculate horizontal spacing to avoid overlaps - offset based on port index
        offset_x = 20 + src_port_idx * 5
        mid_x = src_x + offset_x
        
        # Check if this connection is highlighted
        is_highlighted = (self.highlight_connection == 
                         (src_inst.name, src_port.name, dst_inst.name, dst_port.name))
        
        color = '#FF6F00' if is_highlighted else '#4CAF50'
        width = 3 if is_highlighted else 1.5
        
        # Path: horizontal out from source -> vertical -> horizontal into dest
        self.create_line(src_x, src_y, mid_x, src_y, mid_x, dst_y, dst_x, dst_y,
                        fill=color, width=width)
        
        # Store line info for hit detection
        self.lines.append((src_inst, src_port, dst_inst, dst_port))
    
    def draw_instance(self, inst: Instance):
        x, y = inst.x, inst.y
        w, h = inst.width, inst.height
        
        # Draw block with shadow effect
        self.create_rectangle(x + 2, y + 2, x + w + 2, y + h + 2,
                             fill='#ddd', outline='')
        
        # Draw main block
        color = '#fff9e6' if inst.name == self.highlight_instance else '#e8f4f8'
        self.create_rectangle(x, y, x + w, y + h,
                             fill=color, outline='black', width=2)
        
        # Title
        self.create_text(x + w/2, y + 12,
                        text=inst.name, font=("Arial", 10, "bold"), fill='black')
        self.create_text(x + w/2, y + 26,
                        text=f"({inst.entity})", font=("Arial", 7), fill='gray')
        
        # Separator line
        self.create_line(x, y + 35, x + w, y + 35, fill='#ccc', width=1)
        
        # Separate ports by direction
        in_ports = [p for p in inst.ports if p.direction == 'IN']
        out_ports = [p for p in inst.ports if p.direction == 'OUT']
        
        # Draw input ports (left side)
        for i, port in enumerate(in_ports):
            py = y + 50 + i * self.port_height
            self.create_oval(x - 6, py - 3, x, py + 3, fill='#2196F3', outline='#1565C0')
            
            # Truncate long names
            port_name = port.name if len(port.name) < 20 else port.name[:17] + '...'
            self.create_text(x + 8, py, text=port_name, font=("Arial", 8),
                           anchor='w', fill='#1565C0')
        
        # Draw output ports (right side)
        for i, port in enumerate(out_ports):
            py = y + 50 + i * self.port_height
            self.create_oval(x + w - 6, py - 3, x + w, py + 3, fill='#F44336', outline='#C62828')
            
            # Truncate long names
            port_name = port.name if len(port.name) < 20 else port.name[:17] + '...'
            self.create_text(x + w - 8, py, text=port_name,
                           font=("Arial", 8), anchor='e', fill='#F44336')

class VHDLDiagramApp:
    def __init__(self, root):
        self.root = root
        self.root.title("VHDL Instance Diagram Generator")
        self.root.geometry("1400x900")
        
        self.instances: List[Instance] = []
        self.canvas = None
        
        # Top frame for buttons
        top_frame = tk.Frame(root, bg='#f0f0f0', height=60)
        top_frame.pack(fill=tk.X, padx=5, pady=5)
        top_frame.pack_propagate(False)
        
        btn_frame = tk.Frame(top_frame, bg='#f0f0f0')
        btn_frame.pack(side=tk.LEFT, padx=5)
        
        tk.Button(btn_frame, text="Load VHDL File", command=self.load_file,
                 bg='#2196F3', fg='white', padx=10, pady=5).pack(side=tk.LEFT, padx=3)
        tk.Button(btn_frame, text="Parse Text", command=self.parse_text,
                 bg='#4CAF50', fg='white', padx=10, pady=5).pack(side=tk.LEFT, padx=3)
        
        info_frame = tk.Frame(top_frame, bg='#f0f0f0')
        info_frame.pack(side=tk.RIGHT, padx=5)
        
        info_label = tk.Label(info_frame, 
                             text="🔍 Scroll: Zoom | 🖱 Drag: Pan | 🔵 Blue: Inputs | 🔴 Red: Outputs",
                             font=("Arial", 9), bg='#f0f0f0')
        info_label.pack()
        
        # Canvas
        self.canvas = DiagramCanvas(root, self.instances, bg='white', cursor="hand2")
        self.canvas.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
    
    def load_file(self):
        file_path = filedialog.askopenfilename(filetypes=[("VHDL files", "*.vhdl *.vhd"), ("All files", "*.*")])
        if file_path:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                vhdl_text = f.read()
            self.parse_vhdl(vhdl_text)
    
    def parse_text(self):
        text_window = tk.Toplevel(self.root)
        text_window.title("Paste VHDL Code")
        text_window.geometry("600x400")
        
        frame = tk.Frame(text_window)
        frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        text_widget = tk.Text(frame, font=("Courier", 9))
        text_widget.pack(fill=tk.BOTH, expand=True)
        
        def on_parse():
            vhdl_text = text_widget.get(1.0, tk.END)
            self.parse_vhdl(vhdl_text)
            text_window.destroy()
        
        tk.Button(text_window, text="Parse", command=on_parse, bg='#4CAF50', 
                 fg='white', padx=20, pady=5).pack(pady=5)
    
    def parse_vhdl(self, vhdl_text: str):
        parser = VHDLParser(vhdl_text)
        parser.parse()
        self.instances = parser.instances
        
        if not self.instances:
            messagebox.showwarning("No Instances", "No instances found in the VHDL code.")
            return
        
        self.canvas.instances = self.instances
        self.canvas.draw()
        messagebox.showinfo("Success", f"Found {len(self.instances)} instances.")

if __name__ == "__main__":
    root = tk.Tk()
    app = VHDLDiagramApp(root)
    root.mainloop()