"""終局結果の観測文を世界固有の語彙から分離する。"""

from __future__ import annotations

import pytest

from ai_rpg_world.application.player.services.player_outcome_observation_formatter import (
    PlayerOutcomeObservationFormatter,
)
from ai_rpg_world.domain.player.enum.player_outcome_enum import PlayerOutcomeEnum


class TestGenericOutcomeMessages:
    """宣言のない世界では場所を決めつけない汎用文を返す。"""

    @pytest.mark.parametrize(
        ("outcome", "expected"),
        [
            (PlayerOutcomeEnum.DEAD, "リンは死亡した。もう蘇生できない。"),
            (PlayerOutcomeEnum.EJECTED, "リンは投票で追放された。もう戻らない。"),
            (PlayerOutcomeEnum.RESCUED, "リンは救助された。"),
            (PlayerOutcomeEnum.STRANDED, "リンは取り残された。"),
        ],
    )
    def test_formats_generic_message(
        self,
        outcome: PlayerOutcomeEnum,
        expected: str,
    ) -> None:
        """確定結果ごとの既定文は人物を示し、特定の舞台を捏造しない。"""
        formatter = PlayerOutcomeObservationFormatter()

        assert formatter.format(player_name="リン", outcome=outcome) == expected

    def test_unresolved_has_no_observation(self) -> None:
        """未確定への遷移は通知対象ではないため文を返さない。"""
        formatter = PlayerOutcomeObservationFormatter()

        assert (
            formatter.format(
                player_name="リン",
                outcome=PlayerOutcomeEnum.UNRESOLVED,
            )
            is None
        )


class TestScenarioOutcomeMessages:
    """シナリオが宣言した結果文だけを既定文から差し替える。"""

    def test_scenario_can_name_its_location(self) -> None:
        """島シナリオは STRANDED の舞台をシナリオ側の文型で表現できる。"""
        formatter = PlayerOutcomeObservationFormatter(
            {PlayerOutcomeEnum.STRANDED: "{player_name}は島に取り残されたままだ。"}
        )

        assert formatter.format(
            player_name="リン",
            outcome=PlayerOutcomeEnum.STRANDED,
        ) == "リンは島に取り残されたままだ。"

    def test_unspecified_outcome_keeps_generic_message(self) -> None:
        """一結果だけ差し替えても、他の結果は汎用の既定文を保つ。"""
        formatter = PlayerOutcomeObservationFormatter(
            {PlayerOutcomeEnum.STRANDED: "{player_name}は島に残された。"}
        )

        assert formatter.format(
            player_name="リン",
            outcome=PlayerOutcomeEnum.RESCUED,
        ) == "リンは救助された。"
