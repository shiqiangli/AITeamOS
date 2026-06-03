"""Development FastAPI app — file-first P0 Member Chat Workbench.

Run with:
    uvicorn aiteamos_api.dev_app:app --reload
"""

from __future__ import annotations

from .main import create_app

app = create_app()
