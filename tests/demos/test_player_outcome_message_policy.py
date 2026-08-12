"""終局結果の世界固有文がシナリオ宣言から観測へ届くことを保証する。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.enum.player_outcome_enum import PlayerOutcomeEnum
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

_ROOT = Path(__file__).resolve().parents[2]
_SCENARIOS = _ROOT / "data" / "scenarios"
_NON_ISLAND = _ROOT / "tests" / "fixtures" / "scenarios" / "darkened_station.json"
_ISLAND_SCENARIOS = (
    "survival_island_v2.json",
    "survival_island_v2_short.json",
    "survival_island_v3_coop.json",
    "survival_island_v4_coop.json",
)


def _outcome_entry(runtime, recipient: PlayerId):
    return next(
        entry
        for entry in reversed(runtime._obs_buffer.get_observations(recipient))
        if entry.output.structured.get("type") == "player_outcome_resolved"
    )


class TestOutcomeMessageDeclaration:
    """島シナリオだけが終局通知で島という舞台を宣言する。"""

    @pytest.mark.parametrize("scenario_name", _ISLAND_SCENARIOS)
    def test_each_island_scenario_declares_stranded_message(
        self,
        scenario_name: str,
    ) -> None:
        """STRANDED を使う島4本は従来の文面をシナリオデータに保持する。"""
        raw = json.loads((_SCENARIOS / scenario_name).read_text(encoding="utf-8"))

        assert raw["metadata"]["player_outcome_messages"]["STRANDED"] == (
            "{player_name}は島に取り残されたままだ。"
        )


class TestOutcomeMessageWiring:
    """読込済み表示方針が結果確定時の観測へ適用される。"""

    def test_island_keeps_its_declared_wording(self) -> None:
        """島シナリオの STRANDED 観測は従来どおり島を明示する。"""
        runtime = create_world_runtime(_SCENARIOS / "survival_island_v4_coop.json")
        actor, recipient = PlayerId(1), PlayerId(2)

        runtime._player_outcome_registry.set_outcome(
            actor,
            PlayerOutcomeEnum.STRANDED,
        )

        entry = _outcome_entry(runtime, recipient)
        assert entry.output.prose == (
            f"{runtime.get_player_name(actor)}は島に取り残されたままだ。"
        )
        assert entry.output.structured["new_outcome"] == "STRANDED"
        assert entry.output.schedules_turn is True

    def test_world_without_declaration_does_not_invent_an_island(self) -> None:
        """宣言のない世界で STRANDED が確定しても島という舞台を捏造しない。"""
        runtime = create_world_runtime(_NON_ISLAND)
        actor, recipient = PlayerId(1), PlayerId(2)

        runtime._player_outcome_registry.set_outcome(
            actor,
            PlayerOutcomeEnum.STRANDED,
        )

        entry = _outcome_entry(runtime, recipient)
        assert entry.output.prose == f"{runtime.get_player_name(actor)}は取り残された。"
        assert "島" not in entry.output.prose
