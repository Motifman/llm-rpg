"""``HeartbeatObservationEmitter`` の挙動を検証する単体テスト。

idle tick でも LLM エージェントが行動できるようにする合成観測の機構。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional

import pytest

from ai_rpg_world.application.llm.contracts.interfaces import (
    ILLMPlayerResolver,
    ILlmTurnTrigger,
)
from ai_rpg_world.application.observation.contracts.dtos import (
    ObservationOutput,
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


class _AllLlmPlayerResolver(ILLMPlayerResolver):
    """テスト用: 全プレイヤーを LLM 制御扱いにする resolver。"""

    def is_llm_controlled(self, player_id: PlayerId) -> bool:
        return True


@dataclass
class _RecordingTurnTrigger(ILlmTurnTrigger):
    """schedule_turn の呼び出し履歴を記録するだけのトリガ。"""

    scheduled: List[int] = field(default_factory=list)

    def schedule_turn(self, player_id: PlayerId) -> None:
        self.scheduled.append(player_id.value)

    def run_scheduled_turns(self) -> None:
        return None


def _build_emitter(
    *,
    interval_ticks: int = 5,
    llm_players: Optional[List[PlayerId]] = None,
) -> tuple[
    HeartbeatObservationEmitter,
    DefaultObservationContextBuffer,
    _RecordingTurnTrigger,
]:
    buffer = DefaultObservationContextBuffer()
    appender = ObservationAppender(buffer)
    turn_trigger = _RecordingTurnTrigger()
    turn_scheduler = ObservationTurnScheduler(
        turn_trigger=turn_trigger,
        llm_player_resolver=_AllLlmPlayerResolver(),
    )
    players = llm_players if llm_players is not None else [PlayerId(1)]
    emitter = HeartbeatObservationEmitter(
        observation_appender=appender,
        turn_scheduler=turn_scheduler,
        llm_player_ids_provider=lambda: list(players),
        interval_ticks=interval_ticks,
        now_provider=lambda: datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    return emitter, buffer, turn_trigger


class TestHeartbeatObservationEmitter:
    """``HeartbeatObservationEmitter`` の発行と turn スケジューリングの挙動。"""

    def test_first_tick_only_anchors_no_emission(self) -> None:
        """初回 tick では発行せず基準点を記録するだけ (起動直後の一斉発火回避)。"""
        emitter, buffer, trigger = _build_emitter(interval_ticks=3)

        emitter.run(WorldTick(10))

        assert buffer.get_observations(PlayerId(1)) == []
        assert trigger.scheduled == []

    def test_emits_after_interval_ticks_elapsed(self) -> None:
        """interval_ticks 経過後の tick で 1 件発行されターンも積まれる。"""
        emitter, buffer, trigger = _build_emitter(interval_ticks=3)

        emitter.run(WorldTick(10))  # anchor
        emitter.run(WorldTick(11))  # gap=1 < 3
        emitter.run(WorldTick(12))  # gap=2 < 3
        emitter.run(WorldTick(13))  # gap=3 >= 3 → emit

        observations = buffer.get_observations(PlayerId(1))
        assert len(observations) == 1
        out = observations[0].output
        assert out.structured["type"] == "heartbeat"
        assert out.structured["tick"] == 13
        assert out.schedules_turn is True
        assert out.observation_category == "environment"
        assert trigger.scheduled == [1]

    def test_repeated_emission_respects_interval(self) -> None:
        """連続発行されず、毎回 interval_ticks 開く。"""
        emitter, buffer, trigger = _build_emitter(interval_ticks=2)

        for tick in range(1, 8):
            emitter.run(WorldTick(tick))

        # tick=1: anchor, 3,5,7 で発行 → 3 回
        ticks = [
            o.output.structured["tick"]
            for o in buffer.get_observations(PlayerId(1))
        ]
        assert ticks == [3, 5, 7]
        assert trigger.scheduled == [1, 1, 1]

    def test_multiple_players_tracked_independently(self) -> None:
        """プレイヤーごとに最終発行 tick が独立に管理される。"""
        emitter, buffer, trigger = _build_emitter(
            interval_ticks=2,
            llm_players=[PlayerId(1), PlayerId(2)],
        )

        emitter.run(WorldTick(0))  # both anchor
        emitter.run(WorldTick(2))  # both emit

        assert len(buffer.get_observations(PlayerId(1))) == 1
        assert len(buffer.get_observations(PlayerId(2))) == 1
        assert sorted(trigger.scheduled) == [1, 2]

    def test_provider_exception_does_not_propagate(self) -> None:
        """provider が例外を投げても tick 全体を倒さず安全に return する。"""
        buffer = DefaultObservationContextBuffer()
        appender = ObservationAppender(buffer)
        trigger = _RecordingTurnTrigger()
        scheduler = ObservationTurnScheduler(
            turn_trigger=trigger,
            llm_player_resolver=_AllLlmPlayerResolver(),
        )

        def boom() -> List[PlayerId]:
            raise RuntimeError("provider failed")

        emitter = HeartbeatObservationEmitter(
            observation_appender=appender,
            turn_scheduler=scheduler,
            llm_player_ids_provider=boom,
            interval_ticks=1,
        )

        # 例外を投げず、観測も投入されないこと
        emitter.run(WorldTick(5))
        assert trigger.scheduled == []

    def test_non_player_id_entries_are_skipped(self) -> None:
        """provider が PlayerId 以外を返した要素は警告ログを残して skip。"""
        buffer = DefaultObservationContextBuffer()
        appender = ObservationAppender(buffer)
        trigger = _RecordingTurnTrigger()
        scheduler = ObservationTurnScheduler(
            turn_trigger=trigger,
            llm_player_resolver=_AllLlmPlayerResolver(),
        )

        emitter = HeartbeatObservationEmitter(
            observation_appender=appender,
            turn_scheduler=scheduler,
            llm_player_ids_provider=lambda: [PlayerId(1), "bogus"],  # type: ignore[list-item]
            interval_ticks=1,
        )

        emitter.run(WorldTick(0))  # anchor
        emitter.run(WorldTick(1))  # emit for valid one only

        assert len(buffer.get_observations(PlayerId(1))) == 1
        assert trigger.scheduled == [1]

    def test_invalid_interval_rejected(self) -> None:
        """interval_ticks < 1 は構築時に弾かれる。"""
        buffer = DefaultObservationContextBuffer()
        appender = ObservationAppender(buffer)
        scheduler = ObservationTurnScheduler()
        with pytest.raises(ValueError):
            HeartbeatObservationEmitter(
                observation_appender=appender,
                turn_scheduler=scheduler,
                llm_player_ids_provider=lambda: [],
                interval_ticks=0,
            )

    def test_schedule_failure_does_not_cause_duplicate_observation(self) -> None:
        """maybe_schedule が失敗しても次 tick で同じ観測が再投入されない。

        HIGH 指摘: append 成功後 schedule 失敗のケースで _last_emitted_tick を
        進めないと、次の interval 経過時に append が再発火し buffer に
        duplicate が乗る。これを防ぐ仕様であることをテストで固定する。
        """
        buffer = DefaultObservationContextBuffer()
        appender = ObservationAppender(buffer)

        class _FailingScheduler:
            def maybe_schedule(self, player_id, output):
                raise RuntimeError("schedule blew up")

        emitter = HeartbeatObservationEmitter(
            observation_appender=appender,
            turn_scheduler=_FailingScheduler(),  # type: ignore[arg-type]
            llm_player_ids_provider=lambda: [PlayerId(1)],
            interval_ticks=1,
            now_provider=lambda: datetime(2026, 1, 1, tzinfo=timezone.utc),
        )

        emitter.run(WorldTick(0))  # anchor
        emitter.run(WorldTick(1))  # emit append, schedule fails
        emitter.run(WorldTick(2))  # interval ok だがちょうど 1 tick 経過 → emit
        emitter.run(WorldTick(3))  # 同上

        # 各 tick で 1 件ずつ → 計 3 件 (duplicate ではない)
        observations = buffer.get_observations(PlayerId(1))
        ticks = [o.output.structured["tick"] for o in observations]
        assert ticks == [1, 2, 3]

    def test_emitter_payload_includes_tick_and_interval(self) -> None:
        """発行される観測の structured に tick と interval_ticks が入る。"""
        emitter, buffer, _ = _build_emitter(interval_ticks=4)

        emitter.run(WorldTick(100))  # anchor
        emitter.run(WorldTick(104))  # emit

        out = buffer.get_observations(PlayerId(1))[0].output
        assert isinstance(out, ObservationOutput)
        assert out.structured == {
            "type": "heartbeat",
            "tick": 104,
            "interval_ticks": 4,
        }


class TestHeartbeatSkipsTravelingPlayers:
    """``#404`` fix: 移動中の player には heartbeat を発行しない。

    旧実装は heartbeat が ``schedules_turn=True`` で届いて移動中 player の LLM
    ターンが空回りし、travel 73 tick × 4 player × 約 15s = ~656s の wall time
    スパイクを生んでいた。is_traveling_provider で skip させる。
    """

    def _build_emitter_with_traveling(
        self,
        traveling_pids: set[int],
    ) -> tuple[
        HeartbeatObservationEmitter,
        DefaultObservationContextBuffer,
        _RecordingTurnTrigger,
    ]:
        buffer = DefaultObservationContextBuffer()
        appender = ObservationAppender(buffer)
        turn_trigger = _RecordingTurnTrigger()
        turn_scheduler = ObservationTurnScheduler(
            turn_trigger=turn_trigger,
            llm_player_resolver=_AllLlmPlayerResolver(),
        )
        emitter = HeartbeatObservationEmitter(
            observation_appender=appender,
            turn_scheduler=turn_scheduler,
            llm_player_ids_provider=lambda: [PlayerId(1), PlayerId(2)],
            interval_ticks=2,
            now_provider=lambda: datetime(2026, 1, 1, tzinfo=timezone.utc),
            is_traveling_provider=lambda pid: pid.value in traveling_pids,
        )
        return emitter, buffer, turn_trigger

    def test_移動中の_player_には_heartbeat_を発行しない(self) -> None:
        """is_traveling=True の player は buffer に観測が積まれず schedule も走らない。"""
        emitter, buffer, trigger = self._build_emitter_with_traveling({1})
        emitter.run(WorldTick(10))  # anchor
        emitter.run(WorldTick(12))  # gap=2 → 通常は emit
        assert buffer.get_observations(PlayerId(1)) == []
        # 同じ tick で別 player (移動中でない) には届く
        assert len(buffer.get_observations(PlayerId(2))) == 1
        assert trigger.scheduled == [2]

    def test_provider_が例外を投げても_fail_safe_で従来通り発行する(self) -> None:
        """provider 失敗は heartbeat を止めない。silent failure 防止のため fail-open。"""
        buffer = DefaultObservationContextBuffer()
        appender = ObservationAppender(buffer)
        turn_trigger = _RecordingTurnTrigger()
        turn_scheduler = ObservationTurnScheduler(
            turn_trigger=turn_trigger,
            llm_player_resolver=_AllLlmPlayerResolver(),
        )

        def raising_provider(pid: PlayerId) -> bool:
            raise RuntimeError("provider boom")

        emitter = HeartbeatObservationEmitter(
            observation_appender=appender,
            turn_scheduler=turn_scheduler,
            llm_player_ids_provider=lambda: [PlayerId(1)],
            interval_ticks=2,
            now_provider=lambda: datetime(2026, 1, 1, tzinfo=timezone.utc),
            is_traveling_provider=raising_provider,
        )
        emitter.run(WorldTick(10))  # anchor
        emitter.run(WorldTick(12))  # emit
        assert len(buffer.get_observations(PlayerId(1))) == 1
        assert turn_trigger.scheduled == [1]

    def test_provider_未指定なら従来通り全員発行(self) -> None:
        """is_traveling_provider 省略時 (後方互換) は全員に発行される。"""
        emitter, buffer, trigger = _build_emitter(interval_ticks=2)
        emitter.run(WorldTick(10))
        emitter.run(WorldTick(12))
        assert len(buffer.get_observations(PlayerId(1))) == 1
        assert trigger.scheduled == [1]
