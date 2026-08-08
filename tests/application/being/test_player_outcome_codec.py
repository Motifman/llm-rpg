"""PlayerOutcomeRegistry の確定状態を world snapshot で連続させる。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from ai_rpg_world.application.being.world_subsystems.player_outcome_codec import (
    PlayerOutcomeSubsystemCodec,
)
from ai_rpg_world.domain.player.enum.player_outcome_enum import PlayerOutcomeEnum
from ai_rpg_world.domain.player.exception.player_exceptions import (
    PlayerOutcomeRegistryValidationException,
)
from ai_rpg_world.domain.player.service.player_outcome_registry import (
    PlayerOutcomeRegistry,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


_PLAYERS = [PlayerId(index) for index in range(1, 6)]
_OUTCOMES = (
    PlayerOutcomeEnum.UNRESOLVED,
    PlayerOutcomeEnum.RESCUED,
    PlayerOutcomeEnum.DEAD,
    PlayerOutcomeEnum.EJECTED,
    PlayerOutcomeEnum.STRANDED,
)


def _runtime(registry: PlayerOutcomeRegistry) -> SimpleNamespace:
    return SimpleNamespace(
        _player_outcome_registry=registry,
        get_player_ids=lambda: list(_PLAYERS),
    )


def _registry_with_every_outcome() -> PlayerOutcomeRegistry:
    registry = PlayerOutcomeRegistry.new_for_players(_PLAYERS)
    for player_id, outcome in zip(_PLAYERS, _OUTCOMES):
        if outcome is not PlayerOutcomeEnum.UNRESOLVED:
            registry.set_outcome(player_id, outcome)
    return registry


class TestPlayerOutcomeSubsystemCodec:
    """全 outcome を欠落や再通知なしで保存・復元する。"""

    def test_every_outcome_survives_a_round_trip(self) -> None:
        """全 PlayerOutcomeEnum が capture → restore で同じ意味に戻る。"""
        codec = PlayerOutcomeSubsystemCodec()
        source = _registry_with_every_outcome()
        restored = PlayerOutcomeRegistry.new_for_players(_PLAYERS)

        payload = codec.capture(_runtime(source))
        codec.restore(_runtime(restored), payload)

        assert restored.snapshot() == source.snapshot()
        assert codec.capture(_runtime(restored)) == payload

    def test_restore_does_not_emit_outcome_callbacks(self) -> None:
        """復元は過去の確定を新しい出来事として callback へ再通知しない。"""
        codec = PlayerOutcomeSubsystemCodec()
        restored = PlayerOutcomeRegistry.new_for_players(_PLAYERS)
        callbacks: list[tuple[PlayerId, PlayerOutcomeEnum, PlayerOutcomeEnum]] = []
        restored.register_callback(
            lambda player_id, old, new: callbacks.append((player_id, old, new))
        )

        codec.restore(
            _runtime(restored),
            codec.capture(_runtime(_registry_with_every_outcome())),
        )

        assert callbacks == []

    @pytest.mark.parametrize(
        "entries",
        [
            [
                {"player_id": index, "outcome": outcome.value}
                for index, outcome in zip(range(1, 5), _OUTCOMES[:4])
            ],
            [
                {"player_id": index, "outcome": outcome.value}
                for index, outcome in zip(range(1, 6), _OUTCOMES)
            ]
            + [{"player_id": 6, "outcome": "UNRESOLVED"}],
        ],
    )
    def test_player_set_mismatch_fails_before_replacing_state(
        self, entries: list[dict[str, object]]
    ) -> None:
        """player の欠落・余分がある payload は部分復元せず拒否する。"""
        codec = PlayerOutcomeSubsystemCodec()
        restored = PlayerOutcomeRegistry.new_for_players(_PLAYERS)
        before = restored.snapshot()

        with pytest.raises(PlayerOutcomeRegistryValidationException):
            codec.restore(
                _runtime(restored),
                {"schema_version": 1, "entries": entries},
            )

        assert restored.snapshot() == before

    def test_unknown_outcome_fails_before_replacing_state(self) -> None:
        """未知の outcome は UNRESOLVED に丸めず、状態を変える前に拒否する。"""
        codec = PlayerOutcomeSubsystemCodec()
        restored = PlayerOutcomeRegistry.new_for_players(_PLAYERS)
        entries = [
            {"player_id": index, "outcome": outcome.value}
            for index, outcome in zip(range(1, 6), _OUTCOMES)
        ]
        entries[2]["outcome"] = "GHOST"

        with pytest.raises(ValueError, match="GHOST"):
            codec.restore(
                _runtime(restored),
                {"schema_version": 1, "entries": entries},
            )

        assert restored.snapshot() == {
            index: PlayerOutcomeEnum.UNRESOLVED for index in range(1, 6)
        }
