"""``IntentQueue`` 集約の挙動 (フェーズ順 drain・重複拒否・cancel)。"""

import pytest

from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.intent.aggregate.intent_queue import IntentQueue
from ai_rpg_world.domain.intent.exception.intent_exception import (
    DuplicateIntentForPlayerException,
    IntentValidationException,
    UnknownIntentException,
)
from ai_rpg_world.domain.intent.value_object.intent import Intent
from ai_rpg_world.domain.intent.value_object.intent_id import IntentId
from ai_rpg_world.domain.intent.value_object.intent_phase import IntentPhase
from ai_rpg_world.domain.intent.value_object.intent_priority import (
    IntentPriority,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


def _make_intent(
    intent_id: int,
    player_id: int,
    *,
    phase: IntentPhase = IntentPhase.MOVEMENT,
    submitted: int = 1,
    complete: int | None = None,
    priority: int = 0,
    tool_name: str = "noop",
) -> Intent:
    return Intent(
        intent_id=IntentId(intent_id),
        player_id=PlayerId(player_id),
        tool_name=tool_name,
        arguments={},
        phase=phase,
        submitted_at_tick=WorldTick(submitted),
        complete_at_tick=WorldTick(complete if complete is not None else submitted),
        priority=IntentPriority(priority),
    )


class TestIntentQueueDraining:
    """``IntentQueue.drain_ready_for_tick`` の取り出し挙動。"""

    def test_empty_queue_returns_empty_list(self) -> None:
        """空 queue を drain しても例外にならず空 list を返す。"""
        queue = IntentQueue()
        assert queue.drain_ready_for_tick(WorldTick(0)) == []

    def test_phase_order_is_respected(self) -> None:
        """フェーズ昇順 (MOVEMENT → INTERACTION → ATTACK → SOCIAL → OTHER) で並ぶ。"""
        queue = IntentQueue()
        queue.submit(_make_intent(1, 10, phase=IntentPhase.SOCIAL))
        queue.submit(_make_intent(2, 11, phase=IntentPhase.MOVEMENT))
        queue.submit(_make_intent(3, 12, phase=IntentPhase.ATTACK))
        queue.submit(_make_intent(4, 13, phase=IntentPhase.INTERACTION))

        drained = queue.drain_ready_for_tick(WorldTick(1))
        phases = [i.phase for i in drained]
        assert phases == [
            IntentPhase.MOVEMENT,
            IntentPhase.INTERACTION,
            IntentPhase.ATTACK,
            IntentPhase.SOCIAL,
        ]

    def test_within_phase_higher_priority_wins(self) -> None:
        """同フェーズでは priority が高い方が先に出る。"""
        queue = IntentQueue()
        queue.submit(_make_intent(1, 10, priority=0))
        queue.submit(_make_intent(2, 11, priority=5))
        queue.submit(_make_intent(3, 12, priority=3))

        drained = queue.drain_ready_for_tick(WorldTick(1))
        assert [i.intent_id.value for i in drained] == [2, 3, 1]

    def test_id_breaks_tie_for_same_phase_and_priority(self) -> None:
        """phase + priority が同じなら intent_id 昇順 (早く番号が振られた方が先)。"""
        queue = IntentQueue()
        queue.submit(_make_intent(7, 10))
        queue.submit(_make_intent(2, 11))
        queue.submit(_make_intent(5, 12))

        drained = queue.drain_ready_for_tick(WorldTick(1))
        assert [i.intent_id.value for i in drained] == [2, 5, 7]

    def test_future_intents_stay_in_queue(self) -> None:
        """complete_at_tick が未来の intent は drain で取り出されない。"""
        queue = IntentQueue()
        queue.submit(_make_intent(1, 10, submitted=1, complete=1))
        queue.submit(_make_intent(2, 11, submitted=1, complete=3))

        drained = queue.drain_ready_for_tick(WorldTick(1))
        assert [i.intent_id.value for i in drained] == [1]
        assert queue.size() == 1
        assert queue.pending_for(PlayerId(11))[0].intent_id.value == 2

    def test_drained_intents_are_removed(self) -> None:
        """drain で取り出された intent は queue から消える。"""
        queue = IntentQueue()
        queue.submit(_make_intent(1, 10))
        queue.drain_ready_for_tick(WorldTick(1))
        assert queue.size() == 0

    def test_drain_invalid_tick_type_rejected(self) -> None:
        """current_tick が WorldTick でなければ弾く。"""
        queue = IntentQueue()
        with pytest.raises(IntentValidationException):
            queue.drain_ready_for_tick(1)  # type: ignore[arg-type]


class TestIntentQueueSubmit:
    """``IntentQueue.submit`` の重複拒否挙動。"""

    def test_same_player_same_tick_double_submit_rejected(self) -> None:
        """1 プレイヤー / 1 tick / 1 intent の不変条件を集約が保証する。"""
        queue = IntentQueue()
        queue.submit(_make_intent(1, 10, submitted=5))
        with pytest.raises(DuplicateIntentForPlayerException):
            queue.submit(_make_intent(2, 10, submitted=5))

    def test_same_player_different_tick_allowed(self) -> None:
        """同じプレイヤーでも異なる tick の intent は共存できる。"""
        queue = IntentQueue()
        queue.submit(_make_intent(1, 10, submitted=5, complete=5))
        # tick 6 の intent も投入可能
        queue.submit(_make_intent(2, 10, submitted=6, complete=6))
        assert queue.size() == 2

    def test_different_players_same_tick_allowed(self) -> None:
        """異なるプレイヤーは同一 tick に並列に intent を投稿できる。"""
        queue = IntentQueue()
        queue.submit(_make_intent(1, 10, submitted=5))
        queue.submit(_make_intent(2, 11, submitted=5))
        assert queue.size() == 2

    def test_submit_non_intent_rejected(self) -> None:
        """Intent 以外を submit すると IntentValidationException。"""
        queue = IntentQueue()
        with pytest.raises(IntentValidationException):
            queue.submit("not an intent")  # type: ignore[arg-type]


class TestIntentQueueCancel:
    """``IntentQueue.remove`` (intent 取り消し) 挙動。"""

    def test_remove_existing_intent(self) -> None:
        """既存 intent を ID 指定で取り消すと queue から消える。"""
        queue = IntentQueue()
        queue.submit(_make_intent(1, 10))
        queue.submit(_make_intent(2, 11))

        removed = queue.remove(IntentId(1))
        assert removed.intent_id.value == 1
        assert queue.size() == 1
        assert queue.pending()[0].intent_id.value == 2

    def test_remove_unknown_id_raises(self) -> None:
        """存在しない ID で remove すると UnknownIntentException。"""
        queue = IntentQueue()
        with pytest.raises(UnknownIntentException):
            queue.remove(IntentId(99))


class TestIntentQueueExtend:
    """``IntentQueue.extend`` (まとめて submit) 挙動。"""

    def test_extend_inserts_all_intents(self) -> None:
        """extend は複数 intent を順に submit する。"""
        queue = IntentQueue()
        queue.extend([
            _make_intent(1, 10),
            _make_intent(2, 11),
            _make_intent(3, 12),
        ])
        assert queue.size() == 3

    def test_extend_with_duplicate_rolls_back(self) -> None:
        """重複があれば extend 全体が rollback され queue は変更されない (all-or-none)。"""
        queue = IntentQueue()
        queue.submit(_make_intent(99, 99, submitted=1))  # 事前 state
        with pytest.raises(DuplicateIntentForPlayerException):
            queue.extend([
                _make_intent(1, 10, submitted=5),
                _make_intent(2, 10, submitted=5),  # duplicate
            ])
        # 事前 state だけが残っており、extend 内の途中分は rollback されている
        ids = sorted(i.intent_id.value for i in queue.pending())
        assert ids == [99]
