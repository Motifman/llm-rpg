"""PlayerRevivedPostHocObservationHandler の挙動検証 (Issue #621 Phase 5)。

revive 時に本人の observation_buffer へ「N tick の間意識を失っていた、〇〇に
介抱されて意識が戻った」を post hoc summary として注入する handler。

検証範囲:
- 正常系: caregiver 名・down_ticks が prose に組み込まれる
- caregiver_player_id=None の経路 (= scenario_event 経由 revive 等) では
  「誰かに介抱されて」相当の caregiver 無し prose になる
- grace_timer に downed_at が無い場合 (= 想定外経路) でも落ちず、duration 不明
  扱いで append する fail-safe
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from ai_rpg_world.application.observation.contracts.dtos import ObservationOutput
from ai_rpg_world.application.player.handlers.player_revived_post_hoc_observation_handler import (
    PlayerRevivedPostHocObservationHandler,
)
from ai_rpg_world.application.player.services.player_death_grace_timer import (
    PlayerDeathGraceTimer,
)
from ai_rpg_world.domain.player.event.status_events import PlayerRevivedEvent
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


def _make_event(
    aggregate_id: int = 2,
    *,
    caregiver_player_id: PlayerId | None = None,
    hp_recovered: int = 40,
    total_hp: int = 40,
) -> PlayerRevivedEvent:
    return PlayerRevivedEvent.create(
        aggregate_id=PlayerId(aggregate_id),
        aggregate_type="PlayerStatusAggregate",
        hp_recovered=hp_recovered,
        total_hp=total_hp,
        caregiver_player_id=caregiver_player_id,
    )


class TestSuccessCase:
    """tend_to_player 経由の標準ケース。caregiver と down_ticks が prose に入る。"""

    def test_caregiver_と_down_ticks_を_prose_に_含めて_append_する(self) -> None:
        timer = PlayerDeathGraceTimer()
        timer.register(PlayerId(2), downed_at_tick=10)
        appender = MagicMock()
        handler = PlayerRevivedPostHocObservationHandler(
            grace_timer=timer,
            observation_appender=appender,
            current_tick_provider=lambda: 18,  # 18 - 10 = 8 tick 失神
            caregiver_name_resolver=lambda pid: {1: "ハル"}.get(int(pid)),
        )
        handler.handle(_make_event(aggregate_id=2, caregiver_player_id=PlayerId(1)))

        appender.append.assert_called_once()
        call = appender.append.call_args
        # kwarg / positional のどちらでも player_id=PlayerId(2) を渡している
        player_id = call.kwargs.get("player_id") or call.args[0]
        assert player_id == PlayerId(2)
        output = call.kwargs.get("output") or call.args[1]
        assert isinstance(output, ObservationOutput)
        assert "8" in output.prose  # tick 数
        assert "ハル" in output.prose
        assert "意識" in output.prose
        # 復活後すぐに本人ターンを動かしたい
        assert output.schedules_turn is True

    def test_default_な_caregiver_resolver_未渡しでも_caregiver_id_が_prose_に_出る(self) -> None:
        """resolver が None を返す (= 名前未解決) なら ``Player N`` でフォールバック。"""
        timer = PlayerDeathGraceTimer()
        timer.register(PlayerId(2), downed_at_tick=0)
        appender = MagicMock()
        handler = PlayerRevivedPostHocObservationHandler(
            grace_timer=timer,
            observation_appender=appender,
            current_tick_provider=lambda: 5,
            caregiver_name_resolver=lambda pid: None,
        )
        handler.handle(_make_event(aggregate_id=2, caregiver_player_id=PlayerId(1)))
        output = appender.append.call_args.kwargs.get("output") or appender.append.call_args.args[1]
        assert "Player 1" in output.prose


class TestNoCaregiverCase:
    """caregiver 不明経路 (scenario_event 等)。"""

    def test_caregiver_None_でも_落ちず_caregiver_を_含めない_prose_を_append(self) -> None:
        timer = PlayerDeathGraceTimer()
        timer.register(PlayerId(2), downed_at_tick=3)
        appender = MagicMock()
        handler = PlayerRevivedPostHocObservationHandler(
            grace_timer=timer,
            observation_appender=appender,
            current_tick_provider=lambda: 8,
            caregiver_name_resolver=lambda pid: "誰か",
        )
        handler.handle(_make_event(aggregate_id=2, caregiver_player_id=None))
        output = appender.append.call_args.kwargs.get("output") or appender.append.call_args.args[1]
        # caregiver 不明なので具体名は出さない。失神時間は含む。
        assert "5" in output.prose
        assert "誰か" not in output.prose


class TestMissingDownedAt:
    """grace_timer に downed_at が無い fail-safe ケース。"""

    def test_downed_at_未登録でも_appendは走り_時間表示を_省略する(self) -> None:
        timer = PlayerDeathGraceTimer()
        # register していない
        appender = MagicMock()
        handler = PlayerRevivedPostHocObservationHandler(
            grace_timer=timer,
            observation_appender=appender,
            current_tick_provider=lambda: 50,
            caregiver_name_resolver=lambda pid: "ハル",
        )
        handler.handle(_make_event(aggregate_id=2, caregiver_player_id=PlayerId(1)))
        appender.append.assert_called_once()
        output = appender.append.call_args.kwargs.get("output") or appender.append.call_args.args[1]
        # 時間が分からないので「数 tick」など抽象表現で逃げる
        assert "ハル" in output.prose
        assert "意識" in output.prose


class TestReviveProsePRKappa:
    """PR-κ: prose に HP 情報と travel_to 誘導が含まれる。

    Y_after_pr651_652 trace で「復帰 → 2 tick 後に再ダウン」ループが観測
    された対策として、post_hoc observation に (1) 復帰後 HP、(2) 明示的な
    travel_to 誘導を追記した。復帰した LLM は次 tick でこの prose を読み、
    危険地帯なら travel_to で退避する判断を促される。
    """

    def test_prose_に_HP_情報が含まれる(self) -> None:
        timer = PlayerDeathGraceTimer()
        timer.register(PlayerId(2), downed_at_tick=10)
        appender = MagicMock()
        handler = PlayerRevivedPostHocObservationHandler(
            grace_timer=timer,
            observation_appender=appender,
            current_tick_provider=lambda: 15,
            caregiver_name_resolver=lambda pid: {1: "ハル"}.get(int(pid)),
        )
        handler.handle(
            _make_event(
                aggregate_id=2, caregiver_player_id=PlayerId(1),
                hp_recovered=60, total_hp=60,
            )
        )
        output = appender.append.call_args.kwargs.get("output") or appender.append.call_args.args[1]
        # HP 60 が prose に含まれる
        assert "60" in output.prose

    def test_prose_に_travel_to_誘導が含まれる(self) -> None:
        timer = PlayerDeathGraceTimer()
        timer.register(PlayerId(2), downed_at_tick=10)
        appender = MagicMock()
        handler = PlayerRevivedPostHocObservationHandler(
            grace_timer=timer,
            observation_appender=appender,
            current_tick_provider=lambda: 15,
            caregiver_name_resolver=lambda pid: "ハル",
        )
        handler.handle(_make_event(aggregate_id=2, caregiver_player_id=PlayerId(1)))
        output = appender.append.call_args.kwargs.get("output") or appender.append.call_args.args[1]
        # LLM が travel_to を選ぶ動線を明示的に提供する
        assert "travel_to" in output.prose
        assert "移動" in output.prose


class TestConstructorValidation:
    def test_grace_timer_型_check(self) -> None:
        with pytest.raises(TypeError):
            PlayerRevivedPostHocObservationHandler(
                grace_timer="not a timer",  # type: ignore[arg-type]
                observation_appender=MagicMock(),
                current_tick_provider=lambda: 0,
                caregiver_name_resolver=lambda pid: None,
            )

    def test_current_tick_provider_callable(self) -> None:
        with pytest.raises(TypeError):
            PlayerRevivedPostHocObservationHandler(
                grace_timer=PlayerDeathGraceTimer(),
                observation_appender=MagicMock(),
                current_tick_provider="not callable",  # type: ignore[arg-type]
                caregiver_name_resolver=lambda pid: None,
            )
