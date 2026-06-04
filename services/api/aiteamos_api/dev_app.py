"""Development FastAPI app for the file-first AITeamOS API.

Run with:
    uvicorn aiteamos_api.dev_app:app --reload
"""

from __future__ import annotations

from .main import create_app

app = create_app()
