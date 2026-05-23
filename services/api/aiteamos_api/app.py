from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI

from .routes import create_app as create_routes_app

__all__ = ["create_app"]


def create_app(workspace_path: str | Path = ".aiteamos") -> FastAPI:
    """Create the API app through the route-registration module."""
    return create_routes_app(workspace_path)
