"""シナリオ起動後の公開 tick 入口が個人結果を確定する現行挙動を固定する。

結果規則の宣言形式や内部サービスには依存せず、``create_world_runtime`` と
``advance_tick`` を通した振る舞いだけを検証する。宣言型規則への全面移行でも
この試験を変更せずに通す。
"""

from pathlib import Path

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.enum.player_outcome_enum import PlayerOutcomeEnum
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from tests.runtime_config_helpers import runtime_config


_SCENARIO = Path("data/scenarios/survival_island_v4_coop.json")
_SIGNAL_FIRE_FLAG = "signal_fire_lit"


def _runtime():
    return create_world_runtime(_SCENARIO, config=runtime_config())


def _place_player(runtime, player_id: PlayerId, spot_name: str) -> None:
    graph = runtime._spot_graph_repo.find_graph()
    entity_id = EntityId.create(int(player_id))
    graph.unplace_entity(entity_id)
    graph.place_entity(
        entity_id,
        SpotId.create(runtime.id_mapper.get_int("spot", spot_name)),
    )
    runtime._spot_graph_repo.save(graph)


def _advance_from(runtime, current_tick: int) -> None:
    runtime._time_provider.set_current_tick(current_tick)
    runtime.advance_tick()


class TestDeclaredPlayerOutcomeBehavior:
    """島シナリオの救助・取り残し規則を実行時の振る舞いとして保証する。"""

    def test_rescue_tick_resolves_signaler_at_summit(self) -> None:
        """tick 144 で狼煙が上がり山頂にいる未確定者だけを RESCUED にする。"""
        runtime = _runtime()
        player_id = runtime.get_player_ids()[0]
        _place_player(runtime, player_id, "summit")
        runtime._world_flag_state.add(_SIGNAL_FIRE_FLAG)

        _advance_from(runtime, 143)

        assert (
            runtime._player_outcome_registry.get_outcome(player_id)
            is PlayerOutcomeEnum.RESCUED
        )

    def test_rescue_tick_requires_signal_fire(self) -> None:
        """救助 tick でも狼煙が上がっていなければ山頂の未確定者を救助しない。"""
        runtime = _runtime()
        player_id = runtime.get_player_ids()[0]
        _place_player(runtime, player_id, "summit")

        _advance_from(runtime, 143)

        assert (
            runtime._player_outcome_registry.get_outcome(player_id)
            is PlayerOutcomeEnum.UNRESOLVED
        )

    def test_rescue_tick_requires_player_at_summit(self) -> None:
        """狼煙が上がっていても山頂にいない未確定者を救助しない。"""
        runtime = _runtime()
        player_id = runtime.get_player_ids()[0]
        runtime._world_flag_state.add(_SIGNAL_FIRE_FLAG)

        _advance_from(runtime, 143)

        assert (
            runtime._player_outcome_registry.get_outcome(player_id)
            is PlayerOutcomeEnum.UNRESOLVED
        )

    def test_skipped_rescue_tick_is_caught_up(self) -> None:
        """時刻復元で tick 144 を飛び越えても、次の tick で救助判定を補完する。"""
        runtime = _runtime()
        player_id = runtime.get_player_ids()[0]
        _place_player(runtime, player_id, "summit")
        runtime._world_flag_state.add(_SIGNAL_FIRE_FLAG)

        _advance_from(runtime, 150)

        assert (
            runtime._player_outcome_registry.get_outcome(player_id)
            is PlayerOutcomeEnum.RESCUED
        )

    def test_missed_rescue_ship_cannot_be_used_later(self) -> None:
        """救助 tick で条件未達なら、後から狼煙を上げても通過済みの船では救助しない。"""
        runtime = _runtime()
        player_id = runtime.get_player_ids()[0]
        _place_player(runtime, player_id, "summit")
        _advance_from(runtime, 143)

        runtime._world_flag_state.add(_SIGNAL_FIRE_FLAG)
        _advance_from(runtime, 150)

        assert (
            runtime._player_outcome_registry.get_outcome(player_id)
            is PlayerOutcomeEnum.UNRESOLVED
        )

    def test_stranded_tick_resolves_only_unresolved_players(self) -> None:
        """tick 240 では未確定者を STRANDED にし、確定済み結果を上書きしない。"""
        runtime = _runtime()
        resolved, unresolved = runtime.get_player_ids()[:2]
        runtime._player_outcome_registry.set_outcome(
            resolved,
            PlayerOutcomeEnum.RESCUED,
        )

        _advance_from(runtime, 239)

        assert (
            runtime._player_outcome_registry.get_outcome(resolved)
            is PlayerOutcomeEnum.RESCUED
        )
        assert (
            runtime._player_outcome_registry.get_outcome(unresolved)
            is PlayerOutcomeEnum.STRANDED
        )
