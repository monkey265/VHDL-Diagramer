# ============================================================================
# routing.py - Pathfinding and routing algorithms
# ============================================================================

import heapq
from typing import Dict, List, Optional, Set, Tuple

class Router:
    """Handles wire routing using A* pathfinding."""
    
    def __init__(self, grid_step: int = 10):
        self.grid_step = grid_step
    
    def build_occupancy_grid(
        self, 
        blocks: List[Tuple[int, int, int, int]],
        xmin: int, xmax: int, ymin: int, ymax: int,
        margin: int = 30
    ) -> Dict[Tuple[int, int], bool]:
        """Build grid showing which cells are blocked."""
        occupancy = {}
        
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
    
    def find_path(
        self,
        start: Tuple[int, int],
        goal: Tuple[int, int],
        occupancy: Dict[Tuple[int, int], bool],
        wire_occupancy: Dict[Tuple[int, int], Set[str]],
        signal: str,
        xmin: int, xmax: int, ymin: int, ymax: int
    ) -> Optional[List[Tuple[int, int]]]:
        """Find path using A* algorithm."""
        
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
    
    def find_free_cell(
        self,
        start: Tuple[int, int],
        occupancy: Dict[Tuple[int, int], bool]
    ) -> Tuple[int, int]:
        """Find nearest free cell if start is blocked."""
        if not occupancy.get(start, True):
            return start
        
        # Try immediate neighbors
        for dx, dy in [(self.grid_step, 0), (-self.grid_step, 0),
                      (0, self.grid_step), (0, -self.grid_step),
                      (self.grid_step, self.grid_step), (-self.grid_step, -self.grid_step),
                      (self.grid_step, -self.grid_step), (-self.grid_step, self.grid_step)]:
            test_cell = (start[0] + dx, start[1] + dy)
            if not occupancy.get(test_cell, True):
                return test_cell
        
        # Expand search
        for dist in [2, 3, 4, 5]:
            for dx in range(-dist * self.grid_step, (dist + 1) * self.grid_step, self.grid_step):
                for dy in range(-dist * self.grid_step, (dist + 1) * self.grid_step, self.grid_step):
                    test_cell = (start[0] + dx, start[1] + dy)
                    if not occupancy.get(test_cell, True):
                        return test_cell
        
        return start  # Fallback