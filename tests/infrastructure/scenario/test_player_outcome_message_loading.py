"""player_outcome_messages をシナリオ表示方針として厳格に読み込む。"""

from __future__ import annotations

import pytest

from ai_rpg_world.domain.player.enum.player_outcome_enum import PlayerOutcomeEnum
from ai_rpg_world.infrastructure.scenario.scenario_loader import (
    ScenarioLoadError,
    ScenarioLoader,
)
from tests.infrastructure.scenario.test_scenario_loader import _minimal_scenario


class TestPlayerOutcomeMessageLoading:
    """結果名と文型を検証し、PlayerOutcomeEnum をキーに保持する。"""

    def test_loads_stranded_message(self) -> None:
        """有効な STRANDED 文型は metadata の表示方針へ変換する。"""
        raw = _minimal_scenario()
        raw["metadata"]["player_outcome_messages"] = {
            "STRANDED": "{player_name}は島に取り残されたままだ。"
        }

        loaded = ScenarioLoader().load_from_dict(raw)

        assert loaded.metadata.player_outcome_messages == {
            PlayerOutcomeEnum.STRANDED: "{player_name}は島に取り残されたままだ。"
        }

    @pytest.mark.parametrize(
        ("value", "error"),
        [
            ([], "object"),
            ({"UNKNOWN": "{player_name}の結果"}, "UNKNOWN"),
            ({"UNRESOLVED": "{player_name}は未確定"}, "UNRESOLVED"),
            ({"STRANDED": 1}, "STRANDED"),
            ({"STRANDED": "島に残された"}, "player_name"),
            ({"STRANDED": "{name}は島に残された"}, "name"),
            (
                {
                    "STRANDED": (
                        "{player_name}は島に残され、記録は{name!r}とされた"
                    )
                },
                "name",
            ),
            (
                {"STRANDED": "{player_name}の型は{player_name.__class__!r}"},
                "player_name",
            ),
            ({"STRANDED": "{player_name:>10}は島に残された"}, "format"),
            ({"STRANDED": "{player_name!r}は島に残された"}, "format"),
            ({"STRANDED": "{{player_name}}は島に残された"}, "player_name"),
        ],
        ids=[
            "not-object",
            "unknown-outcome",
            "unresolved-outcome",
            "not-string",
            "missing-player-name",
            "unknown-placeholder",
            "unknown-placeholder-with-conversion",
            "attribute-reference",
            "format-specifier",
            "conversion",
            "escaped-placeholder",
        ],
    )
    def test_rejects_invalid_declaration(self, value: object, error: str) -> None:
        """不正な結果名や文型は実行時に縮退させず、読込時に拒否する。"""
        raw = _minimal_scenario()
        raw["metadata"]["player_outcome_messages"] = value

        with pytest.raises(ScenarioLoadError, match=error):
            ScenarioLoader().load_from_dict(raw)
