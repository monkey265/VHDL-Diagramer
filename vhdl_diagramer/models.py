# ============================================================================
# models.py - Data classes
# ============================================================================

from dataclasses import dataclass

from typing import List

@dataclass


class Port:
    name: str
    direction: str  # 'IN', 'OUT', 'INOUT'
    signal: str

@dataclass


class Instance:
    name: str
    entity: str
    ports: List[Port]
    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0
