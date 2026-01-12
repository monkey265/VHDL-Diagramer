# ============================================================================
# models.py - Data classes
# ============================================================================

from dataclasses import dataclass, field

from typing import List, Optional

@dataclass


class Port:
    name: str
    direction: str  # 'IN', 'OUT', 'INOUT'
    signal: str
    font_family: str = "Arial"
    font_size: int = 8
    font_bold: bool = False
    font_italic: bool = False

@dataclass


class Instance:
    name: str
    entity: str
    ports: List[Port]
    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0
    color_override: Optional[str] = None
    locked: bool = False
    custom_width: int = 0
    custom_height: int = 0
    original_ports: List[Port] = field(default_factory=list)
    visible: bool = True
    font_family: str = "Arial"
    font_size: int = 10
    font_bold: bool = True
    font_italic: bool = False
