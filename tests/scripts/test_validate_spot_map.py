"""spot map validator CLI の終了コードと JSON 出力を保証する。"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.validate_spot_map import main


def test_cli_returns_zero_when_only_warnings(tmp_path: Path, capsys) -> None:
    """warning だけの検査結果は JSON に出力し、終了コード 0 を返す。"""
    scenario_path = tmp_path / "scenario.json"
    scenario_path.write_text(
        json.dumps(
            {
                "spots": [
                    {"id": "a", "name": "A", "description": ""},
                    {"id": "b", "name": "B", "description": ""},
                ],
                "connections": [
                    {
                        "id": "ab",
                        "from": "a",
                        "to": "b",
                        "travel_ticks": 1,
                        "is_bidirectional": True,
                    }
                ],
                "players": [{"id": "p1", "name": "P1", "spawn_spot": "a"}],
            }
        ),
        encoding="utf-8",
    )

    exit_code = main([str(scenario_path)])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["warnings"]


def test_cli_returns_one_when_error_exists(tmp_path: Path, capsys) -> None:
    """error がある検査結果は JSON に出力し、終了コード 1 を返す。"""
    scenario_path = tmp_path / "scenario.json"
    scenario_path.write_text(
        json.dumps(
            {
                "spots": [
                    {"id": "camp", "name": "Camp", "description": ""},
                    {"id": "signal", "name": "Signal", "description": ""},
                ],
                "connections": [],
                "players": [{"id": "p1", "name": "P1", "spawn_spot": "camp"}],
            }
        ),
        encoding="utf-8",
    )

    exit_code = main([str(scenario_path), "--strict"])

    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["errors"]
