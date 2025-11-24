# ============================================================================
# utils.py - Utility functions
# ============================================================================

from typing import List, Tuple

def compress_polyline(points: List[Tuple[int, int]]) -> List[Tuple[int, int]]:
    """Remove collinear points from polyline."""
    if not points:
        return []
    
    out = [points[0]]
    for p in points[1:]:
        if len(out) < 2:
            out.append(p)
            continue
        
        a = out[-2]
        b = out[-1]
        c = p
        
        # Check if collinear
        if (b[0] - a[0]) * (c[1] - a[1]) == (b[1] - a[1]) * (c[0] - a[0]):
            out[-1] = c
        else:
            out.append(c)
    
    return out