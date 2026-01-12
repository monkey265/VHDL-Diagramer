# ============================================================================
# utils.py - Utility functions
# ============================================================================

from typing import List, Tuple

def compress_polyline(points: List[Tuple[int, int]]) -> List[Tuple[int, int]]:
    """Remove collinear points from a polyline, ensuring only horizontal and vertical lines."""
    if not points:
        return []
    
    out = [points[0]]
    for p in points[1:]:
        if len(out) < 2:
            if p != out[-1]:
                out.append(p)
            continue
        
        a = out[-2]
        b = out[-1]
        c = p
        
        # Check for horizontal or vertical collinearity
        if (a[0] == b[0] == c[0]) or \
           (a[1] == b[1] == c[1]):
            out[-1] = c
        else:
            if p != out[-1]:
                out.append(p)
    
    return out