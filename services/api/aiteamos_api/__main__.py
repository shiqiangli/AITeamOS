from __future__ import annotations

import os

import uvicorn

from .app import create_app


workspace = os.environ.get("AITEAMOS_WORKSPACE", ".aiteamos")
app = create_app(workspace)


def main() -> None:
    uvicorn.run(app, host="127.0.0.1", port=8765)


if __name__ == "__main__":
    main()
