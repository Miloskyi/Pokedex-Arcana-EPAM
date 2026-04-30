"""
Entrypoint for uvicorn.
Adds /app to sys.path so 'from backend.xxx import ...' resolves correctly,
then imports and re-exports the FastAPI app.
"""
import sys
import os

# Ensure /app is in the Python path so 'backend' package is found
sys.path.insert(0, "/app")

from backend.main import app  # noqa: E402, F401

__all__ = ["app"]
