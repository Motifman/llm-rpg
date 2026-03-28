"""ASGI/CLI entrypoint for the SQLite-backed visualization web app."""

from __future__ import annotations

import uvicorn

from ai_rpg_world.presentation.web.runtime import create_sqlite_web_app_from_env


def main() -> None:
    uvicorn.run(
        "ai_rpg_world.presentation.web.server:create_sqlite_web_app_from_env",
        factory=True,
        host="127.0.0.1",
        port=8000,
        reload=False,
    )


__all__ = ["create_sqlite_web_app_from_env", "main"]
