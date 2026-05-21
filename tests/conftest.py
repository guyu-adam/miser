"""Shared test fixtures and path setup for miser test suite."""
import os, sys

# Ensure the package root is on sys.path (review #23, #25)
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)
