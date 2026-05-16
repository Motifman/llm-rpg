"""``HeartbeatObservationEmitter`` のクリーンアップ機構テスト。

PR #151 セルフレビュー指摘 (HIGH-2: ``_last_emitted_tick`` の無制限増大) の
回帰防止。
"""

from __future__ import annotations

from datetime import datetime, timezone

from ai_rpg_world.application.llm.contracts.interfaces import (
    ILLMPlayerResolver,
)
from ai_rpg_world.application.observation.services.heartbeat_observation_emitter import (
    HeartbeatObservationEmitter,
)
from ai_rpg_world.application.observation.services.observation_appender import (
    ObservationAppender,
)
from ai_rpg_world.application.observation.services.observation_context_buffer import (
    DefaultObservationContextBuffer,
)
from ai_rpg_world.application.observation.services.observation_turn_scheduler import (
    ObservationTurnScheduler,
)
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class _AllLlm(ILLMPlayerResolver):
    def is_llm_controlled(self, player_id: PlayerId) -> bool:
        return True


def _build(players: list[PlayerId]) -> HeartbeatObservationEmitter:
    buffer = DefaultObservationContextBuffer()
    appender = ObservationAppender(buffer)
    scheduler = ObservationTurnScheduler(llm_player_resolver=_AllLlm())
    return HeartbeatObservationEmitter(
        observation_appender=appender,
        turn_scheduler=scheduler,
        llm_player_ids_provider=lambda: list(players),
        interval_ticks=1,
        now_provider=lambda: datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


class TestHeartbeatEmitterCleanup:
    """``forget_player`` / ``prune_inactive`` の挙動。"""

    def test_forget_player_removes_state(self) -> None:
        """``forget_player`` で指定プレイヤーの記録だけ消える。"""
        emitter = _build([PlayerId(1), PlayerId(2)])
        emitter.run(WorldTick(0))  # 両者 anchor
        assert 1 in emitter._last_emitted_tick
        assert 2 in emitter._last_emitted_tick

        emitter.forget_player(PlayerId(1))
        assert 1 not in emitter._last_emitted_tick
        assert 2 in emitter._last_emitted_tick

    def test_forget_player_on_unknown_is_safe(self) -> None:
        """存在しないプレイヤーを forget しても例外にならない。"""
        emitter = _build([PlayerId(1)])
        emitter.forget_player(PlayerId(999))  # no-op

    def test_prune_inactive_removes_stale_only(self) -> None:
        """active リストに含まれないプレイヤーだけ消える。"""
        emitter = _build([PlayerId(1), PlayerId(2), PlayerId(3)])
        emitter.run(WorldTick(0))  # 3 人 anchor
        assert sorted(emitter._last_emitted_tick.keys()) == [1, 2, 3]

        removed = emitter.prune_inactive([PlayerId(2)])
        assert removed == 2
        assert list(emitter._last_emitted_tick.keys()) == [2]

    def test_prune_inactive_empty_active_removes_all(self) -> None:
        """active が空なら全削除。"""
        emitter = _build([PlayerId(1), PlayerId(2)])
        emitter.run(WorldTick(0))
        removed = emitter.prune_inactive([])
        assert removed == 2
        assert emitter._last_emitted_tick == {}

    def test_prune_inactive_when_no_state_returns_zero(self) -> None:
        """state が空の状態で prune しても 0 を返す。"""
        emitter = _build([])
        assert emitter.prune_inactive([PlayerId(1)]) == 0
