"""本番の問い合わせは、スポットの状態が揃った現在状態だけを整形処理へ渡す。"""

from unittest.mock import Mock

from ai_rpg_world.application.world.contracts.queries import GetPlayerCurrentStateQuery
from ai_rpg_world.application.world_runtime.default_prompt_builder_adapters import (
    WorldRuntimeQueryAdapter,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


def test_missing_snapshot_returns_none() -> None:
    """スポットの状態が取得できなければ None を返し、現在状態の DTO を作らない。"""
    runtime = Mock()
    runtime._state_builder.build_snapshot.return_value = None

    result = WorldRuntimeQueryAdapter(runtime).get_player_current_state(
        GetPlayerCurrentStateQuery(player_id=1)
    )

    assert result is None
    runtime._build_minimal_player_state_dto.assert_not_called()


def test_snapshot_is_passed_to_current_state_builder() -> None:
    """スポットの状態を取得できれば、本人の ID とその状態から作った DTO を返す。"""
    runtime = Mock()
    snapshot = runtime._state_builder.build_snapshot.return_value

    result = WorldRuntimeQueryAdapter(runtime).get_player_current_state(
        GetPlayerCurrentStateQuery(player_id=1)
    )

    runtime._build_minimal_player_state_dto.assert_called_once_with(PlayerId(1), snapshot)
    assert result is runtime._build_minimal_player_state_dto.return_value
