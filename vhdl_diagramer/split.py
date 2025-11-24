"""
VHDL Instance Diagram Generator - Package Structure
====================================================

Recommended directory structure:

vhdl_diagramer/
├── __init__.py
├── __main__.py          # Entry point for python -m vhdl_diagramer
├── config.py            # Constants and configuration
├── models.py            # Data classes (Port, Instance)
├── parser.py            # VHDL parsing logic
├── routing.py           # Pathfinding and routing algorithms
├── canvas.py            # Canvas widget with drawing logic
├── ui/
│   ├── __init__.py
│   ├── main_window.py   # Main application window
│   └── widgets.py       # Custom widgets (signal list panel, etc.)
└── utils.py             # Utility functions (compress_polyline, etc.)

Benefits of this structure:
- Clear separation of concerns
- Easy to test individual components
- Easy to extend (e.g., add new routing algorithms)
- Can be installed as a package: pip install -e .
"""














# ============================================================================
# Usage instructions
# ============================================================================

"""
To use this package structure:

1. Create the directory structure as shown above
2. Split the code into the respective files
3. Add a setup.py for installation:

# setup.py
from setuptools import setup, find_packages

setup(
    name='vhdl-diagramer',
    version='1.0.0',
    packages=find_packages(),
    install_requires=[
        # tkinter is built-in
    ],
    entry_points={
        'console_scripts': [
            'vhdl-diagram=vhdl_diagramer.__main__:main',
        ],
    },
)

4. Install in development mode:
   pip install -e .

5. Run:
   vhdl-diagram
   # or
   python -m vhdl_diagramer

Benefits:
- Maintainable: Each module has a clear purpose
- Testable: Can write unit tests for parser, router separately
- Extensible: Easy to add new features (e.g., export to SVG)
- Reusable: Parser can be used independently
- Professional: Standard Python package structure
"""