#!/usr/bin/env python3
"""Launcher for TIA Toolkit GUI."""
import sys, os
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))
from gui import TiaToolkitApp
app = TiaToolkitApp()
app.mainloop()
