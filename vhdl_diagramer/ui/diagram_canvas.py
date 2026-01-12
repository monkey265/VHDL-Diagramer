import tkinter as tk
import sys

from typing import List, Dict, Optional, Tuple, Set

import math

import heapq

from tkinter import filedialog, messagebox

from vhdl_diagramer.models import Instance, Port

from vhdl_diagramer.config import MIN_BLOCK_WIDTH, MIN_BLOCK_HEIGHT, GRID_OPTIONS, DEFAULT_GRID_LABEL, GRID_STEP

from vhdl_diagramer.utils import compress_polyline



class DiagramCanvas(tk.Canvas):
    def __init__(self, parent, instances: List[Instance], signals: Dict[str, str],
                 variables: Dict[str, str], constants: Dict[str, str], **kwargs):
        super().__init__(parent, **kwargs)
        self.instances = instances
        self.signals = signals
        self.variables = variables
        self.constants = constants
        self.port_height = 20
        self.padding = 15
        self.min_block_width = MIN_BLOCK_WIDTH
        self.min_block_height = MIN_BLOCK_HEIGHT

        self.grid_enabled = False
        self.grid_label = DEFAULT_GRID_LABEL
        self.grid_step = GRID_OPTIONS[self.grid_label]
        self.show_signal_names = True  # Toggle for signal name labels on wires

        self.current_scale = 1.0
        self.scale_min = 0.2
        self.scale_max = 5.0

        self.bind('<MouseWheel>', self.on_mousewheel, add='+')
        self.bind('<Button-4>', self.on_mousewheel, add='+')
        self.bind('<Button-5>', self.on_mousewheel, add='+')
        self.bind('<Button-1>', self.on_click)
        self.bind('<B1-Motion>', self.on_drag)
        self.bind('<Motion>', self.on_motion)
        self.bind('<Leave>', self.on_leave)

        self.scan_mark_x = None
        self.scan_mark_y = None
        self.highlight_instance: Optional[str] = None
        self.highlight_connection: Optional[Tuple[str,str,str,str]] = None
        self.highlight_signal: Optional[str] = None
        self.lines_meta: List[Tuple[Instance,Port,Instance,Port,List[Tuple[Tuple[int,int],Tuple[int,int]]]]] = []

    def set_grid_label(self, label: str):
        if label in GRID_OPTIONS:
            self.grid_label = label
            self.grid_step = GRID_OPTIONS[label]
            self.draw()

    def toggle_grid(self):
        self.grid_enabled = not self.grid_enabled
        self.draw()
    
    def toggle_signal_names(self):
        self.show_signal_names = not self.show_signal_names
        self.draw()

    def on_mousewheel(self, event):
        if hasattr(event, 'delta') and event.delta != 0:
            scale = 1.1 if event.delta > 0 else 0.9
        elif hasattr(event, 'num'):
            if event.num == 4: scale = 1.1
            elif event.num == 5: scale = 0.9
            else: return 'break'
        else:
            return 'break'
        new_scale = self.current_scale * scale
        if new_scale < self.scale_min:
            scale = self.scale_min / self.current_scale
            self.current_scale = self.scale_min
        elif new_scale > self.scale_max:
            scale = self.scale_max / self.current_scale
            self.current_scale = self.scale_max
        else:
            self.current_scale = new_scale
        try:
            cx = self.canvasx(event.x); cy = self.canvasy(event.y)
        except Exception:
            cx, cy = event.x, event.y
        self.scale('all', cx, cy, scale, scale)
        self.configure(scrollregion=self.bbox('all'))
        return 'break'

    def on_click(self, event):
        self.scan_mark(event.x, event.y)
        self.scan_mark_x = event.x
        self.scan_mark_y = event.y
        
        # Check if clicked on a wire/signal
        cx = self.canvasx(event.x)
        cy = self.canvasy(event.y)
        for src_inst, src_port, dst_inst, dst_port, segments in self.lines_meta:
            if self.is_point_near_segments(cx, cy, segments, tolerance=8):
                self.highlight_signal = src_port.signal
                self.draw()
                return
        
        # Clicked on nothing, clear highlight
        self.highlight_signal = None
        self.draw()

    def on_drag(self, event):
        if self.scan_mark_x is not None and self.scan_mark_y is not None:
            self.scan_dragto(event.x, event.y, gain=1)
            self.scan_mark_x = event.x
            self.scan_mark_y = event.y

    def on_motion(self, event):
        cx = self.canvasx(event.x)
        cy = self.canvasy(event.y)
        for inst in self.instances:
            if inst.x <= cx <= inst.x + inst.width and inst.y <= cy <= inst.y + inst.height:
                if self.highlight_instance != inst.name:
                    self.highlight_instance = inst.name
                    self.highlight_connection = None
                    self.draw()
                return
        for src_inst, src_port, dst_inst, dst_port, segments in self.lines_meta:
            if self.is_point_near_segments(cx, cy, segments, tolerance=8):
                key = (src_inst.name, src_port.name, dst_inst.name, dst_port.name)
                if self.highlight_connection != key:
                    self.highlight_connection = key
                    self.highlight_instance = None
                    self.draw()
                return
        if self.highlight_instance is not None or self.highlight_connection is not None:
            self.highlight_instance = None
            self.highlight_connection = None
            self.draw()

    def on_leave(self, event):
        if self.highlight_instance is not None or self.highlight_connection is not None:
            self.highlight_instance = None
            self.highlight_connection = None
            self.draw()

    def is_point_near_segments(self, px, py, segments, tolerance=5):
        for (x1, y1), (x2, y2) in segments:
            if self.distance_point_to_segment(px, py, x1, y1, x2, y2) <= tolerance:
                return True
        return False

    def distance_point_to_segment(self, px, py, x1, y1, x2, y2):
        dx = x2 - x1
        dy = y2 - y1
        if dx == 0 and dy == 0:
            return math.hypot(px - x1, py - y1)
        t = max(0.0, min(1.0, ((px - x1)*dx + (py - y1)*dy) / (dx*dx + dy*dy)))
        cx = x1 + t*dx
        cy = y1 + t*dy
        return math.hypot(px - cx, py - cy)

    def calculate_block_size(self, inst: Instance) -> Tuple[int,int]:
        in_ports = [p for p in inst.ports if p.direction in ('IN','INOUT')]
        out_ports = [p for p in inst.ports if p.direction in ('OUT','INOUT')]
        max_ports = max(len(in_ports), len(out_ports), 1)
        height = max(self.min_block_height, max_ports * self.port_height + self.padding * 2 + 40)
        max_name_len = max([len(p.name) for p in inst.ports], default=0)
        width = max(self.min_block_width, max_name_len * 8 + self.padding * 4 + 40)
        
        # Snap to grid
        height = math.ceil(height / self.grid_step) * self.grid_step
        width = math.ceil(width / self.grid_step) * self.grid_step
        
        return int(width), int(height)

    def arrange_grid(self):
        for inst in self.instances:
            inst.width, inst.height = self.calculate_block_size(inst)
        if not self.instances:
            return
        cols = math.ceil(math.sqrt(len(self.instances)))
        row_heights = {}
        max_width = 0
        for i, inst in enumerate(self.instances):
            r = i // cols
            row_heights[r] = max(row_heights.get(r, 0), inst.height)
            max_width = max(max_width, inst.width)
        y_offset = 40
        for i, inst in enumerate(self.instances):
            row = i // cols
            col = i % cols
            inst.x = col * (max_width + 150) + 50
            inst.y = y_offset + sum(row_heights.get(r, 0) + 100 for r in range(row))
            
            # Snap to grid
            inst.x = math.ceil(inst.x / self.grid_step) * self.grid_step
            inst.y = math.ceil(inst.y / self.grid_step) * self.grid_step

    def _highlight_unconnected_input(self, inst: Instance, port: Port):
        in_ports = [p for p in inst.ports if p.direction in ('IN','INOUT')]
        try:
            idx = in_ports.index(port)
        except ValueError:
            idx = 0
        py = inst.y + 40 + idx * self.port_height
        px = inst.x
        self.create_oval(px - 10, py - 10, px + 10, py + 10, outline='#F44336', width=2, fill='')

    def build_grid_occupancy(self, blocks: List[Tuple[int,int,int,int]], 
                            xmin: int, xmax: int, ymin: int, ymax: int) -> Dict[Tuple[int,int], bool]:
        '''Build grid of which cells are blocked (True = blocked, False = free).'''
        occupancy = {}
        margin = 10
        
        for gx in range(xmin, xmax + 1, self.grid_step):
            for gy in range(ymin, ymax + 1, self.grid_step):
                cell = (gx, gy)
                blocked = False
                
                for (bx, by, bw, bh) in blocks:
                    if (bx - margin) <= gx <= (bx + bw + margin) and \
                       (by - margin) <= gy <= (by + bh + margin):
                        blocked = True
                        break
                
                occupancy[cell] = blocked
        
        return occupancy

    def _mark_segment_occupancy(self, p1: Tuple[int,int], p2: Tuple[int,int], signal: str, wire_occupancy: Dict[Tuple[int,int], Set[str]]):
        x1, y1 = p1
        x2, y2 = p2
        
        # Horizontal segment
        if y1 == y2:
            start = min(x1, x2)
            end = max(x1, x2)
            for x in range(start, end + self.grid_step, self.grid_step):
                cell = (x, y1)
                if cell not in wire_occupancy:
                    wire_occupancy[cell] = set()
                wire_occupancy[cell].add(signal)
        # Vertical segment
        elif x1 == x2:
            start = min(y1, y2)
            end = max(y1, y2)
            for y in range(start, end + self.grid_step, self.grid_step):
                cell = (x1, y)
                if cell not in wire_occupancy:
                    wire_occupancy[cell] = set()
                wire_occupancy[cell].add(signal)


    def astar_path(self, start: Tuple[int,int], goal: Tuple[int,int], 
                   occupancy: Dict[Tuple[int,int], bool],
                   wire_occupancy: Dict[Tuple[int,int], Set[str]],
                   signal: str,
                   xmin: int, xmax: int, ymin: int, ymax: int) -> Optional[List[Tuple[int,int]]]:
        '''A* pathfinding on grid.'''
        def heuristic(a, b):
            return abs(a[0] - b[0]) + abs(a[1] - b[1])
        
        def cost(cell, sig):
            if occupancy.get(cell, True):
                return 1000000
            existing_signals = wire_occupancy.get(cell, set())
            if sig in existing_signals:
                return 1
            return 1 + len(existing_signals) * 500
        
        open_set = [(heuristic(start, goal), 0, start)]
        came_from = {}
        g_score = {start: 0}
        closed = set()
        
        while open_set:
            _, g, current = heapq.heappop(open_set)
            
            if current in closed:
                continue
            
            if current == goal:
                path = [current]
                while current in came_from:
                    current = came_from[current]
                    path.append(current)
                path.reverse()
                return path
            
            closed.add(current)
            cx, cy = current
            
            for nx, ny in [(cx + self.grid_step, cy), (cx - self.grid_step, cy), 
                          (cx, cy + self.grid_step), (cx, cy - self.grid_step)]:
                if nx < xmin or nx > xmax or ny < ymin or ny > ymax:
                    continue
                
                neighbor = (nx, ny)
                if neighbor in closed:
                    continue
                
                move_cost = cost(neighbor, signal)
                if move_cost >= 1000000:
                    continue
                
                tentative_g = g + move_cost
                
                if neighbor not in g_score or tentative_g < g_score[neighbor]:
                    came_from[neighbor] = current
                    g_score[neighbor] = tentative_g
                    f = tentative_g + heuristic(neighbor, goal)
                    heapq.heappush(open_set, (f, tentative_g, neighbor))
        
        return None

    def draw(self):
        self.delete('all')
        self.arrange_grid()

        if self.grid_enabled:
            self._draw_grid_background()

        for inst in self.instances:
            self._draw_instance_visual(inst)

        blocks = [(int(inst.x), int(inst.y), int(inst.width), int(inst.height)) 
                  for inst in self.instances]
                  
        sys.stderr.write(f"DEBUG: Grid Step: {self.grid_step}\n")
        for inst in self.instances:
            sys.stderr.write(f"DEBUG: Instance {inst.name}: x={inst.x}, y={inst.y}, w={inst.width}, h={inst.height}\n")
        sys.stderr.flush()
        
        producers: Dict[str, Tuple[Instance,Port]] = {}
        for inst in self.instances:
            for p in inst.ports:
                if p.direction in ('OUT','INOUT'):
                    if p.signal not in producers:
                        producers[p.signal] = (inst, p)

        connections: List[Tuple[Instance,Port,Instance,Port]] = []
        for inst in self.instances:
            for p in inst.ports:
                if p.direction in ('IN','INOUT'):
                    if p.signal in producers:
                        src_inst, src_port = producers[p.signal]
                        if src_inst is inst and src_port is p:
                            continue
                        connections.append((src_inst, src_port, inst, p))
                    else:
                        self._highlight_unconnected_input(inst, p)

        def conn_len(item):
            s, d = item[0], item[2]
            sx = s.x + s.width
            sy = s.y + 40
            dx = d.x
            dy = d.y + 40
            return -math.hypot(sx - dx, sy - dy)
        connections.sort(key=conn_len)

        if blocks:
            xmin = min(b[0] for b in blocks) - 300
            xmax = max(b[0] + b[2] for b in blocks) + 300
            ymin = min(b[1] for b in blocks) - 300
            ymax = max(b[1] + b[3] for b in blocks) + 300
        else:
            xmin, xmax, ymin, ymax = 0, 2000, 0, 2000

        xmin = (xmin // self.grid_step) * self.grid_step
        xmax = ((xmax // self.grid_step) + 1) * self.grid_step
        ymin = (ymin // self.grid_step) * self.grid_step
        ymax = ((ymax // self.grid_step) + 1) * self.grid_step

        occupancy = self.build_grid_occupancy(blocks, xmin, xmax, ymin, ymax)
        wire_occupancy: Dict[Tuple[int,int], Set[str]] = {}

        self.lines_meta.clear()
        
        for src_inst, src_port, dst_inst, dst_port in connections:
            src_outs = [p for p in src_inst.ports if p.direction in ('OUT','INOUT')]
            try:
                sidx = src_outs.index(src_port)
            except ValueError:
                sidx = 0
            src_px = int(src_inst.x + src_inst.width)
            src_py = int(src_inst.y + 40 + sidx * self.port_height)

            dst_ins = [p for p in dst_inst.ports if p.direction in ('IN','INOUT')]
            try:
                didx = dst_ins.index(dst_port)
            except ValueError:
                didx = 0
            dst_px = int(dst_inst.x)
            dst_py = int(dst_inst.y + 40 + didx * self.port_height)

            # Force start/goal to be on grid
            start_grid = ((src_px // self.grid_step) * self.grid_step, (src_py // self.grid_step) * self.grid_step)
            goal_grid = ((dst_px // self.grid_step) * self.grid_step, (dst_py // self.grid_step) * self.grid_step)
            
            # Assume source (output) is on RIGHT of instance -> stub moves RIGHT (+step)
            start_stub = (start_grid[0] + self.grid_step, start_grid[1])
            
            # Assume destination (input) is on LEFT of instance -> stub moves LEFT (-step)
            goal_stub = (goal_grid[0] - self.grid_step, goal_grid[1])
            
            # A* from stub to stub
            path = self.astar_path(start_stub, goal_stub, occupancy, wire_occupancy, 
                                  src_port.signal, xmin, xmax, ymin, ymax)

            # Validation
            if src_px % self.grid_step != 0 or src_py % self.grid_step != 0:
                sys.stderr.write(f"WARNING: Source port OFF GRID: ({src_px}, {src_py})\n")
            if dst_px % self.grid_step != 0 or dst_py % self.grid_step != 0:
                sys.stderr.write(f"WARNING: Dest port OFF GRID: ({dst_px}, {dst_py})\n")

            sys.stderr.write(f"DEBUG: {src_port.signal} generation:\n")
            sys.stderr.write(f"  Src Port: ({src_px}, {src_py}) -> Start Grid: {start_grid} -> Stub: {start_stub}\n")
            sys.stderr.write(f"  Dst Port: ({dst_px}, {dst_py}) -> Goal Grid: {goal_grid} -> Stub: {goal_stub}\n")

            if path is None:
                # Fallback: simple manhattan
                mid_x = (start_stub[0] + goal_stub[0]) // 2
                mid_x = (mid_x // self.grid_step) * self.grid_step
                path = [start_stub, (mid_x, start_stub[1]), 
                       (mid_x, goal_stub[1]), goal_stub]
                sys.stderr.write(f"  Path (Fallback): {path}\n")
            else:
                sys.stderr.write(f"  Path (A*): {path}\n")

            # Build a polyline with orthogonal connections at the ends.
            # 1. Start at exact port location
            full_pts = [(src_px, src_py)]
            
            # 2. Move horizontally to the start stub X (y matches port y for now)
            full_pts.append((start_stub[0], src_py))
            
            # 3. Move vertically to start_stub Y (this connects to the A* path start)
            #    If src_py is already on grid, this is redundant but harmless.
            if src_py != start_stub[1]:
                 full_pts.append(start_stub)
            
            # 4. The path itself (includes start_stub and goal_stub)
            full_pts.extend(path)
            
            # 5. Move vertically from goal_stub Y to dst_py
            if path[-1][1] != dst_py:
                full_pts.append((path[-1][0], dst_py))

            # 6. Move horizontally to destination port
            full_pts.append((dst_px, dst_py))
            
            compressed = compress_polyline(full_pts)

            sys.stderr.write(f"DEBUG: signal={src_port.signal}, compressed={compressed}\n")
            sys.stderr.flush()


            segments: List[Tuple[Tuple[int,int], Tuple[int,int]]] = []
            for i in range(len(compressed) - 1):
                segments.append((compressed[i], compressed[i+1]))

            self.lines_meta.append((src_inst, src_port, dst_inst, dst_port, segments))
            
            self.lines_meta.append((src_inst, src_port, dst_inst, dst_port, segments))
            
            for i in range(len(full_pts) - 1):
                p1 = full_pts[i]
                p2 = full_pts[i+1]
                self._mark_segment_occupancy(p1, p2, src_port.signal, wire_occupancy)

        # Draw wires
        for src_inst, src_port, dst_inst, dst_port, segments in self.lines_meta:
            key = (src_inst.name, src_port.name, dst_inst.name, dst_port.name)
            if self.highlight_connection != key and self.highlight_signal != src_port.signal:
                self._draw_segments(segments, src_port.signal, highlighted=False)
        for src_inst, src_port, dst_inst, dst_port, segments in self.lines_meta:
            key = (src_inst.name, src_port.name, dst_inst.name, dst_port.name)
            if self.highlight_connection == key or self.highlight_signal == src_port.signal:
                self._draw_segments(segments, src_port.signal, highlighted=True)
        
        # Draw signal names based on toggle
        if self.highlight_signal:
            all_segments = []
            for src_inst, src_port, dst_inst, dst_port, segments in self.lines_meta:
                if src_port.signal == self.highlight_signal:
                    all_segments.extend(segments)
            
            if all_segments:
                mid_idx = len(all_segments) // 2
                (x1, y1), (x2, y2) = all_segments[mid_idx]
                label_x = (x1 + x2) / 2
                label_y = (y1 + y2) / 2 - 20
                
                self.create_rectangle(label_x - 60, label_y - 12, label_x + 60, label_y + 12,
                                    fill='#FF6F00', outline='#FF6F00')
                self.create_text(label_x, label_y, text=self.highlight_signal, 
                               font=('Arial', 9, 'bold'), fill='white')
        elif self.show_signal_names:
            drawn_signals = set()
            for src_inst, src_port, dst_inst, dst_port, segments in self.lines_meta:
                if src_port.signal not in drawn_signals and segments:
                    drawn_signals.add(src_port.signal)
                    mid_idx = len(segments) // 2
                    (x1, y1), (x2, y2) = segments[mid_idx]
                    label_x = (x1 + x2) / 2
                    label_y = (y1 + y2) / 2 - 12
                    
                    if src_port.signal in self.signals:
                        bg_color = '#4CAF50'
                    elif src_port.signal in self.variables:
                        bg_color = '#9C27B0'
                    elif src_port.signal in self.constants:
                        bg_color = '#FF9800'
                    else:
                        bg_color = '#607D8B'
                    
                    text = src_port.signal
                    if len(text) > 15:
                        text = text[:12] + '...'
                    
                    pad = 4
                    bbox = (label_x - len(text) * 3.5, label_y - 8, 
                           label_x + len(text) * 3.5, label_y + 8)
                    self.create_rectangle(bbox[0] - pad, bbox[1] - pad, bbox[2] + pad, bbox[3] + pad,
                                        fill=bg_color, outline=bg_color, tags='signal_label')
                    self.create_text(label_x, label_y, text=text, 
                                   font=('Arial', 7, 'bold'), fill='white', tags='signal_label')

        self.configure(scrollregion=self.bbox('all'))

    def _draw_grid_background(self):
        try:
            bbox = self.bbox('all')
        except Exception:
            bbox = None
        if bbox:
            x0, y0, x1, y1 = bbox
            left = int(x0) - 200
            top = int(y0) - 200
            right = int(x1) + 200
            bottom = int(y1) + 200
        else:
            left, top, right, bottom = -2000, -2000, 2000, 2000
        step = self.grid_step
        start_x = (left // step) * step
        for gx in range(start_x, right + step, step):
            self.create_line(gx, top, gx, bottom, fill='#f6f6f6')
        start_y = (top // step) * step
        for gy in range(start_y, bottom + step, step):
            self.create_line(left, gy, right, gy, fill='#f6f6f6')

    def _draw_instance_visual(self, inst: Instance):
        x, y, w, h = inst.x, inst.y, inst.width, inst.height
        self.create_rectangle(x+2, y+2, x+w+2, y+h+2, fill='#ddd', outline='')
        color = '#fff9e6' if self.highlight_instance == inst.name else '#e8f4f8'
        self.create_rectangle(x, y, x+w, y+h, fill=color, outline='black', width=2)
        self.create_text(x + w/2, y + 12, text=inst.name, font=('Arial', 10, 'bold'), fill='black')
        self.create_text(x + w/2, y + 26, text=f'({inst.entity})', font=('Arial', 7), fill='gray')
        self.create_line(x, y + 35, x + w, y + 35, fill='#ccc', width=1)
        in_ports = [p for p in inst.ports if p.direction in ('IN','INOUT')]
        out_ports = [p for p in inst.ports if p.direction in ('OUT','INOUT')]
        for i, port in enumerate(in_ports):
            py = y + 40 + i * self.port_height
            self.create_oval(x - 6, py - 3, x, py + 3, fill='#2196F3', outline='#1565C0')
            pname = port.name if len(port.name) < 20 else port.name[:17] + '...'
            self.create_text(x + 8, py, text=pname, font=('Arial', 8), anchor='w', fill='#1565C0')
        for i, port in enumerate(out_ports):
            py = y + 40 + i * self.port_height
            self.create_oval(x + w - 6, py - 3, x + w, py + 3, fill='#F44336', outline='#C62828')
            pname = port.name if len(port.name) < 20 else port.name[:17] + '...'
            self.create_text(x + w - 8, py, text=pname, font=('Arial', 8), anchor='e', fill='#F44336')

    def _draw_segments(self, segments: List[Tuple[Tuple[int,int],Tuple[int,int]]], signal_name: str, highlighted: bool):
        color = '#FF6F00' if highlighted else '#4CAF50'
        width = 3 if highlighted else 1.8
        sys.stderr.write(f"DEBUG: drawing {signal_name}\n")
        for i, ((x1, y1), (x2, y2)) in enumerate(segments):
            sys.stderr.write(f"  segment {i}: ({x1},{y1}) -> ({x2},{y2})\n")
            if x1 % self.grid_step != 0 or y1 % self.grid_step != 0 or x2 % self.grid_step != 0 or y2 % self.grid_step != 0:
                 sys.stderr.write(f"  WARNING: Segment OFF GRID! ({x1},{y1}) -> ({x2},{y2})\n")
            self.create_line(x1, y1, x2, y2, fill=color, width=width, smooth=False, capstyle=tk.ROUND, joinstyle=tk.MITER)
        sys.stderr.flush()

        # Draw junction dots
        # Step 1: Group all segments by signal
        signal_segments: Dict[str, Set[Tuple[int,int,int,int]]] = {}
        port_locations: Set[Tuple[int,int]] = set()
        
        # Collect port locations to avoid drawing dots on top of them
        for inst in self.instances:
            in_ports = [p for p in inst.ports if p.direction in ('IN','INOUT')]
            out_ports = [p for p in inst.ports if p.direction in ('OUT','INOUT')]
            for i, p in enumerate(in_ports):
                px = int(inst.x)
                py = int(inst.y + 40 + i * self.port_height)
                port_locations.add((px, py))
            for i, p in enumerate(out_ports):
                px = int(inst.x + inst.width)
                py = int(inst.y + 40 + i * self.port_height)
                port_locations.add((px, py))

        # Collect unit segments for each signal
        for src_inst, src_port, dst_inst, dst_port, segments in self.lines_meta:
            sig = src_port.signal
            if sig not in signal_segments:
                signal_segments[sig] = set()
            
            for (x1, y1), (x2, y2) in segments:
                if x1 == x2: # Vertical
                    start, end = min(y1, y2), max(y1, y2)
                    for y in range(start, end, self.grid_step):
                        signal_segments[sig].add((x1, y, x1, y + self.grid_step))
                elif y1 == y2: # Horizontal
                    start, end = min(x1, x2), max(x1, x2)
                    for x in range(start, end, self.grid_step):
                        signal_segments[sig].add((x, y1, x + self.grid_step, y1))

        # Step 2: For each signal, count connections at each grid point
        for sig, segments in signal_segments.items():
            point_counts: Dict[Tuple[int,int], int] = {}
            for x1, y1, x2, y2 in segments:
                p1 = (x1, y1)
                p2 = (x2, y2)
                point_counts[p1] = point_counts.get(p1, 0) + 1
                point_counts[p2] = point_counts.get(p2, 0) + 1
            
            # Step 3: Draw dots where count > 2 and not a port
            color = '#4CAF50' # Default
            if sig in self.signals: color = '#4CAF50'
            elif sig in self.variables: color = '#9C27B0'
            elif sig in self.constants: color = '#FF9800'
            elif sig in {'OPEN', 'open'}: color = '#607D8B'
            
            if sig == self.highlight_signal:
                color = '#FF6F00'

            for point, count in point_counts.items():
                if count > 2 and point not in port_locations:
                    r = 3
                    self.create_oval(point[0]-r, point[1]-r, point[0]+r, point[1]+r, fill=color, outline=color)
