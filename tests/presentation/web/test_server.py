"""Tests for the web server entrypoint."""

from unittest.mock import MagicMock

from ai_rpg_world.presentation.web import server


def test_main_runs_uvicorn_with_factory(monkeypatch) -> None:
    uvicorn_run = MagicMock()
    monkeypatch.setattr(server, "uvicorn", MagicMock(run=uvicorn_run))

    server.main()

    uvicorn_run.assert_called_once_with(
        "ai_rpg_world.presentation.web.server:create_sqlite_web_app_from_env",
        factory=True,
        host="127.0.0.1",
        port=8000,
        reload=False,
    )
