"""create_world_runtime が戦闘不能/復帰ハンドラに配線する current_tick_provider が
壊れていないことを固定する回帰テスト。

背景 (M7 追試で発覚したクラッシュバグ):
world_runtime の PlayerDownedOutcomeHandler / PlayerRevivedPostHocObservationHandler
への配線が ``lambda: int(runtime.current_tick().value)`` になっていた。
``WorldRuntime.current_tick()`` は既に int を返すため ``.value`` で
``AttributeError: 'int' object has no attribute 'value'`` が毎回送出され、
pipeline がこれを握って継続する結果、戦闘不能→猶予→蘇生/死亡を司る
grace timer 登録が黙って失敗し続けていた (silent failure)。
全機能 ON の survival 実走で 1 run あたり数十回発火していた。

このテストは「戦闘不能/復帰イベントを pipeline に流したとき、side handler が
例外を出さない (= current_tick_provider が int を正しく返す)」ことを固定する。
"""

from __future__ import annotations

import logging
from pathlib import Path

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.event.status_events import (
    PlayerDownedEvent,
    PlayerRevivedEvent,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

_SCENARIO_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "scenarios"
    / "survival_island_v2.json"
)


class TestPlayerDownedCurrentTickWiring:
    """side handler の current_tick_provider が int を返し例外を出さないことを保証する。"""

    def test_downed_event_does_not_raise_attribute_error_in_side_handler(
        self, caplog
    ) -> None:
        """PlayerDownedEvent を流しても current_tick().value 由来の AttributeError が出ない。

        修正前はこの発行で PlayerDownedOutcomeHandler が
        'int' object has no attribute 'value' を送出し、pipeline が
        「side handler ... failed」を error ログに残していた。
        """
        runtime = create_world_runtime(_SCENARIO_PATH)
        event = PlayerDownedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            killer_player_id=None,
        )

        with caplog.at_level(logging.ERROR):
            runtime._speech_event_publisher.publish(event)

        assert "has no attribute 'value'" not in caplog.text
        assert "PlayerDownedOutcomeHandler failed" not in caplog.text

    def test_downed_then_revived_sequence_runs_side_handlers_without_error(
        self, caplog
    ) -> None:
        """戦闘不能→復帰を連続で流しても side handler が例外を出さない。

        復帰の post hoc 観測 handler (行 3667) は grace timer に downed_at_tick が
        登録済みの player でのみ current_tick_provider に到達する。そのため
        「先に downed を登録 → revive」の順で流し、Downed 側 (行 3648) と
        Revived 側 (行 3667) の両方の current_tick_provider を実際に踏ませる。
        どちらも修正前は 'int' object has no attribute 'value' で失敗した。
        """
        runtime = create_world_runtime(_SCENARIO_PATH)
        downed = PlayerDownedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            killer_player_id=None,
        )
        revived = PlayerRevivedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            hp_recovered=10,
            total_hp=30,
            caregiver_player_id=None,
        )

        with caplog.at_level(logging.ERROR):
            runtime._speech_event_publisher.publish(downed)
            runtime._speech_event_publisher.publish(revived)

        assert "has no attribute 'value'" not in caplog.text
        assert "failed on event" not in caplog.text
