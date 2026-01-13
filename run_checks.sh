#!/bin/bash
set -e

echo "========================================"
echo "    VHDL Diagrammer Check Script"
echo "========================================"

echo "[1/2] Running Syntax Checks (py_compile)..."
# Find python files, excluding tests and hidden dirs for now if needed, but checking all is better.
# We skip .gemini or .git if they exist to avoid noise, but typically find works relative to cwd.
find . -name "*.py" -not -path "*/.*" -exec python3 -m py_compile {} +
echo ">> Syntax OK"

echo "[2/2] Running Unit Tests..."
python3 -m unittest discover -s tests -p "test_*.py" -v
echo ">> Tests Passed"

echo "========================================"
echo "    All Checks Passed!"
echo "========================================"
