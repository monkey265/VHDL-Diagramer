import tkinter as tk

from typing import List, Dict, Optional, Tuple, Set

import math, heapq

from tkinter import filedialog, messagebox


class DiagramCanvas(tk.Canvas):
    def __init__(self, parent, instances: List[Instance], signals: Dict[str, str],
                 variables: Dict[str, str], constants: Dict[str, str], **kwargs):
        super().__init__(parent, **kwargs)
        self.instances = instances
        self.signals = signals
        self.variables = variables
        self.constants = constants
        self.port_height = 18
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

        self.bind("<MouseWheel>", self.on_mousewheel, add="+")
        self.bind("<Button-4>", self.on_mousewheel, add="+")
        self.bind("<Button-5>", self.on_mousewheel, add="+")
        self.bind("<Button-1>", self.on_click)
        self.bind("<B1-Motion>", self.on_drag)
        self.bind("<Motion>", self.on_motion)
        self.bind("<Leave>", self.on_leave)

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
            else: return "break"
        else:
            return "break"
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
        self.scale("all", cx, cy, scale, scale)
        self.configure(scrollregion=self.bbox("all"))
        return "break"

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
        y_offset = 50
        for i, inst in enumerate(self.instances):
            row = i // cols
            col = i % cols
            inst.x = col * (max_width + 150) + 50
            inst.y = y_offset + sum(row_heights.get(r, 0) + 100 for r in range(row))

    def build_grid_occupancy(self, blocks: List[Tuple[int,int,int,int]], 
                            xmin: int, xmax: int, ymin: int, ymax: int) -> Dict[Tuple[int,int], bool]:
        """Build grid of which cells are blocked (True = blocked, False = free)."""
        occupancy = {}
        margin = 30
        
        for gx in range(xmin, xmax + 1, GRID_STEP):
            for gy in range(ymin, ymax + 1, GRID_STEP):
                cell = (gx, gy)
                blocked = False
                
                for (bx, by, bw, bh) in blocks:
                    if (bx - margin) <= gx <= (bx + bw + margin) and \
                       (by - margin) <= gy <= (by + bh + margin):
                        blocked = True
                        break
                
                occupancy[cell] = blocked
        
        return occupancy

    def astar_path(self, start: Tuple[int,int], goal: Tuple[int,int], 
                   occupancy: Dict[Tuple[int,int], bool],
                   wire_occupancy: Dict[Tuple[int,int], Set[str]],
                   signal: str,
                   xmin: int, xmax: int, ymin: int, ymax: int) -> Optional[List[Tuple[int,int]]]:
        """A* pathfinding on grid."""
        def heuristic(a, b):
            return abs(a[0] - b[0]) + abs(a[1] - b[1])
        
        def cost(cell, sig):
            if occupancy.get(cell, True):
                return 1000000
            existing_signals = wire_occupancy.get(cell, set())
            if sig in existing_signals:
                return 1
            return 1 + len(existing_signals) * 10
        
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
            
            for nx, ny in [(cx + GRID_STEP, cy), (cx - GRID_STEP, cy), 
                          (cx, cy + GRID_STEP), (cx, cy - GRID_STEP)]:
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
        self.delete("all")
        self.arrange_grid()

        if self.grid_enabled:
            self._draw_grid_background()

        for inst in self.instances:
            self._draw_instance_visual(inst)

        blocks = [(int(inst.x), int(inst.y), int(inst.width), int(inst.height)) 
                  for inst in self.instances]
        
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
            sy = s.y + 50
            dx = d.x
            dy = d.y + 50
            return -math.hypot(sx - dx, sy - dy)
        connections.sort(key=conn_len)

        if blocks:
            xmin = min(b[0] for b in blocks) - 300
            xmax = max(b[0] + b[2] for b in blocks) + 300
            ymin = min(b[1] for b in blocks) - 300
            ymax = max(b[1] + b[3] for b in blocks) + 300
        else:
            xmin, xmax, ymin, ymax = 0, 2000, 0, 2000

        xmin = (xmin // GRID_STEP) * GRID_STEP
        xmax = ((xmax // GRID_STEP) + 1) * GRID_STEP
        ymin = (ymin // GRID_STEP) * GRID_STEP
        ymax = ((ymax // GRID_STEP) + 1) * GRID_STEP

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
            src_py = int(src_inst.y + 50 + sidx * self.port_height)

            dst_ins = [p for p in dst_inst.ports if p.direction in ('IN','INOUT')]
            try:
                didx = dst_ins.index(dst_port)
            except ValueError:
                didx = 0
            dst_px = int(dst_inst.x)
            dst_py = int(dst_inst.y + 50 + didx * self.port_height)

            start_grid = ((src_px // GRID_STEP) * GRID_STEP, (src_py // GRID_STEP) * GRID_STEP)
            goal_grid = ((dst_px // GRID_STEP) * GRID_STEP, (dst_py // GRID_STEP) * GRID_STEP)
            
            if occupancy.get(start_grid, True):
                found = False
                for dx, dy in [(GRID_STEP, 0), (-GRID_STEP, 0), (0, GRID_STEP), (0, -GRID_STEP),
                               (GRID_STEP, GRID_STEP), (-GRID_STEP, -GRID_STEP), 
                               (GRID_STEP, -GRID_STEP), (-GRID_STEP, GRID_STEP)]:
                    test_cell = (start_grid[0] + dx, start_grid[1] + dy)
                    if not occupancy.get(test_cell, True):
                        start_grid = test_cell
                        found = True
                        break
                
                if not found:
                    for dist in [2, 3, 4, 5]:
                        for dx in range(-dist * GRID_STEP, (dist + 1) * GRID_STEP, GRID_STEP):
                            for dy in range(-dist * GRID_STEP, (dist + 1) * GRID_STEP, GRID_STEP):
                                test_cell = (start_grid[0] + dx, start_grid[1] + dy)
                                if not occupancy.get(test_cell, True):
                                    start_grid = test_cell
                                    found = True
                                    break
                            if found:
                                break
                        if found:
                            break
            
            if occupancy.get(goal_grid, True):
                found = False
                for dx, dy in [(GRID_STEP, 0), (-GRID_STEP, 0), (0, GRID_STEP), (0, -GRID_STEP),
                               (GRID_STEP, GRID_STEP), (-GRID_STEP, -GRID_STEP), 
                               (GRID_STEP, -GRID_STEP), (-GRID_STEP, GRID_STEP)]:
                    test_cell = (goal_grid[0] + dx, goal_grid[1] + dy)
                    if not occupancy.get(test_cell, True):
                        goal_grid = test_cell
                        found = True
                        break
                
                if not found:
                    for dist in [2, 3, 4, 5]:
                        for dx in range(-dist * GRID_STEP, (dist + 1) * GRID_STEP, GRID_STEP):
                            for dy in range(-dist * GRID_STEP, (dist + 1) * GRID_STEP, GRID_STEP):
                                test_cell = (goal_grid[0] + dx, goal_grid[1] + dy)
                                if not occupancy.get(test_cell, True):
                                    goal_grid = test_cell
                                    found = True
                                    break
                            if found:
                                break
                        if found:
                            break

            path = self.astar_path(start_grid, goal_grid, occupancy, wire_occupancy, 
                                  src_port.signal, xmin, xmax, ymin, ymax)

            if path is None:
                mid_x = (src_px + dst_px) // 2
                path = [start_grid, ((mid_x // GRID_STEP) * GRID_STEP, start_grid[1]), 
                       ((mid_x // GRID_STEP) * GRID_STEP, goal_grid[1]), goal_grid]

            full_pts = [(src_px, src_py)]
            for p in path:
                full_pts.append(p)
            full_pts.append((dst_px, dst_py))
            compressed = compress_polyline(full_pts)

            segments: List[Tuple[Tuple[int,int], Tuple[int,int]]] = []
            for i in range(len(compressed) - 1):
                segments.append((compressed[i], compressed[i+1]))

            self.lines_meta.append((src_inst, src_port, dst_inst, dst_port, segments))
            
            for cell in path:
                if cell not in wire_occupancy:
                    wire_occupancy[cell] = set()
                wire_occupancy[cell].add(src_port.signal)

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
                               font=("Arial", 9, "bold"), fill='white')
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
                                   font=("Arial", 7, "bold"), fill='white', tags='signal_label')

        self.configure(scrollregion=self.bbox("all"))

    def _draw_grid_background(self):
        try:
            bbox = self.bbox("all")
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
        self.create_text(x + w/2, y + 12, text=inst.name, font=("Arial", 10, "bold"), fill='black')
        self.create_text(x + w/2, y + 26, text=f"({inst.entity})", font=("Arial", 7), fill='gray')
        self.create_line(x, y + 35, x + w, y + 35, fill='#ccc', width=1)
        in_ports = [p for p in inst.ports if p.direction in ('IN','INOUT')]
        out_ports = [p for p in inst.ports if p.direction in ('OUT','INOUT')]
        for i, port in enumerate(in_ports):
            py = y + 50 + i * self.port_height
            self.create_oval(x - 6, py - 3, x, py + 3, fill='#2196F3', outline='#1565C0')
            pname = port.name if len(port.name) < 20 else port.name[:17] + '...'
            self.create_text(x + 8, py, text=pname, font=("Arial", 8), anchor='w', fill='#1565C0')
        for i, port in enumerate(out_ports):
            py = y + 50 + i * self.port_height
            self.create_oval(x + w - 6, py - 3, x + w, py + 3, fill='#F44336', outline='#C62828')
            pname = port.name if len(port.name) < 20 else port.name[:17] + '...'
            self.create_text(x + w - 8, py, text=pname, font=("Arial", 8), anchor='e', fill='#F44336')

    def _draw_segments(self, segments: List[Tuple[Tuple[int,int],Tuple[int,int]]], signal_name: str, highlighted: bool):
        color = '#FF6F00' if highlighted else '#4CAF50'
        width = 3 if highlighted else 1.8
        pts: List[int] = []
        for (x1, y1), (x2, y2) in segments:
            if not pts:
                pts.extend([x1, y1])
            pts.extend([x2, y2])
        self.create_line(*pts, fill=color, width=width, smooth=False, capstyle=tk.ROUND)

    def _highlight_unconnected_input(self, inst: Instance, port: Port):
        in_ports = [p for p in inst.ports if p.direction in ('IN','INOUT')]
        try:
            idx = in_ports.index(port)
        except ValueError:
            idx = 0
        py = inst.y + 50 + idx * self.port_height
        px = inst.x
        self.create_oval(px - 10, py - 10, px + 10, py + 10, outline='#F44336', width=2, fill='')
