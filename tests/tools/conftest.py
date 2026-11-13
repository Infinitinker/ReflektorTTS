"""Lets the tests import the tools as the tools import each other, by module name, as running one
from the repository root does."""

import sys
from pathlib import Path

TOOLS = str(Path(__file__).parents[2] / "tools")
if TOOLS not in sys.path:
    sys.path.append(TOOLS)
