# ============================================================================
# parser.py - VHDL parsing logic
# ============================================================================

import re
from typing import Dict, List

from .models import Instance, Port

class VHDLParser:
    """Parses VHDL code to extract instances, signals, variables, and constants."""
    
    def __init__(self, vhdl_text: str):
        self.text = vhdl_text
        self.instances: List[Instance] = []
        self.signals: Dict[str, str] = {}
        self.variables: Dict[str, str] = {}
        self.constants: Dict[str, str] = {}

    def parse(self) -> None:
        """Main parse method."""
        self._parse_declarations()
        self._parse_instances()
    
    def _parse_declarations(self) -> None:
        """Parse signal, variable, and constant declarations."""
        text_no_comments = re.sub(r'--.*?(\n|$)', '\n', self.text)
        
        # Parse signals
        signal_pattern = r'\bSIGNAL\s+(\w+(?:\s*,\s*\w+)*)\s*:\s*([^;:=]+?)(?::=.*?)?;'
        for match in re.finditer(signal_pattern, text_no_comments, re.IGNORECASE | re.DOTALL):
            names = [n.strip() for n in match.group(1).split(',')]
            sig_type = match.group(2).strip()
            for name in names:
                self.signals[name] = sig_type
        
        # Parse variables
        variable_pattern = r'\bVARIABLE\s+(\w+(?:\s*,\s*\w+)*)\s*:\s*([^;:=]+?)(?::=.*?)?;'
        for match in re.finditer(variable_pattern, text_no_comments, re.IGNORECASE | re.DOTALL):
            names = [n.strip() for n in match.group(1).split(',')]
            var_type = match.group(2).strip()
            for name in names:
                self.variables[name] = var_type
        
        # Parse constants
        constant_pattern = r'\bCONSTANT\s+(\w+)\s*:\s*([^:=]+?)(?::=\s*(.+?))?;'
        for match in re.finditer(constant_pattern, text_no_comments, re.IGNORECASE | re.DOTALL):
            name = match.group(1).strip()
            const_type = match.group(2).strip()
            value = match.group(3).strip() if match.group(3) else ''
            self.constants[name] = f"{const_type} := {value}" if value else const_type

    def _parse_instances(self) -> None:
        """Parse entity instances."""
        instance_pattern = r'(\w+)\s*:\s*ENTITY\s+work\.(\w+)(.*?)PORT\s+MAP\s*\((.*?)\)\s*;'
        matches = re.finditer(instance_pattern, self.text, re.DOTALL | re.IGNORECASE)
        for match in matches:
            inst_name = match.group(1)
            entity_name = match.group(2)
            port_map_text = match.group(4)
            ports = self._parse_port_map(port_map_text)
            self.instances.append(Instance(name=inst_name, entity=entity_name, ports=ports))

    def _parse_port_map(self, port_map_text: str) -> List[Port]:
        """Parse port map connections."""
        ports: List[Port] = []
        port_map_text = re.sub(r'--.*?(\n|$)', '\n', port_map_text)
        port_entries = re.split(r',(?![^()]*\))', port_map_text)
        
        for entry in port_entries:
            entry = entry.strip()
            if not entry or '=>' not in entry:
                continue
            parts = entry.split('=>')
            if len(parts) == 2:
                port_name = parts[0].strip()
                signal_name = parts[1].strip()
                signal_name = re.sub(r'[;)\s]+$', '', signal_name)
                direction = self._guess_direction(port_name, signal_name)
                ports.append(Port(name=port_name, direction=direction, signal=signal_name))
        return ports

    @staticmethod
    def _guess_direction(port_name: str, signal_name: str) -> str:
        """Heuristically determine port direction from name."""
        p = port_name.lower()
        if any(x in p for x in ['out', 'result', 'data_out', 'dout', 'do']):
            return 'OUT'
        if any(x in p for x in ['in', 'data_in', 'din', 'di', 'clk', 'rstn', 'aresetn']):
            return 'IN'
        return 'INOUT'
