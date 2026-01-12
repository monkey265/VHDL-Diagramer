import tkinter as tk
from tkinter import font as tkfont
import sys

from typing import List, Dict, Optional, Tuple, Set

import math

import heapq
from tkinter import filedialog, messagebox, colorchooser, simpledialog, Menu, ttk

from vhdl_diagramer.models import Instance, Port

from vhdl_diagramer import config
import dataclasses
import copy
from vhdl_diagramer.config import MIN_BLOCK_WIDTH, MIN_BLOCK_HEIGHT, GRID_OPTIONS, DEFAULT_GRID_LABEL, GRID_STEP

from vhdl_diagramer.utils import compress_polyline



class DiagramCanvas(tk.Canvas):
    def __init__(self, parent, instances: List[Instance], signals: Dict[str, str],
                 variables: Dict[str, str], constants: Dict[str, str], top_level_pins: List[Port] = [], 
                 assignments: List[Tuple[str, str]] = [], on_update=None, **kwargs):
        super().__init__(parent, **kwargs)
        self.on_update = on_update
        self.instances = instances
        self.signals = signals
        self.variables = variables
        self.constants = constants
        self.top_level_pins = top_level_pins
        self.assignments = assignments
        self.assignments = assignments
        self.show_top_level = True
        self.top_pin_positions: Dict[str, Tuple[int, int]] = {}
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
        self.bind('<ButtonRelease-1>', self.on_release)
        # Panning bindings
        self.bind('<ButtonPress-3>', self.on_right_down)
        self.bind('<B3-Motion>', self.on_right_drag)
        self.bind('<ButtonRelease-3>', self.on_right_up)
        
        self.bind('<B1-Motion>', self.on_drag) # This was self.on_drag, not self.on_motion
        
        # Ensure canvas can take focus for key bindings
        self.config(takefocus=1)
        self.bind('<Button-1>', self.on_click)
        self.bind('<Double-Button-1>', self.on_double_click)
        self.bind('<Motion>', self.on_motion) # Re-added the missing motion bind
        self.bind('<Leave>', self.on_leave)

        self.scan_mark_x = None
        self.scan_mark_y = None
        self.highlight_instance: Optional[str] = None
        self.highlight_connection: Optional[Tuple[str,str,str,str]] = None
        self.highlight_signal: Optional[str] = None
        self.highlight_signal: Optional[str] = None
        self.lines_meta: List[Tuple[Instance,Port,Instance,Port,List[Tuple[Tuple[int,int],Tuple[int,int]]]]] = []

        self.selected_instances: List[Instance] = []
        self.drag_start_x: float = 0
        self.drag_start_y: float = 0
        self.selection_box_id = None
        self.selecting = False
        
        self.drag_offset_map: Dict[Instance, Tuple[float, float]] = {} # Map instance -> (offset_x, offset_y)
        self.drag_pin: Optional[Port] = None
        self.drag_pin_offset_x: float = 0
        self.drag_pin_offset_y: float = 0
        self.pin_colors: Dict[str, str] = {}
        self.drawn_pin_positions: Dict[str, Tuple[int, int]] = {} # Map pin name -> (visual_x, visual_y)
        
        # Undo/Redo
        self.undo_stack: List[Dict] = []
        self.redo_stack: List[Dict] = []
        self._drag_state_snapshot: Optional[Dict] = None
        
        self.resize_handle_active: Optional['Instance'] = None
        self.resizing: bool = False
        self.resize_start_w: int = 0
        self.resize_start_h: int = 0
        
        # Bind keys (defer to after pack or bind to focus)
        # Better to bind to root if possible, or bind to canvas and expect focus.
        # self.focus_set() # Canvas needs focus
        self.bind('<Control-z>', self.undo)
        self.bind('<Control-y>', self.redo)
        # Bind upper case too just in case
        self.bind('<Control-Z>', self.undo)
        self.bind('<Control-Y>', self.redo)



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

    def toggle_top_level(self):
        self.show_top_level = not self.show_top_level
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
            new_scale = self.scale_min
        elif new_scale > self.scale_max:
            new_scale = self.scale_max
        
        # Logical center under mouse
        cx = self.canvasx(event.x) / self.current_scale
        cy = self.canvasy(event.y) / self.current_scale
        
        self.current_scale = new_scale
        self.draw() # Redraw at new scale
        
        # Now adjust scroll to keep (cx, cy) under event.x, event.y
        # New screen pos of cx is cx * scale
        # We need canvasx(event.x) == cx * scale
        
        # This part is tricky with Tkinter's scroll model. 
        # Easier to just center on mouse? Or use scan_dragto logic?
        # Let's rely on update_scrollregion and simple centering for now or assume draw handles it?
        # No, draw just places items. Viewport stays same.
        # If I zoomed in, items got bigger. "canvasx" (screen 0) stays same logical coord? 
        # No, canvasx depends heavily on scroll position.
        
        # Let's keep it simple: Just draw. User can pan.
        # Pro improvement: Adjust view to keep mouse point stable.
        
        self.update_scrollregion()
        return 'break'
    
    def on_double_click(self, event):
        cx = self.canvasx(event.x) / self.current_scale
        cy = self.canvasy(event.y) / self.current_scale
        for inst in self.instances:
            if not inst.visible: continue
            if inst.x <= cx <= inst.x + inst.width and inst.y <= cy <= inst.y + inst.height:
                if inst.is_group:
                    self.toggle_collapse(inst)
                    return

    def on_click(self, event):
        self.focus_set()
        self.scan_mark(event.x, event.y)
        self.scan_mark_x = event.x
        self.scan_mark_y = event.y
        
        cx = self.canvasx(event.x) / self.current_scale
        cy = self.canvasy(event.y) / self.current_scale
        
        if self.resize_handle_active:
             self.resizing = True
             self.resize_start_inst = self.resize_handle_active
             self._drag_state_snapshot = self._capture_state()
             # Store initial offset from corner to handle smooth drag
             self.resize_drag_off_x = cx - (self.resize_start_inst.x + self.resize_start_inst.width)
             self.resize_drag_off_y = cy - (self.resize_start_inst.y + self.resize_start_inst.height)
             return

        # Check for Top Level Pin click - PRIORITY
        # Check for Top Level Pin click - PRIORITY
        if self.show_top_level:
             # Use sensitive Canvas hit detection (screen coordinates)
             cx_screen = self.canvasx(event.x)
             cy_screen = self.canvasy(event.y)
             # Find overlapping items in a small window around click
             items = self.find_overlapping(cx_screen-2, cy_screen-2, cx_screen+2, cy_screen+2)
             for item_id in items:
                 tags = self.gettags(item_id)
                 for tag in tags:
                     if tag.startswith("pin_hitbox:"):
                         pin_name = tag.split(":", 1)[1]
                         target_pin = next((p for p in self.top_level_pins if p.name == pin_name), None)
                         if target_pin:
                             self._drag_state_snapshot = self._capture_state()
                             self.drag_pin = target_pin
                             # Calculate offset based on logically drawn position
                             # cx/cy are logical if we divide by scale? No, find_overlapping uses canvas coords.
                             # But our logic assumes drag_pin_offset is scaled or unscaled?
                             # drag_pin_offset is subtracted from cx in on_drag.
                             # on_drag uses cx/scale.
                             
                             # We need the logical position of the pin.
                             if pin_name in self.drawn_pin_positions:
                                 px, py = self.drawn_pin_positions[pin_name]
                             else:
                                 # Fallback: reverse transform from item coords?
                                 # Or just use mapped position
                                 continue
                             
                             # cx/cy in on_click is currently:
                             cx_logical = self.canvasx(event.x) / self.current_scale
                             cy_logical = self.canvasy(event.y) / self.current_scale
                             
                             self.drag_pin_offset_x = cx_logical - px
                             self.drag_pin_offset_y = cy_logical - py
                             return

        # Check for click on instance (Recursive for nested groups)
        active_instances = self.get_active_instances()
        clicked_inst = None
        for inst in reversed(active_instances):
            if not inst.visible: continue
            if inst.x <= cx <= inst.x + inst.width and inst.y <= cy <= inst.y + inst.height:
                clicked_inst = inst
                break

        
        if clicked_inst:
            # Shift key to add to selection
            if event.state & 0x0001: # Check for Shift (impl dependent, simplified)
                 if clicked_inst in self.selected_instances:
                     self.selected_instances.remove(clicked_inst)
                 else:
                     self.selected_instances.append(clicked_inst)
            else:
                 # If clicked on something not selected, clear and select it
                 if clicked_inst not in self.selected_instances:
                     self.selected_instances = [clicked_inst]
                 # If clicked on something already selected, keep selection for dragging
            
            self._drag_state_snapshot = self._capture_state()
            
            # Calculate offsets for all selected
            self.drag_offset_map = {}
            for inst in self.selected_instances:
                self.drag_offset_map[inst] = (cx - inst.x, cy - inst.y)
                
            self.highlight_instance = clicked_inst.name
            self.draw()
            return
        
        # Clicked on empty space - Start Rubberband or Clear Selection
        if not (event.state & 0x0001): # No shift
            self.selected_instances = []
            
        self.selecting = True
        self.drag_start_x = cx
        self.drag_start_y = cy
        self.selection_box_id = self.create_rectangle(cx, cy, cx, cy, outline='blue', dash=(4, 4))
        self.draw() # To clear highlights



        # Check if clicked on a wire/signal
        for src_inst, src_port, dst_inst, dst_port, segments in self.lines_meta:
            if self.is_point_near_segments(cx, cy, segments, tolerance=8):
                self.highlight_signal = src_port.signal
                self.draw()
                return
        
        # Clicked on nothing, clear highlight
        self.highlight_signal = None
        self.draw()

    def on_drag(self, event):
        cx = self.canvasx(event.x) / self.current_scale
        cy = self.canvasy(event.y) / self.current_scale

        if self.resizing and self.resize_handle_active:
             inst = self.resize_handle_active
             # New width/height
             # Account for offset
             target_w = (cx - self.resize_drag_off_x) - inst.x
             target_h = (cy - self.resize_drag_off_y) - inst.y
             
             # Constraints
             target_w = max(target_w, self.min_block_width)
             target_h = max(target_h, self.min_block_height)
             
             # Group constraints: must be larger than children
             if inst.is_group and not inst.collapsed:
                 # Calculate children bbox
                 if inst.children:
                     bx2 = max(c.x + c.width for c in inst.children)
                     by2 = max(c.y + c.height for c in inst.children)
                     # Need padding
                     target_w = max(target_w, bx2 + 20 - inst.x)
                     target_h = max(target_h, by2 + 20 - inst.y)
                     
             # Snap to grid?
             target_w = round(target_w / self.grid_step) * self.grid_step
             target_h = round(target_h / self.grid_step) * self.grid_step
             
             inst.custom_width = target_w
             inst.custom_height = target_h
             inst.width = target_w
             inst.height = target_h
             
             self.draw(routing=False)
             return

        if self.selecting and self.selection_box_id:
             self.coords(self.selection_box_id, self.drag_start_x, self.drag_start_y, cx, cy)
             return

        if self.selected_instances:
            # Check if any locked
            if any(i.locked for i in self.selected_instances):
                return
            
            for inst in self.selected_instances:
                # Capture old position for delta calculation if needed for children
                old_x, old_y = inst.x, inst.y
                
                off_x, off_y = self.drag_offset_map.get(inst, (0,0))
                new_x = cx - off_x
                new_y = cy - off_y
                
                # Snap to grid
                new_x = round(new_x / self.grid_step) * self.grid_step
                new_y = round(new_y / self.grid_step) * self.grid_step
                
                # Group Containment Logic (Sticky)
                # Instead of hard clamping, we allow visual movement outside.
                # The constraint will be enforced on release with a prompt.
                pass

                    
                inst.x = new_x
                inst.y = new_y
                
                # Move Group Children
                if inst.is_group and inst.children:
                    dx = inst.x - old_x
                    dy = inst.y - old_y
                    if dx != 0 or dy != 0:
                        for child in inst.children:
                            if child not in self.selected_instances:
                                child.x += dx
                                child.y += dy
                            # Update drag map offsets? 
                            # If child is ALSO selected, it will be moved again by loop!
                            # We must be careful.
                            # If child is selected, we should rely on its own move logic?
                            # BUT, the containment constraint logic relies on parent pos.
                            # And parent pos changed.
                            # Standard behavior:
                            # 1. If Parent selected and Child selected: Both move by mouse. Relative pos maintained.
                            # 2. If Parent selected and Child NOT selected: Child must move with Parent.
                            
                            if child not in self.selected_instances:
                                child.x += dx # Wait, I already added dx? Yes.
                                # But if child IS selected, it moves in main loop.
                                # So "if child not in self.selected_instances" check is good.
                                pass
                            else:
                                # Child will move in its own iteration.
                                pass
                                
            self.draw(routing=False)
            return

        if self.drag_pin:
             cx = self.canvasx(event.x) / self.current_scale
             cy = self.canvasy(event.y) / self.current_scale
             
             new_x = cx - self.drag_pin_offset_x
             new_y = cy - self.drag_pin_offset_y
             
             # Snap to grid
             new_x = round(new_x / self.grid_step) * self.grid_step
             new_y = round(new_y / self.grid_step) * self.grid_step
             
             self.top_pin_positions[self.drag_pin.name] = (int(new_x), int(new_y))
             self.draw(routing=False)
             return

        if self.scan_mark_x is not None and self.scan_mark_y is not None:
            self.scan_dragto(event.x, event.y, gain=1)
            self.scan_mark_x = event.x
            self.scan_mark_y = event.y

    def on_release(self, event):
        if self.resizing:
            if self._drag_state_snapshot:
                 self.undo_stack.append(self._drag_state_snapshot)
                 self.redo_stack.clear()
                 if len(self.undo_stack) > 50: self.undo_stack.pop(0)
                 self._drag_state_snapshot = None
            self.resizing = False
            self.draw(routing=True)
            return

        if self.selecting:
             cx = self.canvasx(event.x) / self.current_scale
             cy = self.canvasy(event.y) / self.current_scale
             # Select items in box
             x1, y1 = min(self.drag_start_x, cx), min(self.drag_start_y, cy)
             x2, y2 = max(self.drag_start_x, cx), max(self.drag_start_y, cy)
             
             for inst in self.instances:
                 if not inst.visible: continue
                 # Simple intersection: center of block in box? or full overlap?
                 # Let's say center of block
                 ix = inst.x + inst.width/2
                 iy = inst.y + inst.height/2
                 if x1 <= ix <= x2 and y1 <= iy <= y2:
                      if inst not in self.selected_instances:
                          self.selected_instances.append(inst)
             
             self.delete(self.selection_box_id)
             self.selection_box_id = None
             self.selecting = False
             self.draw()
             return

        if self.selected_instances:
            # Check for drop onto a Group (Add to Group)
            cx = self.canvasx(event.x) / self.current_scale
            cy = self.canvasy(event.y) / self.current_scale
            
            # 1. Detection: Check if any selected item with a parent is now OUTSIDE that parent
            # We process this BEFORE checking for drops onto NEW groups.
            # We group by parent for a better UX.
            out_by_parent: Dict[Instance, List[Instance]] = {}
            for inst in self.selected_instances:
                if inst.parent and inst.parent not in self.selected_instances:
                    parent = inst.parent
                    padding = 10
                    header_h = 40
                    
                    # Bounding box of parent
                    px1 = parent.x + padding
                    py1 = parent.y + padding + (header_h if not parent.collapsed else 0)
                    px2 = parent.x + parent.width - padding
                    py2 = parent.y + parent.height - padding
                    
                    # Check if inst is outside
                    # Condition: is ANY part of the block outside?
                    # Or center? User said "moved out of group". 
                    # Let's use "fully outside" or "mostly outside"? 
                    # "Outside" usually means the center is out or some threshold.
                    # Let's use "mostly out" by checking if center is out.
                    cx_inst = inst.x + inst.width/2
                    cy_inst = inst.y + inst.height/2
                    
                    if not (px1 <= cx_inst <= px2 and py1 <= cy_inst <= py2):
                        if parent not in out_by_parent:
                            out_by_parent[parent] = []
                        out_by_parent[parent].append(inst)

            # Handle removal prompts
            blocks_to_snap_back = []
            for parent, blocks in out_by_parent.items():
                if len(blocks) == 1:
                    msg = f"Remove '{blocks[0].name}' from group '{parent.name}'?"
                else:
                    msg = f"Remove {len(blocks)} blocks from group '{parent.name}'?"
                
                if messagebox.askyesno("Remove from Group", msg):
                    for b in blocks:
                        self.remove_from_group(b)
                else:
                    blocks_to_snap_back.extend(blocks)
            
            # Snap back those that were not removed
            for inst in blocks_to_snap_back:
                parent = inst.parent
                padding = 10
                header_h = 40
                px1 = parent.x + padding
                py1 = parent.y + padding + (header_h if not parent.collapsed else 0)
                px2 = parent.x + parent.width - padding
                py2 = parent.y + parent.height - padding
                
                # Clamp
                if inst.x < px1: inst.x = px1
                if (inst.x + inst.width) > px2: inst.x = px2 - inst.width
                if inst.y < py1: inst.y = py1
                if (inst.y + inst.height) > py2: inst.y = py2 - inst.height
                
                # Double check clamp
                if inst.x < px1: inst.x = px1 # if block wider than parent
                if inst.y < py1: inst.y = py1

            # 2. Check for drop onto a NEW Group (Add to Group)
            target_group = None
            for inst in self.instances:
                if inst not in self.selected_instances and inst.is_group and inst.visible:
                    # Mouse release is simplest.
                    if inst.x <= cx <= inst.x + inst.width and inst.y <= cy <= inst.y + inst.height:
                        target_group = inst
                        break
            
            if target_group:
                # Add to group logic
                if messagebox.askyesno("Add to Group", f"Add {len(self.selected_instances)} items to {target_group.name}?"):
                    self.add_to_group(target_group, self.selected_instances)
                    self.selected_instances = [] # Deselect after adding

            if self._drag_state_snapshot:
                 self.undo_stack.append(self._drag_state_snapshot)
                 self.redo_stack.clear()
                 if len(self.undo_stack) > 50: self.undo_stack.pop(0)
                 self._drag_state_snapshot = None
            
            self.draw(routing=True)

            
        if self.drag_pin:
            if self._drag_state_snapshot:
                 self.undo_stack.append(self._drag_state_snapshot)
                 self.redo_stack.clear()
                 if len(self.undo_stack) > 50: self.undo_stack.pop(0)
                 self._drag_state_snapshot = None

            self.drag_pin = None
            self.draw(routing=True)
            
    def add_to_group(self, group: Instance, instances: List[Instance]):
        # This needs to move instances into group.children
        # AND detect ports needed.
        # It essentially re-runs the "Group Creation" logic but for an existing group.
        
        # 1. Signals connecting these instances to outside (which includes old outside AND group's current outside)
        # 2. Existing internal ports of group might need to be removed if they are now satisfied? 
        #    (No, existing ports are external connections. If we add a block that connects to that port,
        #     we might need to remove the port if it's now fully internal? Or keep it as passthrough?
        #     Usually keep it unless user removes it).
        # 3. New ports for new external connections.
        
        # Simplified: Just find NEW ports needed.
        # User can clean up later in dialog.
        
        suggested_ports = []
        # Pre-fill existing ports
        for p in group.ports:
            suggested_ports.append({'name': p.name, 'direction': p.direction, 'signal': p.signal})
            
        internal_instances = set(group.children + instances)
        
        # Check for new connections
        group_signals = set()
        for inst in internal_instances:
            for p in inst.ports:
                if p.signal: group_signals.add(p.signal)
                
        external_signals = set()
        # Rest of world
        for inst in self.instances:
            if inst == group: continue
            if inst in instances: continue # Should be gone from here later but currently in list
            if not inst.visible: continue
            
            for p in inst.ports:
                if p.signal in group_signals:
                    external_signals.add(p.signal)
        
        top_pin_names = {p.name for p in self.top_level_pins}
        for sig in group_signals:
             if sig in top_pin_names:
                 external_signals.add(sig)
        
        # Add new suggestions
        existing_port_signals = {p['signal'] for p in suggested_ports}
        for sig in external_signals:
            if sig not in existing_port_signals:
                suggested_ports.append({'name': sig, 'direction': 'INOUT', 'signal': sig})
                
        # Open Dialog
        dialog = GroupCreationDialog(self, group.name, suggested_ports)
        if not dialog.result:
            return 
            
        final_name = dialog.result['name']
        final_ports_data = dialog.result['ports']
        
        # Update Group
        group.name = final_name
        group.ports = [Port(name=p['name'], direction=p['direction'], signal=p['signal']) for p in final_ports_data]
        
        # Move instances
        for inst in instances:
            if inst in self.instances:
                self.instances.remove(inst)
            if inst not in group.children:
                group.children.append(inst)
        
        # Recalculate size if collapsed? 
        if group.collapsed:
            self.calculate_block_size(group)
        else:
            # If expanded, we might need to expand bbox?
            # Or just let them be where they are (absolute coords).
            pass
            
        self.draw()

    def on_motion(self, event):
        cx = self.canvasx(event.x) / self.current_scale
        cy = self.canvasy(event.y) / self.current_scale
        
        # Default cursor
        current_cursor = "hand2" if self.selected_instances and not self.selecting else "arrow"
        
        # Check for resize handle and instance highlight
        self.resize_handle_active = None
        active_instances = self.get_active_instances()
        
        # Search from front (topmost) to back
        for inst in reversed(active_instances):
             if not inst.visible: continue
             
             # Hit detection
             if inst.x <= cx <= inst.x + inst.width and inst.y <= cy <= inst.y + inst.height:
                 # 1. Check for resize handle hit (bottom-right 10x10)
                 # Only if selected
                 if inst in self.selected_instances:
                      if (inst.x + inst.width - 10) <= cx <= (inst.x + inst.width) and \
                         (inst.y + inst.height - 10) <= cy <= (inst.y + inst.height):
                          self.resize_handle_active = inst
                          current_cursor = "bottom_right_corner"
                          self.config(cursor=current_cursor)
                          return # Handled
                 
                 # 2. Handle highlighting
                 if self.highlight_instance != inst.name:
                     self.highlight_instance = inst.name
                     self.highlight_connection = None
                     self.draw()
                 
                 self.config(cursor=current_cursor)
                 return # Handled

        # Check for wire/signal highlighting
        for src_inst, src_port, dst_inst, dst_port, segments in self.lines_meta:
            if self.is_point_near_segments(cx, cy, segments, tolerance=8):
                key = (src_inst.name, src_port.name, dst_inst.name, dst_port.name)
                if self.highlight_connection != key:
                    self.highlight_connection = key
                    self.highlight_instance = None
                    self.draw()
                self.config(cursor="hand2")
                return
        
        # If we reached here, nothing is hovered
        if self.highlight_instance is not None or self.highlight_connection is not None:
            self.highlight_instance = None
            self.highlight_connection = None
            self.draw()
        
        self.config(cursor=current_cursor)


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

    def on_right_click(self, event):
        self.focus_set()
        
        cx = self.canvasx(event.x) / self.current_scale
        cy = self.canvasy(event.y) / self.current_scale
        
        clicked_inst: Optional[Instance] = None
        current_active = self.get_active_instances()
        for inst in reversed(current_active):
            if not inst.visible: continue
            if inst.x <= cx <= inst.x + inst.width and inst.y <= cy <= inst.y + inst.height:
                clicked_inst = inst
                break

        
        if clicked_inst:
            m = Menu(self, tearoff=0)
            m.add_command(label="Change Color", command=lambda: self.change_instance_color(clicked_inst))
            m.add_command(label="Reset Color", command=lambda: self.reset_instance_color(clicked_inst))
            m.add_command(label="Change Size", command=lambda: self.change_instance_size(clicked_inst))
            
            m.add_command(label="Reset Ports", command=lambda: self.reset_instance_ports(clicked_inst))
            
            m.add_separator()
            m.add_command(label="Delete Block", command=lambda: self.delete_instance(clicked_inst))
            
            # Port deletions - submenu
            
            # Port deletions - submenu
            port_menu = Menu(m, tearoff=0)
            p_in = [p for p in clicked_inst.ports if p.direction in ('IN','INOUT')]
            p_out = [p for p in clicked_inst.ports if p.direction in ('OUT','INOUT')]
            
            if p_in:
                pi_menu = Menu(port_menu, tearoff=0)
                for p in p_in:
                    pi_menu.add_command(label=p.name, command=lambda p=p: self.delete_port(clicked_inst, p))
                port_menu.add_cascade(label="Delete Input Port", menu=pi_menu)
            
            if p_out:
                po_menu = Menu(port_menu, tearoff=0)
                for p in p_out:
                    po_menu.add_command(label=p.name, command=lambda p=p: self.delete_port(clicked_inst, p))
                port_menu.add_cascade(label="Delete Output Port", menu=po_menu)

            m.add_cascade(label="Delete Ports", menu=port_menu)
            
            m.add_command(label="Edit Font...", command=lambda: self.edit_font(clicked_inst))
            
            if clicked_inst.is_group:
                m.add_separator()
                label = "Expand Group" if clicked_inst.collapsed else "Collapse Group"
                m.add_command(label=label, command=lambda: self.toggle_collapse(clicked_inst))
                m.add_command(label="Ungroup", command=lambda: self.ungroup_selection())
            
            lock_label = "Unlock Position" if clicked_inst.locked else "Lock Position"
            m.add_command(label=lock_label, command=lambda: self.toggle_lock(clicked_inst))
            
            m.tk_popup(event.x_root, event.y_root)
            return

        # Check for right click on Top Level Pin
        if self.show_top_level:
             cx_screen = self.canvasx(event.x)
             cy_screen = self.canvasy(event.y)
             items = self.find_overlapping(cx_screen-2, cy_screen-2, cx_screen+2, cy_screen+2)
             for item_id in items:
                 tags = self.gettags(item_id)
                 for tag in tags:
                     if tag.startswith("pin_hitbox:"):
                         pin_name = tag.split(":", 1)[1]
                         target_pin = next((p for p in self.top_level_pins if p.name == pin_name), None)
                         if target_pin:
                             # Show Menu
                             menu = tk.Menu(self, tearoff=0)
                             menu.add_command(label="Rename Pin", command=lambda p=target_pin: self.rename_pin_dialog(p))
                             menu.add_command(label="Change Color", command=lambda p=target_pin: self.change_pin_color(p))
                             menu.add_command(label="Reset Color", command=lambda p=target_pin: self.reset_pin_color(p))
                             menu.add_separator()
                             menu.add_command(label="Delete Pin", command=lambda p=target_pin: self.delete_pin(p))
                             
                             menu.tk_popup(event.x_root, event.y_root)
                             return

    def change_pin_color(self, pin: Port):
        self.snapshot()
        color = colorchooser.askcolor(title=f"Choose color for {pin.name}")
        if color[1]:
            self.pin_colors[pin.name] = color[1]
            self.draw()

    def reset_pin_color(self, pin: Port):
        self.snapshot()
        if pin.name in self.pin_colors:
            del self.pin_colors[pin.name]
            self.draw()

    def delete_pin(self, pin: Port):
        self.snapshot()
        if messagebox.askyesno("Delete Pin", f"Delete top level pin '{pin.name}'?"):
            if pin in self.top_level_pins:
                self.top_level_pins.remove(pin)
                # also remove custom pos
                if pin.name in self.top_pin_positions:
                    del self.top_pin_positions[pin.name]
                if pin.name in self.pin_colors:
                    del self.pin_colors[pin.name]
                self.draw()

    def change_instance_color(self, inst: Instance):
        self.snapshot()
        color = colorchooser.askcolor(title=f"Choose color for {inst.name}")
        if color[1]:
            inst.color_override = color[1]
            self.draw()

    def reset_instance_color(self, inst: Instance):
        self.snapshot()
        inst.color_override = None
        self.draw()

    def change_instance_name(self, inst: Instance):
        self.snapshot()
        new_name = simpledialog.askstring("Rename", f"New name for '{inst.name}':", parent=self, initialvalue=inst.name)
        if new_name and new_name != inst.name:
            inst.name = new_name
            self.draw()
            if self.on_update: self.on_update()

    def rename_pin_dialog(self, pin: Port):
        self.snapshot()
        new_name = simpledialog.askstring("Rename Pin", f"New name for '{pin.name}':", parent=self, initialvalue=pin.name)
        if new_name and new_name != pin.name:
            if pin.name in self.top_pin_positions:
                self.top_pin_positions[new_name] = self.top_pin_positions.pop(pin.name)
            if pin.name in self.pin_colors:
                self.pin_colors[new_name] = self.pin_colors.pop(pin.name)
            pin.name = new_name
            self.draw()
            if self.on_update: self.on_update()

    def change_instance_size(self, inst: Instance):
        self.snapshot()
        # Current size
        curr = f"{inst.width}x{inst.height}"
        res = simpledialog.askstring("Resize", f"Enter WxH (current {curr})\nSet 0x0 to reset to automatic.", parent=self)
        if res:
            try:
                parts = res.lower().split('x')
                if len(parts) == 2:
                    w = int(parts[0].strip())
                    h = int(parts[1].strip())
                    inst.custom_width = w
                    inst.custom_height = h
                    self.arrange_grid() # Re-calc size and pos
                    self.draw()
            except ValueError:
                messagebox.showerror("Error", "Invalid format. Use WxH (e.g. 200x100)")

    def delete_port(self, inst: Instance, port: Port):
        self.snapshot()
        if messagebox.askyesno("Confirm", f"Delete port '{port.name}' from '{inst.name}'?"):
            if port in inst.ports:
                inst.ports.remove(port)
                # Should we remove connections?
                # draw() will handle connections for ports that exist. 
                # If port gone, connection loop won't find it.
                # But we might want to cleanup logical connections too if they exist in some other struct?
                # connections are rebuilt in draw() from producer->consumer scan.
                # If a port is removed, it won't be in producers or consumers, so connection won't be made.
                self.arrange_grid() # Size might change
                self.draw()
    
    def reset_instance_ports(self, inst: Instance):
        self.snapshot()
        if inst.original_ports:
            inst.ports = list(inst.original_ports) # Restore copy
            inst.ports = list(inst.original_ports) # Restore copy
            self.arrange_grid()
            self.draw()

    def delete_instance(self, inst: Instance):
        self.snapshot()
        if messagebox.askyesno("Confirm", f"Delete block '{inst.name}'?"):
            inst.visible = False
            self.arrange_grid() 
            self.draw()
            if self.on_update: self.on_update()

    def restore_instance(self, inst: Instance):
        self.snapshot()
        inst.visible = True
        self.arrange_grid()
        self.draw()
        if self.on_update: self.on_update()

    def toggle_lock(self, inst: Instance):
        self.snapshot()
        inst.locked = not inst.locked
        self.draw(routing=False)

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
        if inst.custom_width and inst.custom_height:
             # Even with custom size, we should probably ensure it's big enough for children?
             # For now, let custom override. If they shrink it too much, children clip.
             return inst.custom_width, inst.custom_height
             
        # Basic size based on ports
        p_in = [p for p in inst.ports if p.direction in ('IN','INOUT')]
        p_out = [p for p in inst.ports if p.direction in ('OUT','INOUT')]
        
        needed_height = max(len(p_in), len(p_out)) * self.port_height + 40 # + header/footer
        needed_width = self.min_block_width
        
        # Name width
        font = tkfont.Font(family=inst.font_family, size=inst.font_size, weight='bold' if inst.font_bold else 'normal', slant='italic' if inst.font_italic else 'roman')
        text_w = font.measure(inst.name) + 20
        needed_width = max(needed_width, text_w)
        
        # If group and expanded, size must contain children
        if inst.is_group and not inst.collapsed:
             if not inst.children:
                 # Empty group default
                 needed_width = max(needed_width, 200)
                 needed_height = max(needed_height, 200)
             else:
                 # Bounding box relative to group (x,y)
                 # Wait, children x,y are absolute.
                 # So we need to ensure group covers them.
                 # This logic is tricky: moving group moves children.
                 # But sizing group? 
                 # If we auto-size group, we look at children's absolute bounds.
                 
                 min_x = min(c.x for c in inst.children)
                 min_y = min(c.y for c in inst.children)
                 max_x = max(c.x + c.width for c in inst.children)
                 max_y = max(c.y + c.height for c in inst.children)
                 
                 # The group position (inst.x, inst.y) might need to move if children are to the left/top?
                 # No, standard is group box surrounds children.
                 # So inst.x must be <= min_x - pad
                 #     inst.y must be <= min_y - pad
                 #     inst.w must cover max_x + pad
                 #     inst.h must cover max_y + pad
                 
                 # BUT, arrange_grid calls this to GET size. It doesn't move x,y usually... 
                 # logic usually assumes x,y is fixed.
                 # If we return size relative to inst.x?
                 
                 pad = 20
                 # We require the group to encompass children.
                 # W = (max_child_x + pad) - inst.x
                 # H = (max_child_y + pad) - inst.y
                 
                 # If inst.x > min_child_x, we have a problem (children sticking out left).
                 # We normally set group pos when creating it.
                 # If children move, they are constrained.
                 # If specific child moves left, it hits inst.x limit.
                 # So we only care about width/height extensions to the right/bottom.
                 
                 req_w = (max_x + pad) - inst.x
                 req_h = (max_y + pad) - inst.y
                 
                 needed_width = max(needed_width, req_w)
                 needed_height = max(needed_height, req_h)

        height = math.ceil(needed_height / self.grid_step) * self.grid_step
        width = math.ceil(needed_width / self.grid_step) * self.grid_step
        
        return int(width), int(height)

    def arrange_grid(self):
        visible_instances = [i for i in self.instances if i.visible]
        for inst in visible_instances:
            inst.width, inst.height = self.calculate_block_size(inst)
        
        if not visible_instances:
            return
            
        # Only arrange if all positions are 0 (fresh load)
        if not all(inst.x == 0 and inst.y == 0 for inst in visible_instances):
            return

        cols = math.ceil(math.sqrt(len(visible_instances)))
        row_heights = {}
        max_width = 0
        for i, inst in enumerate(visible_instances):
            r = i // cols
            row_heights[r] = max(row_heights.get(r, 0), inst.height)
            max_width = max(max_width, inst.width)
        y_offset = 40
        for i, inst in enumerate(visible_instances):
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
            # Exempt start and goal from occupancy check to allow entering ports
            if cell == start or cell == goal:
                 return 1
            
            if occupancy.get(cell, True):
                return 100000000  # Extremely high cost for blocks
            
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

    def get_active_instances(self, instances=None):
        if instances is None:
            instances = self.instances
        
        result = []
        for inst in instances:
            if not inst.visible:
                continue
            result.append(inst)
            if inst.is_group and not inst.collapsed:
                result.extend(self.get_active_instances(inst.children))
        return result

    def get_blocks_for_occupancy(self, instances):
        return [(int(inst.x), int(inst.y), int(inst.width), int(inst.height)) 
                for inst in instances]

    def draw(self, routing: bool = True):
        self.delete('all')
        self.drawn_pin_positions.clear()
        self.arrange_grid()

        if self.grid_enabled:
            self._draw_grid_background()

        # Render order: Parent groups first (backgrounds), then children
        # But _draw_instance_visual is recursive for expanded groups!
        # So we only call it for top-level instances.
        top_level = [i for i in self.instances if i.visible and not i.parent]
        for inst in top_level:
            self._draw_instance_visual(inst)

        active_instances = self.get_active_instances()
        blocks = self.get_blocks_for_occupancy(active_instances)

                  
        # Helper to draw pins - moved before routing check
        # But we need xmin/xmax first.
        # Determine bounding box
        if blocks:
            xmin = min(b[0] for b in blocks) - 200
            xmax = max(b[0] + b[2] for b in blocks) + 200
            ymin = min(b[1] for b in blocks)
            ymax = max(b[1] + b[3] for b in blocks)
        else:
           xmin, xmax, ymin, ymax = 0, 1000, 0, 1000

        # Expand bounding box to include top pin positions
        if self.top_pin_positions:
            px_vals = [p[0] for p in self.top_pin_positions.values()]
            py_vals = [p[1] for p in self.top_pin_positions.values()]
            if px_vals:
                xmin = min(xmin, min(px_vals) - 200)
                xmax = max(xmax, max(px_vals) + 200)
                ymin = min(ymin, min(py_vals) - 200)
                ymax = max(ymax, max(py_vals) + 200)
           
        top_in_ports: List[Tuple[Port, int, int]] = []
        top_out_ports: List[Tuple[Port, int, int]] = []
        self.pin_hitboxes: Dict[str, Tuple[int, int, int, int]] = {}
        
        if self.show_top_level and self.top_level_pins:
           # Height for pins
           total_in = sum(1 for p in self.top_level_pins if p.direction == 'IN')
           total_out = sum(1 for p in self.top_level_pins if p.direction == 'OUT' or p.direction == 'INOUT')
           
           height_in = total_in * 30
           height_out = total_out * 30
           
           start_y_in = ymin + (ymax-ymin - height_in)//2
           start_y_out = ymin + (ymax-ymin - height_out)//2
           
           # Draw In pins on left
           curr_y = start_y_in
           for p in self.top_level_pins:
               if p.direction == 'IN':
                   if p.name in self.top_pin_positions:
                       px, py = self.top_pin_positions[p.name]
                   else:
                       px, py = xmin-40, curr_y
                       curr_y += 40
                   
                   self._draw_pin_symbol(px, py, 'IN', p)
                   top_in_ports.append((p, px, py))
           
           # Draw Out pins on right
           curr_y = start_y_out
           for p in self.top_level_pins:
               if p.direction in ('OUT', 'INOUT'):
                   if p.name in self.top_pin_positions:
                       px, py = self.top_pin_positions[p.name]
                   else:
                       px, py = xmax+40, curr_y
                       curr_y += 40
                   
                   direction = 'OUT' if p.direction == 'OUT' else 'INOUT'
                   self._draw_pin_symbol(px, py, direction, p)
                   top_out_ports.append((p, px, py))

        if not routing:
            # Apply Zoom
            if self.current_scale != 1.0:
                self.scale('all', 0, 0, self.current_scale, self.current_scale)
            self.update_scrollregion()
            return

        # ... (rest of routing logic)

        # Create dummy instances for routing
        # Producer map: signal -> (Instance, Port)
        # We need to handle top level inputs as producers
        producers: Dict[str, Tuple[object, Port]] = {}
        
        # Build Alias Map from assignments
        # assignments is list of (dest, source).
        # We want to know: "If I need signal 'dest', I can get it from 'source'".
        # alias_map[dest] = source
        alias_map = {dest: src for dest, src in self.assignments}

        # 1. Normal instances + Internal Group Ports
        for inst in active_instances:
            # Outputs of any block are producers
            for p in inst.ports:
                if p.direction in ('OUT','INOUT'):
                    if p.signal not in producers:
                        producers[p.signal] = (inst, p)
            
            # INPUTS of an EXPANDED GROUP are producers for its context (Internal connections)
            if inst.is_group and not inst.collapsed:
                for p in inst.ports:
                    if p.direction in ('IN', 'INOUT'):
                         # We treat the group's INPUT port as a producer for internal signals.
                         # Note: This might conflict with an external producer of the same signal!
                         # Usually, the external producer is the source. 
                         # But if there's no external producer (port is the boundary), we need this.
                         # Better: Always register it as a "secondary" producer or only if no other?
                         # Let's prioritize real outputs.
                         if p.signal not in producers:
                             producers[p.signal] = (inst, p)

                        
        # 2. Top Level Inputs (act as producers)
        # We create a dummy instance wrapper for routing coordinates
        top_in_instances = {} 
        for p, x, y in top_in_ports:
             # Dummy instance for top input
             # x, y is center of pin. 
             # For routing, we treat it like an output port of a block to the left.
             # "Instance" is invisible.
             dummy_inst = Instance(name=f"TOP_IN_{p.name}", entity="TOP", ports=[], x=x-20, y=y-20, width=20, height=40)
             # Hack: We need 'y+40+idx*port_height' to match 'y'. 
             # If we set y=py-40, then py = y+40 (assuming idx=0).
             dummy_inst.y = y - 40 
             dummy_inst.x = x - dummy_inst.width # To the left of the pin
             
             # The signal produced by this top pin is usually named same as the pin
             # But if there is an assignment "sig <= pin", then this pin efficiently produces "sig" too via the alias.
             # We register the pin name as key.
             producers[p.name] = (dummy_inst, p)
             top_in_instances[p.name] = dummy_inst

        connections: List[Tuple[object, Port, object, Port]] = []
        
        # Helper to resolve producer
        def get_producer(sig_name):
            # Direct match
            if sig_name in producers:
                return producers[sig_name]
            # Check recursive alias (limit depth to avoid loops?)
            # Just 1 level for now based on user request "rx_serial_in_int <= rx_serial_in"
            if sig_name in alias_map:
                src_sig = alias_map[sig_name]
                if src_sig in producers:
                    return producers[src_sig]
            return None

        # 3. Connections
        # We process connections in a way that respects group boundaries
        for inst in active_instances:
            for p in inst.ports:
                if p.direction in ('IN','INOUT'):
                    target_signal = p.signal
                    if not target_signal: continue
                    
                    # Connection Logic:
                    # 1. If I am inside a group G, and G has an INPUT port for this signal:
                    #    - Connect to G.
                    # 2. Otherwise, find the "nearest" producer (external or internal).
                    
                    if inst.parent and not inst.parent.collapsed:
                        # Check if parent has a port for this signal
                        parent_port = next((pp for pp in inst.parent.ports if pp.signal == target_signal and pp.direction in ('IN', 'INOUT')), None)
                        if parent_port:
                            # Connect to parent group's internal side of the port
                            connections.append((inst.parent, parent_port, inst, p))
                            continue
                    
                    # Not connecting to parent port, find producer
                    prod = get_producer(target_signal)
                    if prod:
                        src_inst, src_port = prod
                        if src_inst is inst and src_port is p:
                            continue
                        
                        # If src is internal to G, and dst is external to G:
                        # SHOULD route through G's output port.
                        # But wait, we iterate through ALL active_instances.
                        # If G is an expanded group, its OUTPUT port will be processed as a consumer below.
                        
                        connections.append((src_inst, src_port, inst, p))
                    else:
                        self._highlight_unconnected_input(inst, p)
            
            # 4. Expanded Group Output Ports (Consumers for internal signals)
            if inst.is_group and not inst.collapsed:
                for p in inst.ports:
                    if p.direction in ('OUT', 'INOUT'):
                        # Group output port acts as a consumer for internal producers
                        prod = get_producer(p.signal)
                        if prod:
                            src_inst, src_port = prod
                            # Only connect if producer is INTERNAL to this group
                            # (or at least not this group itself to avoid self-loops)
                            if src_inst != inst:
                                connections.append((src_inst, src_port, inst, p))


                        
        # 4. Top Level Outputs (consumers)
        for p, x, y in top_out_ports:
            # Acts as a sink. Find producer.
            # p.name is the external port name.
            # Is there an assignment "p.name <= internal_sig"?
            # If so, we need to find producer of "internal_sig".
            
            # Check if p.name is a destination in assignments
            # Alias map is dest -> source.
            target_signal = p.name
            if target_signal in alias_map:
                target_signal = alias_map[target_signal]
            
            # Also, check if p.name itself is produced directly (unlikely if it's an output port being driven)
            
            prod = get_producer(target_signal)
            if prod:
                src_inst, src_port = prod
                
                # Dummy instance for destination
                dummy_inst = Instance(name=f"TOP_OUT_{p.name}", entity="TOP", ports=[], x=x, y=y-20, width=20, height=40)
                dummy_inst.y = y - 40
                
                connections.append((src_inst, src_port, dummy_inst, p))

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

        # Add Expanded Group hitboxes? 
        # Actually, wires SHOULD be able to cross expanded group boundaries but avoid internal blocks.
        # But they should probably avoid the header and ports area of the group.
        # For now, let's keep it simple and see.
        
        occupancy = self.build_grid_occupancy(blocks, xmin, xmax, ymin, ymax)

        
        # Add Top Pin Hitboxes to occupancy
        if self.show_top_level:
            for name, (x1, y1, x2, y2) in self.pin_hitboxes.items():
                # integer grid snapping
                gx1 = (x1 // self.grid_step) * self.grid_step - self.grid_step
                gx2 = (x2 // self.grid_step) * self.grid_step + self.grid_step
                gy1 = (y1 // self.grid_step) * self.grid_step - self.grid_step
                gy2 = (y2 // self.grid_step) * self.grid_step + self.grid_step
                
                for gx in range(gx1, gx2 + 1, self.grid_step):
                    for gy in range(gy1, gy2 + 1, self.grid_step):
                        # Approximate
                         if x1 - 5 <= gx <= x2 + 5 and y1 - 5 <= gy <= y2 + 5:
                             occupancy[(gx, gy)] = True

        wire_occupancy: Dict[Tuple[int,int], Set[str]] = {}

        self.lines_meta.clear()
        
        for src_inst, src_port, dst_inst, dst_port in connections:
            # Source Point
            # If src_inst is a group and we are connecting from its internal side:
            # (An INPUT port acting as a producer for internal blocks)
            # OR if it's a regular block output (RIGHT side)
            
            src_outs = [p for p in src_inst.ports if p.direction in ('OUT','INOUT')]
            src_ins = [p for p in src_inst.ports if p.direction in ('IN','INOUT')]
            
            # Context detection: 
            # If src_inst is a group and dst_inst is a child of src_inst:
            # We are connecting from the INTERNAL side of an INPUT port.
            is_internal_from_group_in = src_inst.is_group and dst_inst.parent == src_inst and src_port in src_ins
            
            if is_internal_from_group_in:
                # Source is the LEFT side of the group's input port
                # But visually, the connection starts at the RIGHT side of the pin dot?
                # Usually, port pins are drawn AT the boundary.
                # Left ports: dot at x. Right ports: dot at x+w.
                src_px = int(src_inst.x)
                try:
                    sidx = src_ins.index(src_port)
                except ValueError:
                    sidx = 0
                src_py = int(src_inst.y + 40 + sidx * self.port_height)
            else:
                # Normal output (RIGHT side)
                src_px = int(src_inst.x + src_inst.width)
                try:
                    sidx = src_outs.index(src_port)
                except ValueError:
                    sidx = 0
                src_py = int(src_inst.y + 40 + sidx * self.port_height)

            # Destination Point
            # If dst_inst is a group and src_inst is its child:
            # We are connecting to the INTERNAL side of an OUTPUT port.
            is_internal_to_group_out = dst_inst.is_group and src_inst.parent == dst_inst and dst_port in [p for p in dst_inst.ports if p.direction in ('OUT', 'INOUT')]
            
            if is_internal_to_group_out:
                # Destination is the RIGHT side of the group's output port
                dst_px = int(dst_inst.x + dst_inst.width)
                dst_outs = [p for p in dst_inst.ports if p.direction in ('OUT','INOUT')]
                try:
                    didx = dst_outs.index(dst_port)
                except ValueError:
                    didx = 0
                dst_py = int(dst_inst.y + 40 + didx * self.port_height)
            else:
                # Normal input (LEFT side)
                dst_px = int(dst_inst.x)
                dst_ins = [p for p in dst_inst.ports if p.direction in ('IN','INOUT')]
                try:
                    didx = dst_ins.index(dst_port)
                except ValueError:
                    didx = 0
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
                if config.DEBUG: sys.stderr.write(f"WARNING: Source port OFF GRID: ({src_px}, {src_py})\n")
            if dst_px % self.grid_step != 0 or dst_py % self.grid_step != 0:
                if config.DEBUG: sys.stderr.write(f"WARNING: Dest port OFF GRID: ({dst_px}, {dst_py})\n")

            if config.DEBUG: sys.stderr.write(f"DEBUG: {src_port.signal} generation:\n")
            if config.DEBUG: sys.stderr.write(f"  Src Port: ({src_px}, {src_py}) -> Start Grid: {start_grid} -> Stub: {start_stub}\n")
            if config.DEBUG: sys.stderr.write(f"  Dst Port: ({dst_px}, {dst_py}) -> Goal Grid: {goal_grid} -> Stub: {goal_stub}\n")

            if path is None:
                # Fallback: simple manhattan
                mid_x = (start_stub[0] + goal_stub[0]) // 2
                mid_x = (mid_x // self.grid_step) * self.grid_step
                path = [start_stub, (mid_x, start_stub[1]), 
                       (mid_x, goal_stub[1]), goal_stub]
                if config.DEBUG: sys.stderr.write(f"  Path (Fallback): {path}\n")
            else:
                if config.DEBUG: sys.stderr.write(f"  Path (A*): {path}\n")

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

            if config.DEBUG: sys.stderr.write(f"DEBUG: signal={src_port.signal}, compressed={compressed}\n")
            sys.stderr.flush()


            segments: List[Tuple[Tuple[int,int], Tuple[int,int]]] = []
            for i in range(len(compressed) - 1):
                segments.append((compressed[i], compressed[i+1]))

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
                    self.create_text(label_x, label_y, text=text,                                    font=('Arial', 7, 'bold'), fill='white', tags='signal_label')
        
        # Apply Zoom
        if self.current_scale != 1.0:
            self.scale('all', 0, 0, self.current_scale, self.current_scale)
            
        self.update_scrollregion()

    def update_scrollregion(self):
        bbox = self.bbox('all')
        if bbox:
            x0, y0, x1, y1 = bbox
            # Infinite scroll: pad massively
            pad = 20000 
            self.configure(scrollregion=(x0-pad, y0-pad, x1+pad, y1+pad))
        else:
            self.configure(scrollregion=(-20000, -20000, 20000, 20000))

    def zoom_to_fit(self):
        self.update_idletasks() # Ensure bbox is accurate
        bbox = self.bbox('all')
        if not bbox: return
        
        x0, y0, x1, y1 = bbox
        content_w = x1 - x0
        content_h = y1 - y0
        
        # Current view size
        view_w = self.winfo_width()
        view_h = self.winfo_height()
        
        if content_w <= 0 or content_h <= 0 or view_w <= 0 or view_h <= 0:
            return

        # Add some padding
        padding = 50
        target_w = content_w + padding * 2
        target_h = content_h + padding * 2
        
        scale_x = view_w / target_w
        scale_y = view_h / target_h
        
        # Choose smaller scale to fit both dimensions
        scale = min(scale_x, scale_y)
        
        # Limit scale bounds
        scale = max(self.scale_min, min(self.scale_max, scale))
        
        # Apply scaling - we need relative scale factor
        ratio = scale / self.current_scale
        
        # Center of content
        cx = (x0 + x1) / 2
        cy = (y0 + y1) / 2
        
        self.scale('all', cx, cy, ratio, ratio)
        self.current_scale = scale
        self.update_scrollregion()
        
        # Center view logic is tricky with infinite scroll
        # We need to scroll so that (cx, cy) is in center of view
        # xview_moveto takes fraction (0.0 - 1.0) of scrollregion
        
        # Re-get bbox after scale
        bbox = self.bbox('all')
        if not bbox: return
        x0, y0, x1, y1 = bbox
        cx = (x0 + x1) / 2
        cy = (y0 + y1) / 2
        
        pad = 20000
        # Scrollregion is x0-pad, y0-pad, x1+pad, y1+pad
        sr_x0 = x0 - pad
        sr_y0 = y0 - pad
        sr_w = (x1 + pad) - (x0 - pad)
        sr_h = (y1 + pad) - (y0 - pad)
        
        # Center of view in scrollregion coordinates
        # We want view_center = cx
        # view_left = cx - view_w/2
        
        view_left = cx - view_w / 2
        view_top = cy - view_h / 2
        
        x_fraction = (view_left - sr_x0) / sr_w
        y_fraction = (view_top - sr_y0) / sr_h
        
        self.xview_moveto(x_fraction)
        self.yview_moveto(y_fraction)

    def _draw_grid_background(self):
        try:
            bbox = self.bbox('all')
        except Exception:
            bbox = None
            
        # Get current view bounds to ensure grid covers visible area too
        vx1 = self.canvasx(0)
        vy1 = self.canvasy(0)
        vx2 = self.canvasx(self.winfo_width())
        vy2 = self.canvasy(self.winfo_height())
        
        if bbox:
            x0, y0, x1, y1 = bbox
            # Union with view
            left = int(min(x0, vx1)) - 200
            top = int(min(y0, vy1)) - 200
            right = int(max(x1, vx2)) + 200
            bottom = int(max(y1, vy2)) + 200
        else:
            left, top, right, bottom = int(vx1)-200, int(vy1)-200, int(vx2)+200, int(vy2)+200
        step = self.grid_step
        start_x = (left // step) * step
        for gx in range(start_x, right + step, step):
            self.create_line(gx, top, gx, bottom, fill='#f6f6f6')
        start_y = (top // step) * step
        for gy in range(start_y, bottom + step, step):
            self.create_line(left, gy, right, gy, fill='#f6f6f6')

    def edit_font(self, item: object):
        '''Opens a dialog to edit font settings for an Instance or Port.'''
        # Initial values
        family = getattr(item, 'font_family', "Arial")
        size = getattr(item, 'font_size', 10)
        bold = getattr(item, 'font_bold', False)
        italic = getattr(item, 'font_italic', False)
        
        new_settings = self.ask_font_settings(initial={'family': family, 'size': size, 'bold': bold, 'italic': italic})
        
        if new_settings:
            # Snapshot before change
            self.snapshot()
            
            # Update attributes
            item.font_family = new_settings['family']
            item.font_size = new_settings['size']
            item.font_bold = new_settings['bold']
            item.font_italic = new_settings['italic']
            
            self.draw() # Redraw

    def ask_font_settings(self, initial=None):
        if initial is None:
            initial = {'family': 'Arial', 'size': 10, 'bold': False, 'italic': False}
            
        dlg = tk.Toplevel(self)
        dlg.title("Edit Font")
        dlg.geometry("300x250")
        
        result = {}
        
        # Family
        tk.Label(dlg, text="Font Family:").pack(pady=(10, 0))
        families = ['Arial', 'Courier', 'Times', 'Helvetica', 'Verdana']
        family_var = tk.StringVar(value=initial['family'])
        if initial['family'] not in families:
            families.insert(0, initial['family'])
            
        cb_family = tk.OptionMenu(dlg, family_var, *families)
        cb_family.pack()
        
        # Size
        tk.Label(dlg, text="Font Size:").pack(pady=(10, 0))
        size_var = tk.IntVar(value=initial['size'])
        # Spinbox or entry
        sb_size = tk.Spinbox(dlg, from_=6, to=72, textvariable=size_var, width=5)
        sb_size.pack()
        
        # Style
        tk.Label(dlg, text="Style:").pack(pady=(10, 0))
        bold_var = tk.BooleanVar(value=initial['bold'])
        italic_var = tk.BooleanVar(value=initial['italic'])
        
        tk.Checkbutton(dlg, text="Bold", variable=bold_var).pack()
        tk.Checkbutton(dlg, text="Italic", variable=italic_var).pack()
        
        def on_ok():
            result['family'] = family_var.get()
            try:
                result['size'] = int(size_var.get())
            except ValueError:
                result['size'] = 10
            result['bold'] = bold_var.get()
            result['italic'] = italic_var.get()
            dlg.destroy()
            
        def on_cancel():
            result.clear()
            dlg.destroy()
            
        btn_frame = tk.Frame(dlg)
        btn_frame.pack(pady=20)
        tk.Button(btn_frame, text="OK", command=on_ok, width=8).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Cancel", command=on_cancel, width=8).pack(side=tk.LEFT, padx=5)
        
        dlg.transient(self)
        dlg.grab_set()
        self.wait_window(dlg)
        
        return result if result else None

    def create_group_from_selection(self):
        if len(self.selected_instances) < 1:
            return

        self.snapshot()
        
        # Calculate bounding box (same as before for defaults)
        x1 = min(i.x for i in self.selected_instances)
        y1 = min(i.y for i in self.selected_instances)
        x2 = max(i.x + i.width for i in self.selected_instances)
        y2 = max(i.y + i.height for i in self.selected_instances)
        
        pad = 20
        x1 -= pad; y1 -= pad; x2 += pad; y2 += pad
        
        default_name = f"Group_{len(self.instances)}"
        
        # --- Port Detection Logic ---
        suggested_ports = []
        
        internal_instances = set(self.selected_instances)
        group_signals = set()
        for inst in self.selected_instances:
            for p in inst.ports:
                if p.signal: group_signals.add(p.signal)
        
        external_signals = set()
        # Check against non-selected instances
        for inst in self.instances:
            if inst in internal_instances: continue
            if not inst.visible: continue
            for p in inst.ports:
                if p.signal in group_signals:
                    external_signals.add(p.signal)
        
        # Check against top level pins
        top_pin_names = {p.name for p in self.top_level_pins}
        for sig in group_signals:
            if sig in top_pin_names:
                external_signals.add(sig)
            for d, s in self.assignments:
                if (d == sig and s in top_pin_names) or (s == sig and d in top_pin_names):
                    external_signals.add(sig)

        for sig in sorted(list(external_signals)):
             suggested_ports.append({'name': sig, 'direction': 'INOUT', 'signal': sig})

        # Determine blocks for dialog list
        potential = [i for i in self.instances if i.visible and (not i.is_group or not i.parent)]
        checked = list(self.selected_instances)
        
        # --- Open Dialog ---
        dialog = GroupCreationDialog(self, default_name, suggested_ports, potential, checked)
        if not dialog.result:
            return # User cancelled
            
        final_name = dialog.result['name']
        final_ports_data = dialog.result['ports']
        final_blocks_names = dialog.result.get('blocks', [])
        
        blocks_to_group = []
        all_candidates = potential + checked
        for b in all_candidates:
             if b.name in final_blocks_names:
                 blocks_to_group.append(b)

        if blocks_to_group:
             x1 = min(i.x for i in blocks_to_group) - 20
             y1 = min(i.y for i in blocks_to_group) - 40
             x2 = max(i.x + i.width for i in blocks_to_group) + 20
             y2 = max(i.y + i.height for i in blocks_to_group) + 20
        
        new_ports = []
        for pdata in final_ports_data:
            new_ports.append(Port(name=pdata['name'], direction=pdata['direction'], signal=pdata['signal']))

        # Create Group Instance
        group = Instance(name=final_name, entity="GROUP", ports=new_ports, 
                         x=x1, y=y1, width=x2-x1, height=y2-y1, 
                         is_group=True, children=blocks_to_group[:], visible=True)
                         
        for inst in blocks_to_group:
            if inst in self.instances:
                self.instances.remove(inst)
            inst.parent = group # Linking parent
        
        self.instances.append(group)
        self.draw() # Ensure bounds are updated
        if self.on_update: self.on_update()

    def get_unique_group_name(self):
        existing_names = set(i.name for i in self.instances)
        idx = 1
        while True:
            name = f"Group_{idx}"
            if name not in existing_names:
                return name
            idx += 1

    def create_empty_group(self):
        self.snapshot()
        group_name = self.get_unique_group_name()
        
        # Center in view
        offset_y = self.canvasy(0)
        # Or better: center of current view
        w = self.winfo_width()
        h = self.winfo_height()
        cx = self.canvasx(w/2)
        cy = self.canvasy(h/2)
        
        group = Instance(name=group_name, entity="GROUP", ports=[], 
                         x=int(cx)-100, y=int(cy)-100, width=200, height=200, 
                         is_group=True, children=[], visible=True)
        
        self.instances.append(group)
        self.selected_instances = [group]
        self.draw()
        if self.on_update: self.on_update()



    def ungroup_selection(self):
        new_selection = []
        indices_to_remove = []
        
        self.snapshot()
        
        # Copy list to modify safely
        current_selection = list(self.selected_instances)
        
        for group in current_selection:
            if group.is_group:
                # Add children back to main list
                # Logic to 'unpack' them?
                # If group was moved, children need offset?
                # If they were absolute coordinates, they are already at correct place visually.
                # If collapsed, they might be stale?
                # For now assume absolute coords are kept updated or don't matter if collapsed.
                
                # If collapsed, we should probably update children coords to match group center?
                # Or just let them appear where they were.
                
                for child in group.children:
                    child.parent = None # Unlink
                    if child not in self.instances:
                        self.instances.append(child)
                    new_selection.append(child)
                
                if group in self.instances:
                    self.instances.remove(group)
        
        self.selected_instances = new_selection
        self.draw()
        if self.on_update: self.on_update()  # Refresh inspector

    def remove_from_group(self, inst: Instance):
        if not inst.parent: return
        self.snapshot()
        
        group = inst.parent
        if inst in group.children:
            group.children.remove(inst)
        
        inst.parent = None
        self.instances.append(inst)
        
        group.width, group.height = self.calculate_block_size(group)
        self.draw()
        if self.on_update: self.on_update()  # Refresh inspector

    def toggle_collapse(self, group: Instance):
        if not group.is_group: return
        self.snapshot()
        
        group.collapsed = not group.collapsed
        
        if group.collapsed:
            # Hide children
            # Recalculate size based on ports
            group.width, group.height = self.calculate_block_size(group)
        else:
            # Expand: Show children
            # Recalculate size based on children's bounding box
            if group.children:
                 x1 = min(i.x for i in group.children)
                 y1 = min(i.y for i in group.children)
                 x2 = max(i.x + i.width for i in group.children)
                 y2 = max(i.y + i.height for i in group.children)
                 pad = 20
                 group.x = x1 - pad
                 group.y = y1 - pad
                 group.width = (x2+pad) - (x1-pad)
                 group.height = (y2+pad) - (y1-pad)

        self.draw()

    def _draw_instance_visual(self, inst: Instance):
        x, y, w, h = inst.x, inst.y, inst.width, inst.height
        
        # Shadow
        self.create_rectangle(x+2, y+2, x+w+2, y+h+2, fill='#ddd', outline='')
        
        is_expanded_group = inst.is_group and not inst.collapsed

        # Regular block or Collapsed Group coloring
        if inst.color_override:
            color = inst.color_override
        else:
            if inst.is_group:
                 color = '#E1BEE7' # Purpleish for groups
            elif inst in self.selected_instances:
                 color = '#FFF59D' # Selection color
            elif self.highlight_instance == inst.name:
                 color = '#fff9e6'
            else:
                 color = '#e8f4f8'
            
        outline = 'black'
        width = 2
        
        if inst.locked:
            outline = '#D32F2F' # distinct color for locked
            
        if is_expanded_group:
            # Drawn dashed container with light tint background
            # We use a very light version of the group color or transparent
            bg_color = '#F3E5F5' # Very light purple
            self.create_rectangle(x, y, x+w, y+h, outline='#555', dash=(4,4), width=1, fill=bg_color)
            
            # Draw a solid HEADER area
            header_h = 35
            self.create_rectangle(x, y, x+w, y+header_h, fill=color, outline=outline, width=width)
            
            # Recursively draw children
            for child in inst.children:
                if child.visible:
                    self._draw_instance_visual(child)
        else:
            # Full solid block
            self.create_rectangle(x, y, x+w, y+h, fill=color, outline=outline, width=width)

        
        # Title
        weight = 'bold' if inst.font_bold else 'normal'
        slant = 'italic' if inst.font_italic else 'roman'
        title_font = tkfont.Font(family=inst.font_family, size=inst.font_size, weight=weight, slant=slant)
        
        self.create_text(x + w/2, y + 12, text=inst.name, font=title_font, fill='black')
        
        if inst.is_group:
             self.create_text(x + w/2, y + 26, text='(Group)', font=('Arial', 7), fill='blue')
        else:
             self.create_text(x + w/2, y + 26, text=f'({inst.entity})', font=('Arial', 7), fill='gray')
        
        if inst.locked:
            self.create_text(x + w - 10, y + 10, text='🔒', font=('Arial', 8))
            
        # Draw Ports with inherited or default font styles (could expand to per-port font later)
        # For now, keep ports as is, or maybe scale them slightly?
        port_font = tkfont.Font(family='Arial', size=8)

        self.create_line(x, y + 35, x + w, y + 35, fill='#ccc', width=1)
        in_ports = [p for p in inst.ports if p.direction in ('IN','INOUT')]
        out_ports = [p for p in inst.ports if p.direction in ('OUT','INOUT')]
        for i, port in enumerate(in_ports):
            py = y + 40 + i * self.port_height
            self.create_oval(x - 6, py - 3, x, py + 3, fill='#2196F3', outline='#1565C0')
            pname = port.name if len(port.name) < 20 else port.name[:17] + '...'
            self.create_text(x + 8, py, text=pname, font=port_font, anchor='w', fill='#1565C0')
        for i, port in enumerate(out_ports):
            py = y + 40 + i * self.port_height
            self.create_oval(x + w - 6, py - 3, x + w, py + 3, fill='#F44336', outline='#C62828')
            pname = port.name if len(port.name) < 20 else port.name[:17] + '...'
            self.create_text(x + w - 8, py, text=pname, font=port_font, anchor='e', fill='#F44336')

    def _draw_segments(self, segments: List[Tuple[Tuple[int,int],Tuple[int,int]]], signal_name: str, highlighted: bool):
        color = '#FF6F00' if highlighted else '#4CAF50'
        width = 3 if highlighted else 1.8
        if config.DEBUG: sys.stderr.write(f"DEBUG: drawing {signal_name}\n")
        for i, ((x1, y1), (x2, y2)) in enumerate(segments):
            if config.DEBUG: sys.stderr.write(f"  segment {i}: ({x1},{y1}) -> ({x2},{y2})\n")
            if x1 % self.grid_step != 0 or y1 % self.grid_step != 0 or x2 % self.grid_step != 0 or y2 % self.grid_step != 0:
                 if config.DEBUG: sys.stderr.write(f"  WARNING: Segment OFF GRID! ({x1},{y1}) -> ({x2},{y2})\n")
            self.create_line(x1, y1, x2, y2, fill=color, width=width, smooth=False, capstyle=tk.ROUND, joinstyle=tk.MITER)
        sys.stderr.flush()

        # Draw junction dots
        # Step 1: Group all segments by signal
        signal_segments: Dict[str, Set[Tuple[int,int,int,int]]] = {}
        port_locations: Set[Tuple[int,int]] = set()
        
        # Collect port locations to avoid drawing dots on top of them
        for inst in self.instances:
            if not inst.visible: continue
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

    def _draw_pin_symbol(self, x: int, y: int, direction: str, port: Port):
         name = port.name
         # Prepare Font
         weight = 'bold' if port.font_bold else 'normal'
         slant = 'italic' if port.font_italic else 'roman'
         pin_font = tkfont.Font(family=port.font_family, size=port.font_size, weight=weight, slant=slant)

         # Shapes based on user image.
         # Coordinates centered at x,y? Or x,y is the connection point?
         # Let's assume x,y is the connection point (tip towards wire).
         # IN:  [     >
         #      x,y is right tip.
         # OUT: [     >
         #      x,y is left tail? No, OUT drives internal, so x,y should be left tip interacting with wire implies...
         #      Wait, top-level IN drives internal logic. So connection comes from the RIGHT of the pin symbol.
         #      Top-level OUT is driven BY internal logic. Connection comes into the LEFT of the pin symbol.
         
         # IN Pin:
         # Shape: Rectangle body, arrow head on right?
         # User image: "IN" -> Rectangular left, Arrow right.
         # Since it connects to internal logic to its right, the tip at right is the connection point.
         # Let's define x,y as that Right Tip.
         
         size = 15
         text_offset = 25
         
         # Determine fill color
         fill_color = self.pin_colors.get(name)
         
         if direction == 'IN':
             # Polygon points relative to x,y (Tip)
             # Tip at (0,0) locally.
             # Arrow head ends at 0. Back of arrow at -10?
             points = [
                 x, y,            # Tip
                 x-10, y-10,      # Top shoulder
                 x-30, y-10,      # Top back
                 x-30, y+10,      # Bottom back
                 x-10, y+10       # Bottom shoulder
             ]
             c = fill_color if fill_color else '#E1F5FE'
             self.create_polygon(points, fill=c, outline='black', width=1.5, tags=(f"pin_hitbox:{name}", "pin"))
             # Text to the LEFT (x-offset)
             self.create_text(x-40, y, text=name, anchor='e', font=pin_font, tags=(f"pin_hitbox:{name}", "pin")) 
             # Hitbox - Expanded to include text (approx 150px left)
             self.pin_hitboxes[name] = (x-200, y-15, x, y+15)
             self.drawn_pin_positions[name] = (x, y)
             
         elif direction == 'OUT':
             # Shape: Rectangular right, Arrow tail (tip) left?
             # User said: "just opposite direction" of IN.IN points Right. OUT points Left?
             # IN: Tip at Right (x,y). Back at Left.
             # OUT: Tip at Left (x,y). Back at Right.
             
             points = [
                 x, y,            # Tip (Left, connection point)
                 x+10, y-10,      # Top shoulder
                 x+30, y-10,      # Top back
                 x+30, y+10,      # Bottom back
                 x+10, y+10       # Bottom shoulder
             ]
             
             c = fill_color if fill_color else '#FFEBEE'
             self.create_polygon(points, fill=c, outline='black', width=1.5, tags=(f"pin_hitbox:{name}", "pin"))
             # Text to the RIGHT (x+offset)
             self.create_text(x+40, y, text=name, anchor='w', font=pin_font, tags=(f"pin_hitbox:{name}", "pin"))
             # Hitbox - Expanded to include text (approx 150px right)
             self.pin_hitboxes[name] = (x, y-15, x+200, y+15)
             self.drawn_pin_positions[name] = (x, y)
             
         elif direction == 'INOUT':
             # Shape: Hexagon (Diamond-ish)
             # Connection could be both sides... usually treated as wire connecting to it.
             # Let's center it at x,y? 
             # Or assume connection point is "Inner" side?
             # Let's stick to x,y being a reliable anchor.
             # If on left side of screen, conn is right. If on right side, conn is left.
             # Usually INOUT are placed on sides.
             # Let's draw Hexagon centered at x,y.
             
             w = 15 # half width
             h = 10 # half height
             points = [
                 x-w, y,
                 x-w/2, y-h,
                 x+w/2, y-h,
                 x+w, y,
                 x+w/2, y+h,
                 x-w/2, y+h
             ]
             c = fill_color if fill_color else '#FFF3E0'
             self.create_polygon(points, fill=c, outline='black', width=1.5, tags=(f"pin_hitbox:{name}", "pin"))
             self.create_text(x, y, text=name, anchor='c', font=pin_font, tags=(f"pin_hitbox:{name}", "pin"))
             self.pin_hitboxes[name] = (x-w, y-h, x+w, y+h)

    def zoom(self, factor):
        width = self.winfo_width()
        height = self.winfo_height()
        cx = self.canvasx(width/2)
        cy = self.canvasy(height/2)
        
        new_scale = self.current_scale * factor
        if new_scale < self.scale_min:
            factor = self.scale_min / self.current_scale
            self.current_scale = self.scale_min
        elif new_scale > self.scale_max:
            factor = self.scale_max / self.current_scale
            self.current_scale = self.scale_max
        else:
            self.current_scale = new_scale
            
        self.scale('all', cx, cy, factor, factor)
        self.configure(scrollregion=self.bbox('all'))

    # ============================================================================
    # Undo / Redo
    # ============================================================================
    
    def _capture_state(self):
        import copy
        return {
            'instances': [copy.deepcopy(inst) for inst in self.instances],
            'top_pin_positions': self.top_pin_positions.copy(),
            'pin_colors': self.pin_colors.copy(),
            'top_level_pins': copy.deepcopy(self.top_level_pins)
        }
    
    def snapshot(self):
        '''Save current state to undo stack.'''
        state = self._capture_state()
        self.undo_stack.append(state)
        self.redo_stack.clear()
        
        if len(self.undo_stack) > 50:
            self.undo_stack.pop(0)

    def undo(self, event=None):
        if not self.undo_stack:
            return
            
        current_state = self._capture_state()
        self.redo_stack.append(current_state)
        
        state = self.undo_stack.pop()
        self._apply_state(state)
        self.draw()

    def redo(self, event=None):
        if not self.redo_stack:
            return
            
        current_state = self._capture_state()
        self.undo_stack.append(current_state)
        
        state = self.redo_stack.pop()
        self._apply_state(state)
        self.draw()

    def _apply_state(self, state):
        self.instances = state['instances']
        self.top_pin_positions = state['top_pin_positions']
        self.pin_colors = state['pin_colors']
        self.top_level_pins = state['top_level_pins']
    # --- Panning Methods ---
    def on_right_down(self, event):
        self.scan_mark(event.x, event.y)
        self.config(cursor="fleur")
        self._is_panning = True
        # If we clicked on an instance, we might want to still have context menu if no drag occurred.
        self._pan_start_x = event.x
        self._pan_start_y = event.y

    def on_right_drag(self, event):
        self.scan_dragto(event.x, event.y, gain=1)
        
    def on_right_up(self, event):
        self.config(cursor="")
        self._is_panning = False
        
        # Check for drag distance
        dist = math.hypot(event.x - self._pan_start_x, event.y - self._pan_start_y)
        if dist < 5:
            # Treat as click
            # Treat as click
            self.on_right_click(event)
        else:
            # Pan finished - update grid
            self.draw()

    def on_right_click(self, event):
        # This is now called explicitly if no pan occurred
        # ... logic for context menu ...
        self.focus_set()
        
        cx = self.canvasx(event.x) / self.current_scale
        cy = self.canvasy(event.y) / self.current_scale
        
        # Check for instance click
        clicked_inst = None
        for inst in self.instances:
             if not inst.visible: continue
             if inst.x <= cx <= inst.x + inst.width and inst.y <= cy <= inst.y + inst.height:
                 clicked_inst = inst
                 break
        
        if clicked_inst:
            # Show context menu
            menu = tk.Menu(self, tearoff=0)
            menu.add_command(label="Change Name", command=lambda i=clicked_inst: self.change_instance_name(i))
            menu.add_command(label="Change Color", command=lambda i=clicked_inst: self.change_instance_color(i))
            menu.add_command(label="Reset Color", command=lambda i=clicked_inst: self.reset_instance_color(i))
            menu.add_command(label="Change Size", command=lambda i=clicked_inst: self.change_instance_size(i))
            menu.add_command(label="Toggle Lock", command=lambda i=clicked_inst: self.toggle_lock(i))
            menu.add_command(label="Reset Ports", command=lambda i=clicked_inst: self.reset_instance_ports(i))
            menu.add_separator()
            if clicked_inst.is_group:
                 lbl = "Expand" if clicked_inst.collapsed else "Collapse"
                 menu.add_command(label=lbl, command=lambda i=clicked_inst: self.toggle_collapse(i))
                 menu.add_separator()
            
            if clicked_inst.parent:
                 menu.add_command(label="Remove from Group", command=lambda i=clicked_inst: self.remove_from_group(i))
                 menu.add_separator()

            menu.add_command(label="Delete", command=lambda i=clicked_inst: self.delete_instance(i))
            
            menu.tk_popup(event.x_root, event.y_root)
            return
            
        # Check for Pin
        # Use hitboxes or proximity
        if self.show_top_level:
            for p in self.top_level_pins:
                 if p.name in self.top_pin_positions:
                     px, py = self.top_pin_positions[p.name]
                     if abs(cx - px) < 10 and abs(cy - py) < 10:
                         target_pin = p
                         menu = tk.Menu(self, tearoff=0)
                         menu.add_command(label="Rename Pin", command=lambda p=target_pin: self.rename_pin_dialog(p))
                         menu.add_command(label="Change Color", command=lambda p=target_pin: self.change_pin_color(p))
                         menu.add_command(label="Reset Color", command=lambda p=target_pin: self.reset_pin_color(p))
                         menu.add_separator()
                         menu.add_command(label="Delete Pin", command=lambda p=target_pin: self.delete_pin(p))
                         
                         menu.tk_popup(event.x_root, event.y_root)
                         return

class GroupCreationDialog(tk.Toplevel):
    def __init__(self, parent, default_name, initial_ports, potential_blocks=[], checked_blocks=[]):
        super().__init__(parent)
        self.title("Create Group")
        self.geometry("700x500") # Wider
        self.result = None
        
        self.ports = initial_ports 
        self.potential_blocks = potential_blocks
        self.checked_blocks = checked_blocks
        
        # Main Layout
        main_frame = tk.Frame(self, padx=10, pady=10)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Name
        name_frame = tk.Frame(main_frame)
        name_frame.pack(fill=tk.X, pady=(0, 10))
        tk.Label(name_frame, text="Group Name:").pack(side=tk.LEFT)
        self.name_var = tk.StringVar(value=default_name)
        tk.Entry(name_frame, textvariable=self.name_var).pack(side=tk.LEFT, padx=10, fill=tk.X, expand=True)
        
        # Notebook
        notebook = ttk.Notebook(main_frame)
        notebook.pack(fill=tk.BOTH, expand=True)
        
        # --- Ports Tab ---
        ports_frame = tk.Frame(notebook, padx=5, pady=5)
        notebook.add(ports_frame, text="Ports")
        
        # Ports Tree
        list_frame = tk.Frame(ports_frame)
        list_frame.pack(fill=tk.BOTH, expand=True)
        
        self.tree = ttk.Treeview(list_frame, columns=('name', 'direction', 'signal'), show='headings')
        self.tree.heading('name', text='Port Name')
        self.tree.heading('direction', text='Direction')
        self.tree.heading('signal', text='Signal')
        self.tree.column('name', width=120)
        self.tree.column('direction', width=80)
        self.tree.column('signal', width=200)
        
        vsb = ttk.Scrollbar(list_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Ports Toolbar
        toolbar = tk.Frame(ports_frame)
        toolbar.pack(fill=tk.X, pady=5)
        tk.Button(toolbar, text="Add Port", command=self.add_port).pack(side=tk.LEFT, padx=2)
        tk.Button(toolbar, text="Remove Port", command=self.remove_port).pack(side=tk.LEFT, padx=2)

        # --- Blocks Tab ---
        blocks_frame = tk.Frame(notebook, padx=5, pady=5)
        notebook.add(blocks_frame, text="Included Blocks")
        
        # Checkbox List for blocks
        blocks_list_frame = tk.Frame(blocks_frame)
        blocks_list_frame.pack(fill=tk.BOTH, expand=True)
        
        canvas = tk.Canvas(blocks_list_frame)
        scrollbar = ttk.Scrollbar(blocks_list_frame, orient="vertical", command=canvas.yview)
        self.scrollable_frame = tk.Frame(canvas)

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(
                scrollregion=canvas.bbox("all")
            )
        )

        canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        self.block_vars = {}
        
        # Populate with checked first
        for block in self.checked_blocks:
             var = tk.BooleanVar(value=True)
             cb = tk.Checkbutton(self.scrollable_frame, text=f"{block.name} ({block.entity})", variable=var, anchor='w')
             cb.pack(fill='x', padx=5, pady=2)
             self.block_vars[block.name] = var
             
        # Then potential
        for block in self.potential_blocks:
             var = tk.BooleanVar(value=False)
             cb = tk.Checkbutton(self.scrollable_frame, text=f"{block.name} ({block.entity})", variable=var, anchor='w')
             cb.pack(fill='x', padx=5, pady=2)
             self.block_vars[block.name] = var
        

        
        # Bottom Buttons
        btn_frame = tk.Frame(main_frame)
        btn_frame.pack(pady=10)
        tk.Button(btn_frame, text="OK", command=self.on_ok, width=10).pack(side=tk.LEFT, padx=10)
        tk.Button(btn_frame, text="Cancel", command=self.on_cancel, width=10).pack(side=tk.LEFT, padx=10)
        
        self.populate_tree()
        self.transient(parent)
        self.grab_set()
        self.parent = parent
        self.wait_window(self)
        
    def populate_tree(self):
        self.tree.delete(*self.tree.get_children())
        for p in self.ports:
            self.tree.insert('', 'end', values=(p['name'], p['direction'], p['signal']))
            
    def add_port(self):
        # Allow user to add a custom port
        name = simpledialog.askstring("New Port", "Port Name:", parent=self)
        if not name: return
        # Default direction INOUT
        self.ports.append({'name': name, 'direction': 'INOUT', 'signal': name})
        self.populate_tree()
    
    def remove_port(self):
        selected = self.tree.selection()
        if not selected: return
        for item in selected:
            values = self.tree.item(item, 'values')
            # find and remove from self.ports
            # values is tuple (name, dir, sig)
            for i, p in enumerate(self.ports):
                if p['name'] == values[0] and p['signal'] == values[2]:
                    del self.ports[i]
                    break
        self.populate_tree()
        
    def on_ok(self):
        # Gather ports
        final_ports = []
        for item in self.tree.get_children():
            values = self.tree.item(item)['values']
            final_ports.append({'name': values[0], 'direction': values[1], 'signal': values[2]})
        
        # Gather blocks
        final_blocks = []
        for name, var in self.block_vars.items():
            if var.get():
                final_blocks.append(name)
        
        self.result = {
            'name': self.name_var.get(),
            'ports': final_ports,
            'blocks': final_blocks
        }
        self.destroy()
        
    def on_cancel(self):
        self.result = None
        self.destroy()
