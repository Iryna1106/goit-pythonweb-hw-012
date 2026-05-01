"""Sphinx configuration for the Contacts REST API documentation."""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Make project root importable so autodoc can pull in src/.
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

# Provide deterministic env vars before settings are imported.
os.environ.setdefault("JWT_SECRET_KEY", "docs-build-placeholder")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

project = "Contacts REST API"
author = "goit-pythonweb-hw-012"
release = "2.0.0"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx.ext.intersphinx",
]

templates_path = ["_templates"]
exclude_patterns = []

html_theme = "sphinx_rtd_theme"
html_static_path = ["_static"]

autodoc_default_options = {
    "members": True,
    "undoc-members": False,
    "show-inheritance": True,
    "member-order": "bysource",
}
autodoc_typehints = "description"

napoleon_google_docstring = True
napoleon_numpy_docstring = True

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "fastapi": ("https://fastapi.tiangolo.com/", None),
    "sqlalchemy": ("https://docs.sqlalchemy.org/en/20/", None),
}
